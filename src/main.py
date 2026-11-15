import sys
from pathlib import Path
from file_organiser import SmartFileOrganiser, Move
from assignments import AssignmentTracker, format_table, AssignmentNotFound, parse_estimate_hours
from reports import generate_study_report, ReportDataError
from study_planner import generate_study_plan, generate_plan_from_assignments, PlannerConfig
from document_processor import process_document, process_folder, DocumentError
from session_log import log_session
from paths import (
    DEFAULT_ASSIGNMENTS_CSV,
    DEFAULT_ESTIMATES_CSV,
    DEFAULT_LOG,
    DEFAULT_PLAN,
    REPORTS_DIR,
)

def print_global_menu():
    print("\n" + "=" * 50)
    print("🎓  STUDENT PRODUCTIVITY AUTOMATION TOOLKIT")
    print("=" * 50)
    print("1. 📅 Open Assignment Tracker Dashboard")
    print("2. 📁 Open Smart File Organiser Menu")
    print("3. 📈 Generate Study Performance Reports")
    print("4. 🗓️  Generate Automated Study Plan")
    print("5. 🔍 Run Document Analytics Processor")
    print("6. ✍️  Log a Study Session")
    print("7. ❌ Exit Toolkit")
    print("-" * 50)

def print_assignment_menu():
    print("\n" + "=" * 45)
    print("    STUDENT PRODUCTIVITY: ASSIGNMENT TRACKER")
    print("=" * 45)
    print("1. View all assignments")
    print("2. Filter assignments (by Subject or Priority)")
    print("3. Add a new assignment")
    print("4. Mark an assignment as completed")
    print("5. Set study-time estimate for an assignment")
    print("6. Return to Main Menu")
    print("-" * 45)

def print_file_menu():
    print("\n" + "=" * 45)
    print("    📁 STUDENT PRODUCTIVITY: SMART FILE ORGANISER")
    print("=" * 45)
    print("1. Preview organisation (Dry Run)")
    print("2. Organise files (with confirmation)")
    print("3. Organise files (Automatic / No confirmation)")
    print("4. Undo last operation")
    print("5. Return to Main Menu")
    print("-" * 45)

def keyboard_confirm(move: Move) -> bool:
    try:
        response = input(
            f"Move '{move.source.name}' to '{move.category}/{move.destination.name}'? (y/n): "
        ).strip().lower()
        return response == "y"
    except (KeyboardInterrupt, EOFError):
        print("\nSkipping current file...")
        return False

def handle_assignment_tracker(tracker: AssignmentTracker):
    """Brings your assignment tracking loop right into the toolkit router"""
    while True:
        print_assignment_menu()
        choice = input("Select an option (1-6): ").strip()

        if choice == "1":
            assignments = tracker.list_assignments(include_completed=False)
            print("\n" + format_table(assignments))

        elif choice == "2":
            print("\n--- Filter Options ---")
            print("1. Filter by Subject")
            print("2. Filter by Priority")
            filter_type = input("Choose filter type (1-2): ").strip()

            if filter_type == "1":
                subject = input("Enter subject name (e.g., Mathematics): ").strip()
                assignments = tracker.list_assignments(subject=subject)
                print("\n" + format_table(assignments))
            elif filter_type == "2":
                priority = input("Enter priority (Low, Medium, High): ").strip()
                try:
                    assignments = tracker.list_assignments(priority=priority)
                    print("\n" + format_table(assignments))
                except ValueError as e:
                    print(f"❌ {e}")
            else:
                print("❌ Invalid filter choice.")

        elif choice == "3":
            print("\n--- Add New Assignment ---")
            subject = input("Subject: ").strip()
            task = input("Task/Assignment Name: ").strip()
            due_date = input("Due Date (YYYY-MM-DD): ").strip()
            priority = input("Priority [Low / Medium / High] (Default: Medium): ").strip()
            estimate_input = input("Estimated study hours (optional, e.g. 2.5): ")

            if not priority:
                priority = "Medium"

            try:
                tracker.add(subject=subject, task=task, due=due_date, priority=priority,
                            estimated_hours=parse_estimate_hours(estimate_input))
                print(f"✅ Successfully added: [{subject}] {task}")
            except ValueError as e:
                print(f"❌ Input Error: {e}")

        elif choice == "4":
            assignments = tracker.list_assignments(include_completed=False)
            print("\n" + format_table(assignments))
            try:
                assignment_id = int(input("\nEnter the ID of the assignment to mark as completed: ").strip())
                tracker.complete(assignment_id)
                print(f"🎉 Assignment ID {assignment_id} marked as Completed!")
            except ValueError:
                print("❌ Error: Please enter a valid numeric ID.")
            except AssignmentNotFound:
                print(f"❌ Error: Assignment ID {assignment_id} not found.")

        elif choice == "5":
            assignments = tracker.list_assignments(include_completed=False)
            print("\n" + format_table(assignments))
            try:
                assignment_id = int(input("\nEnter the ID of the assignment: ").strip())
            except ValueError:
                print("❌ Error: Please enter a valid numeric ID.")
                continue
            try:
                minutes = parse_estimate_hours(input("Estimated study hours (e.g. 2.5): "))
                if minutes is None:
                    raise ValueError("Please enter a number of hours.")
                tracker.set_estimate(assignment_id, minutes)
            except ValueError as e:
                print(f"❌ {e}")
            except AssignmentNotFound:
                print(f"❌ Error: Assignment ID {assignment_id} not found.")
            else:
                print(f"✅ Estimate saved for assignment ID {assignment_id}.")

        elif choice == "6":
            print("Returning to global toolkit dashboard...")
            break
        else:
            print("❌ Invalid option. Please choose a number between 1 and 6.")

def handle_file_organiser():
    organiser = SmartFileOrganiser()
    folder_input = input("Enter path to folder to organise: ").strip()
    if not folder_input:
        print("❌ Please enter a folder path.")
        return
    target_folder = Path(folder_input)

    try:
        target_folder = target_folder.expanduser().resolve()
        if not target_folder.is_dir():
            print(f"Error: '{target_folder}' is not a valid directory.")
            return
    except Exception as e:
        print(f"Error resolving path: {e}")
        return

    while True:
        print_file_menu()
        choice = input("Select an option (1-5): ").strip()

        if choice == "1":
            print(f"\n[Running Preview for: {target_folder}]")
            try:
                moves = organiser.plan(target_folder)
                if not moves:
                    print("🎉 Everything is already perfectly structured!")
                    continue
                for m in moves:
                    print(f"[PREVIEW] {m.source.name} -> {m.category}/{m.destination.name}")
            except Exception as e:
                print(f"An error occurred during planning: {e}")

        elif choice == "2":
            print(f"\n[Organising with Confirmation for: {target_folder}]")
            try:
                moves = organiser.plan(target_folder)
                if not moves:
                    print("🎉 No unorganised files detected.")
                    continue
                summary = organiser.execute(target_folder, moves, confirm=keyboard_confirm)
                print("\n--- Summary ---")
                for action in summary:
                    print(action)
            except Exception as e:
                print(f"An error occurred during execution: {e}")

        elif choice == "3":
            confirm_run = input("Are you sure you want to organise without prompting? (y/n): ").strip().lower()
            if confirm_run == "y":
                print(f"\n[Auto-Organising for: {target_folder}]")
                try:
                    moves = organiser.plan(target_folder)
                    if not moves:
                        print("🎉 No files require sorting.")
                        continue
                    summary = organiser.execute(target_folder, moves, confirm=None)
                    print("\n--- Summary ---")
                    for action in summary:
                        print(action)
                except Exception as e:
                    print(f"An error occurred during execution: {e}")
            else:
                print("Cancelled.")

        elif choice == "4":
            print("\n[Undoing Last Operation]")
            try:
                undo_actions = organiser.undo_last(target_folder)
                for action in undo_actions:
                    print(action)
            except Exception as e:
                print(f"An error occurred during rollback: {e}")

        elif choice == "5":
            print("Returning to global toolkit dashboard...")
            break
        else:
            print("❌ Invalid option. Please choose a number between 1 and 5.")

def handle_study_reporter():
    """Encapsulated Study Analytics Trigger Feature"""
    print("\n--- 📈 Study Performance Report Engine ---")
    log_input = input("Enter path to your study_log.csv (Leave blank for data/study_log.csv): ").strip()
    csv_path = Path(log_input) if log_input else DEFAULT_LOG

    try:
        print("\nCrunching data models, filtering bad rows and plotting charts...")
        generate_study_report(csv_path=csv_path, output_dir=REPORTS_DIR)
    except FileNotFoundError:
        print(f"❌ Error: Target log spreadsheet could not be found at: {csv_path}")
    except ReportDataError as rde:
        print(f"❌ Data Schema/Parsing Failure: {rde}")
    except Exception as e:
        print(f"❌ An unexpected analytics system crash occurred: {e}")

def handle_study_planner(tracker):
    """Automated Back-to-Back Calendar Logic Router"""
    print("\n--- 🗓️  Automated Study Plan Generator ---")
    print("Plan from:")
    print("1. Assignment Tracker (recommended)")
    print("2. CSV files")
    source = input("Choose a source (1-2, leave blank for 1): ").strip() or "1"
    if source not in ("1", "2"):
        print("❌ Invalid choice.")
        return

    if source == "2":
        assign_input = input("Enter path to assignments CSV (Leave blank for DEFAULT_ASSIGNMENTS_CSV): ").strip()
        assign_path = Path(assign_input) if assign_input else DEFAULT_ASSIGNMENTS_CSV

        estim_input = input("Enter path to task estimates CSV (Leave blank for DEFAULT_ESTIMATES_CSV): ").strip()
        estim_path = Path(estim_input) if estim_input else DEFAULT_ESTIMATES_CSV

    out_input = input("Enter path to save the generated plan CSV (Leave blank for DEFAULT_PLAN): ").strip()
    out_path = Path(out_input) if out_input else DEFAULT_PLAN

    try:
        print("\nLoading schedules, resolving hourly capacities and building calendar targets...")
        if source == "1":
            plan = generate_plan_from_assignments(tracker.list_assignments(), output_path=out_path)
        else:
            plan = generate_study_plan(
                assignments_path=assign_path,
                requirements_path=estim_path,
                output_path=out_path
            )
        print(f"✅ Study plan successfully compiled and saved to: {out_path}")
        print(f"📊 Scheduled total of {len(plan.sessions)} sessions.")

        if plan.issues:
            print("\n⚠️  Planner Validation Notices:")
            for issue in plan.issues:
                print(f"- [{issue.kind.upper()}] {issue.message}")

    except FileNotFoundError as fnf:
        print(f"❌ Configuration Error: {fnf}")
    except ValueError as ve:
        print(f"❌ Data Formatter Mismatch: {ve}")
    except Exception as e:
        print(f"❌ An unexpected planning engine failure occurred: {e}")

def handle_document_processor():
    """Brings the multi-format privacy masking & text statistics engine online"""
    print("\n--- 🔍 Document Analytics & Privacy Processor ---")
    print("1. Process a single document file (.txt, .md, .pdf, .docx, .csv)")
    print("2. Process a whole folder batch")
    choice = input("Select processing mode (1-2): ").strip()

    if choice not in ("1", "2"):
        print("❌ Invalid mode choice choice.")
        return

    target_input = input("Enter path to the target file/folder: ").strip()
    if not target_input:
        print("❌ Path cannot be left blank.")
        return

    target_path = Path(target_input).expanduser().resolve()

    out_input = input("Enter output directory for text reports (Leave blank for REPORTS_DIR): ").strip()
    out_dir = Path(out_input) if out_input else REPORTS_DIR

    mask_input = input("Enable best-effort privacy masking? (y/n, Default: y): ").strip().lower()
    mask_privacy = mask_input != "n"

    try:
        if choice == "1":
            report_file = process_document(target_path, out_dir, mask_privacy=mask_privacy)
            print(f"✅ Document analysis saved to: {report_file}")
        else:
            if not target_path.is_dir():
                print(f"❌ Error: '{target_path}' is not a valid directory.")
                return
            reports, failures = process_folder(target_path, out_dir, mask_privacy=mask_privacy)
            print("\n--- Batch Job Complete ---")
            print(f"✅ Processed {len(reports)} file(s).")
            for name, err in failures.items():
                print(f" - ⚠️ {name}: {err}")
    except FileNotFoundError:
        print(f"❌ File/Folder System Error: Target could not be found at '{target_path}'")
    except DocumentError as de:
        print(f"❌ Processing Engine Error: {de}")
    except Exception as e:
        print(f"❌ An unexpected analytical document system crash occurred: {e}")

def handle_session_logger():
    """Append a study session to the CSV the report feature reads."""
    print("\n--- ✍️  Log a Study Session ---")
    subject = input("Subject: ").strip()
    minutes = input("Minutes studied: ").strip()
    day = input("Date (YYYY-MM-DD, leave blank for today): ").strip()

    try:
        row = log_session(
            DEFAULT_LOG, subject, minutes, day or None,
            plan_path=DEFAULT_PLAN,
        )
    except ValueError as e:
        print(f"❌ Input Error: {e}")
        return
    except OSError as e:
        print(f"❌ Could not write the study log: {e}")
        return
    print(
        f"✅ Logged {row['duration_minutes']} min of {row['subject']} on {row['date']} "
        f"(planned: {row['planned_minutes']} min)."
    )

def run_menu() -> int:
    tracker = AssignmentTracker()

    while True:
        print_global_menu()
        global_choice = input("Select a toolkit option (1-7): ").strip()

        if global_choice == "1":
            handle_assignment_tracker(tracker)
        elif global_choice == "2":
            handle_file_organiser()
        elif global_choice == "3":
            handle_study_reporter()
        elif global_choice == "4":
            handle_study_planner()
        elif global_choice == "5":
            handle_document_processor()
        elif global_choice == "6":
            handle_session_logger()
        elif global_choice =="7":
            print("Exiting Toolkit. Keep crushing your goals! 🚀")
            return 0
        else:
            print("❌ Invalid option. Please choose a number between 1 and 7.")

def main(argv: list[str] | None = None) -> int:
    """No arguments: interactive menu. With arguments: run one command (see cli.py)."""
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        return run_menu()
    from cli import run
    return run(argv)

if __name__ == "__main__":
    sys.exit(main())