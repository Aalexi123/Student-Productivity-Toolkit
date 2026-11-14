from pathlib import Path
import pytest
from src.file_organiser import SmartFileOrganiser

@pytest.fixture
def organiser(tmp_path):
    return SmartFileOrganiser(log_filename=str(tmp_path / "organiser_log.json"))

def test_get_unique_path(tmp_path, organiser):
    file_a = tmp_path / "report.pdf"
    file_a.touch()

    unique_path = organiser.get_unique_path(file_a)
    assert unique_path.name == "report_1.pdf"

    unique_path.touch()
    next_unique_path = organiser.get_unique_path(file_a)
    assert next_unique_path.name == "report_2.pdf"

def test_organise_folder_dry_run(tmp_path, organiser):
    (tmp_path / "notes.txt").touch()
    (tmp_path / "script.py").touch()

    actions = organiser.organise_folder(tmp_path, dry_run=True)

    assert (tmp_path / "notes.txt").exists()
    assert (tmp_path / "script.py").exists()
    assert len(actions) == 2
    assert any("[PREVIEW]" in action for action in actions)

def test_duplicate_filename_never_overwrites(tmp_path, organiser):
    docs_folder = tmp_path / "Documents"
    docs_folder.mkdir()
    (docs_folder / "note.txt").write_text("existing content")

    (tmp_path / "note.txt").write_text("new content")

    organiser.organise_folder(tmp_path, dry_run=False, confirm=True)

    assert (docs_folder / "note.txt").read_text() == "existing content"
    assert (docs_folder / "note_1.txt").read_text() == "new content"

def test_organise_folder_rejects_files_when_confirmation_is_false(tmp_path, organiser):
    source = tmp_path / "notes.txt"
    source.write_text("keep me")

    actions = organiser.organise_folder(tmp_path, confirm=False)

    assert actions == ["[SKIPPED] notes.txt"]
    assert source.read_text() == "keep me"

def test_execute_records_moves_and_undo_restores_them(tmp_path, organiser):
    source = tmp_path / "notes.txt"
    source.write_text("study notes")
    moves = organiser.plan(tmp_path)

    actions = organiser.execute(tmp_path, moves)

    moved = tmp_path / "Documents" / "notes.txt"
    assert actions == ["[MOVED] notes.txt -> Documents/notes.txt"]
    assert moved.read_text() == "study notes"
    assert organiser.undo_last(tmp_path) == ["[RESTORED] notes.txt"]
    assert source.read_text() == "study notes"
    assert not moved.exists()

def test_organise_folder_can_be_undone(tmp_path, organiser):
    (tmp_path / "notes.txt").write_text("study notes")
    organiser.organise_folder(tmp_path, confirm=True)
    
    assert (tmp_path / "Documents" / "notes.txt").exists()
    assert organiser.undo_last(tmp_path) == ["[RESTORED] notes.txt"]
    assert (tmp_path / "notes.txt").read_text() == "study notes"