"""Sign in with an employee ID (or email) and password.

Supabase Auth only knows emails, so the backend resolves the employee ID to the account's email
and signs in on the user's behalf. The email is never returned, and every failure gives the same
message, so the endpoint doesn't reveal which employee IDs exist.
"""
import httpx
from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.config import get_settings
from app.db import get_db

router = APIRouter(tags=["session"])

INVALID = "Invalid employee ID or password"


class LoginIn(BaseModel):
    login: str = Field(min_length=1, description="Employee ID, or email for admins")
    password: str = Field(min_length=1)


def normalise_employee_id(value: str) -> str:
    """Employee IDs are stored upper-case, so sign-in is case-insensitive with an exact match."""
    return value.strip().upper()


def resolve_email(login: str) -> str | None:
    login = login.strip()
    if "@" in login:
        return login
    rows = (get_db().table("profiles").select("email")
            .eq("employee_id", normalise_employee_id(login)).limit(1).execute().data)
    return rows[0]["email"] if rows else None


@router.post("/auth/login")
def login(body: LoginIn):
    email = resolve_email(body.login)
    if email is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    s = get_settings()
    try:
        res = httpx.post(
            f"{s.supabase_url}/auth/v1/token?grant_type=password",
            headers={"apikey": s.supabase_service_role_key},
            json={"email": email, "password": body.password},
            timeout=30,
        )
    except httpx.HTTPError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Sign-in service unreachable, try again") from exc
    if res.status_code == 429:
        raise HTTPException(status.HTTP_429_TOO_MANY_REQUESTS, "Too many sign-in attempts, wait a minute")
    if res.status_code != 200:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, INVALID)
    data = res.json()
    return {k: data[k] for k in ("access_token", "refresh_token", "expires_in", "token_type")}
