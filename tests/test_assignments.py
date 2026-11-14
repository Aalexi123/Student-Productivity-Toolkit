from datetime import date
import pytest
from src.assignments import AssignmentTracker, AssignmentNotFound

def test_overdue_status(tmp_path):
    t = AssignmentTracker(tmp_path / "test.db")
    a = t.add("Math", "Problem set", "2026-10-01")

    assert "OVERDUE by 22" in a.status_text(today=date(2026, 10, 23))

def test_invalid_date_raises(tmp_path):
    t = AssignmentTracker(tmp_path/ "test.db")

    with pytest.raises(ValueError):
        t.add("Math", "HW", "23/10/2026")

def test_complete_missing_id(tmp_path):
    t = AssignmentTracker(tmp_path / "test.db")

    with pytest.raises(AssignmentNotFound):
        t.complete(999)

def test_completed_asssignments_can_be_listed(tmp_path):
    t = AssignmentTracker(tmp_path / "t.db")
    a = t.add("Math", "HW", "2026-12-01")
    t.complete(a.id)
    assert t.list_assignments(include_completed=True)[0].completed