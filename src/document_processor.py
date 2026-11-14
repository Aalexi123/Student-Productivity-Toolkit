from __future__ import annotations

import re
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable

MAX_FILE_BYTES = 50 * 1024 * 1024

class DocumentError(Exception):
    """Base class for expected, reportable problems with a document."""

class UnsupportedFormatError(DocumentError): pass
class EncryptedDocumentError(DocumentError): pass
class EmptyDocumentError(DocumentError): pass
class UnreadableDocumentError(DocumentError): pass

_PATTERNS = [
    ("secret", re.compile(
        r"(?i)\b((?:api[_-]?key|token|secret|password)\s*[=:]\s*)[\w\-./+=]{8,}"),
     r"\1[REDACTED_SECRET]"),
    ("email", re.compile(r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b"),
     "[REDACTED_EMAIL]"),
    # (555) 123-4567 / 555-123-4567 / +1 555 123 4567 (separators required: avoids bare IDs)
    ("phone", re.compile(
        r"(?<!\w)(?:\+\d{1,3}[\s.-]?)?(?:\(\d{3}\)|\d{3})[\s.-]\d{3}[\s.-]\d{4}(?!\w)"),
     "[REDACTED_PHONE]"),
    # country code + 8-digit local number, e.g. +CC 1234 5678
    ("phone", re.compile(r"(?<!\w)\+\d{1,3}[\s.-]?\d{4}[\s.-]?\d{4}(?!\w)"),
     "[REDACTED_PHONE]"),
]

def mask_sensitive_data(text: str) -> tuple[str, dict[str, int]]:
    counts:  dict[str, int] = {}
    for kind, pattern, replacement in _PATTERNS:
        text, n = pattern.subn(replacement, text)
        if n:
            counts[kind] = counts.get(kind, 0) + n
    return text, counts

def _read_txt(path: Path) -> str:
    raw = path.read_bytes()
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")

def _read_pdf(path: Path) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError

    try:
        reader = PdfReader(str(path))
        if reader.is_encrypted and not reader.decrypt(""):
            raise EncryptedDocumentError("PDF is password-protected.")
        return "\n".join(page.extract_text() or "" for page in reader.pages)
    except PdfReadError as e:
        raise UnreadableDocumentError(f"Could not read PDF: {e}") from e

def _read_docx(path: Path) -> str:
    from docx import Document
    from docx.opc.exceptions import PackageNotFoundError
    from docx.table import Table

    try:
        doc = Document(str(path))
    except (PackageNotFoundError, zipfile.BadZipFile, KeyError) as e:
        raise UnreadableDocumentError(f"Could not read DOCX (corrupted?): {e}") from e

    parts = []
    for block in doc.iter_inner_content():  # python-docx >= 1.0: document order
        if isinstance(block, Table):
            for row in block.rows:
                seen, cells = set(), []
                for cell in row.cells:
                    if cell._tc in seen:  # merged cells repeat
                        continue
                    seen.add(cell._tc)
                    if cell.text.strip():
                        cells.append(cell.text.strip())
                if cells:
                    parts.append(" | ".join(cells))
        elif block.text.strip():
            parts.append(block.text)
    return "\n".join(parts)

EXTRACTORS: dict[str, Callable[[Path], str]] = {
    ".txt": _read_txt,
    ".md": _read_txt,
    ".pdf": _read_pdf,
    ".docx": _read_docx,
}
SUPPORTED_SUFFIXES = set(EXTRACTORS) | {".csv"}

def extract_text(path: Path, mask_privacy: bool = True) -> tuple[str, dict[str, int]]:
    suffix = path.suffix.lower()
    extractor = EXTRACTORS.get(suffix)
    if extractor is None:
        raise UnsupportedFormatError(f"Unsupported document format: {suffix or '(none)'}")
    if path.stat().st_size > MAX_FILE_BYTES:
        raise UnreadableDocumentError(f"File is larger than {MAX_FILE_BYTES // 2**20} MB.")

    text = extractor(path)
    if not text.strip():
        hint = " It may be a scanned document (needs OCR)." if suffix == ".pdf" else ""
        raise EmptyDocumentError(f"No extractable text found.{hint}")
    return mask_sensitive_data(text) if mask_privacy else (text, {})

STOPWORDS = frozenset(
    "the and for are but not you all can had her was one our out has have been "
    "were they this that with from will would there their what about which when "
    "your said each she how its into than them these some could other then".split()
)

def text_stats(text: str) -> dict:
    words = text.split()
    keywords = Counter(
        w for w in re.findall(r"[a-z][a-z'-]{2,}", text.lower()) if w not in STOPWORDS
    ).most_common(10)
    return {
        "characters": len(text),
        "words": len(words),
        "lines": len(text.splitlines()),
        "reading_minutes": max(1, round(len(words) / 230)),
        "keywords": keywords,
    }

def summarise_csv(path: Path) -> str:
    import pandas as pd
    
    try:
        df = pd.read_csv(path, encoding_errors="replace")
    except pd.errors.EmptyDataError as e:
        raise EmptyDocumentError("The CSV file is empty.") from e
    except pd.errors.ParserError as e:
        raise UnreadableDocumentError(f"Could not parse CSV: {e}") from e

    missing = df.isna().sum()
    missing = missing[missing > 0]
    numeric = df.select_dtypes("number")
    lines = [
        f"Rows: {len(df):,}   Columns: {len(df.columns)}",
        "",
        "Column types:",
        df.dtypes.astype(str).to_string(),
        "",
        "Missing values:",
        missing.to_string() if not missing.empty else "None",
    ]
    if not numeric.empty:
        lines += ["", "Numeric summary:", numeric.describe().round(2).T.to_string()]
    return "\n".join(lines)

def truncate_at_boundary(text: str, limit: int) -> tuple[str, bool]:
    if len(text) <= limit:
        return text, False
    return text[:limit].rsplit(None, 1)[0] + "\n\n... [TRUNCATED] ...", True

@dataclass
class DocumentResult:
    source: Path
    kind: str
    body: str
    stats: dict = field(default_factory=dict)
    truncated: bool = False
    masked: bool = True
    redactions: dict[str, int] = field(default_factory=dict)

    def to_report(self) -> str:
        lines = [f"=== {self.kind.upper()} DOCUMENT REPORT ===", f"Document: {self.source.name}"]
        if self.kind == "text":
            s = self.stats
            lines += [
                f"Words: {s['words']:,} | Characters: {s['characters']:,} | Lines: {s['lines']:,}",
                f"Reading time: ~{s['reading_minutes']} min",
            ]
            if s["keywords"]:
                lines.append("Top terms: " + ", ".join(f"{w} ({c})" for w, c in s["keywords"]))
            redacted = ", ".join(f"{n} {k}" for k, n in self.redactions.items()) or "nothing found"
            lines.append(f"Privacy masking: {'ON (' + redacted + ')' if self.masked else 'OFF'}")
            lines.append(f"Preview truncated: {self.truncated}")
            lines += ["", "Preview:"]
        lines += [self.body]
        return "\n".join(lines) + "\n"

def analyse_document(file_path: str | Path, max_preview_chars: int = 5000,
                     mask_privacy: bool = True) -> DocumentResult:
    path = Path(file_path).expanduser().resolve(strict=False)
    if not path.is_file():
        raise FileNotFoundError(f"File not found: {path}")

    if path.suffix.lower() == ".csv":
        return DocumentResult(path, "csv", summarise_csv(path), masked=False)

    text, redactions = extract_text(path, mask_privacy)
    preview, truncated = truncate_at_boundary(text, max_preview_chars)
    return DocumentResult(path, "text", preview, text_stats(text), truncated,
                          mask_privacy, redactions)

def _unique_path(path: Path) -> Path:
    candidate, n = path, 1
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_{n}{path.suffix}")
        n += 1
    return candidate

def save_report(result: DocumentResult, output_dir: str | Path) -> Path:
    out = Path(output_dir).expanduser()
    out.mkdir(parents=True, exist_ok=True)
    name = f"{result.source.stem}_{result.source.suffix.lstrip('.')}_report.txt"
    report_path = _unique_path(out / name)
    report_path.write_text(result.to_report(), encoding="utf-8")
    return report_path

def process_document(file_path: str | Path, output_dir: str | Path,
                     max_output_chars: int = 5000, mask_privacy: bool = True) -> Path:
    "Same entry point as before."
    return save_report(analyse_document(file_path, max_output_chars, mask_privacy), output_dir)

def process_folder(folder: str | Path, output_dir: str | Path,
                   **kwargs) -> tuple[list[Path], dict[str, str]]:
    """One bad file doesn't stop the batch; failures are returned by filename."""
    reports, failures = [], {}
    for f in sorted(Path(folder).expanduser().iterdir()):
        if not f.is_file() or f.name.startswith(".") or f.suffix.lower() not in SUPPORTED_SUFFIXES:
            continue
        try:
            reports.append(save_report(analyse_document(f, **kwargs), output_dir))
        except (DocumentError, FileNotFoundError) as e:
            failures[f.name] = str(e)
    return reports, failures