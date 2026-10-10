from typing import Any

from app.auth import CurrentUser
from app.db import get_db


def write_audit(user: CurrentUser, action: str, entity_type: str, entity_id: str | None,
                before: Any = None, after: Any = None) -> None:
    get_db().table("audit_log").insert({
        "college_id": user.college_id,
        "actor_id": user.id,
        "action": action,
        "entity_type": entity_type,
        "entity_id": entity_id,
        "before": before,
        "after": after,
    }).execute()
