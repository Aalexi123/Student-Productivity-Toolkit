import sys
import types
from datetime import date

import pytest

from src.assignments import AssignmentTracker
from src.reminders import (
    NotificationUnavailable,
    build_reminder,
    format_reminder,
    notification_text,
    notify,
)

TODAY = date(2026, 11, 15)


@pytest.fixture
def assignments(tmp_path):
    t = AssignmentTracker(tmp_path / "t.db")
    t.add("Physics", "Lab report", "2026-11-10", "high")                       # 5 days overdue
    t.add("Art", "Sketch", "2026-11-14", "low")                                 # 1 day overdue
    t.add("Math", "Problem set", "2026-11-15", "medium")                        # due today
    t.add("History", "Essay", "2026-11-15", "high", estimated_minutes=90)       # due today, High
    t.add("Chem", "Quiz prep", "2026-11-18", "low")                             # in 3 days
    t.add("Bio", "Reading", "2026-11-19", "high")                               # in 4 days: outside
    done = t.add("CS", "Project", "2026-11-12")
    t.complete(done.id)                                                         # completed: ignored
    return t.list_assignments(include_completed=True)


def test_selects_and_orders_assignments(assignments):
    summary = build_reminder(assignments, days=3, today=TODAY)
    assert [a.task for a in summary.overdue] == ["Lab report", "Sketch"]
    assert [a.task for a in summary.upcoming] == ["Essay", "Problem set", "Quiz prep"]


def test_zero_days_means_only_today(assignments):
    summary = build_reminder(assignments, days=0, today=TODAY)
    assert [a.task for a in summary.upcoming] == ["Essay", "Problem set"]


def test_negative_days_are_rejected(assignments):
    with pytest.raises(ValueError):
        build_reminder(assignments, days=-1, today=TODAY)


def test_formatted_text(assignments):
    text = format_reminder(build_reminder(assignments, days=3, today=TODAY), today=TODAY)
    assert "OVERDUE (2)" in text
    assert "was due 2026-11-10 (5 days ago)" in text
    assert "was due 2026-11-14 (1 day ago)" in text
    assert "due TODAY" in text
    assert "est 1h30" in text
    assert "DUE WITHIN 3 DAY(S) (3)" in text
    assert text.isascii()  # safe for scheduled runs and log files


def test_all_clear_when_nothing_is_due(tmp_path):
    summary = build_reminder([], days=3, today=TODAY)
    assert "All clear" in format_reminder(summary, today=TODAY)
    assert notification_text(summary) is None


def test_notification_text(assignments):
    text = notification_text(build_reminder(assignments, days=3, today=TODAY))
    assert text.startswith("2 overdue, 3 due within 3 day(s)")
    assert text.endswith("...")  # more than three tasks


def test_notify_uses_plyer_when_available(monkeypatch):
    calls = []
    fake = types.SimpleNamespace(notification=types.SimpleNamespace(notify=lambda **kw: calls.append(kw)))
    monkeypatch.setitem(sys.modules, "plyer", fake)
    notify("Title", "Body")
    assert calls[0]["title"] == "Title" and calls[0]["message"] == "Body"


def test_notify_without_plyer_raises_a_clear_error(monkeypatch):
    monkeypatch.setitem(sys.modules, "plyer", None)  # makes "import plyer" fail
    with pytest.raises(NotificationUnavailable, match="plyer"):
        notify("Title", "Body")