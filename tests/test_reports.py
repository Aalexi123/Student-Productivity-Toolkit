import pytest
import pandas as pd
from datetime import date
from src.reports import (
    load_study_log,
    summarise_by_subject,
    fmt_duration,
    build_text_report,
    plot_planned_vs_actual,
    plot_weekly_trend,
    ReportDataError
)

def test_load_study_log_valid(tmp_path):
    """Ensures a normal, valid CSV is loaded perfectly."""
    csv = tmp_path / "good_log.csv"
    csv.write_text("date,subject,duration_minutes,planned_minutes\n2026-10-01,Physics,60,60\n")
    df = load_study_log(csv)
    assert len(df) == 1
    assert df.loc[0, "subject"] == "Physics"

def test_load_missing_file_raises():
    """Ensures the program gives a clear error if the file doesn't exist."""
    with pytest.raises(FileNotFoundError):
        load_study_log("this_file_does_not_exist.csv")

def test_load_missing_column_raises(tmp_path):
    """Ensures an error is raised if the CSV is missing crucial columns."""
    csv = tmp_path / "bad_log.csv"
    csv.write_text("date,subject\n2026-10-01,Math\n")
    with pytest.raises(ReportDataError) as exc_info:
        load_study_log(csv)
    assert "CSV is missing columns" in str(exc_info.value)

def test_load_cleans_whitespace_and_skips_invalid_rows(tmp_path):
    """Ensures spaces are stripped and negative time rows are filtered out."""
    csv = tmp_path / "dirt_log.csv"
    csv.write_text(
        "date,subject,duration_minutes,planned_minutes\n"
        "2026-10-01,  Biology  ,60,60\n"
        "2026-10-02,Chemistry,-10,60\n"
    )
    with pytest.warns(UserWarning):
        df = load_study_log(csv)

    assert len(df) == 1
    assert df.iloc[0]["subject"] == "Biology"

def test_load_filters_by_date_and_raises_if_empty(tmp_path):
    """Ensures the 'since' filter cuts off old dates and empty results crash gracefully."""
    csv = tmp_path / "dates.csv"
    csv.write_text(
        "date,subject,duration_minutes,planned_minutes\n"
        "2026-01-01,Math,60,60\n"
    )
    with pytest.raises(ReportDataError):
        load_study_log(csv, since=date(2026, 10, 1))

def test_summarise_by_subject_math():
    """Tests the math formulas: totals, variances and division by zero."""
    fake_df = pd.DataFrame({
        "subject": ["Math", "Math", "History"],
        "duration_minutes": [30, 60, 0],
        "planned_minutes": [60, 60, 0]
    })

    summary = summarise_by_subject(fake_df)

    assert summary.loc["Math", "actual_min"] == 90
    assert summary.loc["Math", "variance_min"] == -30
    assert summary.loc["Math", "completion"] == 0.75

    assert pd.isna(summary.loc["History", "completion"])

def test_fmt_duration():
    """Tests that minutes turn into beautiful 'Xh XXm' strings."""
    assert fmt_duration(0) == "0h 00m"
    assert fmt_duration(65) == "1h 05m"
    assert fmt_duration(-90) == "-1h 30m"

def test_build_text_report():
    """Verifies the text report builds matching header titles."""
    fake_df = pd.DataFrame  ({"date": [pd.Timestamp("2026-10-01")]})
    fake_summary = pd.DataFrame({
        "actual_min": [90],
        "planned_min": [60],
        "variance_min": [30],
        "completion": [1.5],
    }, index=["Math"])

    report = build_text_report(fake_df, fake_summary)
    assert "STUDY PERFORMANCE REPORT" in report
    assert "Math" in report
    assert "You studied 0h 30m more than planned!" in report

def test_charts_are_generated_without_crashing(tmp_path):
    """Ensures the charting functions generate actual image files."""
    fake_df = pd.DataFrame({
        "date": [pd.Timestamp("2026-10-01"), pd.Timestamp("2026-10-08")],
        "subject": ["Math", "Math"],
        "duration_minutes": [60, 120],
        "planned_minutes": [60, 60]
    })
    summary = summarise_by_subject(fake_df)

    chart1 = tmp_path / "chart1.png"
    chart2 = tmp_path / "chart2.png"

    plot_planned_vs_actual(summary, chart1)
    plot_weekly_trend(fake_df, chart2)

    assert chart1.exists()
    assert chart2.exists()