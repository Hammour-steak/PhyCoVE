"""Measure the mug cavity and build the solid saucer collider from the exported geometry.

usage: python cavity_coffee_ice_drop.py <geometry_dir>
- cavity.json: inner floor height, rim height and the inner wall radius every 0.5 mm of height (minimum over 72 rays
  cast outward from the cup axis). The simulation fills this cavity with a rest-density particle lattice, builds the ice's
  hidden collision floor from it, and the surface step uses it to tell drops inside the cup from drops outside.
- saucer_solid.obj: the saucer as a solid of revolution from the table up to its measured top surface. The real plate is
  2-3 mm thick and fast drops tunnelled through its SDF; drops can never be under a saucer anyway.
"""
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

geom = Path(sys.argv[1])
TABLE_Z = json.load(open(geom / "geom_info.json"))["Plane.049"]["hi"][2]   # top of the stage's table
cup = trimesh.load(geom / "cup_world.obj", process=True)
lo, hi = cup.bounds
floor = max(cup.ray.intersects_location([[r, 0, hi[2] + 0.01]], [[0, 0, -1]])[0][:, 2].max() for r in (0.0, 0.004, 0.008))
zs = np.arange(floor + 0.0002, hi[2] - 0.0002, 0.0005)
angles = np.linspace(0, 2 * np.pi, 72, endpoint=False)
dirs = np.stack([np.cos(angles), np.sin(angles), np.zeros_like(angles)], 1)
prof = []
for z in zs:
    loc, idx, _ = cup.ray.intersects_location(np.tile([0, 0, z], (len(angles), 1)), dirs, multiple_hits=False)
    r = np.full(len(angles), np.inf)
    r[idx] = np.hypot(loc[:, 0], loc[:, 1])
    prof.append((float(z), float(r.min()), float(np.median(r))))
json.dump({"inner_floor_z": float(floor), "rim_z": float(hi[2]), "profile_z_rmin_rmedian": np.round(prof, 5).tolist()},
          open(geom / "cavity.json", "w"), indent=1)
print(f"cavity: floor {floor:.4f}, rim {hi[2]:.4f}, {len(prof)} profile rows")

s = trimesh.load(geom / "saucer_world.obj")
c = np.array([(s.bounds[0, 0] + s.bounds[1, 0]) / 2, (s.bounds[0, 1] + s.bounds[1, 1]) / 2])
R = float(np.hypot(s.vertices[:, 0] - c[0], s.vertices[:, 1] - c[1]).max())
top = []
for r in np.linspace(0, R - 0.0005, 60):
    zs_ = []
    for a in np.linspace(0, 2 * np.pi, 12, endpoint=False):
        loc, _, _ = s.ray.intersects_location([[c[0] + r * np.cos(a), c[1] + r * np.sin(a), 0.95]], [[0, 0, -1]])
        if len(loc):
            zs_.append(loc[:, 2].max())
    top.append((r, np.median(zs_) if zs_ else TABLE_Z + 0.001))
ring = np.concatenate([[[0.0, TABLE_Z - 0.002]], [[R, TABLE_Z - 0.002]], np.array(top)[::-1]])
solid = trimesh.creation.revolve(ring[::-1], sections=128)
solid.apply_translation([c[0], c[1], 0])
trimesh.repair.fix_normals(solid)
solid.export(geom / "saucer_solid.obj")
print(f"saucer solid: centre {np.round(c, 4).tolist()}, radius {R:.4f}, watertight {solid.is_watertight}")
