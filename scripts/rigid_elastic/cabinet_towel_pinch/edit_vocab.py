"""Load the scene's edit vocabulary (physics/edit_vocab.py) with the shared strict policy."""
from pathlib import Path
import importlib.util
import sys

directory = Path(__file__).resolve().parent / "physics"
sys.path.insert(0, str(directory))
spec = importlib.util.spec_from_file_location("pcve_scene_vocabulary", directory / "edit_vocab.py")
vocab = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vocab)
VOCAB = vocab.VOCAB
