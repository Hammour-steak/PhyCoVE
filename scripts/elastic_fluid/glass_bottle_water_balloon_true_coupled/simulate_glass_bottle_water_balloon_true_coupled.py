#!/usr/bin/env python3
"""XPBD balloon with hydrostatic water and an explicit no-overflow idealization.

Default retain_all keeps every injected unit of water. Before the lip is
reached the original hydrostatic model is unchanged. Once full, an additional
unilateral volume constraint supplies the pressure needed to stretch the
membrane, instead of discarding water. This represents idealized retention,
NOT a physically open mouth or resolved CFD. Geometry, stiffness and injected
water determine the shape; no growth/shape trajectory is prescribed.

The open-mouth overflow model is available explicitly with
--water-retention spill_at_lip. --sealed is a separate experimental mode.
"""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'simulate')
# PCVE_UNIFIED_ENTRY_END

import argparse
import json
import math
import time
from pathlib import Path

import numpy as np

FPS = 24
G = 9.81
RHO_WATER = 1000.0
# Bottle and fittings, simulation coordinates (render z = sim z + 0.771).
STOPPER_BOTTOM_Z = 0.336
PIN_ABOVE_Z = 0.300
TUBE_OUTLET_Z = 0.312
WIDE_AXIS = np.array([0.901, 0.434, 0.0])   # flat bag faces the camera
THIN_AXIS = np.array([-0.434, 0.901, 0.0])
# Kitchen jar inner wall, (z, r): the render's outer profile minus its 3 mm wall.
GLASS_PROFILE = np.array([
    (0.108, 0.065), (0.118, 0.069), (0.225, 0.069), (0.245, 0.063), (0.265, 0.045),
    (0.284, 0.031), (0.304, 0.023), (0.400, 0.023),
])
JAR_FLOOR_Z = 0.108                     # top of the 8 mm glass base
WET_BLEND_M = 0.002                     # wet/dry transition width for the lumped water mass


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser()
    p.add_argument("--out", "--out-dir", type=Path, required=True)
    p.add_argument("--frames", type=int, default=96)
    p.add_argument("--flow-l-min", type=float, default=4.5)
    p.add_argument("--pump-start-frame", type=int, default=2)
    p.add_argument("--edge-stiffness", type=float, default=25.0, help="N/m per triangle edge")
    p.add_argument("--bend-stiffness", type=float, default=6.0,
                   help="N/m for springs across each interior edge; keeps the empty bag from folding flat-free")
    p.add_argument("--elastic-modulus-scale",type=float,default=1.0,
                   help="dimensionless uniform multiplier on ALL stretch/shear-network and bending spring energies; not an absolute Young modulus in Pa")
    p.add_argument("--settle-seconds", type=float, default=1.0, help="dry settling before frame 1")
    p.add_argument("--latex-areal-density", type=float, default=0.285, help="kg/m^2 (0.3 mm latex)")
    p.add_argument("--damping", type=float, default=5.0, help="velocity decay rate, 1/s")
    p.add_argument("--substeps", type=int, default=120, help="per frame")
    p.add_argument("--segments", type=int, default=72)
    p.add_argument("--ring-dz", type=float, default=0.0016)
    p.add_argument("--neck-rest-r", type=float, default=0.007)
    p.add_argument("--body-half-width", type=float, default=0.026)
    p.add_argument("--body-half-depth", type=float, default=0.004)
    p.add_argument("--body-length", type=float, default=0.070)
    p.add_argument("--level-every", type=int, default=6, help="substeps between water-level solves")
    p.add_argument("--no-volume", action="store_true", help="debug: drop the sealed-contents constraint")
    p.add_argument("--timed-edits-json", type=Path, default=None,
                   help='[{"frame": n, "params": {"flow_l_min": q}}]: from frame n on, the tap delivers q')
    p.add_argument("--open-mouth", action="store_true", default=True,
                   help="visible open neck; retain_all adds idealized retention pressure when full")
    p.add_argument("--sealed", dest="open_mouth", action="store_false", help="experimental sealed-contents mode")
    p.add_argument("--water-retention", choices=("retain_all", "spill_at_lip"), default="retain_all",
                   help="retain_all: no overflow, idealized volume retention; spill_at_lip: open-mouth overflow model")
    p.add_argument("--without-balloon", action="store_true",
                   help="DELETE balloon: no membrane; the tap water collects in the open jar (jar_water.npz/.json)")
    args=p.parse_args(argv)
    if not np.isfinite(args.elastic_modulus_scale) or args.elastic_modulus_scale<=0:
        p.error("--elastic-modulus-scale must be finite and positive")
    if args.out.exists() and any(args.out.iterdir()):
        p.error("Refusing to overwrite existing simulation output: "+str(args.out))
    return args


def smooth(t):
    t = np.clip(t, 0.0, 1.0)
    return t * t * (3.0 - 2.0 * t)


def rest_profile(z, args):
    """Outer semi-axes (wide, thin) of the deflated balloon at height z."""
    neck_r = 0.0215                       # stretched over the 23 mm glass neck
    body_top = 0.272
    trans_bottom = 0.282
    if z >= PIN_ABOVE_Z:
        return neck_r, neck_r
    if z >= trans_bottom:
        s = smooth((PIN_ABOVE_Z - z) / (PIN_ABOVE_Z - trans_bottom))
        r = neck_r + (args.neck_rest_r - neck_r) * s
        return r, r
    if z >= body_top:
        return args.neck_rest_r, args.neck_rest_r
    s = (body_top - z) / args.body_length
    w = max(np.sin(np.pi * min(s, 1.0)), 0.0) ** 0.55
    blend = smooth(s / 0.28)
    a = args.neck_rest_r + (args.body_half_width * w - args.neck_rest_r) * blend
    b = args.neck_rest_r + (args.body_half_depth * w - args.neck_rest_r) * blend
    return max(a, 1e-4), max(b, 1e-4)


def stadium_ring(a, b, n):
    """n points equally spaced by arc length on a stadium (two flat faces of
    half-width a-b joined by semicircular ends of radius b), starting at the
    centre of the +thin face.  A deflated balloon is two flat sheets with
    rounded edges; a thin ellipse would put sliver triangles at its tips."""
    b = min(b, a)
    flat = a - b
    perim = 4.0 * flat + 2.0 * np.pi * b
    s = np.arange(n) / n * perim
    u = np.empty(n)
    w = np.empty(n)
    seg = [flat, np.pi * b, 2.0 * flat, np.pi * b, flat]
    edges = np.cumsum([0.0] + seg)
    for k, t in enumerate(s):
        if t < edges[1]:                      # +thin face, moving toward +wide
            u[k], w[k] = t, b
        elif t < edges[2]:                    # +wide end cap
            ang = (t - edges[1]) / b
            u[k], w[k] = flat + b * np.sin(ang), b * np.cos(ang)
        elif t < edges[3]:                    # -thin face, moving toward -wide
            u[k], w[k] = flat - (t - edges[2]), -b
        elif t < edges[4]:                    # -wide end cap
            ang = (t - edges[3]) / b
            u[k], w[k] = -flat - b * np.sin(ang), -b * np.cos(ang)
        else:                                 # back along +thin face
            u[k], w[k] = -flat + (t - edges[4]), b
    return u, w


def build_mesh(args):
    body_bottom = 0.272 - args.body_length
    zs = list(np.arange(body_bottom + args.ring_dz, STOPPER_BOTTOM_Z + 1e-9, args.ring_dz))
    zs[-1] = STOPPER_BOTTOM_Z
    S = args.segments
    verts = [np.array([0.0, 0.0, body_bottom])]
    for z in zs:
        a, b = rest_profile(z, args)
        u, w = stadium_ring(a, b, S)
        ring = np.outer(u, WIDE_AXIS) + np.outer(w, THIN_AXIS)
        ring[:, 2] = z
        verts.extend(ring)
    verts.append(np.array([0.0, 0.0, STOPPER_BOTTOM_Z]))      # stopper face centre
    verts = np.asarray(verts)
    R = len(zs)
    top = len(verts) - 1
    faces = []
    for j in range(S):
        faces.append((0, 1 + (j + 1) % S, 1 + j))
    for r in range(R - 1):
        a0, b0 = 1 + r * S, 1 + (r + 1) * S
        for j in range(S):
            k = (j + 1) % S
            faces.append((a0 + j, a0 + k, b0 + k))
            faces.append((a0 + j, b0 + k, b0 + j))
    last = 1 + (R - 1) * S
    for j in range(S):
        faces.append((last + j, last + (j + 1) % S, top))
    faces = np.asarray(faces, dtype=np.int64)
    return verts, faces, R, S


def bend_pairs(faces):
    """Opposite-vertex pairs across every interior edge (bending springs)."""
    opp = {}
    pairs = []
    for f in faces:
        for k in range(3):
            a, b, c = f[k], f[(k + 1) % 3], f[(k + 2) % 3]
            key = (min(a, b), max(a, b))
            if key in opp:
                pairs.append((opp[key], c))
            else:
                opp[key] = c
    pairs = np.asarray(pairs, dtype=np.int64)
    pairs.sort(axis=1)
    return np.unique(pairs, axis=0)


def edges_of(faces):
    e = np.concatenate([faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]])
    e.sort(axis=1)
    return np.unique(e, axis=0)


def color_edges(edges, rest, n_verts):
    """Greedy edge colouring -> list of (i0, i1, rest) groups with disjoint vertices."""
    used = [set() for _ in range(n_verts)]
    color = np.empty(len(edges), dtype=np.int64)
    for k, (a, b) in enumerate(edges):
        c = 0
        while c in used[a] or c in used[b]:
            c += 1
        color[k] = c
        used[a].add(c)
        used[b].add(c)
    groups = []
    for c in range(color.max() + 1):
        sel = color == c
        groups.append((edges[sel, 0], edges[sel, 1], rest[sel]))
    return groups


def volume_and_grad(x, faces):
    a, b, c = x[faces[:, 0]], x[faces[:, 1]], x[faces[:, 2]]
    vol = np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0
    g = np.zeros_like(x)
    np.add.at(g, faces[:, 0], np.cross(b, c))
    np.add.at(g, faces[:, 1], np.cross(c, a))
    np.add.at(g, faces[:, 2], np.cross(a, b))
    return vol, g / 6.0               # g_i = (1/3) sum of adjacent area vectors


def wet_volume(x, faces, h):
    """Volume of the enclosed region below z = h (vertices clamped onto the plane)."""
    y = x.copy()
    np.minimum(y[:, 2], h, out=y[:, 2])
    y[:, 2] -= h
    a, b, c = y[faces[:, 0]], y[faces[:, 1]], y[faces[:, 2]]
    return np.einsum("ij,ij->i", a, np.cross(b, c)).sum() / 6.0


def solve_level(x, faces, water_volume, lo, hi):
    if water_volume <= 0.0:
        return lo
    for _ in range(26):
        mid = 0.5 * (lo + hi)
        if wet_volume(x, faces, mid) < water_volume:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


def glass_radius(z):
    return np.interp(z, GLASS_PROFILE[:, 0], GLASS_PROFILE[:, 1])


def elastic_coefficients(args):
    """Scale the entire discrete elastic energy, without inventing an absolute E.

    Shear arises from the same triangulated edge network. Scaling all its
    edge springs and all opposite-vertex bending springs by s gives
    U_s(x) = s * U_1(x), hence the same scaling of its elastic forces and
    tangent stiffness at a given configuration, in every deformation mode.
    This does not introduce a separately calibrated continuum Poisson ratio.
    """
    scale=float(getattr(args,"elastic_modulus_scale",1.0))
    return {"relative_modulus_scale":scale,"stretch_edge_k_N_m":args.edge_stiffness*scale,
        "bending_spring_k_N_m":args.bend_stiffness*scale,
        "shear":"implicit in the same triangulated edge network; uniformly scaled",
        "absolute_Young_modulus_Pa":None,"poisson_ratio":"emergent from the discrete network, not independently prescribed",
        "mapping":"U_scaled(x) = relative_modulus_scale * U_base(x), for all elastic spring terms"}


def conservative_overflow(poured,spilled,capacity):
    """Water that has spilled cannot re-enter when the membrane capacity grows."""
    retained=max(poured-spilled,0.0)
    lost=max(retained-max(capacity,0.0),0.0)
    return retained-lost,spilled+lost


def retained_water_balance(poured, spilled, capacity, policy):
    """Retain every injected unit by default; do not silently clip or hide water."""
    if policy == "retain_all":
        if spilled != 0.0:
            raise ValueError("Cannot resume a spilling state as a retain-all state")
        return poured, 0.0
    if policy == "spill_at_lip":
        return conservative_overflow(poured, spilled, capacity)
    raise ValueError("Unknown retention policy: " + str(policy))


def wet_volume_and_grad(x, faces, h):
    """Exact derivative of this model's plane-clamped wet_volume expression."""
    y = x.copy()
    np.minimum(y[:, 2], h, out=y[:, 2])
    y[:, 2] -= h
    volume, gradient = volume_and_grad(y, faces)
    gradient[x[:, 2] >= h, 2] = 0.0
    return volume, gradient


def retain_water_projection(x, faces, inverse_mass, water_volume, lip_z, iterations=2):
    """Enforce capacity >= retained water by pressure, only when already full.

    Mutates positions, never a prescribed scale. A positive multiplier is an
    idealized retention-pressure impulse; this is not open-mouth hydrodynamics.
    Dry/part-filled states are exactly unchanged. Contact is applied afterwards.
    """
    multiplier = 0.0
    for _ in range(iterations):
        capacity, gradient = wet_volume_and_grad(x, faces, lip_z)
        deficit = water_volume - capacity
        if deficit <= 1e-12:
            break
        denominator = float((inverse_mass[:, None] * gradient * gradient).sum())
        if denominator <= 1e-30:
            raise RuntimeError("No free membrane degrees of freedom to retain the injected water")
        step_multiplier = deficit / denominator
        x += step_multiplier * inverse_mass[:, None] * gradient
        multiplier += step_multiplier
    return multiplier


def read_timed_flows(args):
    """{frame: flow m^3/s} of --timed-edits-json, checked as in main()."""
    timed = {}
    if args.timed_edits_json is not None:
        for item in json.loads(args.timed_edits_json.read_text()):
            unknown = set(item["params"]) - {"flow_l_min"}
            if unknown:
                raise ValueError(f"unsupported timed edit parameters: {sorted(unknown)}")
            frame_n = int(item["frame"])
            if not 2 <= frame_n <= args.frames:
                raise ValueError(f"timed edit frame {frame_n} outside 2..{args.frames}")
            timed[frame_n] = float(item["params"]["flow_l_min"]) / 60000.0
    return timed


def jar_volume_table(step=2e-5):
    """Water volume below height z inside the jar's inner wall (GLASS_PROFILE, solid of revolution)."""
    z = np.arange(JAR_FLOOR_Z, GLASS_PROFILE[-1, 0] + step / 2, step)
    area = np.pi * glass_radius(z) ** 2
    return z, np.concatenate([[0.0], np.cumsum(0.5 * (area[1:] + area[:-1]) * np.diff(z))])


def fill_open_jar(args) -> None:
    """DELETE balloon: there is no membrane, so the tap water falls through the open neck and collects in the jar.

    Same water model as the balloon case (incompressible, hydrostatic, no velocity field): the free surface is
    the height whose enclosed jar volume equals the poured volume, with the tap schedule of main() (pouring from
    pump_start_frame, timed flow changes at the top of their frame).
    """
    args.out.mkdir(parents=True, exist_ok=True)
    timed = read_timed_flows(args)
    z_table, v_table = jar_volume_table()
    flow = args.flow_l_min / 60000.0
    poured, levels, rows = 0.0, [], []
    for frame in range(1, args.frames + 1):
        if frame in timed:
            flow = timed[frame]
        if frame > 1 and frame >= args.pump_start_frame:
            poured += flow / FPS
        if poured > v_table[-1]:
            raise ValueError("The poured water exceeds the jar's inner volume")
        level = float(np.interp(poured, v_table, z_table))
        levels.append(level)
        rows.append({"frame": frame, "water_ml": poured * 1e6, "poured_ml": poured * 1e6, "spilled_ml": 0.0,
                     "water_level_z_mm": level * 1e3, "water_depth_mm": (level - JAR_FLOOR_Z) * 1e3})
        print("FRAME", json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items()}), flush=True)
    np.savez_compressed(args.out / "jar_water.npz", water_level=np.asarray(levels), poured_m3=np.asarray([r["poured_ml"] for r in rows]) * 1e-6,
                        jar_inner_profile_zr=GLASS_PROFILE, jar_floor_z=JAR_FLOOR_Z)
    (args.out / "jar_water.json").write_text(json.dumps({
        "solver": "hydrostatic free surface of the water collected in the open jar; no membrane (DELETE balloon)",
        "water_model": "incompressible volume; level from the jar's inner wall profile (GLASS_PROFILE) and the poured volume; "
                       "no velocity field, splash or sloshing, as in the balloon case",
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "jar_capacity_ml": float(v_table[-1] * 1e6), "rows": rows}, indent=1))
    print("DONE", flush=True)


def main() -> None:
    args = parse_args()
    if args.without_balloon:
        fill_open_jar(args)
        return
    del args.without_balloon            # membrane.json records the membrane run's arguments only
    args.out.mkdir(parents=True, exist_ok=True)
    X, faces, n_rings, n_seg = build_mesh(args)
    edges = edges_of(faces)
    L0 = np.linalg.norm(X[edges[:, 0]] - X[edges[:, 1]], axis=1)
    pinned = X[:, 2] >= PIN_ABOVE_Z - 1e-9
    _, g0 = volume_and_grad(X, faces)
    vert_area = np.linalg.norm(g0, axis=1) * 3.0          # |sum of area vectors| ~ vertex area
    tri = X[faces]
    tri_area = 0.5 * np.linalg.norm(np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0]), axis=1)
    vert_area = np.zeros(len(X))
    for c in range(3):
        np.add.at(vert_area, faces[:, c], tri_area / 3.0)
    m_latex = args.latex_areal_density * vert_area
    V0, _ = volume_and_grad(X, faces)
    if V0 < 0:
        faces = faces[:, ::-1].copy()
        V0 = -V0
    color_groups = color_edges(edges, L0, len(X))
    bends = bend_pairs(faces)
    B0 = np.linalg.norm(X[bends[:, 0]] - X[bends[:, 1]], axis=1)
    bend_groups = color_edges(bends, B0, len(X))

    dt = 1.0 / FPS / args.substeps
    material_parameters = elastic_coefficients(args)
    alpha = 1.0 / material_parameters["stretch_edge_k_N_m"] / dt ** 2
    alpha_bend = 1.0 / material_parameters["bending_spring_k_N_m"] / dt ** 2
    flow = args.flow_l_min / 60000.0
    timed = {}
    if args.timed_edits_json is not None:
        for item in json.loads(args.timed_edits_json.read_text()):
            unknown = set(item["params"]) - {"flow_l_min"}
            if unknown:
                raise ValueError(f"unsupported timed edit parameters: {sorted(unknown)}")
            frame_n = int(item["frame"])
            if not 2 <= frame_n <= args.frames:
                raise ValueError(f"timed edit frame {frame_n} outside 2..{args.frames}")
            timed[frame_n] = float(item["params"]["flow_l_min"]) / 60000.0
    t_pump = (args.pump_start_frame - 1) / FPS
    decay = math.exp(-args.damping * dt)
    print(f"MESH verts={len(X)} faces={len(faces)} edges={len(edges)} colors={len(color_groups)} pinned={int(pinned.sum())} "
          f"V0_air={V0*1e6:.1f}mL latex_mass={m_latex.sum()*1e3:.2f}g dt={dt:.2e}", flush=True)

    x = X.copy()
    v = np.zeros_like(x)
    z_bottom0 = X[:, 2].min()
    level = z_bottom0
    traj, rows = [x.astype(np.float32)], []
    levels = [float(level)]

    def record(frame, wall, water_v, vol, pressure):
        free = x[~pinned]
        r = np.linalg.norm(free[:, :2], axis=1)
        measured_capacity = wet_volume(x, faces, STOPPER_BOTTOM_Z)
        rows.append({
            "frame": frame, "water_ml": water_v * 1e6, "contents_ml": vol * 1e6,
            "poured_ml":poured*1e6,"capacity_ml":measured_capacity*1e6,
            "retention_capacity_deficit_ml":max(water_v-measured_capacity,0.0)*1e6,
            "mass_balance_error_ml":(poured-water_v-spilled)*1e6,
            "retention_gauge_pa":retention_pressure_acc / args.substeps,
            "air_gauge_pa": pressure, "water_level_z_mm": level * 1e3,
            "radius_max_mm": float(r.max() * 1e3), "bottom_z_mm": float(free[:, 2].min() * 1e3),
            "max_edge_stretch": float((np.linalg.norm(x[edges[:, 0]] - x[edges[:, 1]], axis=1) / L0).max()),
            "spilled_ml": spilled * 1e6,
            "wall_seconds": wall,
        })
        print("FRAME", json.dumps({k: (round(v, 3) if isinstance(v, float) else v) for k, v in rows[-1].items()}),
              flush=True)

    all_groups = [g + (alpha,) for g in color_groups] + [g + (alpha_bend,) for g in bend_groups]
    settle_frames = int(round(args.settle_seconds * FPS))
    step = 0
    capacity = V0
    spilled = 0.0
    poured = 0.0
    m_prev = m_latex.copy()
    for frame in range(1 - settle_frames, args.frames + 1):
        tick = time.monotonic()
        pressure_acc = 0.0
        retention_pressure_acc = 0.0
        if frame == 1:
            traj[0] = x.astype(np.float32)
            record(1, 0.0, 0.0, V0, 0.0)
            continue
        if frame in timed:
            flow = timed[frame]
        for sub in range(args.substeps):
            if frame >= args.pump_start_frame:
                poured += flow * dt
            water_v = poured-spilled
            if args.open_mouth:
                capacity = wet_volume(x, faces, STOPPER_BOTTOM_Z) if step % args.level_every == 0 else capacity
                water_v,spilled = retained_water_balance(poured,spilled,capacity,args.water_retention)
            if step % args.level_every == 0:
                level = solve_level(x, faces, water_v, z_bottom0 - 0.01, STOPPER_BOTTOM_Z)
                level = min(level, STOPPER_BOTTOM_Z)
            depth = np.clip(level - x[:, 2], 0.0, None)
            # lump the water's mass onto the wetted latex, by area, fading in
            # over WET_BLEND_M below the water line so it never jumps
            m = m_latex.copy()
            wet_weight = np.clip(depth / WET_BLEND_M, 0.0, 1.0)
            if water_v > 0.0 and wet_weight.any():
                wet_area = vert_area * wet_weight
                m += RHO_WATER * water_v * wet_area / wet_area.sum()
            # water joining or leaving a node changes its mass, not its momentum
            v *= (m_prev / m)[:, None]
            m_prev = m
            w = np.where(pinned, 0.0, 1.0 / m)
            vol, gv = volume_and_grad(x, faces)
            # external loads: latex weight and hydrostatic water pressure (= water weight)
            f = np.zeros_like(x)
            f[:, 2] -= m_latex * G
            f += (RHO_WATER * G * depth)[:, None] * gv
            v += f * w[:, None] * dt
            v *= decay
            p = x + v * dt
            # latex edges: one small-step XPBD Gauss-Seidel sweep, vectorised per
            # edge colour (no two edges of a colour share a vertex)
            for i0, i1, rest_len, comp in all_groups:
                d = p[i0] - p[i1]
                ln = np.linalg.norm(d, axis=1)
                lam = -(ln - rest_len) / (w[i0] + w[i1] + comp)
                step_vec = (lam / np.maximum(ln, 1e-12))[:, None] * d
                p[i0] += w[i0][:, None] * step_vec
                p[i1] -= w[i1][:, None] * step_vec
            if args.open_mouth and args.water_retention == "retain_all" and water_v > 0.0:
                # A water-only lower bound, NOT initial trapped air + water.
                # This preserves all part-filled trajectories and only supplies
                # additional pressure when hydrostatic expansion is insufficient.
                retention_lam = retain_water_projection(p, faces, w, water_v, STOPPER_BOTTOM_Z)
                retention_pressure_acc += retention_lam / dt ** 2
            # sealed contents: initial air + pumped water
            target = V0 + water_v
            lam_v = 0.0
            for _ in range(0 if (args.no_volume or args.open_mouth) else 2):
                vol, gv = volume_and_grad(p, faces)
                denom = (w[:, None] * gv * gv).sum()
                lam_v = (target - vol) / max(denom, 1e-30)
                p += lam_v * w[:, None] * gv
            # bottle glass wall (frictionless)
            r = np.linalg.norm(p[:, :2], axis=1)
            rmax = glass_radius(p[:, 2]) - 0.001
            over = r > rmax
            if over.any():
                p[over, :2] *= (rmax[over] / r[over])[:, None]
            np.maximum(p[:, 2], JAR_FLOOR_Z + 0.001, out=p[:, 2])
            v = (p - x) / dt
            v[pinned] = 0.0
            x = np.where(pinned[:, None], X, p)
            # air gauge pressure from the volume multiplier: dV = sum w g . dx,  p = lam/dt^2 scale
            pressure_acc += lam_v / dt ** 2
            step += 1
        if frame < 1:
            continue
        traj.append(x.astype(np.float32))
        levels.append(float(level))
        record(frame, time.monotonic() - tick, water_v, vol, pressure_acc / args.substeps)
        if not np.isfinite(x).all():
            raise SystemExit("non-finite state")

    np.savez_compressed(args.out / "membrane.npz", rest=X.astype(np.float32), faces=faces.astype(np.int32),
                        trajectory=np.asarray(traj), pinned=pinned, water_level=np.asarray(levels),
                        rings=n_rings, segments=n_seg)
    (args.out / "membrane.json").write_text(json.dumps({
        "solver": "NumPy XPBD membrane + hydrostatic water; not Genesis or resolved two-way CFD",
        "water_retention_model": {"policy": args.water_retention,
            "all_injected_water_retained": args.water_retention == "retain_all",
            "additional_pressure": "unilateral water-volume constraint after filling; idealized, not a real open-mouth boundary",
            "finite_jar_capacity": "wall/floor contact still applies; infinite water in a finite jar is not physically possible"},
        "material_parameters":material_parameters,
        "args": {k: (str(v) if isinstance(v, Path) else v) for k, v in vars(args).items()},
        "initial_air_ml": V0 * 1e6, "rows": rows,
    }, indent=1))
    print("DONE", flush=True)


if __name__ == "__main__":
    main()
