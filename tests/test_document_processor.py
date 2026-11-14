import pytest
import shutil
from pathlib import Path
import pandas as pd

from src.document_processor import (
    analyse_document,
    process_folder,
    DocumentError,
    EmptyDocumentError
)

@pytest.fixture
def test_env(tmp_path):
    """
    A pytest fixture that provides a clean, isolated temporary director
    for every individual test run. Pytest handles the cleanup automatically.
    """
    sandbox_dir = tmp_path / "test_sandbox"
    output_dir = tmp_path / "test_reports"
    sandbox_dir.mkdir()
    output_dir.mkdir()

    md_content = (
        "# Project Notes\n\n"
        "Staging credentials: api-key = x8923-jsdklf92348-secret\n"
        "Reach out at support@example.com or phone: 555-019-2834.\n"
        "Keyword frequency metrics: analysis, python, token, parsing, analysis."
    )
    (sandbox_dir / "notes.md").write_text(md_content, encoding="utf-8")

    csv_content = (
        "student_id,grade,attendance\n"
        "101,92.5,0.98\n"
        "102,,0.85\n"
        "103,88.0,0.90\n"
    )
    (sandbox_dir / "grades.csv").write_text(csv_content, encoding="utf-8")

    empty_f = sandbox_dir / "empty_file.txt"
    empty_f.write_text("", encoding="utf-8")
    
    assert empty_f.exists()

    (sandbox_dir / "holiday_photo.png").write_text("fake_binary_image_data", encoding="utf-8")

    return sandbox_dir, output_dir

def test_privacy_masking_and_statistics(test_env):
    """TEST 1: Validates regex pattern captures and text metadata extraction calculations."""
    sandbox, _ = test_env
    file_path = sandbox / "notes.md"

    res = analyse_document(file_path, mask_privacy=True)

    assert "[REDACTED_SECRET]" in res.body
    assert "[REDACTED_EMAIL]" in res.body
    assert "[REDACTED_PHONE]" in res.body

    assert res.stats["words"] > 0
    assert res.stats["characters"] > 0
    assert any(word == "analysis" for word, _ in res.stats["keywords"])

def test_spreadsheet_summary_profiling(test_env):
    """TEST 2: Verifies pandas data parsing matrices and descriptive metric generations."""
    sandbox, _ = test_env
    file_path = sandbox / "grades.csv"

    res = analyse_document(file_path)

    assert res.kind == "csv"
    assert "Rows: 3" in res.body
    assert "Columns: 3" in res.body
    assert "Missing values:" in res.body
    assert "attendance" in res.body

def test_empty_document_exception_handling(test_env):
    """TEST 3: Assures empty file structures trigger custom application alerts."""
    sandbox, _ = test_env
    file_path = sandbox / "empty_file.txt"

    with pytest.raises(EmptyDocumentError):
        analyse_document(file_path)

def test_batch_folder_processing_filters(test_env):
    """TEST 4: Evaluates directory routing maps, file skips and crash isolations."""
    sandbox, out_dir = test_env

    reports, failures = process_folder(sandbox, out_dir, mask_privacy=True)

    assert len(reports) == 2
    assert "empty_file.txt" in failures
    assert "holiday_photo.png" not in failures

    for report_path in reports:
        assert report_path.is_file()
        assert report_path.suffix == ".txt"