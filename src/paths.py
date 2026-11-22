"""Default locations, anchored to the project folder so they don't depend on where you run from."""
from pathlib import Path
import os
import sys

if getattr(sys, "frozen", False):
    PROJECT_ROOT = Path(sys.executable).resolve().parent
else:
    PROJECT_ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = PROJECT_ROOT / "data"
REPORTS_DIR = PROJECT_ROOT / "reports"

DEFAULT_LOG = DATA_DIR / "study_log.csv"
DEFAULT_ASSIGNMENTS_CSV = DATA_DIR / "assignments.csv"
DEFAULT_ESTIMATES_CSV = DATA_DIR / "estimates.csv"
DEFAULT_PLAN = REPORTS_DIR / "study_plan.csv"

def resource_path(relative_path: str) -> str:
    base_path = getattr(sys, "_MEIPASS", os.path.abspath("."))
    return os.path.join(base_path, relative_path)