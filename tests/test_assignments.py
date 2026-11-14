import sqlite3
from datetime import date
import pytest
from src.assignments import AssignmentTracker, AssignmentNotFound, parse_estimate_hours

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

def test_add_with_estimate_and_set_estimate(tmp_path):
    t = AssignmentTracker(tmp_path / "t.db")
    a = t.add("Math", "HW", "2026-12-01", estimated_minutes=90)
    assert a.estimated_minutes == 90
    t.set_estimate(a.id, 120)
    assert t.list_assignments()[0].estimated_minutes == 120


def test_estimate_must_be_positive(tmp_path):
    t = AssignmentTracker(tmp_path / "t.db")
    with pytest.raises(ValueError):
        t.add("Math", "HW", "2026-12-01", estimated_minutes=0)


def test_old_database_is_migrated(tmp_path):
    db = tmp_path / "old.db"
    conn = sqlite3.connect(db)
    conn.executescript("""
        CREATE TABLE assignments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            subject TEXT NOT NULL, task TEXT NOT NULL, due_date TEXT NOT NULL,
            priority INTEGER NOT NULL, created_at TEXT NOT NULL, completed_at TEXT
        );
        INSERT INTO assignments (subject, task, due_date, priority, created_at)
        VALUES ('Math', 'HW', '2026-12-01', 2, '2026-11-01T10:00:00');
    """)
    conn.commit()
    conn.close()

    t = AssignmentTracker(db)
    a = t.list_assignments()[0]
    assert a.task == "HW" and a.estimated_minutes is None

    conn = sqlite3.connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == 1
    conn.close()

    t.set_estimate(a.id, 60)  # the new column works
    assert t.list_assignments()[0].estimated_minutes == 60


def test_opening_the_same_database_twice_is_safe(tmp_path):
    AssignmentTracker(tmp_path / "t.db")
    AssignmentTracker(tmp_path / "t.db")


def test_parse_estimate_hours():
    assert parse_estimate_hours("") is None
    assert parse_estimate_hours("2.5") == 150
    for bad in ("abc", "0", "-1", "nan"):
        with pytest.raises(ValueError):
            parse_estimate_hours(bad)