from app.ai.client import strict_schema
from app.ai.schemas import Grading, Segmentation


def _walk(node):
    if isinstance(node, dict):
        yield node
        for v in node.values():
            yield from _walk(v)
    elif isinstance(node, list):
        for v in node:
            yield from _walk(v)


def test_strict_schema_is_closed_and_inlined():
    # The models the LLM must reply in (page transcripts are plain text, built in code).
    for model in (Segmentation, Grading):
        schema = strict_schema(model)
        for node in _walk(schema):
            assert "$ref" not in node and "$defs" not in node and "title" not in node
            if node.get("type") == "object":
                assert node["additionalProperties"] is False
                assert sorted(node["required"]) == sorted(node["properties"])


def test_strict_schema_keeps_enums():
    schema = strict_schema(Grading)
    verdict = schema["properties"]["points"]["items"]["properties"]["verdict"]
    assert verdict["enum"] == ["full", "partial", "absent"]


def _rate_limit(message: str, retry_after: str | None = None):
    import groq
    import httpx
    headers = {"retry-after": retry_after} if retry_after else {}
    response = httpx.Response(429, headers=headers, request=httpx.Request("POST", "https://api.groq.com"))
    return groq.RateLimitError(message, response=response, body=None)


def test_rate_limit_wait_parses_groq_messages():
    from app.ai.client import rate_limit_wait
    assert rate_limit_wait(_rate_limit("Please try again in 35.58s.")) == 36.08
    assert rate_limit_wait(_rate_limit("Please try again in 2m3.5s.")) == 124.0
    assert rate_limit_wait(_rate_limit("Please try again in 1h2m0s.")) == 3720.5
    assert rate_limit_wait(_rate_limit("slow down", retry_after="7")) == 7.5


def test_daily_limit_detected():
    from app.ai.client import is_daily_limit
    assert is_daily_limit(_rate_limit("Rate limit reached ... on tokens per day (TPD): Limit 200000"))
    assert not is_daily_limit(_rate_limit("Rate limit reached ... on tokens per minute (TPM): Limit 8000"))
