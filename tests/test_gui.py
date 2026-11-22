"""GUI smoke tests. Skipped automatically where there is no display (e.g. CI)."""
from datetime import date, timedelta

import pytest

pytest.importorskip("customtkinter")
import tkinter  # noqa: E402

from assignments import AssignmentTracker  # noqa: E402


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


@pytest.fixture
def app(tmp_path):
    import gui

    tracker = AssignmentTracker(tmp_path / "t.db")
    try:
        window = gui.ToolkitApp(tracker)
    except tkinter.TclError:
        pytest.skip("no display available")
    window.withdraw()
    yield window
    window.destroy()


def test_every_page_opens(app):
    for key in app.pages:
        app.show(key)


def test_add_assignment_from_the_form(app):
    page = app.pages["assignments"]
    page.subject.insert(0, "History")
    page.task.insert(0, "Essay")
    page.due.insert(0, iso(5))
    page.estimate.insert(0, "2")
    page.add_assignment()
    saved = app.tracker.list_assignments()[0]
    assert saved.task == "Essay" and saved.estimated_minutes == 120


def test_bad_due_date_shows_an_error_and_saves_nothing(app):
    page = app.pages["assignments"]
    page.subject.insert(0, "History")
    page.task.insert(0, "Essay")
    page.due.insert(0, "tomorrow")
    page.add_assignment()
    assert "YYYY-MM-DD" in page.status.cget("text")
    assert app.tracker.list_assignments() == []


def test_done_button_completes_an_assignment(app):
    a = app.tracker.add("Math", "HW", iso(3))
    app.pages["assignments"].complete(a.id)
    assert app.tracker.list_assignments() == []


def test_planner_page_writes_a_plan(app, tmp_path):
    app.tracker.add("History", "Essay", iso(5), "high", estimated_minutes=60)
    page = app.pages["planner"]
    page.output_path.delete(0, "end")
    page.output_path.insert(0, str(tmp_path / "plan.csv"))
    page.generate()
    assert (tmp_path / "plan.csv").exists()
    assert "1 sessions" in page.status.cget("text")


def test_planner_page_rejects_non_numeric_days(app, tmp_path):
    page = app.pages["planner"]
    page.days.delete(0, "end")
    page.days.insert(0, "abc")
    page.generate()
    assert "whole numbers" in page.status.cget("text")


def test_log_page_appends_to_the_study_log(app, tmp_path, monkeypatch):
    import gui

    log = tmp_path / "log.csv"
    monkeypatch.setattr(gui, "DEFAULT_LOG", log)
    monkeypatch.setattr(gui, "DEFAULT_PLAN", tmp_path / "none.csv")
    page = app.pages["log"]
    page.subject.set("Physics")
    page.minutes.insert(0, "45")
    page.log()
    assert "Physics" in log.read_text(encoding="utf-8")


def test_organiser_preview_lists_one_checkbox_per_file(app, tmp_path):
    messy = tmp_path / "messy"  # separate from the tracker database in tmp_path
    messy.mkdir()
    for name in ("a.pdf", "b.png"):
        (messy / name).write_text("x")
    page = app.pages["organiser"]
    page.folder_entry.insert(0, str(messy))
    page.preview()
    assert len(page.checks) == 2
