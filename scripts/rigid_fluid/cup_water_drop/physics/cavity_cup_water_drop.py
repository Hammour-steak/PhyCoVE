"""Measure the mug cavity and build the plate and napkin colliders.

usage: python cavity_cup_water_drop.py <geometry_dir>
- cavity.json (cup frame): inner floor, rim and outer bottom heights, and the inner wall radius every 0.5 mm of height
  (minimum and median over 72 rays cast outward from the cup axis). The simulation fills this cavity with the water
  lattice and counts the water in the cup with it; the surface step tells drops in the cup from drops outside.
- plate_collider.obj, napkin_collider.obj (world frame): the side plate (disk + ring) and the folded napkin where the
  renderer draws them (layout_cup_water_drop.py), each filled down to the table so fast drops cannot tunnel through.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import json
import sys
from pathlib import Path

import numpy as np
import trimesh

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import layout_cup_water_drop as layout  # noqa: E402

geom = Path(sys.argv[1])
m = trimesh.load(geom / "cup_local.obj", process=True)
lo, hi = m.bounds
floor = max(m.ray.intersects_location([[r, 0, hi[2] + 0.01]], [[0, 0, -1]])[0][:, 2].max() for r in (0.0, 0.006, 0.012))
zs = np.arange(floor + 0.0002, hi[2] - 0.0002, 0.0005)
ang = np.linspace(0, 2 * np.pi, 72, endpoint=False)
dirs = np.stack([np.cos(ang), np.sin(ang), np.zeros_like(ang)], 1)
prof = []
for z in zs:
    loc, idx, _ = m.ray.intersects_location(np.tile([0, 0, z], (72, 1)), dirs, multiple_hits=False)
    r = np.full(72, np.inf)
    r[idx] = np.hypot(loc[:, 0], loc[:, 1])
    prof.append((float(z), float(r.min()), float(np.median(r))))
json.dump({"inner_floor_z": float(floor), "rim_z": float(hi[2]), "outer_bottom_z": float(lo[2]),
           "profile_z_rmin_rmedian": np.round(prof, 6).tolist()}, open(geom / "cavity.json", "w"), indent=1)
print(f"cavity: floor {floor:.4f}, rim {hi[2]:.4f}, outer bottom {lo[2]:.4f}, {len(prof)} profile rows")

disk = trimesh.creation.cylinder(radius=layout.PLATE_RADIUS, height=layout.PLATE_TOP, sections=96)
disk.apply_translation([*layout.PLATE_XY, layout.PLATE_TOP / 2])
ring = trimesh.creation.torus(major_radius=layout.RING_MAJOR, minor_radius=layout.RING_MINOR, major_sections=64,
                              minor_sections=16)
ring.apply_translation([*layout.PLATE_XY, layout.RING_Z])
plate = trimesh.util.concatenate([disk, ring])
plate.export(geom / "plate_collider.obj")
nap = trimesh.creation.box(extents=[*layout.NAPKIN_SIZE, layout.NAPKIN_TOP])
nap.apply_transform(trimesh.transformations.rotation_matrix(np.radians(layout.NAPKIN_YAW_DEG), [0, 0, 1]))
nap.apply_translation([*layout.NAPKIN_XY, layout.NAPKIN_TOP / 2])
nap.export(geom / "napkin_collider.obj")
print("plate", np.round(plate.bounds, 3).tolist(), "napkin", np.round(nap.bounds, 3).tolist())
