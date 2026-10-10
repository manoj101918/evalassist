"""Thin wrapper over the Groq SDK: strict JSON-schema or plain-text output, rate-limit pacing,
cost tracking."""
import asyncio
import base64
import copy
import json
import re
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any, TypeVar

import groq
from pydantic import BaseModel, ValidationError

from app.config import estimate_cost

T = TypeVar("T", bound=BaseModel)


class AIError(RuntimeError):
    pass


class OutputTruncated(AIError):
    """The reply hit max_completion_tokens before it was complete."""


class InvalidOutput(AIError):
    """The reply didn't match the requested JSON schema."""


class QuotaExhausted(AIError):
    """A Groq daily (or long) usage limit is reached; the whole script should stop, not
    just one answer, and be retried later."""


@dataclass
class CallUsage:
    step: str
    model: str
    input_tokens: int
    output_tokens: int
    cache_read_tokens: int
    cache_write_tokens: int
    cost_usd: float


@dataclass
class UsageTracker:
    calls: list[CallUsage] = field(default_factory=list)

    @property
    def total_cost(self) -> float:
        return sum(c.cost_usd for c in self.calls)


def strict_schema(model: type[BaseModel]) -> dict[str, Any]:
    """Pydantic JSON schema → the subset Groq's strict mode accepts.

    Inlines $defs, drops titles/defaults, closes every object and marks all fields required.
    """
    schema = model.model_json_schema()
    defs = schema.pop("$defs", {})

    def fix(node: Any) -> Any:
        if isinstance(node, list):
            return [fix(n) for n in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            return fix(copy.deepcopy(defs[node["$ref"].split("/")[-1]]))
        out = {k: fix(v) for k, v in node.items() if k not in ("title", "default")}
        if out.get("type") == "object":
            out["additionalProperties"] = False
            out["required"] = list(out.get("properties", {}))
        return out

    return fix(schema)


MAX_RATE_LIMIT_WAITS = 30
# Per-minute limits clear within a minute. A longer wait means a daily quota is used up, and
# waiting silently for hours is worse than stopping with a clear message.
MAX_RATE_LIMIT_WAIT_SECONDS = 90


def rate_limit_wait(exc: groq.RateLimitError) -> float:
    """Seconds to wait before retrying, from the retry-after header or the error message."""
    header = exc.response.headers.get("retry-after") if exc.response is not None else None
    if header:
        try:
            return float(header) + 0.5
        except ValueError:
            pass
    m = re.search(r"try again in (?:(\d+)h)?(?:(\d+)m)?(?:([\d.]+)s)?", exc.message)
    if m and any(m.groups()):
        h, mins, secs = m.groups()
        return int(h or 0) * 3600 + int(mins or 0) * 60 + float(secs or 0) + 0.5
    return 10.0


def is_daily_limit(exc: groq.RateLimitError) -> bool:
    return bool(re.search(r"per day \((TPD|RPD)\)", exc.message))


def _reasoning_kwargs(model: str, effort: str) -> dict[str, Any]:
    """Reasoning controls differ per model family on Groq."""
    if model.startswith("openai/gpt-oss"):
        return {"reasoning_effort": effort, "include_reasoning": False}
    if model.startswith("qwen/"):
        # Reasoning text must be hidden (or parsed) when a JSON response format is used.
        return {"reasoning_effort": effort, "reasoning_format": "hidden"}
    return {}


class Grader:
    """All LLM calls the pipeline makes go through `parse`."""

    def __init__(self, vision_model: str, grading_model: str, check_model: str,
                 api_key: str | None = None, max_parallel: int = 4,
                 on_usage: Callable[[CallUsage], None] | None = None,
                 reader: Any = None):
        self.vision_model = vision_model
        self.grading_model = grading_model
        self.check_model = check_model
        # Optional OCR service for page reading (e.g. AzureReader); the vision model is the fallback.
        self.reader = reader
        # The SDK retries transient 5xx/connection errors (flaky networks need a few); rate limits
        # are paced in _create.
        self.client = groq.AsyncGroq(api_key=api_key, max_retries=4) if api_key else groq.AsyncGroq(max_retries=4)
        self.semaphore = asyncio.Semaphore(max_parallel)
        self.tracker = UsageTracker()
        self.on_usage = on_usage

    async def _create(self, step: str, **kwargs: Any) -> Any:
        """Call Groq, waiting out per-minute rate limits (common on the free tier)."""
        for _ in range(MAX_RATE_LIMIT_WAITS):
            async with self.semaphore:
                try:
                    return await self.client.chat.completions.create(**kwargs)
                except groq.RateLimitError as exc:
                    if "Request too large" in exc.message:
                        # A single request bigger than the per-minute limit never succeeds by waiting.
                        raise AIError(f"{step}: request exceeds your Groq rate limit: {exc.message}") from exc
                    wait = rate_limit_wait(exc)
                    if is_daily_limit(exc) or wait > MAX_RATE_LIMIT_WAIT_SECONDS:
                        m = re.search(r"try again in ([\w.]+)", exc.message)
                        raise QuotaExhausted(
                            f"Groq usage limit reached for {kwargs.get('model')}"
                            f"{f'; it resets in {m.group(1)}' if m else ''}. "
                            "Retry the script later, or upgrade the Groq plan.") from exc
                except groq.BadRequestError as exc:
                    # Groq validates structured output server-side and rejects replies that don't fit.
                    if "max completion tokens reached" in exc.message:
                        raise OutputTruncated(f"{step}: reply was cut off before it was complete") from exc
                    if "json_validate_failed" in str(exc.body):
                        raise InvalidOutput(f"{step}: model reply did not match the schema") from exc
                    raise AIError(f"{step}: Groq API error {exc.status_code}: {exc.message}") from exc
                except groq.APIStatusError as exc:
                    raise AIError(f"{step}: Groq API error {exc.status_code}: {exc.message}") from exc
                except groq.APIConnectionError as exc:
                    raise AIError(f"{step}: could not reach Groq API") from exc
            await asyncio.sleep(wait)
        raise AIError(f"{step}: still rate limited after {MAX_RATE_LIMIT_WAITS} waits")

    async def parse(self, *, step: str, model: str, system: str, content: list[dict[str, Any]] | str,
                    output: type[T], effort: str = "medium", max_tokens: int = 2000) -> T:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": output.__name__, "strict": True, "schema": strict_schema(output)},
        }
        messages = [{"role": "system", "content": system}, {"role": "user", "content": content}]
        last_error: Exception | None = None
        for _ in range(2):  # one retry if the reply is cut off or doesn't validate
            try:
                response = await self._create(
                    step,
                    model=model,
                    messages=messages,
                    response_format=response_format,
                    max_completion_tokens=max_tokens,
                    **_reasoning_kwargs(model, effort),
                )
            except OutputTruncated as exc:
                # Usually hidden reasoning used up the budget; retry with more room.
                last_error, max_tokens = exc, max_tokens * 2
                continue
            except InvalidOutput as exc:
                last_error = exc
                continue
            self._record(step, model, response)
            choice = response.choices[0]
            if choice.finish_reason == "length":
                last_error, max_tokens = OutputTruncated(f"{step}: reply was cut off"), max_tokens * 2
                continue
            try:
                return output.model_validate(json.loads(choice.message.content or ""))
            except (json.JSONDecodeError, ValidationError) as exc:
                last_error = exc
        raise AIError(f"{step}: no valid reply after retrying: {last_error}")

    async def text(self, *, step: str, model: str, system: str, content: list[dict[str, Any]] | str,
                   effort: str = "none", max_tokens: int = 1000) -> str:
        """Plain-text reply. Used for transcription: the vision model produces garbage
        when constrained to a JSON schema, but transcribes accurately as free text."""
        response = await self._create(
            step,
            model=model,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": content}],
            max_completion_tokens=max_tokens,
            **_reasoning_kwargs(model, effort),
        )
        self._record(step, model, response)
        choice = response.choices[0]
        if choice.finish_reason == "length":
            raise AIError(f"{step}: response was cut off (max tokens)")
        return (choice.message.content or "").strip()

    def _record(self, step: str, model: str, response: Any) -> None:
        u = response.usage
        details = getattr(u, "prompt_tokens_details", None)
        cached = (getattr(details, "cached_tokens", None) or 0) if details else 0
        uncached = max((u.prompt_tokens or 0) - cached, 0)
        usage = CallUsage(
            step=step, model=model,
            input_tokens=uncached, output_tokens=u.completion_tokens or 0,
            cache_read_tokens=cached, cache_write_tokens=0,
            cost_usd=estimate_cost(model, uncached, u.completion_tokens or 0, cached),
        )
        self._add(usage)

    def record_external(self, step: str, model: str, cost_usd: float) -> None:
        """Record a call to a non-LLM service (e.g. Azure OCR), priced per call rather than per token."""
        self._add(CallUsage(step=step, model=model, input_tokens=0, output_tokens=0,
                            cache_read_tokens=0, cache_write_tokens=0, cost_usd=cost_usd))

    def _add(self, usage: CallUsage) -> None:
        self.tracker.calls.append(usage)
        if self.on_usage:
            self.on_usage(usage)


def image_block(png: bytes) -> dict[str, Any]:
    data = base64.standard_b64encode(png).decode("ascii")
    return {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{data}"}}


def text_block(text: str) -> dict[str, Any]:
    return {"type": "text", "text": text}
