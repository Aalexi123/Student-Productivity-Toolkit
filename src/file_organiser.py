from __future__ import annotations

import json
import os
import shutil
import tempfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable

DEFAULT_CATEGORIES = {
    "Documents": {".pdf", ".doc", ".docx", ".ppt", ".pptx", ".txt"},
    "Spreadsheets": {".csv", ".xls", ".xlsx"},
    "Images": {".png", ".jpg", ".jpeg", ".gif"},
    "Code": {".py", ".c", ".cpp", ".java", ".js", ".cs"},
    "Archives": {".zip", ".rar", ".7z"},
}
IGNORED_SUFFIXES = {".crdownload", ".part", ".tmp", ".download"}
LOG_NAME = ".organiser_log.json"

@dataclass(frozen=True)
class Move:
    source:Path
    destination: Path

    @property
    def category(self) -> str:
        return self.destination.parent.name
    
class SmartFileOrganiser:
    def __init__(self, categories: dict[str, set[str]] | None = None, log_filename: str | None = None):
        raw = categories or DEFAULT_CATEGORIES
        self.categories = {
            name: {"." + e.lstrip(".").lower() for e in exts}
            for name, exts in raw.items()
        }
        self.log_filename = log_filename or LOG_NAME

    # ---------- planning ----------
    def get_category(self, file_path: Path) -> str:
        ext = file_path.suffix.lower()
        for category, exts in self.categories.items():
            if ext in exts:
                return category
        return "Other"

    @staticmethod
    def _unique_path(dest: Path, reserved:set[Path] | None = None) -> Path:
        reserved = reserved or set()
        candidate, n = dest, 1
        while candidate.exists() or candidate in reserved:
            candidate = dest.with_name(f"{dest.stem}_{n}{dest.suffix}")
            n += 1
        return candidate

    @staticmethod
    def _validate(folder: Path) -> Path:
        folder = folder.expanduser().resolve()
        if not folder.is_dir():
            raise NotADirectoryError(f"Not a valid folder: {folder}")
        if folder == Path(folder.anchor) or folder == Path.home():
            raise ValueError(f"Refusing to organise {folder}; pick a subfolder.")
        return folder

    def get_unique_path(self, file_path: Path, reserved: set[Path] | None = None) -> Path:
        return self._unique_path(file_path, reserved)

    def organise_folder(self, folder: Path, dry_run: bool = False, confirm: bool | Callable[[Move], bool] | None = None) -> list[str]:
        folder = self._validate(folder)
        moves = self.plan(folder)
        if not moves:
            return []

        if dry_run:
            return [f"[PREVIEW] {m.source.name} -> {m.category}/{m.destination.name}" for m in moves]
        if isinstance(confirm, bool):
            confirm = (lambda _m: True) if confirm else (lambda _m: False)
        return self.execute(folder, moves, confirm)

    def plan(self, folder: Path) -> list[Move]:
        folder = self._validate(folder)
        moves, reserved = [], set()
        for f in sorted(folder.iterdir()):
            if (not f.is_file() or f.name == Path(self.log_filename).name
                     or f.suffix.lower() in IGNORED_SUFFIXES):
                continue
            dest = self._unique_path(folder / self.get_category(f) / f.name, reserved)
            reserved.add(dest)
            moves.append(Move(f, dest))
        return moves
    
    # ---------- executing ----------
    def execute(self, folder: Path, moves: list[Move],
                confirm: Callable[[Move], bool] | None = None) -> list[str]:
        folder = self._validate(folder)
        results, done = [], []
        for m in moves:
            if confirm and not confirm(m):
                results.append(f"[SKIPPED] {m.source.name}")
                continue
            try:
                m.destination.parent.mkdir(exist_ok=True)
                target = self._unique_path(m.destination)
                shutil.move(m.source, target)
                done.append({"original": str(m.source), "destination": str(target)})
                results.append(f"[MOVED] {m.source.name} -> {m.category}/{target.name}")
            except OSError as e:  # includes PermissionError
                results.append (f"[ERROR] {m.source.name}: {e}")
        if done:
            history = self._load_log(folder)
            history.append({"timestamp": datetime.now().isoformat(), "moves": done})
            self._save_log(folder, history)
        return results

    # ---------- undo ----------
    def undo_last(self, folder: Path) -> list[str]:
        folder = self._validate(folder)
        history = self._load_log(folder)
        if not history:
            return ["[UNDO] Nothing to undo."]
        batch, results, failed = history[-1], [], []
        for item in reversed(batch["moves"]):
            current, original = Path(item["destination"]), Path(item["original"])
            if not current.exists():
                results.append(f"[WARNING] {current.name} is no longer there.")
                continue
            try:
                target = self._unique_path(original)  # never overwrite
                shutil.move(current, target)
                results.append(f"[RESTORED] {target.name}")
            except OSError as e:
                failed.append(item)
                results.append(f"[ERROR] {current.name}: {e}")
        if failed:
            batch["moves"] = failed       # keep so the user can retry
        else:
            history.pop()
        self._save_log(folder, history)
        for d in {Path(i["destination"]).parent for i in batch["moves"]}:
            try: d.rmdir()                # only succeeds if empty
            except OSError: pass
        return results

    # ---------- log helpers ----------
    def _load_log(self, folder: Path) -> list[dict]:
        path = folder / self.log_filename
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save_log(self, folder: Path, data: list[dict]) -> None:
        fd, tmp = tempfile.mkstemp(dir=folder, suffix=".tmp")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, folder / self.log_filename)