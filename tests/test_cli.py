import csv
from datetime import date, timedelta

import pytest

import main as main_module
import paths
from assignments import AssignmentTracker
from cli import build_parser
from main import main


def iso(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def read_csv(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


# ---------- entry point ----------
def test_no_arguments_opens_the_menu(monkeypatch):
    opened = []
    monkeypatch.setattr(main_module, "run_menu", lambda: opened.append(True) or 0)
    assert main([]) == 0
    assert opened


def test_help_lists_the_commands(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0
    out = capsys.readouterr().out
    for command in ("plan", "report", "organise", "process", "log"):
        assert command in out


def test_unknown_command_is_a_usage_error():
    with pytest.raises(SystemExit) as exc:
        main(["bogus"])
    assert exc.value.code == 2


def test_default_paths_do_not_depend_on_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    args = build_parser().parse_args(["report"])
    assert args.log == paths.DEFAULT_LOG
    assert args.log.is_absolute()
    assert paths.DEFAULT_LOG.parent == paths.PROJECT_ROOT / "data"


# ---------- plan ----------
def test_plan_from_csv_files(tmp_path):
    assignments, estimates, out = tmp_path / "a.csv", tmp_path / "e.csv", tmp_path / "plan.csv"
    assignments.write_text(f"task,subject,due_date,priority\nEssay,History,{iso(5)},High\n")
    estimates.write_text("task,estimated_hours\nEssay,2\n")
    code = main(["plan", "--source", "csv", "--assignments", str(assignments),
                 "--estimates", str(estimates), "--output", str(out)])
    assert code == 0
    assert sum(int(r["planned_minutes"]) for r in read_csv(out)) == 120


def test_plan_from_tracker_database(tmp_path, capsys):
    db, out = tmp_path / "t.db", tmp_path / "plan.csv"
    tracker = AssignmentTracker(db)
    tracker.add("History", "Essay", iso(5), "high", estimated_minutes=60)
    tracker.add("Math", "HW", iso(6))  # no estimate: a warning, not a failure
    code = main(["plan", "--db", str(db), "--output", str(out), "--no-weekends"])
    assert code == 0
    assert sum(int(r["planned_minutes"]) for r in read_csv(out)) == 60
    assert "MISSING_ESTIMATE" in capsys.readouterr().out


def test_plan_without_a_database_fails_cleanly(tmp_path, capsys):
    code = main(["plan", "--db", str(tmp_path / "missing.db"), "--output", str(tmp_path / "p.csv")])
    assert code == 1
    assert "not found" in capsys.readouterr().err


def test_plan_rejects_a_zero_capacity():
    with pytest.raises(SystemExit) as exc:
        main(["plan", "--capacity", "0"])
    assert exc.value.code == 2


# ---------- log and report ----------
def test_log_then_report(tmp_path):
    log, none_plan, out_dir = tmp_path / "log.csv", tmp_path / "none.csv", tmp_path / "out"
    assert main(["log", "Math", "45", "--date", iso(-1), "--log", str(log), "--plan", str(none_plan)]) == 0
    assert main(["log", "Math", "30", "--log", str(log), "--plan", str(none_plan)]) == 0
    assert main(["report", "--log", str(log), "--output-dir", str(out_dir)]) == 0
    assert list(out_dir.glob("*.png"))


def test_log_rejects_bad_minutes(tmp_path, capsys):
    code = main(["log", "Math", "abc", "--log", str(tmp_path / "log.csv")])
    assert code == 1
    assert "whole number" in capsys.readouterr().err


def test_report_with_a_missing_log_fails_cleanly(tmp_path, capsys):
    code = main(["report", "--log", str(tmp_path / "nope.csv"), "--output-dir", str(tmp_path / "o")])
    assert code == 1
    assert "not found" in capsys.readouterr().err.lower()


def test_debug_flag_shows_the_real_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        main(["--debug", "report", "--log", str(tmp_path / "nope.csv")])


# ---------- organise ----------
def test_organise_previews_applies_and_undoes(tmp_path):
    folder = tmp_path / "downloads"
    folder.mkdir()
    (folder / "notes.txt").write_text("x")

    assert main(["organise", str(folder)]) == 0
    assert (folder / "notes.txt").exists()  # a preview moves nothing

    assert main(["organise", str(folder), "--apply"]) == 0
    assert (folder / "Documents" / "notes.txt").exists()

    assert main(["organise", str(folder), "--undo"]) == 0
    assert (folder / "notes.txt").exists()


def test_organise_apply_and_undo_cannot_be_combined(tmp_path):
    with pytest.raises(SystemExit) as exc:
        main(["organise", str(tmp_path), "--apply", "--undo"])
    assert exc.value.code == 2


def test_organise_a_missing_folder_fails_cleanly(tmp_path, capsys):
    assert main(["organise", str(tmp_path / "nope")]) == 1
    assert "Not a valid folder" in capsys.readouterr().err


# ---------- process ----------
def test_process_a_document(tmp_path):
    doc, out_dir = tmp_path / "notes.txt", tmp_path / "reports"
    doc.write_text("hello world study notes")
    assert main(["process", str(doc), "--output-dir", str(out_dir)]) == 0
    assert list(out_dir.glob("*_report.txt"))


def test_process_an_unsupported_file_fails_cleanly(tmp_path, capsys):
    bad = tmp_path / "a.xyz"
    bad.write_text("hi")
    assert main(["process", str(bad), "--output-dir", str(tmp_path / "o")]) == 1
    assert "Unsupported" in capsys.readouterr().err


def test_process_a_folder_reports_failures_in_the_exit_code(tmp_path, capsys):
    folder = tmp_path / "docs"
    folder.mkdir()
    (folder / "good.txt").write_text("some study notes")
    (folder / "bad.pdf").write_text("this is not really a pdf")
    code = main(["process", str(folder), "--output-dir", str(tmp_path / "o")])
    assert code == 1
    assert "bad.pdf" in capsys.readouterr().err
    assert list((tmp_path / "o").glob("good_txt_report.txt"))

# ---------- remind ----------
def make_reminder_db(tmp_path):
    db = tmp_path / "t.db"
    tracker = AssignmentTracker(db)
    tracker.add("Physics", "Lab report", iso(-2), "high")
    tracker.add("Math", "HW", iso(1))
    tracker.add("Art", "Sketch", iso(30))
    return db


def test_remind_lists_overdue_and_upcoming(tmp_path, capsys):
    db = make_reminder_db(tmp_path)
    assert main(["remind", "--db", str(db), "--days", "3"]) == 0
    out = capsys.readouterr().out
    assert "OVERDUE (1)" in out and "Lab report" in out and "HW" in out
    assert "Sketch" not in out


def test_remind_with_a_missing_database_fails_cleanly(tmp_path, capsys):
    assert main(["remind", "--db", str(tmp_path / "missing.db")]) == 1
    assert "not found" in capsys.readouterr().err


def test_remind_notify_sends_a_notification(tmp_path, monkeypatch):
    import sys
    import types

    calls = []
    fake = types.SimpleNamespace(notification=types.SimpleNamespace(notify=lambda **kw: calls.append(kw)))
    monkeypatch.setitem(sys.modules, "plyer", fake)
    assert main(["remind", "--db", str(make_reminder_db(tmp_path)), "--notify"]) == 0
    assert calls and "overdue" in calls[0]["message"]


def test_remind_notify_without_plyer_fails_cleanly(tmp_path, monkeypatch, capsys):
    import sys

    monkeypatch.setitem(sys.modules, "plyer", None)
    assert main(["remind", "--db", str(make_reminder_db(tmp_path)), "--notify"]) == 1
    assert "plyer" in capsys.readouterr().err