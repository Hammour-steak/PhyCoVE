"""Canonical simulate entry for the horizontal spring pendulum scene."""

import sys
from pathlib import Path

if __name__ == "__main__":
    # PCVE_UNIFIED_ENTRY_BEGIN
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry

    prepare_entry(__file__, "simulate")
    # PCVE_UNIFIED_ENTRY_END
    from model.simulation import main

    main()
