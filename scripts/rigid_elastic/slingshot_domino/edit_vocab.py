"""Public vocabulary shared with the scene's native solver."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent / "physics"))
from vocabulary import VOCAB, resolve
from config import BASE, CASE_ID, EDITS, CAT

__all__ = ["VOCAB", "resolve", "BASE", "CASE_ID", "EDITS", "CAT"]
