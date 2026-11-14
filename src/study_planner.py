from __future__ import annotations

import csv
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path

PRIORITY_LEAD_DAYS = {"high": 2, "medium": 1, "low": 0}

@dataclass(frozen=True)
class PlannerConfig:
    daily_capacity_min: int = 180
    session_min: int = 60
    min_session_min: int = 30
    max_task_min_per_day: int = 120
    planning_days: int = 7
    include_weekends: bool = True
    blocked_dates: frozenset[date] = frozenset()
    buffer_days: int = 0

    def __post_init__(self):
        durations = (self.daily_capacity_min, self.session_min,
                     self.min_session_min, self.max_task_min_per_day)
        if min(durations) <= 0:
            raise ValueError("Study durations must be positive.")
        if self.planning_days < 1:
            raise ValueError("Planning period must be at least one day.")
        if self.buffer_days < 0:
            raise ValueError("buffer_days cannot be negative.")

@dataclass
class Task:
    name: str
    subject: str
    deadline: date
    priority: str
    minutes: int

    @property
    def sort_key(self) -> tuple:
        lead = PRIORITY_LEAD_DAYS.get(self.priority, 0)
        return (self.deadline - timedelta(days=lead), self.deadline, self.name)

@dataclass(frozen=True)
class Session:
    date: date
    subject: str
    task: str
    minutes: int

@dataclass(frozen=True)
class PlanIssue:
    kind: str
    task: str
    message: str

@dataclass
class StudyPlan:
    sessions: list[Session] = field(default_factory=list)
    issues: list[PlanIssue] = field(default_factory=list)

def fmt_minutes(m: int) -> str:
    return f"{m // 60}h {m % 60:02d}m"

def read_csv_rows(path: str | Path, required: set[str]) -> list[dict]:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    with path.open(newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        reader.fieldnames = [h.strip().lower() for h in reader.fieldnames or []]
        missing = required - set(reader.fieldnames)
        if missing:
            raise ValueError(f"{path.name} is missing columns: {', '.join(sorted(missing))}")
        return list(reader)

def load_estimates(path: str | Path) -> tuple[dict[str, int], list[PlanIssue]]:
    """Map normalised task name -> estimated minutes."""
    estimates, issues = {}, []
    for row in read_csv_rows(path, {"task", "estimated_hours"}):
        name = (row.get("task") or "").strip()
        try:
            minutes = round(float(row.get("estimated_hours") or "") * 60)
        except (ValueError, OverflowError):
            minutes = 0
        if not name or minutes <= 0:
            issues.append(PlanIssue("bad_estimate", name,
                                    f"Ignored invalid estimate row for '{name or '?'}'."))
            continue
        key = name.casefold()
        if key in estimates:
            issues.append(PlanIssue("bad_estimate", name,
                                    f"Duplicate estimate for '{name}'; using the last one."))
        estimates[key] = minutes
    return estimates, issues

def build_tasks(rows: list[dict], estimates: dict[str, int],
                start: date) -> tuple[list[Task], list[PlanIssue]]:
    tasks, issues = [], []
    for row in rows:
        if (row.get("status") or "").strip().lower() == "completed":
            continue
        name = (row.get("task") or "").strip()
        if not name:
            issues.append(PlanIssue("bad_task", name, "Skipped a row with no task name."))
            continue
        subject = (row.get("subject") or "").strip() or "General"
        priority = (row.get("priority") or "").strip().lower() or "medium"
        try:
            deadline = date.fromisoformat((row.get("due_date") or "").strip())
        except ValueError:
            issues.append(PlanIssue("bad_task", name, f"Invalid due date for '{name}'. Skipped."))
            continue
        if deadline < start:
            issues.append(PlanIssue("overdue", name,
                                    f"'{name}' ({subject}) was due {deadline.isoformat()}."))
            continue
        minutes = estimates.get(name.casefold())
        if minutes is None:
            issues.append(PlanIssue("missing_estimate", name,
                                    f"'{name}' ({subject}) has no estimate. Skipped."))
            continue
        tasks.append(Task(name, subject, deadline, priority, minutes))
    return tasks, issues

def build_days(start: date, cfg: PlannerConfig) -> list[date]:
    days = []
    for offset in range(cfg.planning_days):
       d = start + timedelta(days=offset)
       if (not cfg.include_weekends and d.weekday() >= 5) or d in cfg.blocked_dates:
           continue
       days.append(d)
    return days

def schedule_tasks(tasks: list[Task], days: list[date],
                   cfg: PlannerConfig) -> tuple[list[Session], list[PlanIssue]]:
    used = defaultdict(int)
    per_task = defaultdict(int)
    sessions, issues = [], []

    for i, task in enumerate(sorted(tasks, key=lambda t: t.sort_key)):
        last_day = task.deadline - timedelta(days=cfg.buffer_days)
        remaining = task.minutes

        for d in days:
            if d > last_day or remaining == 0:
                break
            while remaining > 0:
                room = min(cfg.daily_capacity_min - used[d],
                           cfg.max_task_min_per_day - per_task[i, d])
                chunk = min(cfg.session_min, room, remaining)
                if chunk <= 0 or (chunk < cfg.min_session_min and chunk < remaining):
                    break
                sessions.append(Session(d, task.subject, task.name, chunk))
                used[d] += chunk
                per_task[i, d] += chunk
                remaining -= chunk

        if remaining > 0:
            beyond = bool(days) and last_day > days[-1]
            if beyond:
                issues.append(PlanIssue(
                    "beyond_window", task.name,
                    f"'{task.name}' ({task.subject}): {fmt_minutes(remaining)} not planned yet; "
                    f"its deadline ({task.deadline.isoformat()}) is past the planning window."))
            else:
                issues.append(PlanIssue(
                    "overflow", task.name,
                    f"'{task.name}' ({task.subject}): can't fit {fmt_minutes(remaining)} before "
                    f"{task.deadline.isoformat()}. Raise capacity or move the deadline."))
    return sorted(sessions, key=lambda s: s.date), issues

def write_schedule(sessions: list[Session], output_path: str | Path) -> None:
    out = Path(output_path).expanduser()
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["date", "subject", "task", "planned_minutes"])
        for s in sessions:
            writer.writerow([s.date.isoformat(), s.subject, s.task, s.minutes])

def generate_study_plan(assignments_path: str | Path,
                        requirements_path: str | Path,
                        output_path: str | Path | None = None,
                        config: PlannerConfig | None = None,
                        start_date: date | None = None) -> StudyPlan:
    cfg = config or PlannerConfig()
    start = start_date or date.today()

    estimates, issues = load_estimates(requirements_path)
    rows = read_csv_rows(assignments_path, {"task", "due_date"})
    tasks, task_issues = build_tasks(rows, estimates, start)
    sessions, schedule_issues = schedule_tasks(tasks, build_days(start, cfg), cfg)

    plan = StudyPlan(sessions, issues + task_issues + schedule_issues)
    if output_path:
        write_schedule(plan.sessions, output_path)
    return plan