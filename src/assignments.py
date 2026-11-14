from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path

DEFAULT_DB = Path.home() / ".student_toolkit" / "assignments.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS assignments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    subject TEXT NOT NULL CHECK (length(trim(subject)) > 0),
    task TEXT NOT NULL CHECK (length(trim(task)) > 0),
    due_date TEXT NOT NULL,
    priority INTEGER NOT NULL CHECK (priority BETWEEN 1 and 3),
    created_at TEXT NOT NULL,
    completed_at TEXT
);
CREATE INDEX IF NOT EXISTS idx_assignments_due ON assignments(due_date);
"""

class Priority(Enum):
    LOW = 1
    MEDIUM = 2
    HIGH = 3

    @classmethod
    def parse(cls, value: str | Priority) -> Priority:
        if isinstance(value, cls):
            return value
        try:
            return cls[value.strip().upper()]
        except KeyError:
            names = ", ".join(p.name.title() for p in cls)
            raise ValueError(f"Priority must be one of: {names}.") from None 

class AssignmentNotFound(LookupError):
    pass

@dataclass(frozen=True)
class Assignment:
    id: int
    subject: str
    task: str
    due_date: date
    priority: Priority
    completed_at: datetime | None

    @property
    def completed(self) -> bool:
        return self.completed_at is not None

    def days_left(self, today: date | None = None) -> int:
        return (self.due_date - (today or date.today())).days

    def status_text(self, today: date | None = None) -> str:
        if self.completed:
            return "✅ Completed"
        d = self.days_left(today)
        if d < 0:
            return f"🚨 OVERDUE by {-d} day(s)"
        if d == 0:
            return "🔥 Due today"
        if d <= 3:
            return f"⚠️ Due in {d} day(s)"
        return f"📅 {d} days left"

class AssignmentTracker:

    def __init__(self, db_path: str | Path = DEFAULT_DB):
        self.db_path = Path(db_path).expanduser()
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as conn:
            conn.executescript(SCHEMA)

    @contextmanager
    def _connect(self):
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def _to_assignment(row: sqlite3.Row) -> Assignment:
        done = row["completed_at"]
        return Assignment(
            id=row["id"],
            subject=row["subject"],
            task=row["task"],
            due_date=date.fromisoformat(row["due_date"]),
            priority=Priority(row["priority"]),
            completed_at=datetime.fromisoformat(done) if done else None,
        )

    def add(self, subject: str, task: str, due: str | date,
            priority: str | Priority = Priority.MEDIUM) -> Assignment:
        """Add an assignment. Raises ValueError on invalid input."""
        subject, task = subject.strip(), task.strip()
        if not subject or not task:
            raise ValueError("Subject and task cannot be empty.")
        if isinstance(due, str):
            try:
                due = datetime.strptime(due, "%Y-%m-%d").date()
            except ValueError:
                raise ValueError("Due date must be in YYYY-MM-DD format.") from None
        prio = Priority.parse(priority)

        with self._connect() as conn:
            cur = conn.execute(
                "INSERT INTO assignments (subject, task, due_date, priority, created_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (subject, task, due.isoformat(), prio.value,
                 datetime.now().isoformat(timespec="seconds")),
            )
            row = conn.execute(
                "SELECT * FROM assignments WHERE id = ?", (cur.lastrowid,)
            ).fetchone()
            return self._to_assignment(row)

    def list_assignments(self, *, subject: str | None = None,
                         priority: str | Priority | None = None,
                         include_completed: bool = False) -> list[Assignment]:
        query, params = "SELECT * FROM assignments WHERE 1=1", []
        if not include_completed:
            query += " AND completed_at is NULL"
        if subject:
            query += " AND subject = ? COLLATE NOCASE"
            params.append(subject.strip())
        if priority:
            query += " AND priority = ?"
            params.append(Priority.parse(priority).value)
        query += " ORDER BY due_date ASC, priority DESC"
        with self._connect() as conn:
            return [self._to_assignment(r) for r in conn.execute(query, params)]

    def complete(self, assignment_id: int) -> None:
        self._update(assignment_id, "completed_at = ?",
                     (datetime.now().isoformat(timespec="seconds"),))

    def reopen(self, assignment_id: int) -> None:
        self._update(assignment_id, "completed_at = NULL", ())

    def delete(self, assignment_id: int) -> None:
        with self._connect() as conn:
            cur = conn.execute("DELETE FROM assignments WHERE id = ?", (assignment_id,))
            if cur.rowcount == 0:
                raise AssignmentNotFound(assignment_id)

    def _update(self, assignment_id: int, set_clause: str, params: tuple) -> None:
        with self._connect() as conn:
            cur = conn.execute(
                f"UPDATE assignments SET {set_clause} WHERE id = ?",
                (*params, assignment_id),
            )
            if cur.rowcount == 0:
                raise AssignmentNotFound(assignment_id)

def format_table(assignments: list[Assignment], today: date | None = None) -> str:
    """Presentation lives outside the tracker, so it can be swapped for rich/GUI later."""
    if not assignments:
        return "📭 No assignments found."

    def cut(text:str, width: int) -> str:
        return text if len(text) <= width else text [: width - 1]

    lines = [f"{'ID':<4} {'Subject':<12} {'Task':<24} {'Due':<10} {'Pri':<6} Status"]
    lines.append("-" * 75)
    for a in assignments:
        lines.append(
            f"{a.id:<4} {cut(a.subject, 12):<12} {cut(a.task, 24):<24} "
            f"{a.due_date.isoformat():<10} {a.priority.name.title():<6} "
            f"{a.status_text(today)}"
        )
    return "\n".join(lines)