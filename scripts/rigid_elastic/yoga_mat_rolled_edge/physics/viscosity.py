"""Load the already-audited remote native shell-viscosity extension."""
from pathlib import Path
import hashlib
import json
import os
import sys

ROOT = Path(__file__).resolve().parents[4]
if str(ROOT / "scripts") not in sys.path:
    sys.path.append(str(ROOT / "scripts"))
from pcve_assets import asset

# The scene's registered build of the extension; simulate_yoga_mat_rolled_edge.py passes the same folder.
PLUGIN = Path(os.environ.get("PCVE_VISCOSITY_PLUGIN") or asset("scenes/yoga_mat_rolled_edge/native"))
sys.path.insert(0, str(PLUGIN))
import pcve_viscosity as native  # module name fixed by the compiled extension


def apply_viscosity(mesh, shear, bulk, bending):
    native.apply_to(mesh, float(shear), float(bulk), float(bending))


def manifest():
    data = json.loads((PLUGIN / "build_manifest.json").read_text(encoding="utf-8"))
    binary = Path(native.__file__)
    if hashlib.sha256(binary.read_bytes()).hexdigest() != data["sha256"]:
        raise RuntimeError("remote native viscosity extension differs from its frozen manifest")
    data["loaded_module"] = str(binary.resolve())
    return data
