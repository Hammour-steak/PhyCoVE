"""CPU check of a native render folder against its native solve (no Blender).

    .venv-rigid-elastic/bin/python tools/verify_replay.py RENDER_DIR [--cache-dir DIR] [--write]

RENDER_DIR is a folder written by appearance/realism.py (render_replay.jsonl, ruler_render_binding.npz,
realism_provenance.json). For every receipt the ruler vertices are rebuilt from the rest geometry and the cached
centreline with the renderer's mapping and hashed (float32, as Blender stores them), and the coin matrices are
compared with T(x, 0, z) R_y(-pitch) of the cached state. --cache-dir defaults to the solve named in the
provenance. --write stores render_replay_audit.json in RENDER_DIR.
"""
from pathlib import Path
import argparse
import hashlib
import json

import numpy as np


def ruler_world(rest, curve, ss, z0):
    xxx = rest[:, 0]
    free = xxx >= 0
    xyz = rest.copy()
    xyz[:, 2] += z0
    theta = np.interp(xxx[free], ss, curve[:, 2])
    xyz[free, 0] = np.interp(xxx[free], ss, curve[:, 0]) - np.sin(theta) * rest[free, 2]
    xyz[free, 2] = np.interp(xxx[free], ss, curve[:, 1]) + np.cos(theta) * rest[free, 2]
    return xyz


def audit(folder, cache_dir=None, write=False, frames=96):
    folder = Path(folder)
    provenance = json.loads((folder / "realism_provenance.json").read_text())
    npz = Path(cache_dir) / "simulation.npz" if cache_dir else Path(provenance["native_cache"])
    cache = np.load(npz)
    binding = np.load(folder / "ruler_render_binding.npz")
    rests = [binding[k] for k in sorted((k for k in binding.files if k.startswith("rest_")), key=lambda k: int(k[5:]))]
    z0 = float(binding["midplane_z_m"])
    receipts = {}
    for line in (folder / "render_replay.jsonl").read_text().splitlines():
        entry = json.loads(line)
        if entry["definition_sha256"] == provenance["definition_sha256"]:
            receipts[entry["frame"]] = entry
    failures, worst = [], 0.0
    for f, entry in sorted(receipts.items()):
        i = f - 1
        if abs(entry["time_s"] - float(cache["times"][i])) > 1e-13:
            failures.append({"frame": f, "type": "time"})
        parts = [ruler_world(r, cache["beam_curves"][i], cache["arc_length"], z0).astype(np.float32).tobytes() for r in rests]
        if hashlib.sha256(b"".join(parts)).hexdigest() != entry["ruler_vertex_sha256"]:
            failures.append({"frame": f, "type": "ruler_mesh"})
        for b, matrix in enumerate(entry["coin_matrices"]):
            if not bool(cache["present"][b]):
                if matrix is not None:
                    failures.append({"frame": f, "type": "absent_coin_rendered", "coin": b})
                continue
            x, z, a = (float(v) for v in cache["coin_states"][i, b])
            c, s = np.cos(a), np.sin(a)
            expected = np.array([[c, 0, -s, x], [0, 1, 0, 0], [s, 0, c, z], [0, 0, 0, 1]])
            err = float(np.max(np.abs(np.array(matrix) - expected)))
            worst = max(worst, err)
            if err > 2e-6:
                failures.append({"frame": f, "type": "coin_matrix", "coin": b, "error": err})
    result = {"render_dir": str(folder), "native_cache": str(npz), "receipts": len(receipts),
              "all_frames": sorted(receipts) == list(range(1, frames + 1)), "max_coin_matrix_error": worst,
              "failures": failures}
    result["passed"] = result["all_frames"] and not failures
    if write:
        (folder / "render_replay_audit.json").write_text(json.dumps(result, indent=2) + "\n")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("render_dir", type=Path)
    p.add_argument("--cache-dir", type=Path)
    p.add_argument("--write", action="store_true")
    a = p.parse_args()
    r = audit(a.render_dir, a.cache_dir, a.write)
    print(json.dumps(r))
    raise SystemExit(0 if r["passed"] else 1)
