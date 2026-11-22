"""Graphical interface for the toolkit, built with customtkinter.

    python src/main.py gui

This module only handles presentation (see theme.py for the look). Every feature calls
the same functions the menu and the command line use, so behaviour stays identical.
"""
from __future__ import annotations

import threading
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

import theme
from assignments import AssignmentNotFound, AssignmentTracker, Priority, parse_estimate_hours
from document_processor import SUPPORTED_SUFFIXES, DocumentError, process_document, process_folder
from file_organiser import SmartFileOrganiser
from paths import (
    DEFAULT_ASSIGNMENTS_CSV,
    DEFAULT_ESTIMATES_CSV,
    DEFAULT_LOG,
    DEFAULT_PLAN,
    REPORTS_DIR,
)
from reminders import NotificationUnavailable, build_reminder, notification_text, notify
from reports import ReportDataError, generate_study_report
from session_log import log_session
from study_planner import PlannerConfig, fmt_minutes, generate_plan_from_assignments, generate_study_plan
from theme import ACCENT, ACCENT_SOFT, AMBER, BG, BORDER, GREEN, HOVER, MUTED, RED, SIDEBAR, SLATE, SURFACE, TEXT

PAD = 32  # horizontal page padding

PRIORITY_COLOUR = {Priority.HIGH: RED, Priority.MEDIUM: AMBER, Priority.LOW: SLATE}


# ---------- helpers ----------
def run_async(widget: ctk.CTkBaseClass, work, done) -> None:
    """Run work() on a background thread so the window doesn't freeze.

    done(value, error) is always called on the main thread. Tk widgets must only be
    touched from the main thread, so the worker never calls into the UI itself; the
    main thread polls for the result instead.
    """
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = work()
        except Exception as e:  # noqa: BLE001 - shown to the user by `done`
            box["error"] = e

    worker = threading.Thread(target=target, daemon=True)
    worker.start()

    def poll() -> None:
        if worker.is_alive():
            widget.after(100, poll)
        else:
            done(box.get("value"), box.get("error"))

    widget.after(100, poll)


def plural(n: int, word: str) -> str:
    return f"{n} {word}" + ("" if n == 1 else "s")


def assignment_status(a, today: date | None = None) -> tuple[str, tuple[str, str] | None]:
    """Plain-text status and colour. Emoji are avoided because Tk renders them inconsistently."""
    if a.completed:
        return "Completed", GREEN
    left = a.days_left(today)
    if left < 0:
        return f"Overdue by {plural(-left, 'day')}", RED
    if left == 0:
        return "Due today", RED
    if left == 1:
        return "Due tomorrow", AMBER
    if left <= 3:
        return f"Due in {left} days", AMBER
    return f"Due in {left} days", None


def set_text(box: ctk.CTkTextbox, text: str) -> None:
    box.configure(state="normal")
    box.delete("1.0", "end")
    box.insert("1.0", text)
    box.configure(state="disabled")


def clear(frame) -> None:
    for child in frame.winfo_children():
        child.destroy()


def browse_into(entry: ctk.CTkEntry, kind: str = "file", filetypes=None) -> None:
    if kind == "folder":
        chosen = filedialog.askdirectory()
    elif kind == "save":
        chosen = filedialog.asksaveasfilename(defaultextension=".csv")
    else:
        chosen = filedialog.askopenfilename(filetypes=filetypes or [("All files", "*.*")])
    if chosen:
        entry.delete(0, "end")
        entry.insert(0, chosen)


def path_row(parent, label: str, default: str = "", kind: str = "file", filetypes=None):
    """A labelled entry with a Browse button. Returns (frame, entry)."""
    frame = theme.box(parent, fg_color="transparent")
    frame.grid_columnconfigure(1, weight=1)
    theme.label(frame, label, width=130).grid(row=0, column=0, padx=(0, 8))
    entry = theme.entry(frame, width=200)
    entry.grid(row=0, column=1, sticky="ew")
    if default:
        entry.insert(0, default)
    theme.ghost_button(frame, "Browse", lambda: browse_into(entry, kind, filetypes), width=84).grid(
        row=0, column=2, padx=(8, 0))
    return frame, entry


def labelled(parent, caption: str, widget_factory):
    """A small caption above a widget. Returns (frame, widget)."""
    frame = theme.box(parent, fg_color="transparent")
    theme.caption(frame, caption).pack(anchor="w", pady=(0, 4))
    widget = widget_factory(frame)
    widget.pack(anchor="w")
    return frame, widget


def assignment_row(parent, a, on_done=None, on_estimate=None) -> ctk.CTkFrame:
    """One assignment. The coloured bar is its priority; the status colour is its urgency."""
    row = theme.box(parent, fg_color=SURFACE, border_width=1, border_color=BORDER, corner_radius=10)
    row.grid_columnconfigure(1, weight=1)
    theme.box(row, width=4, corner_radius=2, fg_color=PRIORITY_COLOUR[a.priority]).grid(
        row=0, column=0, sticky="ns", padx=(12, 12), pady=12)

    text = theme.box(row, fg_color="transparent")
    text.grid(row=0, column=1, sticky="w", pady=10)
    theme.label(text, a.task, size=14, weight="bold").pack(anchor="w")
    meta = theme.box(text, fg_color="transparent")
    meta.pack(anchor="w")
    theme.caption(meta, a.subject).pack(side="left")
    theme.label(meta, f"{a.priority.name.title()} priority", size=12,
                color=PRIORITY_COLOUR[a.priority]).pack(side="left", padx=(10, 0))

    status_text, colour = assignment_status(a)
    when = theme.box(row, fg_color="transparent")
    when.grid(row=0, column=2, padx=16, sticky="e")
    theme.label(when, status_text, weight="bold", color=colour, anchor="e").pack(anchor="e")
    est = "No estimate" if a.estimated_minutes is None else f"{fmt_minutes(a.estimated_minutes)} estimated"
    theme.caption(when, f"{a.due_date:%a %d %b}, {est}", anchor="e").pack(anchor="e")

    col = 3
    if on_done and not a.completed:
        theme.ghost_button(row, "Done", lambda: on_done(a.id), accent=True, width=64, height=32).grid(
            row=0, column=col, padx=(0, 6))
        col += 1
    if on_estimate and not a.completed:
        theme.ghost_button(row, "Estimate", lambda: on_estimate(a.id), width=80, height=32).grid(
            row=0, column=col, padx=(0, 12))
    return row


class Page(ctk.CTkFrame):
    """Base class: a header, a status line, and an on_show() hook called when opened."""

    title = ""
    subtitle = ""

    def __init__(self, master, app: "ToolkitApp"):
        super().__init__(master, fg_color="transparent")
        self.app = app
        self.grid_columnconfigure(0, weight=1)
        self.header = theme.box(self, fg_color="transparent")
        self.header.grid(row=0, column=0, sticky="ew", padx=PAD, pady=(30, 18))
        self.header.grid_columnconfigure(0, weight=1)
        theme.label(self.header, self.title, size=26, weight="bold").grid(row=0, column=0, sticky="w")
        if self.subtitle:
            theme.label(self.header, self.subtitle, color=MUTED).grid(row=1, column=0, sticky="w")
        self.status = theme.label(self, "", wraplength=820, justify="left")

    def say(self, message: str, kind: str = "ok") -> None:
        colour = {"ok": GREEN, "error": RED, "info": MUTED}[kind]
        self.status.configure(text=message, text_color=colour)

    def on_show(self) -> None:
        pass


# ---------- pages ----------
class DashboardPage(Page):
    title = "Dashboard"
    subtitle = "What needs your attention."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(1, weight=1)

        controls = theme.box(self.header, fg_color="transparent")
        controls.grid(row=0, column=1, rowspan=2, sticky="e")
        theme.label(controls, "Look ahead", color=MUTED).pack(side="left", padx=(0, 8))
        self.days_menu = theme.menu(controls, ["1", "3", "7", "14"], width=72,
                                    command=lambda _v: self.refresh())
        self.days_menu.set("3")
        self.days_menu.pack(side="left")
        theme.label(controls, "days", color=MUTED).pack(side="left", padx=(8, 16))
        theme.ghost_button(controls, "Send notification", self.send_notification, width=140).pack(side="left")

        self.body = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.body.grid(row=1, column=0, sticky="nsew", padx=(PAD - 8, PAD - 8))
        self.status.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(6, 16))

    def _summary(self):
        return build_reminder(self.app.tracker.list_assignments(), days=int(self.days_menu.get()))

    def on_show(self) -> None:
        self.refresh()

    def refresh(self) -> None:
        summary = self._summary()
        overdue, soon = len(summary.overdue), len(summary.upcoming)
        window = plural(summary.days, "day")
        if summary.is_empty:
            headline = f"You're clear for the next {window}."
        elif overdue and soon:
            headline = f"{overdue} overdue, and {soon} due in the next {window}."
        elif overdue:
            headline = f"{overdue} overdue, and nothing else due in the next {window}."
        else:
            headline = f"{soon} due in the next {window}."
        open_count = len(self.app.tracker.list_assignments())

        clear(self.body)
        theme.label(self.body, headline, size=20, weight="bold").pack(anchor="w", padx=8, pady=(0, 2))
        theme.caption(self.body, f"{plural(open_count, 'open assignment')} in total.").pack(
            anchor="w", padx=8, pady=(0, 14))
        if summary.is_empty:
            theme.primary_button(self.body, "Add an assignment",
                                 lambda: self.app.show("assignments"), width=170).pack(anchor="w", padx=8)
        for heading, items in (("Overdue", summary.overdue), ("Due soon", summary.upcoming)):
            if items:
                theme.label(self.body, heading, size=15, weight="bold").pack(anchor="w", padx=8, pady=(14, 6))
                for a in items:
                    assignment_row(self.body, a).pack(fill="x", padx=8, pady=3)

    def send_notification(self) -> None:
        text = notification_text(self._summary())
        if text is None:
            self.say("Nothing to remind you about.", "info")
            return
        try:
            notify("Study reminders", text)
            self.say("Notification sent.")
        except NotificationUnavailable as e:
            self.say(str(e), "error")


class AssignmentsPage(Page):
    title = "Assignments"
    subtitle = "Track deadlines and how long each one will take."
    PRIORITY_FILTER = ("All priorities", "Low", "Medium", "High")

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(3, weight=1)

        form = theme.panel(self)
        form.grid(row=1, column=0, sticky="ew", padx=PAD, pady=(0, 14))
        form.grid_columnconfigure(1, weight=1)  # the task field absorbs spare width
        self.subject = theme.entry(form, "Subject", 130)
        self.task = theme.entry(form, "Task", 160)
        self.due = theme.entry(form, "Due (YYYY-MM-DD)", 150)
        self.priority = theme.menu(form, ["Low", "Medium", "High"], width=100)
        self.priority.set("Medium")
        self.estimate = theme.entry(form, "Hours", 70)
        for i, widget in enumerate((self.subject, self.task, self.due, self.priority, self.estimate)):
            widget.grid(row=0, column=i, padx=(14 if i == 0 else 5, 5), pady=14,
                        sticky="ew" if widget is self.task else "")
        theme.primary_button(form, "Add", self.add_assignment, width=76).grid(
            row=0, column=5, padx=(8, 14), pady=14)

        filters = theme.box(self, fg_color="transparent")
        filters.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(0, 8))
        self.filter_subject = theme.entry(filters, "Filter by subject", 180)
        self.filter_subject.pack(side="left")
        self.filter_subject.bind("<Return>", lambda _e: self.refresh())
        self.filter_priority = theme.menu(filters, list(self.PRIORITY_FILTER), width=150,
                                          command=lambda _v: self.refresh())
        self.filter_priority.pack(side="left", padx=8)
        self.show_completed = ctk.CTkSwitch(filters, text="Show completed", font=theme.font(13),
                                            command=self.refresh)
        self.show_completed.pack(side="left", padx=12)
        theme.ghost_button(filters, "Apply", self.refresh, width=72).pack(side="left")

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=(PAD - 8, PAD - 8))
        self.status.grid(row=4, column=0, sticky="ew", padx=PAD, pady=(6, 16))

    def on_show(self) -> None:
        self.refresh()

    def add_assignment(self) -> None:
        try:
            self.app.tracker.add(
                subject=self.subject.get(),
                task=self.task.get(),
                due=self.due.get().strip(),
                priority=self.priority.get(),
                estimated_minutes=parse_estimate_hours(self.estimate.get()),
            )
        except ValueError as e:
            self.say(str(e), "error")
            return
        self.say(f"Added: [{self.subject.get().strip()}] {self.task.get().strip()}")
        for entry in (self.subject, self.task, self.due, self.estimate):
            entry.delete(0, "end")
        self.refresh()

    def refresh(self) -> None:
        priority = self.filter_priority.get()
        assignments = self.app.tracker.list_assignments(
            subject=self.filter_subject.get().strip() or None,
            priority=None if priority == self.PRIORITY_FILTER[0] else priority,
            include_completed=bool(self.show_completed.get()),
        )
        clear(self.list_frame)
        if not assignments:
            theme.label(self.list_frame, "No assignments match. Add one above to get started.",
                        color=MUTED).pack(anchor="w", padx=8, pady=12)
            return
        for a in assignments:
            assignment_row(self.list_frame, a, self.complete, self.set_estimate).pack(
                fill="x", padx=8, pady=3)

    def complete(self, assignment_id: int) -> None:
        try:
            self.app.tracker.complete(assignment_id)
        except AssignmentNotFound:
            self.say(f"Assignment {assignment_id} no longer exists.", "error")
        else:
            self.say("Marked as completed.")
        self.refresh()

    def set_estimate(self, assignment_id: int) -> None:
        answer = ctk.CTkInputDialog(text="Estimated study hours (e.g. 2.5):", title="Study estimate").get_input()
        if answer is None:  # dialog cancelled
            return
        try:
            minutes = parse_estimate_hours(answer)
            if minutes is None:
                raise ValueError("Please enter a number of hours.")
            self.app.tracker.set_estimate(assignment_id, minutes)
        except ValueError as e:
            self.say(str(e), "error")
        except AssignmentNotFound:
            self.say(f"Assignment {assignment_id} no longer exists.", "error")
        else:
            self.say("Estimate saved.")
        self.refresh()


class PlannerPage(Page):
    title = "Study Planner"
    subtitle = "Turn deadlines and estimates into a day-by-day schedule."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(4, weight=1)

        self.source = ctk.CTkSegmentedButton(self, values=["Assignment Tracker", "CSV files"],
                                             height=34, font=theme.font(13), command=self._source_changed)
        self.source.set("Assignment Tracker")
        self.source.grid(row=1, column=0, sticky="w", padx=PAD, pady=(0, 12))

        settings = theme.panel(self)
        settings.grid(row=2, column=0, sticky="ew", padx=PAD)
        settings.grid_columnconfigure(0, weight=1)

        self.csv_frame = theme.box(settings, fg_color="transparent")
        self.csv_frame.grid_columnconfigure(0, weight=1)
        row, self.assignments_csv = path_row(self.csv_frame, "Assignments CSV", str(DEFAULT_ASSIGNMENTS_CSV))
        row.grid(row=0, column=0, sticky="ew", pady=3)
        row, self.estimates_csv = path_row(self.csv_frame, "Estimates CSV", str(DEFAULT_ESTIMATES_CSV))
        row.grid(row=1, column=0, sticky="ew", pady=3)

        options = theme.box(settings, fg_color="transparent")
        options.grid(row=1, column=0, sticky="ew", padx=16, pady=(16, 8))
        for caption, default, attr in (("Days to plan", "7", "days"), ("Hours per day", "3", "capacity"),
                                       ("Buffer days", "0", "buffer")):
            frame, entry = labelled(options, caption, lambda p: theme.entry(p, width=100))
            entry.insert(0, default)
            setattr(self, attr, entry)
            frame.pack(side="left", padx=(0, 16))
        self.weekends = ctk.CTkSwitch(options, text="Include weekends", font=theme.font(13))
        self.weekends.select()
        self.weekends.pack(side="left", pady=(20, 0))

        save = theme.box(settings, fg_color="transparent")
        save.grid(row=2, column=0, sticky="ew", padx=16, pady=(0, 16))
        save.grid_columnconfigure(0, weight=1)
        row, self.output_path = path_row(save, "Save plan to", str(DEFAULT_PLAN), kind="save")
        row.grid(row=0, column=0, sticky="ew")
        theme.primary_button(save, "Generate plan", self.generate, width=130).grid(row=0, column=1, padx=(14, 0))

        self.result = ctk.CTkScrollableFrame(self, fg_color="transparent")
        self.result.grid(row=4, column=0, sticky="nsew", padx=(PAD - 8, PAD - 8), pady=(8, 0))
        self.status.grid(row=5, column=0, sticky="ew", padx=PAD, pady=(6, 16))

    def _source_changed(self, value: str) -> None:
        if value == "CSV files":
            self.csv_frame.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        else:
            self.csv_frame.grid_forget()

    def build_config(self) -> PlannerConfig:
        try:
            capacity_min = round(float(self.capacity.get()) * 60)
            days = int(self.days.get())
            buffer_days = int(self.buffer.get())
        except ValueError:
            raise ValueError("Days and buffer must be whole numbers; hours must be a number.") from None
        # PlannerConfig raises ValueError with its own clear message for out-of-range values
        return PlannerConfig(
            daily_capacity_min=capacity_min,
            planning_days=days,
            include_weekends=bool(self.weekends.get()),
            buffer_days=buffer_days,
        )

    def generate(self) -> None:
        try:
            config = self.build_config()
            out = Path(self.output_path.get().strip() or DEFAULT_PLAN)
            if self.source.get() == "Assignment Tracker":
                plan = generate_plan_from_assignments(
                    self.app.tracker.list_assignments(), output_path=out, config=config)
            else:
                plan = generate_study_plan(
                    self.assignments_csv.get().strip(), self.estimates_csv.get().strip(),
                    output_path=out, config=config)
        except (ValueError, FileNotFoundError, OSError) as e:
            self.say(str(e), "error")
            return
        self.show_plan(plan)
        self.say(f"Plan saved to {out} ({len(plan.sessions)} sessions).")

    def show_plan(self, plan) -> None:
        clear(self.result)
        if not plan.sessions:
            theme.label(self.result, "No sessions were scheduled.", color=MUTED).pack(anchor="w", padx=8, pady=8)
        current_day = None
        for s in plan.sessions:
            if s.date != current_day:
                current_day = s.date
                theme.label(self.result, f"{s.date:%A, %d %B}", size=14, weight="bold").pack(
                    anchor="w", padx=8, pady=(14, 4))
            line = theme.box(self.result, fg_color="transparent")
            line.pack(fill="x", padx=8)
            theme.label(line, fmt_minutes(s.minutes), weight="bold", color=ACCENT, width=84).pack(side="left")
            theme.label(line, f"{s.subject}: {s.task}").pack(side="left")
        if plan.issues:
            theme.label(self.result, "Things to check", size=14, weight="bold").pack(
                anchor="w", padx=8, pady=(18, 4))
            for issue in plan.issues:
                theme.label(self.result, f"{issue.kind.replace('_', ' ').capitalize()}: {issue.message}", color=AMBER,
                            wraplength=780, justify="left").pack(anchor="w", padx=8, pady=1)


class ReportsPage(Page):
    title = "Study Reports"
    subtitle = "Planned versus actual study time."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(3, weight=1)
        self._images: list[ctk.CTkImage] = []  # keep references or Tk drops the pictures

        row, self.log_path = path_row(self, "Study log CSV", str(DEFAULT_LOG),
                                      filetypes=[("CSV files", "*.csv")])
        row.grid(row=1, column=0, sticky="ew", padx=PAD, pady=2)

        controls = theme.box(self, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(8, 10))
        theme.label(controls, "Only the last", color=MUTED).pack(side="left")
        self.since = theme.entry(controls, "all", 64)
        self.since.pack(side="left", padx=8)
        theme.label(controls, "days", color=MUTED).pack(side="left", padx=(0, 16))
        self.generate_button = theme.primary_button(controls, "Generate report", self.generate, width=140)
        self.generate_button.pack(side="left")

        self.tabs = ctk.CTkTabview(
            self, corner_radius=theme.RADIUS_PANEL, border_width=1, border_color=BORDER, fg_color=SURFACE,
            segmented_button_fg_color=HOVER, segmented_button_selected_color=SURFACE,
            segmented_button_selected_hover_color=SURFACE, segmented_button_unselected_color=HOVER,
            segmented_button_unselected_hover_color=BORDER, text_color=TEXT)
        self.tabs.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=(0, 8))
        summary_tab = self.tabs.add("Summary")
        subject_tab = self.tabs.add("By subject")
        weekly_tab = self.tabs.add("Weekly trend")
        for tab in (summary_tab, subject_tab, weekly_tab):
            tab.grid_columnconfigure(0, weight=1)
            tab.grid_rowconfigure(0, weight=1)
        self.summary = ctk.CTkTextbox(summary_tab, wrap="none", state="disabled", font=theme.mono(13),
                                      border_width=0, fg_color="transparent")
        self.summary.grid(row=0, column=0, sticky="nsew")
        self.subject_image = theme.label(subject_tab, "Generate a report to see this chart.", color=MUTED,
                                         anchor="center")
        self.subject_image.grid(row=0, column=0)
        self.weekly_image = theme.label(weekly_tab, "Generate a report to see this chart.", color=MUTED,
                                        anchor="center")
        self.weekly_image.grid(row=0, column=0)
        self.status.grid(row=4, column=0, sticky="ew", padx=PAD, pady=(0, 16))

    def generate(self) -> None:
        since = None
        raw = self.since.get().strip()
        if raw:
            try:
                days = int(raw)
                if days < 1:
                    raise ValueError
            except ValueError:
                self.say("Days must be a whole number of at least 1.", "error")
                return
            since = date.fromordinal(date.today().toordinal() - days)

        csv_path = Path(self.log_path.get().strip() or DEFAULT_LOG)
        self.generate_button.configure(state="disabled")
        self.say("Crunching the numbers and drawing charts...", "info")
        run_async(self, lambda: generate_study_report(csv_path, REPORTS_DIR, since=since), self._done)

    def _done(self, paths, error) -> None:
        self.generate_button.configure(state="normal")
        if isinstance(error, FileNotFoundError):
            self.say(f"Study log not found: {self.log_path.get()}", "error")
        elif isinstance(error, ReportDataError):
            self.say(str(error), "error")
        elif error is not None:
            self.say(f"Could not build the report: {error}", "error")
        else:
            set_text(self.summary, paths["text"].read_text(encoding="utf-8"))
            self._show_chart(self.subject_image, paths["subject_chart"])
            self._show_chart(self.weekly_image, paths["weekly_chart"])
            self.say(f"Report saved in {paths['text'].parent}")

    def _show_chart(self, label: ctk.CTkLabel, image_path: Path) -> None:
        from PIL import Image  # installed with matplotlib

        with Image.open(image_path) as img:
            img.load()
            width = 640
            image = ctk.CTkImage(light_image=img.copy(), size=(width, round(width * img.height / img.width)))
        self._images.append(image)
        label.configure(image=image, text="")


class OrganiserPage(Page):
    title = "File Organiser"
    subtitle = "Sort a messy folder into Documents, Images, Code and more."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(3, weight=1)
        self.organiser = SmartFileOrganiser()
        self.folder: Path | None = None
        self.moves: list = []
        self.checks: list[tuple[ctk.CTkCheckBox, object]] = []

        row, self.folder_entry = path_row(self, "Folder to organise", kind="folder")
        row.grid(row=1, column=0, sticky="ew", padx=PAD, pady=2)

        buttons = theme.box(self, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="ew", padx=PAD, pady=(8, 10))
        theme.ghost_button(buttons, "Preview", self.preview, width=100).pack(side="left")
        self.move_button = theme.primary_button(buttons, "Move selected files", self.move_selected,
                                                width=160, state="disabled")
        self.move_button.pack(side="left", padx=8)
        theme.ghost_button(buttons, "Undo last", self.undo, width=100).pack(side="left")
        theme.caption(buttons, "Untick a file in the preview to leave it where it is.").pack(
            side="left", padx=14)

        self.list_frame = ctk.CTkScrollableFrame(self, fg_color=SURFACE, border_width=1, border_color=BORDER,
                                                 corner_radius=theme.RADIUS_PANEL)
        self.list_frame.grid(row=3, column=0, sticky="nsew", padx=PAD, pady=(0, 10))
        self.result = ctk.CTkTextbox(self, height=110, wrap="word", state="disabled", font=theme.mono(12))
        self.result.grid(row=4, column=0, sticky="ew", padx=PAD, pady=(0, 6))
        self.status.grid(row=5, column=0, sticky="ew", padx=PAD, pady=(0, 16))

    def _target(self) -> Path | None:
        raw = self.folder_entry.get().strip()
        if not raw:
            self.say("Please choose a folder first.", "error")
            return None
        folder = Path(raw).expanduser()
        if not folder.is_dir():
            self.say(f"'{folder}' is not a valid folder.", "error")
            return None
        return folder

    def _clear_list(self) -> None:
        clear(self.list_frame)
        self.checks = []
        self.moves = []
        self.move_button.configure(state="disabled")

    def preview(self) -> None:
        folder = self._target()
        if folder is None:
            return
        self._clear_list()
        try:
            moves = self.organiser.plan(folder)
        except (ValueError, OSError) as e:  # e.g. refusing to organise the home folder
            self.say(str(e), "error")
            return
        self.folder = folder
        if not moves:
            self.say("Everything is already organised.", "info")
            return
        self.moves = moves
        for m in moves:
            box = ctk.CTkCheckBox(self.list_frame, font=theme.font(13),
                                  text=f"{m.source.name}   to   {m.category}/{m.destination.name}")
            box.select()
            box.pack(anchor="w", padx=10, pady=5)
            self.checks.append((box, m))
        self.move_button.configure(state="normal")
        self.say(f"{plural(len(moves), 'file')} would be moved.", "info")

    def move_selected(self) -> None:
        if self.folder is None:
            return
        chosen = [m for box, m in self.checks if box.get()]
        if not chosen:
            self.say("No files are ticked.", "error")
            return
        if not messagebox.askyesno("Move files", f"Move {len(chosen)} file(s) into category folders?\n"
                                                 "You can undo this afterwards."):
            return
        try:
            results = self.organiser.execute(self.folder, chosen)
        except (ValueError, OSError) as e:
            self.say(str(e), "error")
            return
        set_text(self.result, "\n".join(results))
        self._clear_list()
        self.say(f"Done: {len(results)} file(s) processed.")

    def undo(self) -> None:
        folder = self._target()
        if folder is None:
            return
        if not messagebox.askyesno("Undo", "Undo the last organise operation in this folder?"):
            return
        try:
            results = self.organiser.undo_last(folder)
        except (ValueError, OSError) as e:
            self.say(str(e), "error")
            return
        set_text(self.result, "\n".join(results))
        self._clear_list()
        self.say("Undo finished.")


class DocumentsPage(Page):
    title = "Document Analytics"
    subtitle = "Word counts, reading time and top terms, with private details masked."

    def __init__(self, master, app):
        super().__init__(master, app)
        self.grid_rowconfigure(4, weight=1)
        types = " ".join(f"*{s}" for s in sorted(SUPPORTED_SUFFIXES))
        self._filetypes = [("Supported documents", types), ("All files", "*.*")]

        self.mode = ctk.CTkSegmentedButton(self, values=["Single file", "Whole folder"], height=34,
                                           font=theme.font(13), command=self._mode_changed)
        self.mode.set("Single file")
        self.mode.grid(row=1, column=0, sticky="w", padx=PAD, pady=(0, 12))

        form = theme.panel(self)
        form.grid(row=2, column=0, sticky="ew", padx=PAD)
        form.grid_columnconfigure(0, weight=1)
        self.target_holder = theme.box(form, fg_color="transparent")
        self.target_holder.grid(row=0, column=0, sticky="ew", padx=16, pady=(16, 4))
        self.target_holder.grid_columnconfigure(0, weight=1)
        self.target_row = None
        self.target_entry = None
        self._build_target_row("file")

        row, self.out_entry = path_row(form, "Save reports to", str(REPORTS_DIR), kind="folder")
        row.grid(row=1, column=0, sticky="ew", padx=16, pady=4)

        controls = theme.box(form, fg_color="transparent")
        controls.grid(row=2, column=0, sticky="ew", padx=16, pady=(8, 16))
        self.mask = ctk.CTkSwitch(controls, text="Mask emails, phone numbers and secrets", font=theme.font(13))
        self.mask.select()
        self.mask.pack(side="left")
        self.run_button = theme.primary_button(controls, "Analyse", self.run, width=110)
        self.run_button.pack(side="right")

        self.result = ctk.CTkTextbox(self, wrap="word", state="disabled", font=theme.mono(12))
        self.result.grid(row=4, column=0, sticky="nsew", padx=PAD, pady=(12, 8))
        self.status.grid(row=5, column=0, sticky="ew", padx=PAD, pady=(0, 16))

    def _build_target_row(self, kind: str) -> None:
        if self.target_row is not None:
            self.target_row.destroy()
        label = "Document" if kind == "file" else "Folder"
        self.target_row, self.target_entry = path_row(
            self.target_holder, label, kind=kind, filetypes=self._filetypes)
        self.target_row.grid(row=0, column=0, sticky="ew")

    def _mode_changed(self, value: str) -> None:
        self._build_target_row("file" if value == "Single file" else "folder")

    def run(self) -> None:
        raw = self.target_entry.get().strip()
        if not raw:
            self.say("Please choose a file or folder.", "error")
            return
        target = Path(raw).expanduser().resolve()
        out_dir = Path(self.out_entry.get().strip() or REPORTS_DIR)
        masking = bool(self.mask.get())
        single = self.mode.get() == "Single file"
        if not single and not target.is_dir():
            self.say(f"'{target}' is not a valid folder.", "error")
            return

        def work():
            if single:
                return process_document(target, out_dir, mask_privacy=masking)
            return process_folder(target, out_dir, mask_privacy=masking)

        self.run_button.configure(state="disabled")
        self.say("Analysing...", "info")
        run_async(self, work, lambda value, error: self._done(value, error, single))

    def _done(self, value, error, single: bool) -> None:
        self.run_button.configure(state="normal")
        if isinstance(error, FileNotFoundError):
            self.say(f"Could not find: {self.target_entry.get()}", "error")
        elif isinstance(error, DocumentError):
            self.say(f"Could not process that document: {error}", "error")
        elif error is not None:
            self.say(f"Unexpected error: {error}", "error")
        elif single:
            set_text(self.result, value.read_text(encoding="utf-8"))
            self.say(f"Report saved to {value}")
        else:
            reports, failures = value
            lines = [f"Processed {len(reports)} file(s)."] + [f"  saved: {r}" for r in reports]
            if failures:
                lines += ["", "Skipped:"] + [f"  {name}: {err}" for name, err in failures.items()]
            set_text(self.result, "\n".join(lines))
            self.say(f"Batch complete: {len(reports)} report(s), {len(failures)} skipped.")


class LogSessionPage(Page):
    title = "Log a Study Session"
    subtitle = "Record what you studied so reports can compare it with your plan."

    def __init__(self, master, app):
        super().__init__(master, app)
        form = theme.panel(self)
        form.grid(row=1, column=0, sticky="w", padx=PAD)
        inner = theme.box(form, fg_color="transparent")
        inner.pack(padx=22, pady=22)

        frame, self.subject = labelled(inner, "Subject", lambda p: ctk.CTkComboBox(
            p, values=[""], width=340, height=theme.CONTROL_HEIGHT, font=theme.font(13),
            dropdown_font=theme.font(13)))
        frame.pack(anchor="w", pady=(0, 14))
        frame, self.minutes = labelled(inner, "Minutes studied", lambda p: theme.entry(p, "e.g. 45", 340))
        frame.pack(anchor="w", pady=(0, 14))
        frame, self.day = labelled(inner, "Date (leave blank for today)",
                                   lambda p: theme.entry(p, "YYYY-MM-DD", 340))
        frame.pack(anchor="w", pady=(0, 20))
        theme.primary_button(inner, "Log session", self.log, width=340).pack(anchor="w")
        self.status.grid(row=2, column=0, sticky="ew", padx=PAD, pady=14)

    def on_show(self) -> None:
        subjects = sorted({a.subject for a in self.app.tracker.list_assignments(include_completed=True)})
        self.subject.configure(values=subjects or [""])

    def log(self) -> None:
        try:
            row = log_session(DEFAULT_LOG, self.subject.get(), self.minutes.get(),
                              self.day.get().strip() or None, plan_path=DEFAULT_PLAN)
        except ValueError as e:
            self.say(str(e), "error")
            return
        except OSError as e:
            self.say(f"Could not write the study log: {e}", "error")
            return
        self.say(f"Logged {row['duration_minutes']} min of {row['subject']} on {row['date']} "
                 f"(planned: {row['planned_minutes']} min).")
        self.minutes.delete(0, "end")


# ---------- application ----------
class ToolkitApp(ctk.CTk):
    NAV = (
        ("dashboard", "Dashboard", DashboardPage),
        ("assignments", "Assignments", AssignmentsPage),
        ("planner", "Study Planner", PlannerPage),
        ("log", "Log Session", LogSessionPage),
        ("reports", "Reports", ReportsPage),
        ("organiser", "File Organiser", OrganiserPage),
        ("documents", "Documents", DocumentsPage),
    )

    def __init__(self, tracker: AssignmentTracker | None = None):
        super().__init__()
        theme.apply_theme()  # after the root exists: it needs to see the installed fonts
        self.configure(fg_color=BG)
        self.tracker = tracker or AssignmentTracker()
        self.title("Student Productivity Toolkit")
        self.geometry("1120x740")
        self.minsize(980, 640)
        self.grid_columnconfigure(2, weight=1)
        self.grid_rowconfigure(0, weight=1)

        sidebar = theme.box(self, width=232, corner_radius=0, fg_color=SIDEBAR)
        sidebar.grid(row=0, column=0, sticky="nsw")
        sidebar.grid_propagate(False)
        sidebar.grid_columnconfigure(0, weight=1)
        sidebar.grid_rowconfigure(len(self.NAV) + 1, weight=1)
        theme.box(self, width=1, corner_radius=0, fg_color=BORDER).grid(row=0, column=1, sticky="ns")
        theme.label(sidebar, "Study Toolkit", size=18, weight="bold").grid(
            row=0, column=0, padx=22, pady=(28, 22), sticky="w")

        content = theme.box(self, fg_color="transparent", corner_radius=0)
        content.grid(row=0, column=2, sticky="nsew")
        content.grid_columnconfigure(0, weight=1)
        content.grid_rowconfigure(0, weight=1)

        self.pages: dict[str, Page] = {}
        self.nav_buttons: dict[str, ctk.CTkButton] = {}
        for i, (key, label, page_class) in enumerate(self.NAV, start=1):
            button = ctk.CTkButton(sidebar, text=label, anchor="w", height=40, font=theme.font(14),
                                   fg_color="transparent", text_color=TEXT, hover_color=HOVER,
                                   command=lambda k=key: self.show(k))
            button.grid(row=i, column=0, padx=14, pady=2, sticky="ew")
            self.nav_buttons[key] = button
            page = page_class(content, self)
            page.grid(row=0, column=0, sticky="nsew")
            self.pages[key] = page

        theme.caption(sidebar, "Appearance").grid(row=len(self.NAV) + 2, column=0, padx=22, pady=(0, 4), sticky="w")
        appearance = theme.menu(sidebar, ["System", "Light", "Dark"], width=196, command=ctk.set_appearance_mode)
        appearance.set("System")
        appearance.grid(row=len(self.NAV) + 3, column=0, padx=18, pady=(0, 22), sticky="w")

        self.show("dashboard")

    def show(self, key: str) -> None:
        for name, button in self.nav_buttons.items():
            active = name == key
            button.configure(fg_color=ACCENT_SOFT if active else "transparent",
                             text_color=ACCENT if active else TEXT,
                             font=theme.font(14, "bold" if active else "normal"))
        page = self.pages[key]
        page.say("", "info")  # drop stale messages from the last visit
        page.tkraise()
        page.on_show()


def run_gui() -> int:
    ctk.set_appearance_mode("System")
    ToolkitApp().mainloop()
    return 0
