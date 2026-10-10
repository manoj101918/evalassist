import time
from collections.abc import Callable
from functools import lru_cache
from typing import TypeVar

import httpcore
import httpx
from supabase import Client, create_client

from app.config import get_settings

PAGE_SIZE = 1000  # PostgREST's default max rows per request
T = TypeVar("T")


@lru_cache
def get_db() -> Client:
    """Service-role client. Bypasses RLS, so every route must scope queries by college."""
    s = get_settings()
    if not s.supabase_url or not s.supabase_service_role_key:
        raise RuntimeError("Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY in backend/.env")
    return create_client(s.supabase_url, s.supabase_service_role_key)


def with_retry(fn: Callable[[], T], attempts: int = 5, delay: float = 2.0) -> T:
    """Run a database call, retrying transient network failures (DNS, dropped connections)."""
    for i in range(attempts):
        try:
            return fn()
        except (httpx.TransportError, httpcore.NetworkError, OSError):
            if i == attempts - 1:
                raise
            time.sleep(delay * (i + 1))
    raise AssertionError("unreachable")


def fetch_all(build_query: Callable[[], object]) -> list[dict]:
    """Page through a query that may exceed PAGE_SIZE rows. build_query returns a fresh builder."""
    rows: list[dict] = []
    start = 0
    while True:
        batch = build_query().range(start, start + PAGE_SIZE - 1).execute().data
        rows.extend(batch)
        if len(batch) < PAGE_SIZE:
            return rows
        start += PAGE_SIZE


def storage():
    return get_db().storage.from_(get_settings().storage_bucket)


def signed_url(path: str, expires_in: int = 3600) -> str:
    res = storage().create_signed_url(path, expires_in)
    return res.get("signedURL") or res.get("signedUrl") or res["signed_url"]
