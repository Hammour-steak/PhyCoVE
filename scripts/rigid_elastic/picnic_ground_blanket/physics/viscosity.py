"""Load the isolated native coupled constitutive extension."""
from pathlib import Path
import sys,json,hashlib,os
ROOT=Path(__file__).resolve().parents[4];B=Path(os.environ.get('PCVE_NATIVE_RUNTIME',str(ROOT/'tools/viscosity_plugin')))
sys.path.insert(0,str(B))
import pcve_viscosity as native
def apply_viscosity(mesh,eta,zeta,bending,disabled=False):
    if not disabled:native.apply_to(mesh,eta,zeta,bending)

def apply_static_preparation(mesh,inertia_scale,gravity):
    native.apply_static_preparation_to(mesh,inertia_scale,*map(float,gravity))
def viscosity_manifest():
    m=json.loads((B/'build_manifest.json').read_text())
    binary=Path(native.__file__)
    if hashlib.sha256(binary.read_bytes()).hexdigest()!=m['sha256']:raise ValueError('Native viscosity binary changed')
    return m
