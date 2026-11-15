from datetime import date, timedelta

import pytest

import main as main_module
from assignments import AssignmentTracker


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


@pytest.fixture
def tracker(tmp_path):
    return AssignmentTracker(tmp_path / "t.db")


def feed(monkeypatch, *answers):
    """Answer each input() prompt in order. Asking for more prompts than expected fails the test."""
    remaining = iter(answers)
    monkeypatch.setattr("builtins.input", lambda prompt="": next(remaining))


def test_tracker_menu_adds_an_assignment_with_an_estimate(tracker, monkeypatch):
    feed(monkeypatch, "3", "History", "Essay", iso(5), "high", "2", "6")
    main_module.handle_assignment_tracker(tracker)
    saved = tracker.list_assignments()[0]
    assert saved.task == "Essay" and saved.estimated_minutes == 120


def test_tracker_menu_sets_an_estimate(tracker, monkeypatch):
    tracker.add("Math", "HW", iso(3))
    feed(monkeypatch, "5", "1", "1.5", "6")
    main_module.handle_assignment_tracker(tracker)
    assert tracker.list_assignments()[0].estimated_minutes == 90


def test_planner_menu_plans_from_the_tracker(tracker, tmp_path, monkeypatch, capsys):
    tracker.add("History", "Essay", iso(5), "high", estimated_minutes=60)
    out = tmp_path / "plan.csv"
    feed(monkeypatch, "", str(out))  # source: default (tracker), then output path
    main_module.handle_study_planner(tracker)
    assert out.exists()
    assert "Scheduled total" in capsys.readouterr().out


def test_main_menu_option_4_runs_the_planner(tracker, tmp_path, monkeypatch):
    tracker.add("History", "Essay", iso(5), "high", estimated_minutes=60)
    out = tmp_path / "plan.csv"
    monkeypatch.setattr(main_module, "AssignmentTracker", lambda: tracker)
    feed(monkeypatch, "4", "", str(out), "7")
    assert main_module.run_menu() == 0
    assert out.exists()


def test_main_menu_option_6_logs_a_session(tracker, tmp_path, monkeypatch):
    log = tmp_path / "log.csv"
    monkeypatch.setattr(main_module, "AssignmentTracker", lambda: tracker)
    monkeypatch.setattr(main_module, "DEFAULT_LOG", log)
    monkeypatch.setattr(main_module, "DEFAULT_PLAN", tmp_path / "none.csv")
    feed(monkeypatch, "6", "Physics", "45", "2026-11-10", "7")
    assert main_module.run_menu() == 0
    assert "Physics" in log.read_text(encoding="utf-8")


def test_main_menu_exit(tracker, monkeypatch):
    monkeypatch.setattr(main_module, "AssignmentTracker", lambda: tracker)
    feed(monkeypatch, "7")
    assert main_module.run_menu() == 0