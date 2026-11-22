"""Edit vocabulary of the scene, re-exported from physics/vocab.py (VOCAB, CASES, resolve)."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent/'physics'))
from vocab import VOCAB, CASES, resolve

__all__ = ['VOCAB', 'CASES', 'resolve']
