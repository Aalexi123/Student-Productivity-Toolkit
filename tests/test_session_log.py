import csv

import pytest

from src.reports import load_study_log
from src.session_log import log_session


def read_rows(path):
    with path.open(newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_creates_file_with_header(tmp_path):
    log = tmp_path / "log.csv"
    log_session(log, "Physics", 45, "2026-11-10")
    assert read_rows(log) == [
        {"date": "2026-11-10", "subject": "Physics",
         "duration_minutes": "45", "planned_minutes": "0"}
    ]


def test_planned_minutes_come_from_plan_and_count_once_per_day(tmp_path):
    plan = tmp_path / "plan.csv"
    plan.write_text(
        "date,subject,task,planned_minutes\n"
        "2026-11-10,Physics,Lab report,60\n"
        "2026-11-10,Physics,Lab report,60\n"
    )
    log = tmp_path / "log.csv"
    first = log_session(log, "physics", 50, "2026-11-10", plan_path=plan)
    second = log_session(log, "Physics", 30, "2026-11-10", plan_path=plan)
    assert first["planned_minutes"] == 120
    assert second["planned_minutes"] == 0  # not double counted
    assert {r["subject"] for r in read_rows(log)} == {"Physics"}  # spelling reused


@pytest.mark.parametrize("subject, minutes, day", [
    ("", 30, None),
    ("Math", 0, None),
    ("Math", "abc", None),
    ("Math", 30, "10/11/2026"),
    ("Math", 5000, None),
])
def test_invalid_input_is_rejected_and_nothing_is_written(tmp_path, subject, minutes, day):
    log = tmp_path / "log.csv"
    with pytest.raises(ValueError):
        log_session(log, subject, minutes, day)
    assert not log.exists()


def test_appends_after_a_file_without_trailing_newline(tmp_path):
    log = tmp_path / "log.csv"
    log.write_text("date,subject,duration_minutes,planned_minutes\n2026-11-09,Math,30,30",
                   encoding="utf-8")
    log_session(log, "Math", 20, "2026-11-10")
    rows = read_rows(log)
    assert len(rows) == 2 and rows[1]["date"] == "2026-11-10"


def test_report_can_read_logged_sessions(tmp_path):
    log = tmp_path / "log.csv"
    log_session(log, "Math", 45, "2026-11-10")
    log_session(log, "Math", 30, "2026-11-11")
    assert len(load_study_log(log)) == 2