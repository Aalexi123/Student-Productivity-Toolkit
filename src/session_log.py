"""Study-session logging: append sessions to the CSV that the reports feature reads."""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path

LOG_COLUMNS = ["date", "subject", "duration_minutes", "planned_minutes"]
MAX_SESSION_MINUTES = 24 * 60


def _parse_day(value: str | date | None) -> date:
    if value is None or value == "":
        return date.today()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise ValueError("Date must be in YYYY-MM-DD format.") from None


def _parse_minutes(value: int | str) -> int:
    try:
        minutes = int(str(value).strip())
    except ValueError:
        raise ValueError("Minutes must be a whole number.") from None
    if not 0 < minutes <= MAX_SESSION_MINUTES:
        raise ValueError(f"Minutes must be between 1 and {MAX_SESSION_MINUTES}.")
    return minutes


def _read_rows(path: Path) -> list[dict]:
    if not path.exists() or path.stat().st_size == 0:
        return []
    with path.open(newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _same(a: str | None, b: str | None) -> bool:
    return (a or "").strip().casefold() == (b or "").strip().casefold()


def _to_int(value: str | None) -> int:
    try:
        return int(float(value or 0))
    except ValueError:
        return 0


def _canonical_subject(subject: str, *row_sets: list[dict]) -> str:
    """Reuse the spelling already in the log/plan so 'physics' and 'Physics' don't split."""
    for rows in row_sets:
        for row in rows:
            if _same(row.get("subject"), subject):
                return row["subject"].strip()
    return subject


def log_session(log_path: str | Path, subject: str, minutes: int | str,
                day: str | date | None = None,
                plan_path: str | Path | None = None) -> dict:
    """Append one study session and return the row written.

    planned_minutes is taken from the study plan for that day and subject. It is
    counted once per day: later sessions for the same subject and day get 0, so the
    report doesn't double count planned time.
    """
    subject = (subject or "").strip()
    if not subject:
        raise ValueError("Subject cannot be empty.")
    minutes = _parse_minutes(minutes)
    day = _parse_day(day)

    log_path = Path(log_path).expanduser()
    existing = _read_rows(log_path)
    plan_rows = _read_rows(Path(plan_path).expanduser()) if plan_path else []

    subject = _canonical_subject(subject, existing, plan_rows)
    iso = day.isoformat()

    planned_total = sum(
        _to_int(r.get("planned_minutes"))
        for r in plan_rows
        if r.get("date") == iso and _same(r.get("subject"), subject)
    )
    already_assigned = sum(
        _to_int(r.get("planned_minutes"))
        for r in existing
        if r.get("date") == iso and _same(r.get("subject"), subject)
    )
    row = {
        "date": iso,
        "subject": subject,
        "duration_minutes": minutes,
        "planned_minutes": max(0, planned_total - already_assigned),
    }

    log_path.parent.mkdir(parents=True, exist_ok=True)
    is_new = not log_path.exists() or log_path.stat().st_size == 0
    needs_newline = False
    if not is_new:  # a hand-edited file may not end with a newline
        with log_path.open("rb") as f:
            f.seek(-1, 2)
            needs_newline = f.read(1) not in (b"\n", b"\r")

    with log_path.open("a", newline="", encoding="utf-8") as f:
        if needs_newline:
            f.write("\n")
        writer = csv.DictWriter(f, fieldnames=LOG_COLUMNS, lineterminator="\n")
        if is_new:
            writer.writeheader()
        writer.writerow(row)
    return row