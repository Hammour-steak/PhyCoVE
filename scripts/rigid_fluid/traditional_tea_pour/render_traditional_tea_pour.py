"""Render a Genesis tea case in Blender (appearance/render_tea_contact.py on the prepared native scene)."""
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import runpy
import sys
HERE=Path(__file__).resolve().parent

def main():
    target=HERE/'appearance/render_tea_contact.py'
    sys.path.insert(0,str(target.parent))
    sys.argv[0]=str(target)
    runpy.run_path(str(target),run_name='__main__')

if __name__=='__main__':main()
