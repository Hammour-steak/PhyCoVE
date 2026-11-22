"""PCVE toy-car source and five native-physics counterfactuals."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=='__main__':
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/'pcve_scene_entry.py').is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,'build_pcve')
# PCVE_UNIFIED_ENTRY_END
from counterfactual_suite import main

if __name__=='__main__':main()
