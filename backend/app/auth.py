from collections.abc import Iterable
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import get_settings
from app.db import get_db

bearer = HTTPBearer(auto_error=False)

STAFF = ("admin", "coordinator")
ANY_ROLE = ("admin", "coordinator", "teacher")


@dataclass(frozen=True)
class CurrentUser:
    id: str
    college_id: str
    role: str
    full_name: str
    email: str
    employee_id: str | None = None

    @property
    def is_staff(self) -> bool:
        return self.role in STAFF


@lru_cache
def _jwks_client() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(f"{get_settings().supabase_url}/auth/v1/.well-known/jwks.json")


def _verify(token: str) -> str:
    """Return the user id (sub) from a Supabase access token."""
    try:
        header = jwt.get_unverified_header(token)
        if header.get("alg", "").startswith("HS"):
            # Legacy symmetric-key projects: fall back to asking Supabase Auth.
            user = get_db().auth.get_user(token)
            return user.user.id
        key = _jwks_client().get_signing_key_from_jwt(token)
        claims = jwt.decode(token, key.key, algorithms=[header["alg"]], audience="authenticated")
        return claims["sub"]
    except Exception as exc:  # noqa: BLE001 - any failure is an auth failure
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired session") from exc


def current_user(creds: HTTPAuthorizationCredentials | None = Depends(bearer)) -> CurrentUser:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not signed in")
    user_id = _verify(creds.credentials)
    rows = get_db().table("profiles").select("*").eq("id", user_id).limit(1).execute().data
    if not rows:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No profile for this account")
    p = rows[0]
    return CurrentUser(p["id"], p["college_id"], p["role"], p["full_name"], p["email"], p.get("employee_id"))


def require_role(*roles: str):
    allowed: Iterable[str] = roles

    def dep(user: CurrentUser = Depends(current_user)) -> CurrentUser:
        if user.role not in allowed:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "You don't have permission for this")
        return user

    return dep


def require_script_access(user: CurrentUser, script: dict) -> None:
    """Teachers may only work on scripts assigned to them; staff may work on any in their college."""
    if not user.is_staff and script.get("assigned_to") != user.id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "This script is not assigned to you")
