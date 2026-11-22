"""Check/export a case's registered native solver cache.

--stage verify (default): check the registered cache of --case against assets.json and its exact
  sample clock (--window 4s: the 0-4 s 240 Hz cache the videos are rendered from; --window 3s: the
  accepted 0-3 s reference cache it was compared with); with --out-root, copy it there.
The 0-4 s caches come from re-running each case's original solver from t = 0 with every physical
setting unchanged; the solver producers and their inputs are not part of this repository, so the
registered caches are the reproduction inputs.
"""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
    from pcve_scene_entry import prepare_entry
    prepare_entry(__file__, "simulate")
# PCVE_UNIFIED_ENTRY_END
from pathlib import Path
import argparse
import json

from tools.scene_common import CASE_IDS, copy_verified, native_cache

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--case", choices=CASE_IDS, default="source")
    parser.add_argument("--stage", choices=("verify",), default="verify")
    parser.add_argument("--window", choices=("4s", "3s"), default="4s")
    parser.add_argument("--out", type=Path, help="Export directory")
    args = parser.parse_args()
    state, times, digest = native_cache(args.case, args.window)
    if args.out:
        copy_verified(state, args.out / args.case / state.name)
    print(json.dumps({"case_id": args.case, "window": args.window, "native_cache": str(state), "sha256": digest,
                      "states": len(times), "rate_hz": round(1 / (times[1] - times[0])),
                      "physical_window_s": [times[0], times[-1]]}))
