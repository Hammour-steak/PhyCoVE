"""Prepare the porcelain vase: install transform of the Poly Haven scan and its hollow IPC collision shell.

Run in Blender (reads the glTF), e.g.
    blender -b --factory-startup --python tools/prepare_vase.py -- --out assets/scenes/curtain_doraemon_drape/porcelain_vase
The scan (antique_ceramic_vase_01, CC0) is a surface of revolution sampled in rings of 49 vertices. The
collider revolves the measured outer ring radii (96 segments, so it encloses the 49-gon by <= 0.2 mm), keeps
the open mouth and the scanned inner wall (inscribed) down to a flat inner floor: cloth can sag into the mouth and never
crosses the visible glaze. Uniform scale only (real proportions), height 0.32 m.
"""
import bpy, hashlib, json, sys
from pathlib import Path
import numpy as np

args = sys.argv[sys.argv.index('--') + 1:]
out = Path(args[args.index('--out') + 1]); out.mkdir(parents=True, exist_ok=True)
REPO = Path(args[args.index('--repo') + 1]) if '--repo' in args else Path(__file__).resolve().parents[4]
SRC = REPO / 'assets/polyhaven/antique_ceramic_vase_01/antique_ceramic_vase_01_2k.gltf'
HEIGHT, SEGMENTS, FLOOR = .32, 96, .012  # FLOOR: lowest inner ring kept (inner bottom of the scan above it is flattened)

bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=str(SRC))
obs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
bpy.context.view_layer.update()
V = np.concatenate([np.array([o.matrix_world @ v.co for v in o.data.vertices]) for o in obs])
N = np.concatenate([np.array([(o.matrix_world.to_3x3() @ v.normal).normalized() for v in o.data.vertices]) for o in obs])
lo, hi = V.min(0), V.max(0)
centre = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
scale = HEIGHT / (hi[2] - lo[2])
P = (V - centre) * scale
r = np.hypot(P[:, 0], P[:, 1]); z = P[:, 2]
# Outer glaze only: the scan also models the inner wall, whose normals point towards the axis.
radial = (P[:, 0] * N[:, 0] + P[:, 1] * N[:, 1]) / np.maximum(r, 1e-9)
outer = radial > .3
ri, zi = r[radial < -.3], z[radial < -.3]  # inner wall
r, z = r[outer], z[outer]
# Rings: cluster vertex heights (rings are exact horizontal loops in the scan).
levels = np.unique(np.round(z, 5))
rings = []
for zz in levels:
    m = np.abs(z - zz) < 2e-5
    near = np.abs(z - zz) < 2.5e-3  # envelope: the widest outer glaze within 2.5 mm of the ring
    rings.append((float(zz), float(max(r[m].max(), r[near].max()))))
# keep the outer envelope only: drop interior rings whose rmax is below the outer silhouette at that height
rings = sorted(rings)
zs = np.array([a for a, b in rings]); rs = np.array([b for a, b in rings])
# merge levels closer than 0.3 mm (take max radius)
merged = []
for zz, rr in zip(zs, rs):
    if merged and zz - merged[-1][0] < 3e-4: merged[-1] = (merged[-1][0], max(merged[-1][1], rr))
    else: merged.append((zz, rr))
zs = np.array([a for a, b in merged]); rs = np.array([b for a, b in merged])
outer_r = rs / np.cos(np.pi / SEGMENTS) / np.cos(np.pi / 49) * 1.0  # circumscribe the scan polygon
zs[0] = 0.; zs[-1] = HEIGHT
theta = np.arange(SEGMENTS) * 2 * np.pi / SEGMENTS
ring = lambda rad, zz: np.stack([rad * np.cos(theta), rad * np.sin(theta), np.full(SEGMENTS, zz)], 1)
# Inner wall from the scan's inward-facing rings, inscribed (collider never outside the visible inner glaze).
inner = []
for zz in np.unique(np.round(zi, 5)):
    near = np.abs(zi - zz) < 2.5e-3
    inner.append((float(ri[near].min() * np.cos(np.pi / 49)), float(zz)))
inner = [(a, b) for a, b in inner if b >= FLOOR and b < HEIGHT - 1e-4]
merged = []
for a, b in sorted(inner, key=lambda t: t[1]):
    if merged and b - merged[-1][1] < 3e-4: merged[-1] = (min(merged[-1][0], a), merged[-1][1])
    else: merged.append((a, b))
inner = merged
FLOOR = inner[0][1]
profile = [(rr, zz) for zz, rr in zip(zs, outer_r)] + inner[::-1]
verts = np.concatenate([ring(rr, zz) for rr, zz in profile])
verts = np.concatenate([verts, [[0, 0, 0], [0, 0, FLOOR]]])
nring = len(profile); faces = []
for k in range(nring - 1):
    for i in range(SEGMENTS):
        j = (i + 1) % SEGMENTS; a = k * SEGMENTS + i; b = k * SEGMENTS + j; c = (k + 1) * SEGMENTS + j; d = (k + 1) * SEGMENTS + i
        faces += [(a, c, b), (a, d, c)]
bottom, floor = nring * SEGMENTS, nring * SEGMENTS + 1
last = (nring - 1) * SEGMENTS
for i in range(SEGMENTS):
    j = (i + 1) % SEGMENTS
    faces += [(bottom, i, j), (floor, last + j, last + i)]
faces = np.asarray(faces, np.int32)[:, ::-1].copy()  # outward normals
np.savez_compressed(out / 'collision.npz', vertices=verts, faces=faces)
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
(out / 'preparation.json').write_text(json.dumps(dict(
    source='https://polyhaven.com/a/antique_ceramic_vase_01', license='CC0', author='James Ray Cock',
    source_files={p.name: sha(p) for p in sorted(SRC.parent.rglob('*')) if p.is_file()},
    install=dict(scale=scale, source_centre_m=centre.tolist(), height_m=HEIGHT,
                 note='visual = (scan_world - source_centre) * scale; figurine-local frame, origin at the foot centre, +Z up'),
    collider=dict(kind="hollow surface of revolution", segments=SEGMENTS, inner_floor_m=FLOOR, inner_profile_r_z=[[a, b] for a, b in inner],
                  outer_profile_r_z=[[float(a), float(b)] for a, b in zip(outer_r, zs)],
                  max_radius_m=float(outer_r.max()), mouth_outer_radius_m=float(outer_r[-1]),
                  vertices=int(len(verts)), faces=int(len(faces)), sha256=sha(out / 'collision.npz'))), indent=1) + '\n')
print('PREPARED', out, 'scale', scale, 'rings', nring, 'max r', outer_r.max())
