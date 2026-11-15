"""Command-line interface.

    python src/main.py                  interactive menu
    python src/main.py <command> ...    run one feature without prompts

Exit codes: 0 = success, 1 = the command failed (message on stderr), 2 = bad usage.
"""
from __future__ import annotations

import argparse
import sys
from datetime import date, timedelta
from pathlib import Path

from assignments import DEFAULT_DB
from paths import (
    DEFAULT_ASSIGNMENTS_CSV,
    DEFAULT_ESTIMATES_CSV,
    DEFAULT_LOG,
    DEFAULT_PLAN,
    REPORTS_DIR,
)


# ---------- argument types ----------
def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _non_negative_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a whole number") from None
    if value < 0:
        raise argparse.ArgumentTypeError("cannot be negative")
    return value


def _positive_float(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{text}' is not a number") from None
    if not value > 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return value


# ---------- helpers ----------
def _open_tracker(db: Path):
    from assignments import AssignmentTracker

    db = db.expanduser()
    if not db.exists():
        raise FileNotFoundError(
            f"Tracker database not found: {db}. Add an assignment in the menu first."
        )
    return AssignmentTracker(db)


def _use_utf8_output() -> None:
    """Redirected or scheduled runs on Windows use a legacy codepage that can't print emoji."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")
        except (AttributeError, ValueError, OSError):
            pass


# ---------- commands ----------
def _cmd_plan(args: argparse.Namespace) -> int:
    from study_planner import PlannerConfig, generate_plan_from_assignments, generate_study_plan

    config = PlannerConfig(
        daily_capacity_min=round(args.capacity * 60),
        planning_days=args.days,
        include_weekends=not args.no_weekends,
        buffer_days=args.buffer_days,
    )
    if args.source == "tracker":
        tracker = _open_tracker(args.db)
        plan = generate_plan_from_assignments(
            tracker.list_assignments(), output_path=args.output, config=config
        )
    else:
        plan = generate_study_plan(
            args.assignments, args.estimates, output_path=args.output, config=config
        )
    print(f"Plan saved to {args.output} ({len(plan.sessions)} sessions).")
    for issue in plan.issues:
        print(f"[{issue.kind.upper()}] {issue.message}")
    return 0


def _cmd_report(args: argparse.Namespace) -> int:
    from reports import generate_study_report  # loads pandas/matplotlib only when needed

    since = date.today() - timedelta(days=args.since) if args.since else None
    generate_study_report(args.log, output_dir=args.output_dir, since=since)
    return 0


def _cmd_organise(args: argparse.Namespace) -> int:
    from file_organiser import SmartFileOrganiser

    organiser = SmartFileOrganiser()
    if args.undo:
        results = organiser.undo_last(args.folder)
    else:
        results = organiser.organise_folder(args.folder, dry_run=not args.apply)

    for line in results:
        print(line)
    if not results:
        print("Nothing to do.")
    elif not args.apply and not args.undo:
        print("(Preview only. Re-run with --apply to move the files.)")
    return 1 if any(line.startswith("[ERROR]") for line in results) else 0


def _cmd_process(args: argparse.Namespace) -> int:
    from document_processor import process_document, process_folder

    path = args.path.expanduser()
    mask = not args.no_mask
    if path.is_dir():
        reports, failures = process_folder(path, args.output_dir, mask_privacy=mask)
        print(f"Processed {len(reports)} file(s). Reports are in {args.output_dir}")
        for name, reason in failures.items():
            print(f"[FAILED] {name}: {reason}", file=sys.stderr)
        return 1 if failures else 0
    report = process_document(path, args.output_dir, mask_privacy=mask)
    print(f"Report saved to {report}")
    return 0


def _cmd_log(args: argparse.Namespace) -> int:
    from session_log import log_session

    row = log_session(args.log, args.subject, args.minutes, args.date, plan_path=args.plan)
    print(
        f"Logged {row['duration_minutes']} min of {row['subject']} on {row['date']} "
        f"(planned: {row['planned_minutes']} min)."
    )
    return 0


# ---------- parser ----------
def _add_db(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--db", type=Path, default=DEFAULT_DB,
                        help="assignment tracker database (default: %(default)s)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="main.py",
        description="Student Productivity Automation Toolkit. "
                    "Run with no command to open the interactive menu.",
    )
    parser.add_argument("--debug", action="store_true",
                        help="show the full traceback if a command fails (put before the command)")
    sub = parser.add_subparsers(dest="command", metavar="<command>")

    plan = sub.add_parser("plan", help="generate a study plan",
                          description="Generate a study plan from the tracker (default) or CSV files.")
    plan.add_argument("--source", choices=("tracker", "csv"), default="tracker")
    _add_db(plan)
    plan.add_argument("--assignments", type=Path, default=DEFAULT_ASSIGNMENTS_CSV,
                      help="assignments CSV, used with --source csv (default: %(default)s)")
    plan.add_argument("--estimates", type=Path, default=DEFAULT_ESTIMATES_CSV,
                      help="estimates CSV, used with --source csv (default: %(default)s)")
    plan.add_argument("--output", type=Path, default=DEFAULT_PLAN,
                      help="where to save the plan (default: %(default)s)")
    plan.add_argument("--days", type=_positive_int, default=7,
                      help="how many days to plan (default: %(default)s)")
    plan.add_argument("--capacity", type=_positive_float, default=3.0, metavar="HOURS",
                      help="study hours available per day (default: %(default)s)")
    plan.add_argument("--no-weekends", action="store_true", help="don't schedule Saturdays or Sundays")
    plan.add_argument("--buffer-days", type=_non_negative_int, default=0, metavar="N",
                      help="finish N days before each deadline (default: %(default)s)")
    plan.set_defaults(handler=_cmd_plan)

    report = sub.add_parser("report", help="planned vs actual study report")
    report.add_argument("--log", type=Path, default=DEFAULT_LOG,
                        help="study log CSV (default: %(default)s)")
    report.add_argument("--since", type=_positive_int, metavar="DAYS",
                        help="only include the last DAYS days")
    report.add_argument("--output-dir", type=Path, default=REPORTS_DIR,
                        help="where to save the report and charts (default: %(default)s)")
    report.set_defaults(handler=_cmd_report)

    organise = sub.add_parser("organise", help="sort a folder's files into category folders",
                              description="Previews by default. Nothing moves unless you pass --apply.")
    organise.add_argument("folder", type=Path)
    mode = organise.add_mutually_exclusive_group()
    mode.add_argument("--apply", action="store_true", help="actually move the files")
    mode.add_argument("--undo", action="store_true", help="undo the last organise run in this folder")
    organise.set_defaults(handler=_cmd_organise)

    process = sub.add_parser("process", help="analyse a document or a folder of documents")
    process.add_argument("path", type=Path, help="a file or a folder")
    process.add_argument("--output-dir", type=Path, default=REPORTS_DIR,
                         help="where to save reports (default: %(default)s)")
    process.add_argument("--no-mask", action="store_true", help="turn off privacy masking")
    process.set_defaults(handler=_cmd_process)

    log = sub.add_parser("log", help="record a study session")
    log.add_argument("subject")
    log.add_argument("minutes", help="minutes studied (whole number)")
    log.add_argument("--date", help="YYYY-MM-DD (default: today)")
    log.add_argument("--log", type=Path, default=DEFAULT_LOG,
                     help="study log CSV (default: %(default)s)")
    log.add_argument("--plan", type=Path, default=DEFAULT_PLAN,
                     help="plan CSV used to fill in planned minutes (default: %(default)s)")
    log.set_defaults(handler=_cmd_log)

    return parser


def run(argv: list[str]) -> int:
    """Run one command and return its exit code."""
    _use_utf8_output()
    parser = build_parser()
    args = parser.parse_args(argv)  # exits with code 2 on bad usage
    handler = getattr(args, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    try:
        return handler(args)
    except KeyboardInterrupt:
        print("\nCancelled.", file=sys.stderr)
        return 130
    except Exception as e:  # noqa: BLE001 - report any failure as a clean message
        if args.debug:
            raise
        print(f"Error: {e}", file=sys.stderr)
        return 1