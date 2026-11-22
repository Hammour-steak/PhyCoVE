"""Exit 3 if the boat's hull came within 2 cm of the pool wall in any frame (the base must glide free).

Usage: .venv-genesis-mpm-sph/bin/python check_wall_toy_boat_pool_glide.py <run dir>
"""
import json, sys
import numpy as np
from pathlib import Path
run = Path(sys.argv[1])
rep = json.loads((run / "simulation_report.json").read_text())
if rep["physics"].get("boat_presence", [1]) == [0]:
    print("WALL no boat in this case")
    sys.exit(0)
root = Path(__file__).resolve().parents[4]  # repository root (scripts/rigid_fluid/<scene>/physics/)
pool = json.loads((root / rep["physics"]["pool_profile"]).read_text())
prof = np.array(pool["inner_wall_profile_z_r_m"])
wall = float(np.interp(pool["authored_water_z_m"], prof[:, 0], prof[:, 1]))
import trimesh
hull = trimesh.load(root / rep["physics"]["boat_collider"], force="mesh").vertices
worst = 1e9
for row in rep["frames"]:
    if not row.get("boat_active", True):
        continue
    w, x, y, z = row["boat_quat_wxyz"]
    R = np.array([[1-2*(y*y+z*z), 2*(x*y-z*w), 2*(x*z+y*w)], [2*(x*y+z*w), 1-2*(x*x+z*z), 2*(y*z-x*w)], [2*(x*z-y*w), 2*(y*z+x*w), 1-2*(x*x+y*y)]])
    pts = hull @ R.T + np.array(row["boat_pos"])
    gap = wall - np.hypot(pts[:, 0], pts[:, 1]).max()
    worst = min(worst, gap)
    last = row["boat_pos"]
print("WALL radius %.3f  closest hull gap %.3f m  final boat %s" % (wall, worst, np.round(last, 3).tolist()))
sys.exit(0 if worst > 0.02 else 3)
