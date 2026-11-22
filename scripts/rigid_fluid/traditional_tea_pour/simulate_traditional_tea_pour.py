"""Run the existing Genesis tea/contact solve using its idle-GPU launcher."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import argparse
import subprocess
import sys
HERE=Path(__file__).resolve().parent
PHYSICS=HERE/'physics'

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('case',type=Path)
    p.add_argument('--skin',type=float,default=0.0005208333472364128)
    a=p.parse_args()
    subprocess.run([sys.executable,str(PHYSICS/'launch_tea_contact.py'),str(a.case),'--skin',str(a.skin)],check=True)

if __name__=='__main__':main()
