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

## Command line

Run with no arguments for the interactive menu, or run one feature directly:

| Command | What it does |
|---|---|
| `python src/main.py plan --days 14 --no-weekends` | Study plan from the tracker (`--source csv` uses CSV files) |
| `python src/main.py report --since 30` | Planned vs actual report for the last 30 days |
| `python src/main.py organise <folder>` | Preview only. Add `--apply` to move files, or `--undo` to reverse |
| `python src/main.py process <file-or-folder>` | Analyse documents (`--no-mask` turns masking off) |
| `python src/main.py log Physics 45` | Record a study session |
| `python src/main.py remind --days 3` | List overdue and due-soon assignments |

Add `--help` after any command for its options. Exit codes: 0 success, 1 failure, 2 bad usage.

### Scheduling daily reminders

Optional desktop notifications need `pip install plyer`.

**Windows (Task Scheduler):** replace the paths with your own.

```powershell
schtasks /Create /SC DAILY /ST 08:00 /TN "StudyToolkitReminders" /TR "C:\path\to\project\.venv\Scripts\python.exe C:\path\to\project\src\main.py remind --days 3 --notify"
schtasks /Run /TN "StudyToolkitReminders"
```

The second command runs it once now so you can test it. If your path contains spaces, wrap each path in escaped quotes (`\"...\"`). Remove the task later with `schtasks /Delete /TN "StudyToolkitReminders" /F`.

**macOS / Linux (cron):** run `crontab -e` and add:

```cron
0 8 * * * /path/to/project/.venv/bin/python /path/to/project/src/main.py remind --days 3 >> ~/study-reminders.log 2>&1
```

Cron usually can't show desktop notifications, so this writes the reminders to a log file.

## Features

| Feature | What it does |
|---|---|
| **Smart File Organiser** | Sorts files into Documents, Spreadsheets, Images, Code and Archives. Preview (dry run) first, confirm each move if you like, never overwrites, and **undo** the last operation. |
| **Assignment Tracker** | SQLite-backed. Add, filter and complete assignments; shows overdue and due-soon items sorted by deadline with an estimated study time per assignment. |
| **Study Planner** | Turns deadlines and estimated hours into a daily schedule with a configurable daily capacity. High-priority tasks are scheduled earlier. Warns about overdue tasks, missing estimates and plans that can't fit. Exports CSV. Plans straight from the tracker (or CSV files). |
| **Document Processor** | Extracts text from TXT, MD, PDF and DOCX; summarises CSVs with pandas. Reports word count, reading time and top terms. Best-effort masking of emails, phone numbers and secrets, with redaction counts in each report. Single file or whole folder. |
| **Productivity Reports** | Planned vs actual study time by subject and week, with text and Matplotlib chart output. Log sessions from the menu. |
| **Deadline Reminders** | The \remind` command lists overdue and due-soon assignments. Schedule it daily, with optional desktop notifications. |

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
├── .github/
│   └── workflows/
│       └── tests.yml
├── src/
│   ├── main.py
│   ├── file_organiser.py
│   ├── assignments.py
│   ├── study_planner.py
│   ├── document_processor.py
│   ├── reports.py
│   ├── session_log.py
│   ├── cli.py
│   ├── paths.py
│   └── reminders.py
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
- Reports only count days with a logged session, so planned time on days you didn’t study isn’t counted yet.
- Assignments need a study-time estimate before the planner can schedule them (menu: Assignment Tracker, option 5)
- Desktop notifications use the optional plyer package and depend on your operating system.

## Testing

```bash
pip install -r requirements-dev.txt
python -m pytest
```

## Roadmap

- [x] Study-session logger feeding the reports
- [x] Tracker → planner bridge (one source of truth for assignments)
- [x] CLI subcommands (`plan`, `report`, `organise --apply`) for cron / Task Scheduler
- [x] Deadline reminders
- [ ] OCR for scanned PDFs

## Why I built this

I built it to practise automation, data processing and testing on problems I actually have as a student.

## Author

**Aalexi123** · [GitHub](https://github.com/Aalexi123)

## License

MIT. See [LICENSE](LICENSE).