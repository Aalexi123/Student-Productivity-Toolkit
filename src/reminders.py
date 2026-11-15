"""Deadline reminders: pick out overdue and soon-due assignments and describe them."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date


class NotificationUnavailable(RuntimeError):
    """Raised when a desktop notification can't be shown."""


@dataclass(frozen=True)
class ReminderSummary:
    days: int
    overdue: list      # assignments past their due date, most overdue first
    upcoming: list     # due today or within `days` days, soonest first

    @property
    def is_empty(self) -> bool:
        return not (self.overdue or self.upcoming)


def _sort_key(a) -> tuple:
    return (a.due_date, -a.priority.value, a.id)  # earliest first, then High before Low


def build_reminder(assignments, days: int = 3, today: date | None = None) -> ReminderSummary:
    """Split assignments (objects like assignments.Assignment) into overdue and due-soon."""
    if days < 0:
        raise ValueError("days cannot be negative.")
    today = today or date.today()
    overdue, upcoming = [], []
    for a in assignments:
        if a.completed:
            continue
        left = (a.due_date - today).days
        if left < 0:
            overdue.append(a)
        elif left <= days:
            upcoming.append(a)
    return ReminderSummary(days, sorted(overdue, key=_sort_key), sorted(upcoming, key=_sort_key))


def _when(a, today: date) -> str:
    left = (a.due_date - today).days
    if left < 0:
        ago = -left
        return f"was due {a.due_date.isoformat()} ({ago} day{'s' if ago != 1 else ''} ago)"
    if left == 0:
        return "due TODAY"
    if left == 1:
        return "due tomorrow"
    return f"due {a.due_date.isoformat()} (in {left} days)"


def _line(a, today: date) -> str:
    extra = a.priority.name.title()
    if a.estimated_minutes:
        extra += f", est {a.estimated_minutes // 60}h{a.estimated_minutes % 60:02d}"
    return f"  - [{a.subject}] {a.task}: {_when(a, today)} ({extra})"


def format_reminder(summary: ReminderSummary, today: date | None = None) -> str:
    """Plain ASCII text, so it is safe in scheduled runs and log files."""
    today = today or date.today()
    if summary.is_empty:
        return f"All clear: nothing overdue or due within {summary.days} day(s)."
    lines = []
    if summary.overdue:
        lines.append(f"OVERDUE ({len(summary.overdue)})")
        lines += [_line(a, today) for a in summary.overdue]
    if summary.upcoming:
        if lines:
            lines.append("")
        lines.append(f"DUE WITHIN {summary.days} DAY(S) ({len(summary.upcoming)})")
        lines += [_line(a, today) for a in summary.upcoming]
    return "\n".join(lines)


def notification_text(summary: ReminderSummary) -> str | None:
    """One short line for a desktop notification, or None when there is nothing to say."""
    if summary.is_empty:
        return None
    parts = []
    if summary.overdue:
        parts.append(f"{len(summary.overdue)} overdue")
    if summary.upcoming:
        parts.append(f"{len(summary.upcoming)} due within {summary.days} day(s)")
    names = [a.task for a in summary.overdue + summary.upcoming]
    shown = ", ".join(names[:3]) + ("..." if len(names) > 3 else "")
    return f"{', '.join(parts)}: {shown}"


def notify(title: str, message: str) -> None:
    """Show a desktop notification using the optional 'plyer' package."""
    try:
        from plyer import notification
    except ImportError:
        raise NotificationUnavailable(
            "Desktop notifications need the optional 'plyer' package: pip install plyer"
        ) from None
    try:
        notification.notify(title=title, message=message, timeout=10)
    except Exception as e:  # noqa: BLE001 - plyer backends differ per operating system
        raise NotificationUnavailable(f"Could not show a notification: {e}") from e