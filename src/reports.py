from __future__ import annotations

import warnings
from datetime import date
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

REQUIRED_COLUMNS = {"date", "subject", "duration_minutes", "planned_minutes"}

class ReportDataError(ValueError):
    """Raised when the study log can't be turned into a report."""

def load_study_log(csv_path: str | Path, since: date | None = None) -> pd.DataFrame:
    csv_path = Path(csv_path).expanduser()
    if not csv_path.exists():
        raise FileNotFoundError(f"Study log not found: {csv_path}")
    try:
        df = pd.read_csv(csv_path)
    except (pd.errors.EmptyDataError, pd.errors.ParserError) as e:
        raise ReportDataError(f"Could not read {csv_path.name}: {e}") from e

    df.columns = df.columns.str.strip().str.lower()
    missing = REQUIRED_COLUMNS - set(df.columns)
    if missing:
        raise ReportDataError(f"CSV is missing columns: {', '.join(sorted(missing))}")

    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    for col in ("duration_minutes", "planned_minutes"):
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["subject"] = df["subject"].astype("string").str.strip()

    before = len(df)
    df = df.dropna(subset=list(REQUIRED_COLUMNS))
    df = df[(df["duration_minutes"] >= 0) & (df["planned_minutes"] >= 0)]
    if before - len(df):
        warnings.warn(f"Skipped {before - len(df)} invalid row(s) in {csv_path.name}.")

    if since is not None:
        df = df[df["date"] >= pd.Timestamp(since)]
    if df.empty:
        raise ReportDataError("No valid study sessions found for that period.")
    return df

def summarise_by_subject(df: pd.DataFrame) -> pd.DataFrame:
    summary = (
        df.groupby("subject")[["duration_minutes", "planned_minutes"]]
        .sum()
        .rename(columns={"duration_minutes": "actual_min",
                         "planned_minutes": "planned_min"})
    )
    summary["variance_min"] = summary["actual_min"] - summary["planned_min"]
    summary["completion"] = summary["actual_min"] / summary["planned_min"].where(
        summary["planned_min"] > 0
    )
    return summary.sort_values("variance_min")

def fmt_duration(minutes: float) -> str:
    total = round(minutes)
    h, m = divmod(abs(total), 60)
    return f"{'-' if total < 0 else ''}{h}h {m:02d}m"

def build_text_report(df: pd.DataFrame, summary: pd.DataFrame) -> str:
    planned = summary["planned_min"].sum()
    actual = summary["actual_min"].sum()
    gap = actual - planned

    lines = [
        "=" * 50,
        "STUDY PERFORMANCE REPORT".center(50),
        "=" * 50,
        f"Period : {df['date'].min():%d %b %Y} - {df['date'].max():%d %b %Y}",
        f"Planned : {fmt_duration(planned)} ",
        f"Actual : {fmt_duration(actual)}",
    ]
    if planned > 0:
        lines.append(f"Hit rate: {actual / planned:.0%}")
    if abs(gap) < 1:
        lines.append("🎯 Right on plan overall.")
    elif gap > 0:
        lines.append(f"🎯 You studied {fmt_duration(gap)} more than planned!")
    else:
        lines.append(f"⚠️ You fell short of plan by {fmt_duration(-gap)}.")

    lines += ["", "--- Subject breakdown (biggest shortfall first) ---"]
    for subject, r in summary.iterrows():
        detail = f"planned {fmt_duration(r.planned_min)}, actual {fmt_duration(r.actual_min)}"
        if pd.notna(r.completion):
            detail += f", {r.completion:.0%}"
        if abs(r.variance_min) < 1:
            lines.append(f"• ⚖️ {subject}: on target ({detail})")
        elif r.variance_min > 0:
            lines.append(f"• 🔥 {subject}: +{fmt_duration(r.variance_min)} ({detail})")
        else:
            lines.append(f"• 📉 {subject}: {fmt_duration(r.variance_min)} ({detail})")
    lines.append("=" * 50)
    return "\n".join(lines)

def plot_planned_vs_actual(summary: pd.DataFrame, out_path: Path) -> None:
    hours = (summary[["planned_min", "actual_min"]] / 60).rename(
        columns={"planned_min": "Planned Hours", "actual_min": "Actual Hours"}
    )
    fig, ax = plt.subplots(figsize=(10, 6))
    hours.plot.bar(ax=ax, color=["skyblue", "salmon"], width=0.8)
    ax.set_xlabel("Subject")
    ax.set_ylabel("Hours")
    ax.set_title("Planned vs. Actual Study Hours by Subject", pad=15)
    ax.grid(axis="y", linestyle="--", alpha=0.7)
    ax.set_axisbelow(True)
    plt.setp(ax.get_xticklabels(), rotation=30, ha="right")
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

def plot_weekly_trend(df: pd.DataFrame, out_path: Path) -> None:
    """Finally uses the date column: planned vs actual hours per week."""
    weekly = (
        df.set_index("date")[["planned_minutes", "duration_minutes"]]
        .resample("W")
        .sum()
        / 60
    )
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.plot(weekly.index, weekly["planned_minutes"], marker="o",
            color="skyblue", label="Planned")
    ax.plot(weekly.index, weekly["duration_minutes"], marker="o",
            color="salmon", label="Actual")
    ax.set_ylabel("Hours per week")
    ax.set_title("Weekly Study Trend")
    ax.grid(linestyle="--", alpha=0.7)
    ax.legend()
    fig.autofmt_xdate()
    fig.tight_layout()
    fig.savefig(out_path, dpi=150)
    plt.close(fig)

def generate_study_report(csv_path: str | Path,
                          output_dir: str | Path = "reports",
                          since: date | None = None) -> dict[str, Path]:
    df = load_study_log(csv_path, since)
    summary = summarise_by_subject(df)

    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    stamp = f"{df['date'].min():%Y%m%d}_{df['date'].max():%Y%m%d}"

    paths = {
        "text": out / f"study_report_{stamp}.txt",
        "subject_chart": out / f"planned_vs_actual_{stamp}.png",
        "weekly_chart": out / f"weekly_trend_{stamp}.png",
    }
    report = build_text_report(df, summary)
    paths["text"].write_text(report, encoding="utf-8")
    plot_planned_vs_actual(summary, paths["subject_chart"])
    plot_weekly_trend(df, paths["weekly_chart"])

    print(report)
    return paths