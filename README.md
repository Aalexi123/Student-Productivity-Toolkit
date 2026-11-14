# Student Productivity Automation Toolkit

![Tests](https://github.com/Aalexi123/student-productivity-toolkit/actions/workflows/tests.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)

A command-line toolkit that automates everyday student admin: organise messy download folders, track assignments, generate a realistic study plan, analyse documents (with privacy masking) and report on study habits.

## Quick start

```bash
git clone https://github.com/Aalexi123/student-productivity-toolkit.git
cd student-productivity-toolkit
python -m venv .venv
# Windows:      .venv\Scripts\activate
# macOS/Linux:  source .venv/bin/activate
pip install -r requirements.txt
python scripts/make_sample_data.py
python src/main.py
```

## Features

| Feature | What it does |
|---|---|
| **Smart File Organiser** | Sorts files into Documents, Spreadsheets, Images, Code and Archives. Preview (dry run) first, confirm each move if you like, never overwrites, and **undo** the last operation. |
| **Assignment Tracker** | SQLite-backed. Add, filter and complete assignments; shows overdue and due-soon items sorted by deadline with an estimated study time per assignment. |
| **Study Planner** | Turns deadlines and estimated hours into a daily schedule with a configurable daily capacity. High-priority tasks are scheduled earlier. Warns about overdue tasks, missing estimates and plans that can't fit. Exports CSV. Plans straight from the tracker (or CSV files). |
| **Document Processor** | Extracts text from TXT, MD, PDF and DOCX; summarises CSVs with pandas. Reports word count, reading time and top terms. Best-effort masking of emails, phone numbers and secrets, with redaction counts in each report. Single file or whole folder. |
| **Productivity Reports** | Planned vs actual study time by subject and week, with text and Matplotlib chart output. Log sessions from the menu. |

## Data formats

| File | Required columns |
|---|---|
| `data/assignments.csv` | `subject, task, due_date (YYYY-MM-DD), priority, status` |
| `data/estimates.csv` | `task, estimated_hours` |
| study log (for reports) | `date, subject, duration_minutes, planned_minutes` |

## Using the modules directly

Run these from the project root.

```python
from pathlib import Path
from src.file_organiser import SmartFileOrganiser

organiser = SmartFileOrganiser()
for line in organiser.organise_folder(Path.home() / "Downloads", dry_run=True):
    print(line)
```

```python
from src.study_planner import PlannerConfig, generate_study_plan

plan = generate_study_plan(
    "data/assignments.csv",
    "data/estimates.csv",
    "reports/study_plan.csv",
    PlannerConfig(daily_capacity_min=180, planning_days=7),
)
for issue in plan.issues:
    print(issue.kind, "-", issue.message)
print(f"{len(plan.sessions)} sessions planned")
```

```python
from pathlib import Path
from src.document_processor import process_document

print(process_document(Path("notes.pdf"), Path("reports")))
```

## Project structure

```text
student-productivity-toolkit/
├── src/
│   ├── main.py
│   ├── file_organiser.py
│   ├── assignments.py
│   ├── study_planner.py
│   ├── document_processor.py
│   ├── reports.py
│   └── session_log.py
├── scripts/
│   └── make_sample_data.py
├── tests/
├── data/
├── reports/
├── LICENSE
├── requirements.txt
├── requirements-dev.txt
└── README.md
```

## Design decisions

- **Plan, then execute.** The organiser builds a list of moves first, so the preview, confirmation and real run share one code path, and every move is logged so it can be undone.
- **Integer minutes for scheduling.** Avoids floating-point scraps like 0-minute sessions.
- **Errors are typed, not printed.** Modules raise specific exceptions (e.g. `UnsupportedFormatError`); the menu decides how to show them, so batch runs survive one bad file.
- **Privacy by default.** Document masking is on unless you turn it off, and each report states what was redacted.

## Limitations

- Masking is regex-based and best effort. It does not catch names, addresses or national ID numbers.
- Scanned PDFs have no text layer and are not supported (no OCR yet).
- The interface is menu-only; there are no command-line flags for scheduling.
- Reports only count days with a logged session, so planned time on days you didn’t study isn’t counted yet.

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Roadmap

- [x] Study-session logger feeding the reports
- [x] Tracker → planner bridge (one source of truth for assignments)
- [ ] CLI subcommands (`plan`, `report`, `organise --apply`) for cron / Task Scheduler
- [ ] Deadline reminders
- [ ] OCR for scanned PDFs

## Why I built this

I built it to practise automation, data processing and testing on problems I actually have as a student.

## Author

**Aalexi123** · [GitHub](https://github.com/Aalexi123)

## License

MIT. See [LICENSE](LICENSE).