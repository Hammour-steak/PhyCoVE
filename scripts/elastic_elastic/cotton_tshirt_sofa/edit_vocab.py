"""Expose the strict edit vocabulary of tools/native/edit_vocab.py at the scene root."""
import importlib.util
import sys
from pathlib import Path

source = Path(__file__).resolve().parent / "tools/native"
sys.path.insert(0, str(source))
spec = importlib.util.spec_from_file_location("cotton_tshirt_sofa_native_edit_vocab", source/"edit_vocab.py")
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
VOCAB = module.VOCAB
