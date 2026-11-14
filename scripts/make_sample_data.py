"""Create demo CSVs in data/ with dates relative to today, so the demo never goes stale.

Usage (from the project root):
    python scripts/make_sample_data.py          # skips files that already exist
    python scripts/make_sample_data.py --force  # overwrite them
"""
import argparse
import csv
from datetime import date, timedelta
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parent.parent / "data"


def write_csv(name: str, header: list[str], rows: list[list], force: bool) -> None:
    path = DATA_DIR / name
    if path.exists() and not force:
        print(f"skipped (already exists): {path}")
        return
    with path.open("w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(header)
        writer.writerows(rows)
    print(f"created: {path}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Create demo data for the toolkit.")
    parser.add_argument("--force", action="store_true", help="overwrite existing files")
    force = parser.parse_args().force

    today = date.today()
    DATA_DIR.mkdir(exist_ok=True)

    write_csv(
        "assignments.csv",
        ["subject", "task", "due_date", "priority", "status"],
        [
            ["Mathematics", "Calculus assignment", (today + timedelta(days=5)).isoformat(), "High", "Pending"],
            ["Computing", "Programming project", (today + timedelta(days=9)).isoformat(), "High", "In Progress"],
            ["Physics", "Lab report", (today + timedelta(days=3)).isoformat(), "Medium", "Pending"],
            ["History", "Essay draft", (today + timedelta(days=12)).isoformat(), "Low", "Pending"],
        ],
        force,
    )
    write_csv(
        "estimates.csv",
        ["task", "estimated_hours"],
        [["Calculus assignment", 3.5], ["Programming project", 6], ["Lab report", 2], ["Essay draft", 4]],
        force,
    )

    subjects = [("Mathematics", 60), ("Computing", 90), ("Physics", 45)]
    log_rows = []
    for back in range(14, 0, -1):
        day = today - timedelta(days=back)
        if day.weekday() == 6:  # rest on Sundays
            continue
        subject, planned = subjects[back % len(subjects)]
        actual = planned + (-20, -5, 0, 10, 25)[back % 5]
        log_rows.append([day.isoformat(), subject, actual, planned])
    write_csv("study_log.csv", ["date", "subject", "duration_minutes", "planned_minutes"], log_rows, force)


if __name__ == "__main__":
    main()