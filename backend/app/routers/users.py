import re
from typing import Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, model_validator

from app.audit import write_audit
from app.auth import STAFF, CurrentUser, current_user, require_role
from app.db import get_db
from app.routers.session import normalise_employee_id

router = APIRouter(tags=["users"])

# Supabase Auth requires an email. Staff without one get a placeholder on the reserved
# .invalid domain; no mail is ever sent to it and they sign in with their employee ID.
PLACEHOLDER_EMAIL_DOMAIN = "staff.evalassist.invalid"


@router.get("/me")
def me(user: CurrentUser = Depends(current_user)):
    college = get_db().table("colleges").select("name").eq("id", user.college_id).execute().data
    return {**user.__dict__, "college_name": college[0]["name"] if college else None}


@router.get("/users")
def list_users(role: Literal["admin", "coordinator", "teacher"] | None = None,
               user: CurrentUser = Depends(require_role(*STAFF))):
    q = (get_db().table("profiles").select("id, full_name, email, employee_id, role, created_at")
         .eq("college_id", user.college_id).order("full_name"))
    if role:
        q = q.eq("role", role)
    rows = q.execute().data
    for r in rows:
        if r["email"].endswith("@" + PLACEHOLDER_EMAIL_DOMAIN):
            r["email"] = None
    return rows


class UserIn(BaseModel):
    full_name: str = Field(min_length=1)
    role: Literal["admin", "coordinator", "teacher"]
    employee_id: str | None = Field(default=None, max_length=40)
    email: EmailStr | None = None
    password: str = Field(min_length=8)

    @model_validator(mode="after")
    def needs_login(self):
        if self.employee_id is not None:
            self.employee_id = normalise_employee_id(self.employee_id) or None
        if self.employee_id and not re.fullmatch(r"[A-Z0-9._\-/]+", self.employee_id):
            raise ValueError("Employee ID may only contain letters, digits and . _ - /")
        if self.role == "teacher" and not self.employee_id:
            raise ValueError("Teachers need an employee ID to sign in")
        if not self.employee_id and not self.email:
            raise ValueError("Give an employee ID or an email")
        return self


@router.post("/users", status_code=201)
def create_user(body: UserIn, user: CurrentUser = Depends(require_role("admin"))):
    db = get_db()
    if body.employee_id and db.table("profiles").select("id").eq("employee_id", body.employee_id).execute().data:
        raise HTTPException(409, f"Employee ID {body.employee_id} is already in use")
    email = body.email or f"{uuid4().hex[:12]}@{PLACEHOLDER_EMAIL_DOMAIN}"
    try:
        created = db.auth.admin.create_user({"email": email, "password": body.password, "email_confirm": True})
    except Exception as exc:  # noqa: BLE001 - surface Supabase Auth's message
        raise HTTPException(400, f"Could not create user: {exc}") from exc
    profile = db.table("profiles").insert({
        "id": created.user.id, "college_id": user.college_id, "full_name": body.full_name,
        "email": email, "employee_id": body.employee_id, "role": body.role,
    }).execute().data[0]
    write_audit(user, "user.create", "profile", profile["id"],
                after={"employee_id": body.employee_id, "email": body.email, "role": body.role})
    return profile
