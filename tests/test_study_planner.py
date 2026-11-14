from datetime import date, timedelta
import pytest
from src.study_planner import (
    PlannerConfig,
    Task,
    read_csv_rows,
    schedule_tasks,
    build_days,
    build_tasks,
    generate_study_plan,
)

START = date(2026, 10, 26)

def make_task(name="Essay", hours=1, due_in=3, priority="medium"):
    return Task(name, "History", START + timedelta(days=due_in), priority, hours * 60)

def test_never_schedules_past_deadline():
    cfg = PlannerConfig()
    sessions, _ = schedule_tasks([make_task(hours=4, due_in=1)], build_days(START, cfg), cfg)
    assert all(s.date <= START + timedelta(days=1) for s in sessions)

def test_overflow_is_reported():
    cfg = PlannerConfig(daily_capacity_min=180, max_task_min_per_day=180, planning_days=3)
    sessions, issues = schedule_tasks([make_task(hours=10, due_in=1)], build_days(START, cfg), cfg)
    assert sum(s.minutes for s in sessions) == 360
    assert any(issue.kind == "overflow" for issue in issues)

def test_high_priority_goes_first_when_deadlines_tie():
    cfg = PlannerConfig(daily_capacity_min=60, max_task_min_per_day=60)
    tasks = [make_task("Low", hours=1, priority="low"), make_task("High", hours=1, priority="high")]
    sessions, _ = schedule_tasks(tasks, build_days(START, cfg), cfg)
    assert sessions[0].task == "High"

def test_reads_excel_bom_csv(tmp_path):
    p = tmp_path / "a.csv"
    p.write_text("task,due_date\nEssay,2026-11-01\n", encoding="utf-8-sig")
    assert read_csv_rows(p, {"task", "due_date"})[0]["task"] == "Essay"

def test_build_tasks_reads_due_date():
    rows = [{"task": "Essay", "subject": "History", "due_date": "2026-11-10"}]
    tasks, issues = build_tasks(rows, {"essay": 120}, date(2026, 11, 1))
    assert len(tasks) == 1 and not issues

def test_generate_study_plan_end_to_end(tmp_path):
    (tmp_path / "a.csv").write_text("task,subject,due_date,priority\nEssay,History,2026-11-10,High\n")
    (tmp_path / "e.csv").write_text("task,estimated_hours\nEssay,2\n")
    plan = generate_study_plan(tmp_path / "a.csv", tmp_path / "e.csv", tmp_path / "out.csv",
                               start_date=date(2026, 11, 1))
    assert sum(s.minutes for s in plan.sessions) == 120

def test_planner_config_rejects_bad_values():
    with pytest.raises(ValueError):
        PlannerConfig(daily_capacity_min=0)