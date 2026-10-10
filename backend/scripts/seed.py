"""Create a college and its first admin account.

Usage:
    python scripts/seed.py --college "ABC Engineering College" --email admin@abc.edu \
        --name "Exam Cell Admin" --password "choose-a-strong-password"
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import get_db  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--college", required=True)
    ap.add_argument("--email", required=True)
    ap.add_argument("--name", required=True)
    ap.add_argument("--password", required=True)
    args = ap.parse_args()

    db = get_db()
    # Reuse a college of the same name so a re-run after a failure doesn't create duplicates.
    existing = db.table("colleges").select("*").eq("name", args.college).limit(1).execute().data
    college = existing[0] if existing else (
        db.table("colleges").insert({"name": args.college, "contact_email": args.email}).execute().data[0])
    user = db.auth.admin.create_user({"email": args.email, "password": args.password, "email_confirm": True})
    db.table("profiles").insert({
        "id": user.user.id, "college_id": college["id"], "full_name": args.name,
        "email": args.email, "role": "admin",
    }).execute()
    print(f"Created college '{args.college}' ({college['id']}) and admin {args.email}")


if __name__ == "__main__":
    main()
