"""Water surface per frame for render_tilted_cup_table_pour.py: <run>/meshes_1mm/water_####.npz (vertices, triangles,
normals, velocity) and <run>/wetmap/wet_####.npz (where the oak is wet). The tabletop water is meshed as a continuous
film (film_tilted_cup_table_pour.py); the rest (cup water, stream, drops) with pysplashsurf, trimmed where it dips into
the film and sealed onto the ceramic and the table (no air gap under the water). Isolated single particles are not
meshed; particles whose motion within +-6 frames stays below 0.4 mm are meshed at their window mean (blended out by
1.0 mm), so the resting puddle does not shimmer.
usage: python surface_tilted_cup_table_pour.py <run_dir> [--close-radius M] [frame ...]   (frames 1-based; all by default)"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
import json, sys, time
from pathlib import Path
import numpy as np
import pysplashsurf
from scipy.spatial import cKDTree
import math
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import film_tilted_cup_table_pour as film_tilt
from scipy import ndimage
from contact_geometry import SUPPORT_CENTER_X, SUPPORT_SIZE, CUP_CENTER_Z, CUP_TILT_DEG, CUP_INNER_RADIUS as RI, CUP_OUTER_RADIUS as RO, CUP_HEIGHT, CUP_BOTTOM_THICKNESS
_a = math.radians(CUP_TILT_DEG)
ROT = np.array([[math.cos(_a), 0, math.sin(_a)], [0, 1, 0], [-math.sin(_a), 0, math.cos(_a)]]); CC = np.array([0, 0, CUP_CENTER_Z])
H2 = CUP_HEIGHT / 2; FL = -H2 + CUP_BOTTOM_THICKNESS
LIP_R, LIP_A, LIP_B = 0.03425, 0.00275, 0.0011


def seal_to_solids(v, n, cup=True, band=1.5e-3, depth=2e-4):
    """Water touches the ceramic and the table: there is no air between them. The isosurface stops ~0.5 mm past the
    particle centres, which sit half a spacing or more from a wall, so a thin air layer would separate the water from
    the cup and the table, and rays inside the water would be totally reflected there (a grey, mirror-like look). The
    vertices of the surface facing a solid within `band` are moved `depth` into it (the solids are opaque)."""
    v = v.copy(); moved = 0
    m = (v[:, 2] < band) & (n[:, 2] < -0.3)                     # tabletop, z = 0
    v[m, 2] = -depth; moved += int(m.sum())
    hx, hy, hz = SUPPORT_SIZE[0] / 2, SUPPORT_SIZE[1] / 2, SUPPORT_SIZE[2]          # support block faces
    dx, dy = v[:, 0] - SUPPORT_CENTER_X, v[:, 1]
    inside_xy = (np.abs(dx) < hx) & (np.abs(dy) < hy)
    m = inside_xy & (np.abs(v[:, 2] - hz) < band) & (n[:, 2] < -0.3)
    v[m, 2] = hz - depth; moved += int(m.sum())
    for axis, half, off in ((0, hx, dx), (1, hy, dy)):
        for sgn in (1.0, -1.0):
            m = (np.abs(sgn * off - half) < band) & (v[:, 2] < hz) & (np.abs(dy if axis == 0 else dx) < (hy if axis == 0 else hx)) \
                & (sgn * n[:, axis] < -0.3)
            v[m, axis] -= (sgn * off[m] - half + depth) * sgn; moved += int(m.sum())
    if not cup:
        return v, moved
    L = (v - CC) @ ROT; nl = n.astype(np.float64) @ ROT; r = np.hypot(L[:, 0], L[:, 1]); z = L[:, 2]
    u = np.zeros_like(L); u[:, :2] = L[:, :2] / np.maximum(r, 1e-9)[:, None]
    ez = np.array([0.0, 0.0, 1.0])
    # rendered lip (ceramic_wood_details.lathed_cup): elliptical crown, centre radius LIP_R, half-width LIP_A, rising
    # LIP_B from the wall tops to H2; the simulation rim is flat, so water crossing it is laid onto the crown here
    zc = H2 - LIP_B
    eu, ew = (r - LIP_R) / LIP_A, (z - zc) / LIP_B
    rho = np.maximum(np.hypot(eu, ew), 1e-9)
    pe = np.stack([LIP_R + LIP_A * eu / rho, zc + LIP_B * ew / rho], 1)                    # crown point along the ray
    ge = np.stack([eu / rho / LIP_A, ew / rho / LIP_B], 1); ge /= np.linalg.norm(ge, axis=1, keepdims=True)
    crown_d = np.where((z >= zc) & (rho > 0), np.sign(rho - 1) * np.hypot(r - pe[:, 0], z - pe[:, 1]), np.inf)
    crown_n = ge[:, :1] * u + ge[:, 1:] * ez
    faces = (                                                      # (distance from the face into the water, face normal)
        (np.where((z > FL) & (z < zc), RI - r, np.inf), -u),      # inner wall, normal toward the axis
        (np.where(r < RI, z - FL, np.inf), np.tile(ez, (len(L), 1))),   # inner floor
        (np.where((z >= -H2) & (z < zc), r - RO, np.inf), u),     # outer wall
        (crown_d, crown_n),                                        # rolled lip
    )
    for dist, fn in faces:
        m = (np.abs(dist) < band) & ((nl * fn).sum(1) < -0.3)
        L[m] -= (dist[m] + depth)[:, None] * fn[m]
        moved += int(m.sum())
    return L @ ROT.T + CC, moved


run = Path(sys.argv[1]); out = run / "meshes_1mm"; out.mkdir(exist_ok=True); wetdir = run / "wetmap"
cup = json.load(open(run / "simulation_report.json"))["physics"]["cup_present"]
L = json.load(open(run / "sim_log.json")); d = L["args"]["particle"]; fps = L["args"]["fps"]; sp = L["args"]["rest_spacing"] * d
P = np.load(run / "water_pos.npy"); V = np.load(run / "water_vel_f16.npy").astype(np.float32)
opts = sys.argv[2:]
if "--close-radius" in opts:                     # gap bridging of the tabletop film (m); wider for thinner, sparser sheets
    k = opts.index("--close-radius"); film_tilt.CLOSE_R = float(opts[k + 1]); del opts[k:k + 2]
only = {int(a) for a in opts} or set(range(1, len(P) + 1))
(tx0, tx1), (ty0, ty1) = L["args"]["table_x"], L["args"]["table_y"]
film = film_tilt.Film(tx0 - 0.01, tx1 + 0.01, ty0 - 0.01, ty1 + 0.01)   # the simulated tabletop patch
K, LO, HI = 6, 0.4e-3, 1.0e-3
t0 = time.time()
for i in range(len(P)):
    k = min(i, len(P) - 1 - i, K)
    pos, vel = P[i].astype(np.float64), V[i]
    if k > 0:
        W = P[i - k:i + k + 1].astype(np.float64)
        w = np.clip((HI - (W.max(0) - W.min(0)).max(1)) / (HI - LO), 0, 1)[:, None]
        pos = w * W.mean(0) + (1 - w) * pos
        vel = (w * (W[-1] - W[0]) / (2 * k / fps) + (1 - w) * vel).astype(np.float32)
    Lc = (pos - CC) @ ROT; in_cup = cup & (np.hypot(Lc[:, 0], Lc[:, 1]) < RI + 1e-3) & (Lc[:, 2] > FL - 1e-3)
    tab = film.select(pos, vel, in_cup)
    hgt, cur = film.height(pos[tab], np.full(int(tab.sum()), sp ** 3))
    # wet oak for the renderer: everywhere the water has been plus a 1.5 mm wicking halo, 30% under the water (the water itself already darkens the view)
    blur = 0.6e-3 / film_tilt.C
    wet = np.clip(ndimage.gaussian_filter((film.wet | ndimage.binary_dilation(cur, structure=film_tilt.disk(1.5e-3))).astype(np.float32), blur), 0, 1)
    under = ndimage.gaussian_filter(ndimage.binary_erosion(cur, structure=film_tilt.disk(1.0e-3)).astype(np.float32), blur)
    wetdir.mkdir(exist_ok=True)
    np.savez_compressed(wetdir / f"wet_{i+1:04d}.npz", wet=(wet * (1 - 0.7 * under)).astype(np.float16),
                        x0=film.x[0], y0=film.y[0], cell=film_tilt.C)
    if i + 1 not in only:
        continue
    fv, ff, fn = film.mesh(hgt)
    rest = pos[~tab]
    nn, _ = cKDTree(rest).query(rest, k=2)
    keep = nn[:, 1] <= 2 * d
    mesh, _ = pysplashsurf.reconstruction_pipeline(rest[keep], particle_radius=0.5 * d, smoothing_length=2.0, cube_size=0.6,
                                                   iso_surface_threshold=0.6, mesh_smoothing_weights=True, mesh_smoothing_iters=25,
                                                   normals_smoothing_iters=10, mesh_cleanup=True, compute_normals=True,
                                                   multi_threading=True)
    v = np.asarray(mesh.mesh.vertices, np.float64); t = np.asarray(mesh.mesh.triangles, np.int32)
    n = np.array(mesh.point_attributes["normals"], np.float32)
    v, moved = seal_to_solids(v, n, cup)
    under = (v[:, 2] < film_tilt.depth_at(hgt, film, v[:, :2])) & (v[:, 2] < film_tilt.Z_CUT + 2e-3)
    t = t[~under[t].any(1)]                                      # the stream and drops end where they enter the film
    used = np.unique(t); remap = np.full(len(v), -1, np.int32); remap[used] = np.arange(len(used))
    v, n, t = v[used], n[used], remap[t]
    vk = vel[~tab][keep]
    dist, idx = cKDTree(rest[keep]).query(v, k=4)
    ww = 1.0 / np.maximum(dist, 1e-5); ww /= ww.sum(1, keepdims=True)
    vv = (vk[idx] * ww[..., None]).sum(1)
    if len(fv):
        dist, idx = cKDTree(pos[tab]).query(fv, k=4)
        ww = 1.0 / np.maximum(dist, 1e-5); ww /= ww.sum(1, keepdims=True)
        fvel = (vel[tab][idx] * ww[..., None]).sum(1)
    else:
        fvel = np.zeros((0, 3))
    np.savez(out / f"water_{i+1:04d}.npz", vertices=np.concatenate([v, fv]).astype(np.float32),
             triangles=np.concatenate([t, ff + len(v)]).astype(np.int32), normals=np.concatenate([n, fn]).astype(np.float32),
             velocity=np.concatenate([vv, fvel]).astype(np.float32))
    print(f"frame {i+1}: table {tab.sum()} film {len(fv)} verts, rest {len(v)} verts, trimmed {under.sum()}  {time.time()-t0:.0f}s", flush=True)
print(f"surfaces done {time.time()-t0:.0f}s")
json.dump({"frames": sorted(only), "cup_present": cup, "close_radius_m": film_tilt.CLOSE_R, "seconds": round(time.time() - t0, 1)}, open(run / "surface_log.json", "w"))
