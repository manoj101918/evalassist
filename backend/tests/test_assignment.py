import pytest
from pydantic import ValidationError

from app.routers.scripts import balanced_assignment
from app.routers.session import normalise_employee_id
from app.routers.users import UserIn


def test_balanced_assignment_spreads_evenly():
    result = balanced_assignment([f"s{i}" for i in range(7)], ["t1", "t2", "t3"], {})
    counts = {t: list(result.values()).count(t) for t in ("t1", "t2", "t3")}
    assert sorted(counts.values()) == [2, 2, 3]


def test_balanced_assignment_accounts_for_existing_load():
    result = balanced_assignment(["a", "b", "c"], ["t1", "t2"], {"t1": 3})
    assert list(result.values()) == ["t2", "t2", "t2"]


def test_employee_id_normalised():
    assert normalise_employee_id("  emp-042 ") == "EMP-042"


def test_teacher_needs_employee_id():
    with pytest.raises(ValidationError):
        UserIn(full_name="T", role="teacher", email="t@x.com", password="password1")
    u = UserIn(full_name="T", role="teacher", employee_id=" emp-7 ", password="password1")
    assert u.employee_id == "EMP-7" and u.email is None


def test_employee_id_rejects_wildcards():
    with pytest.raises(ValidationError):
        UserIn(full_name="T", role="teacher", employee_id="EMP%", password="password1")
