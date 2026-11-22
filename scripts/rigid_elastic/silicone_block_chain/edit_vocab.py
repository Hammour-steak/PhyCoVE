"""Native case IDs, edit DSL and the DSL-to-solver bindings of this scene (owned by physics/config.py)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent / "physics"))
from config import CASE_DSL, TIMED_DSL, VOCAB  # noqa: E402,F401
