"""A toy car drops onto an inflatable float in a bathtub: Genesis 1.4.3 DFSPH, two-way, every solid a ghost-particle shell.

relax: fills the tub from a rest lattice with the float cut out at its Archimedes draft, and lets water and float settle
       (no car). Writes settled.npz.
run:   loads a settled state, releases the car, writes particles/frame_####.npz and sim_log.json.
The bathtub is the rendered shell itself (geometry/tub_shell.npz, the rings of the fitted ceramic), so walls slope as seen.
Solids are ghost-particle shells with their own pressure (physics/coupling_toy_car_float_bathtub.py), the stale second
gravity of Genesis 1.4.3's DFSPH is removed (scripts/pcve_dfsph_patches.py).
usage: <genesis python> simulate_toy_car_float_bathtub.py relax --out RUN [--no-float]
       <genesis python> simulate_toy_car_float_bathtub.py run --out RUN --settled SETTLED.npz [--car-mass KG] [--no-car] ..."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset
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
import argparse, json, math, os, threading, time
from pathlib import Path
import numpy as np
from scipy.spatial import cKDTree

HERE = Path(__file__).resolve().parent


def ASSET(rel):
    return scene_asset(HERE, "assets/" + rel)


ap = argparse.ArgumentParser()
ap.add_argument("mode", choices=("relax", "run"))
ap.add_argument("--out", type=Path, required=True)
ap.add_argument("--settled", type=Path)
ap.add_argument("--particle", type=float, default=0.006)
ap.add_argument("--rest-spacing", type=float, default=0.93)
ap.add_argument("--level", type=float, default=0.42, help="still water surface height above the ground (m)")
ap.add_argument("--fill-extra", type=float, default=0.0045, help="the settled surface ends this far below the fill's top")
ap.add_argument("--frames", type=int, default=96)
ap.add_argument("--fps", type=int, default=24)
ap.add_argument("--steps-per-frame", type=int, default=10)
ap.add_argument("--substeps", type=int, default=8, help="80 per frame at 6 mm: 0.4 d per substep at 4.6 m/s")
ap.add_argument("--surface-tension", type=float, default=0.02, help="Akinci gamma: 0.072 N/m scales as ~d^-2.4 from gamma 1.5 at 1 mm")
ap.add_argument("--mu", type=float, default=1e-6)
ap.add_argument("--float-mass", type=float, default=0.15)
ap.add_argument("--car-mass", type=float, default=2.0)
ap.add_argument("--float-inertia", type=float, default=1.0, help="the float's mass in the rigid solver: its own plus ~1 kg of the water it pushes (weight stays --float-mass)")
ap.add_argument("--float-omega", type=float, default=0.3, help="relaxation of the float's velocity in the pressure iterations")
ap.add_argument("--car-omega", type=float, default=0.5)
ap.add_argument("--float-yaw", type=float, default=90.0)
ap.add_argument("--float-offset", type=float, nargs=2, default=(0.06, -0.22), help="float centre from the tub's centre (m): not over the drain, which would read as its stem")
ap.add_argument("--car-euler", type=float, nargs=3, default=(0.0, 0.0, 180.0))
ap.add_argument("--car-ang-vel", type=float, nargs=3, default=(0.35, 0.0, 0.0))
ap.add_argument("--car-offset", type=float, nargs=2, default=(-0.02, 0.035), help="release point from the float's centre (m): a dropped toy does not land dead centre; towards the tub's middle, so a float that tips over comes away from the wall")
ap.add_argument("--release-z", type=float, default=1.0522)
ap.add_argument("--no-car", action="store_true")
ap.add_argument("--no-float", action="store_true")
ap.add_argument("--relax-frames", type=int, default=30)
ap.add_argument("--relax-damp", type=float, default=0.9)
ap.add_argument("--layers", type=int, default=3, help="ghost shell thickness in lattice spacings")
ap.add_argument("--momentum-avg", type=float, default=5e-5)
ap.add_argument("--momentum-max", type=float, default=5e-4)
ap.add_argument("--position-avg", type=float, default=5e-4)
ap.add_argument("--position-max", type=float, default=0.01)
ap.add_argument("--div-iters", type=int, default=10)
ap.add_argument("--debug-from", type=int, default=0)
ap.add_argument("--momentum-iters", type=int, default=300)
ap.add_argument("--position-iters", type=int, default=150, help="cap of the position solve per substep: it only restores volume, and an impact's frames spend most of the run's time here")
ap.add_argument("--density-after", type=float, help="water density from --density-time on (kg/m^3)")
ap.add_argument("--density-time", type=float, default=0.0, help="clip time of the density change (s)")
ap.add_argument("--checkpoint-frames", type=int, nargs="*", default=[], help="save the full state at these frames")
ap.add_argument("--resume-from", type=Path, help="run whose checkpoint this case continues (its earlier frames are linked)")
ap.add_argument("--resume-frame", type=int, default=0)
ap.add_argument("--warm-omega", type=float, default=0.95)
ap.add_argument("--warm-rise", type=float, default=0.05, help="k_bar may gain this share of g * spacing per substep")
ap.add_argument("--warm-fall", type=float, default=0.2)
ap.add_argument("--still-speed", type=float, default=1e-4, help="below this neighbourhood speed (m/s) the position solve's inelastic part works in the tub's frame")
ap.add_argument("--rho-interior", type=float, default=0.95)
ap.add_argument("--compaction", type=float, default=0.03, help="rate (1/s) at which a stirred, slightly under-dense liquid may close its deficit")
ap.add_argument("--speed-cap", type=float, default=7.0, help="m/s; a 57 cm drop gives 3.3 m/s and a splash about twice that")
a = ap.parse_args()
a.out.mkdir(parents=True, exist_ok=True)
d = a.particle; sp = a.rest_spacing * d; V = 0.8 * d ** 3
if a.mode == "relax":
    a.no_car = True

# ---------------------------------------------------------------- the bathtub: z_s(x, y) from the rendered shell's rings
_t = np.load(HERE / "geometry/tub_shell.npz")
rings, (cx, cy) = _t["rings"], _t["center"]
INNER = np.arange(2, 25)                           # floor ring ... flat top of the rim
nth = rings.shape[1]
prof_rho = np.hypot(rings[INNER, :, 0] - cx, rings[INNER, :, 1] - cy)   # (ring, theta)
prof_z = rings[INNER, 0, 2]
RIM_RHO = np.hypot(rings[25, :, 0] - cx, rings[25, :, 1] - cy)


def tub_surface(x, y):
    """interior surface height z_s above (x, y), and the fractional position in the rim's outline (> 1: outside the tub)"""
    rho = np.hypot(x - cx, y - cy); th = np.arctan2(y - cy, x - cx) % (2 * np.pi) / (2 * np.pi) * nth
    i0 = np.floor(th).astype(int) % nth; i1 = (i0 + 1) % nth; w = th - np.floor(th)
    zs = np.zeros(len(rho)); rim = np.zeros(len(rho))
    for k in range(nth):
        m0, m1 = i0 == k, i1 == k
        if m0.any():
            zs[m0] += (1 - w[m0]) * np.interp(rho[m0], prof_rho[:, k], prof_z)
            rim[m0] += (1 - w[m0]) * RIM_RHO[k]
        if m1.any():
            zs[m1] += w[m1] * np.interp(rho[m1], prof_rho[:, k], prof_z)
            rim[m1] += w[m1] * RIM_RHO[k]
    return zs, rho / rim


def tub_samples(step=0.002):
    """dense points on the interior surface, for distances"""
    th = np.arange(0, nth, 0.25); i0 = np.floor(th).astype(int) % nth; i1 = (i0 + 1) % nth; w = (th - np.floor(th))[:, None]
    rho = (prof_rho[:, i0].T * (1 - w) + prof_rho[:, i1].T * w)    # (theta, ring)
    pts = []
    ang = th / nth * 2 * np.pi
    for j in range(len(ang)):
        rj, zj = np.r_[0.0, rho[j]], np.r_[prof_z[0], prof_z]   # the floor runs on under the drain cover
        s = np.r_[0, np.cumsum(np.hypot(np.diff(rj), np.diff(zj)))]
        q = np.arange(0, s[-1], step)
        r_, z_ = np.interp(q, s, rj), np.interp(q, s, zj)
        pts.append(np.stack([cx + r_ * np.cos(ang[j]), cy + r_ * np.sin(ang[j]), z_], 1))
    return np.concatenate(pts)


# ---------------------------------------------------------------- the lattice: tub ghosts and water on one grid
gx = np.arange(math.floor(-0.95 / sp), math.ceil(0.95 / sp) + 1)
PXY = np.stack(np.meshgrid((gx + 0.5) * sp, (gx + 0.5) * sp, indexing="ij"), -1).reshape(-1, 2)
zs_xy, rim_xy = tub_surface(PXY[:, 0], PXY[:, 1])
keep_xy = rim_xy < 1.0
PXY, zs_xy = PXY[keep_xy], zs_xy[keep_xy]
gz = (np.arange(math.floor(0.09 / sp), math.ceil(0.62 / sp) + 1) + 0.5) * sp
print(f"tub columns {len(PXY)}", flush=True)
water_cols, ghost_cand = [], []
for z in gz:
    above = z > zs_xy
    if z < a.level + a.fill_extra - 0.5 * sp:
        water_cols.append(np.c_[PXY[above], np.full(above.sum(), z)])
    below = (~above) & (zs_xy - z < 8 * a.layers * sp)
    ghost_cand.append(np.c_[PXY[below], np.full(below.sum(), z)])
water0 = np.concatenate(water_cols); ghost_cand = np.concatenate(ghost_cand)
_dist, _ = cKDTree(tub_samples()).query(ghost_cand, workers=-1)
tub_ghost = ghost_cand[_dist < a.layers * sp].astype(np.float64)
print(f"water lattice {len(water0)} ({len(water0) * V * 1e3:.1f} L at V = 0.8 d^3); tub ghosts {len(tub_ghost)}", flush=True)


# ---------------------------------------------------------------- the float and the car: shells on their own lattice
def rotz(deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1.0]])


fm = json.loads(ASSET("procedural_float/float_manifest.json").read_text())
ff = np.load(ASSET("procedural_float/float_field.npz"))
from scipy.interpolate import RegularGridInterpolator
_ti = RegularGridInterpolator((ff["x"], ff["y"]), ff["t"], bounds_error=False, fill_value=-1.0)
_zi = RegularGridInterpolator((ff["x"], ff["y"]), ff["z0"], bounds_error=False, fill_value=0.0)


def inside_float(p):
    q = p[:, :2]
    return np.abs(p[:, 2] - _zi(q)) < _ti(q)


def lattice_shell(lo, hi, inside, surface_pts):
    ax = [np.arange(math.floor(l / sp), math.ceil(h / sp) + 1) * sp + 0.5 * sp for l, h in zip(lo, hi)]
    P = np.stack(np.meshgrid(*ax, indexing="ij"), -1).reshape(-1, 3)
    P = P[inside(P)]
    dist, _ = cKDTree(surface_pts).query(P, workers=-1)
    return P[dist < a.layers * sp]


_fv = np.load(ASSET("procedural_float/float_mesh.npz"))["vertices"][::3].astype(np.float64)
float_ghost = None if a.no_float else lattice_shell(_fv.min(0), _fv.max(0), inside_float, _fv)

import trimesh
car_mesh = trimesh.load(ASSET("amg_vision_gt/collision.obj"), process=True)
_cs, _ci = trimesh.sample.sample_surface(car_mesh, 200000, seed=1)
_cn = car_mesh.face_normals[_ci]
_ct = cKDTree(_cs)


def inside_car(p):
    dist, idx = _ct.query(p, workers=-1)
    return ((p - _cs[idx]) * _cn[idx]).sum(1) < 0


car_ghost = None if a.no_car else lattice_shell(car_mesh.bounds[0], car_mesh.bounds[1], inside_car, _cs)
print("float ghosts", 0 if float_ghost is None else len(float_ghost), "car ghosts", 0 if car_ghost is None else len(car_ghost), flush=True)

# ---------------------------------------------------------------- initial state
zmin = fm["z_range_m"][0]
arch_d, arch_v = np.array(fm["archimedes"]["draft_m"]), np.array(fm["archimedes"]["displaced_m3"])
draft0 = float(np.interp(a.float_mass / 998.0, arch_v, arch_d))
draft_car = float(np.interp((a.float_mass + a.car_mass) / 998.0, arch_v, arch_d))
if a.mode == "relax":
    float_pos0 = np.array([cx + a.float_offset[0], cy + a.float_offset[1], a.level - draft0 - zmin]); float_quat0 = None
    if a.no_float:
        water = water0
    else:
        R0 = rotz(a.float_yaw)
        local = (water0 - float_pos0) @ R0
        q = local[:, :2]
        water = water0[~(np.abs(local[:, 2] - _zi(q)) < _ti(q) + 0.5 * sp)]
    water_vel0 = np.zeros_like(water)
elif a.resume_from:
    st = np.load(a.resume_from / f"ckpt_{a.resume_frame:04d}.npz")
    assert math.isclose(float(st["dx"]), d), "checkpoint has another particle size"
    water, water_vel0 = st["water_pos"], st["water_vel"]
    float_pos0, float_quat0 = st["float_pos"], st["float_quat"]
else:
    st = np.load(a.settled)
    assert math.isclose(float(st["dx"]), d), "settled state has another particle size"
    water, water_vel0 = st["water_pos"], st["water_vel"]
    float_pos0, float_quat0 = st["float_pos"], st["float_quat"]
n_fluid = len(water)
print(f"water particles {n_fluid}", flush=True)

import torch
import genesis as gs
gs.init(backend=gs.cuda, precision="32", seed=20261102, logging_level="warning")
import pcve_dfsph_patches as dfsph
import coupling_toy_car_float_bathtub as coupling
import genesis.engine.simulator as simulator
dfsph.install_dfsph_gravity_fix(); dfsph.install_quiet(0.0, "position", 20)
dfsph.install_surface_tension(a.surface_tension)
simulator.SPHSolver = coupling.make_solver()
dt = 1.0 / a.fps / a.steps_per_frame
scene = gs.Scene(
    sim_options=gs.options.SimOptions(dt=dt, substeps=a.substeps, gravity=(0, 0, -9.81), requires_grad=False),
    sph_options=gs.options.SPHOptions(particle_size=d, pressure_solver="DFSPH", max_density_error_percent=0.005,
                                      max_divergence_error=0.02, max_divergence_solver_iterations=a.div_iters,
                                      max_density_solver_iterations=a.position_iters, lower_bound=(-1.2, -1.6, -0.05), upper_bound=(1.2, 1.6, 2.2)),
    rigid_options=gs.options.RigidOptions(dt=dt / a.substeps, enable_collision=True, enable_joint_limit=True,
                                          integrator=gs.integrator.implicitfast, iterations=25),
    coupler_options=gs.options.LegacyCouplerOptions(rigid_sph=True, rigid_mpm=False, rigid_pbd=False, rigid_fem=False,
                                                    mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
    show_viewer=False)
hidden = lambda friction: gs.materials.Rigid(rho=1000.0, friction=friction, needs_coup=False)
carrier = scene.add_entity(gs.morphs.Box(pos=(0.0, 0.0, -1.0), size=(0.1, 0.1, 0.1), fixed=True, visualization=False), material=hidden(0.5))
# the solids' contact with the tub stands two particle sizes off the ceramic: in a narrower gap water can only be crushed, and it
# shoots out at several m/s (the render lowers a body resting there by the same amount)
scene.add_entity(gs.morphs.Box(pos=(cx, cy, 0.1125 + 2 * d - 0.05), size=(1.1, 2.2, 0.1), fixed=True, visualization=False), material=hidden(0.45))
# the wall: a ring of tilted boxes on the ceramic's own slope, continued 25 cm above the rim (a float released under water shoots
# out of it and has to come back down into the tub). The room's floor catches what still gets out.
from scipy.spatial.transform import Rotation as _Rot
_nseg = 72
_ri = [np.argmin(np.abs(prof_z - z_)) for z_ in (0.20, 0.56)]
for k in range(_nseg):
    th_ = 2 * np.pi * k / _nseg
    i_ = int(round(th_ / (2 * np.pi) * nth)) % nth
    r0_, r1_ = prof_rho[_ri[0], i_], prof_rho[_ri[1], i_]
    z0_, z1_ = prof_z[_ri[0]], prof_z[_ri[1]]
    i2_ = int(round((th_ + 2 * np.pi / _nseg) / (2 * np.pi) * nth)) % nth
    pa_ = np.array([r1_ * math.cos(th_), r1_ * math.sin(th_)]); pb_ = np.array([prof_rho[_ri[1], i2_] * math.cos(th_ + 2 * np.pi / _nseg), prof_rho[_ri[1], i2_] * math.sin(th_ + 2 * np.pi / _nseg)])
    chord_ = 1.3 * np.linalg.norm(pb_ - pa_)
    ta_ = math.atan2(r1_ - r0_, z1_ - z0_)            # the wall's lean away from vertical
    L_ = 1.0
    # box frame: x out of the wall, y along it, z up the slope
    Rb_ = _Rot.from_euler("ZY", [th_, -ta_])
    mid_ = np.array([cx + 0.5 * (r0_ + r1_) * math.cos(th_), cy + 0.5 * (r0_ + r1_) * math.sin(th_), 0.5 * (z0_ + z1_)])
    centre_ = mid_ + Rb_.apply([0.045 - 2 * d, 0, 0.12])
    qx_, qy_, qz_, qw_ = Rb_.as_quat()
    scene.add_entity(gs.morphs.Box(pos=tuple(centre_), size=(0.09, chord_, L_), quat=(qw_, qx_, qy_, qz_), fixed=True, visualization=False), material=hidden(0.45))
scene.add_entity(gs.morphs.Box(pos=(0.0, 0.0, -0.05), size=(8.0, 8.0, 0.1), fixed=True, visualization=False), material=hidden(0.6))
rigid_kw = dict(rho=1000.0, friction_rolling=0.0005, friction_torsional=0.001, needs_coup=False, sdf_min_res=16, sdf_max_res=64)
float_ent = car_ent = None
if not a.no_float:
    kw = dict(pos=tuple(float_pos0)); kw.update(dict(euler=(0, 0, a.float_yaw)) if float_quat0 is None else dict(quat=tuple(float_quat0)))
    float_ent = scene.add_entity(gs.morphs.Mesh(file=str(ASSET("procedural_float/float_collision.obj")), fixed=False, convexify=True,
                                                decompose_object_error_threshold=float("inf"), visualization=False, **kw),
                                 material=gs.materials.Rigid(friction=0.65, sdf_cell_size=0.004, **rigid_kw))
if not a.no_car:
    # released above the float's place, with or without the float
    car_start = (cx + a.float_offset[0] + a.car_offset[0], cy + a.float_offset[1] + a.car_offset[1], a.release_z)
    car_kw = dict(pos=tuple(st["car_pos"]), quat=tuple(st["car_quat"])) if a.resume_from else dict(pos=car_start, euler=tuple(a.car_euler))
    car_ent = scene.add_entity(gs.morphs.Mesh(file=str(ASSET("amg_vision_gt/collision.obj")), **car_kw,
                                              fixed=False, convexify=True, decompose_object_error_threshold=0.05, visualization=False),
                               material=gs.materials.Rigid(friction=0.72, sdf_cell_size=0.002, **rigid_kw))
ghost_parts = [tub_ghost] + ([float_ghost] if float_ent else []) + ([car_ghost] if car_ent else [])
ghost_body = np.concatenate([np.full(len(g), i) for i, g in enumerate(ghost_parts)])
n_ghost = len(ghost_body)
liquid = scene.add_entity(gs.morphs.Nowhere(n_particles=n_fluid), material=gs.materials.SPH.Liquid(rho=998.0, mu=a.mu, gamma=0.0, sampler="regular"))
gho = scene.add_entity(gs.morphs.Nowhere(n_particles=n_ghost), material=gs.materials.SPH.Liquid(rho=998.0, mu=a.mu, gamma=0.0, sampler="regular"))
links = [carrier.links[0].idx] + ([float_ent.links[0].idx] if float_ent else []) + ([car_ent.links[0].idx] if car_ent else [])
mass_list = [0.0] + ([a.float_inertia] if float_ent else []) + ([a.car_mass] if car_ent else [])
mass_true = [0.0] + ([a.float_mass] if float_ent else []) + ([a.car_mass] if car_ent else [])
omega_list = [1.0] + ([a.float_omega] if float_ent else []) + ([a.car_omega] if car_ent else [])
contact_max = [0.0] + ([3 * a.car_mass * 9.81] if float_ent else []) + ([3 * a.car_mass * 9.81] if car_ent else [])
coupling.CONFIG.update(n_fluid=n_fluid, ghost_local=np.zeros((n_ghost, 3)), ghost_psi=np.full(n_ghost, V), ghost_body=ghost_body, body_links=links,
                       momentum_error_avg=a.momentum_avg, momentum_error_max=a.momentum_max, position_error_avg=a.position_avg,
                       max_density_error_max=a.position_max, body_mass=mass_list, body_mass_true=mass_true, body_omega=omega_list, body_contact_max=contact_max,
                       warm_omega=a.warm_omega, warm_rise=a.warm_rise * 9.81 * sp, warm_fall=a.warm_fall, still_speed=a.still_speed, rho_interior=a.rho_interior, compaction_rate=a.compaction, speed_cap=a.speed_cap, momentum_max_iters=a.momentum_iters)
t0 = time.perf_counter(); scene.build(); t_build = time.perf_counter() - t0
sph = scene.sim.sph_solver
if float_ent: float_ent.set_mass(a.float_inertia)
if car_ent: car_ent.set_mass(a.car_mass)
_inert = scene.sim.rigid_solver.dyn_info.links.inertial_i.to_numpy()
_Iinv = np.ones((len(links), 3))
for b_i, ent_ in enumerate([carrier] + ([float_ent] if float_ent else []) + ([car_ent] if car_ent else [])):
    if b_i > 0:
        _Iinv[b_i] = 1.0 / np.diag(_inert[ent_.links[0].idx].reshape(3, 3))
        print(f"body {b_i}: link-frame inertia {1 / _Iinv[b_i]}", flush=True)
sph.body_Iinv.from_numpy(_Iinv.astype(np.float32))
print("masses", None if not float_ent else float(float_ent.get_mass()), None if not car_ent else float(car_ent.get_mass()), "build", round(t_build, 1), flush=True)


# ---------------------------------------------------------------- ghosts in their links' frames (a free mesh body's link sits at its COM on its principal axes)
from scipy.spatial.transform import Rotation
def wxyz(q):
    return Rotation.from_quat([q[1], q[2], q[3], q[0]])


ls = scene.sim.rigid_solver.dyn_state.links
_lp, _lq = ls.pos.to_numpy(), ls.quat.to_numpy()
def link_local(ent, pts, static=False):
    li = ent.links[0].idx
    lp = _lp[li].reshape(-1)[:3]; lq = _lq[li].reshape(-1)[:4]
    if static:
        world = pts
    else:
        p = ent.get_pos().cpu().numpy().reshape(-1)[:3].astype(float); q = ent.get_quat().cpu().numpy().reshape(-1)[:4].astype(float)
        world = wxyz(q).apply(pts) + p
    return wxyz(lq).inv().apply(world - lp), world


g_local, g_world = [], []
for ent, pts, st_ in [(carrier, tub_ghost, True)] + ([(float_ent, float_ghost, False)] if float_ent else []) + ([(car_ent, car_ghost, False)] if car_ent else []):
    l_, w_ = link_local(ent, pts, st_); g_local.append(l_); g_world.append(w_)
sph.g_local.from_numpy(np.concatenate(g_local).astype(np.float32))
gho.set_particles_pos(np.concatenate(g_world).astype(np.float32)); gho.set_particles_vel(np.zeros((n_ghost, 3), np.float32))
gho.set_particles_active(np.ones(n_ghost, bool))
liquid.set_particles_pos(np.asarray(water, np.float32)); liquid.set_particles_vel(np.asarray(water_vel0, np.float32))
active0 = st["active"] if a.resume_from else np.ones(n_fluid, bool)
liquid.set_particles_active(active0)
# the pressure estimate starts hydrostatic
_all = np.concatenate([np.asarray(water, np.float64), np.concatenate(g_world)])
_kb = np.zeros((sph._n_particles, 1), np.float32)
_kb[:, 0] = -9.81 * np.clip(a.level - _all[:, 2], 0, None)
if a.mode == "run" and "k_bar" in st:               # the saved pressure, solids included (a car joins the end, in the air)
    _kb[:, 0] = 0.0
    _kb[:len(st["k_bar"]), 0] = st["k_bar"]
sph.k_bar.from_numpy(_kb)
if a.resume_from:                                   # set_particles_* resets rigid velocities: set them last
    if float_ent: float_ent.set_dofs_velocity(np.r_[st["float_vel"], st["float_ang"]].astype(np.float32))
    if car_ent: car_ent.set_dofs_velocity(np.r_[st["car_vel"], st["car_ang"]].astype(np.float32))
elif car_ent:
    car_ent.set_dofs_velocity(np.array((0, 0, 0, *a.car_ang_vel), np.float32))


def change_density(rho):
    """The liquid's motion does not depend on its density; the force on the bodies does, through the particle mass. Volumes,
    the pressure estimate (k = -p / rho) and the water's optics stay."""
    sph.particles_info.mass.fill(float(sph._particle_volume) * rho)
    sph.particles_info_reordered.mass.fill(float(sph._particle_volume) * rho)


# ---------------------------------------------------------------- diagnostics
def pose(ent):
    if ent is None:
        return np.zeros(3), np.array([1.0, 0, 0, 0]), np.zeros(3), np.zeros(3)
    return tuple(g().cpu().numpy().reshape(-1).astype(np.float64) for g in (ent.get_pos, ent.get_quat, ent.get_vel, ent.get_ang))


def far_surface(p, centre):
    """still-water level: median over 2 cm columns (away from the bodies) of the top particle, plus half a spacing"""
    rr = np.hypot(p[:, 0] - centre[0], p[:, 1] - centre[1])
    zs_, rim_ = tub_surface(p[:, 0], p[:, 1])
    m = (rr > 0.3) & (rim_ < 0.75) & (p[:, 2] < a.level + 0.2)
    if m.sum() < 100:
        return float("nan")
    ij = np.floor(p[m, :2] / 0.02).astype(np.int64); key = ij[:, 0] * 100000 + ij[:, 1]
    order = np.lexsort((p[m, 2], key)); key_s = key[order]; last = np.r_[key_s[1:] != key_s[:-1], True]
    return float(np.median(p[m, 2][order][last])) + 0.5 * sp


def trapped(p):
    """Water with no room left: under a solid that has come within 1.5 spacings of the ceramic, or inside a solid resting there.
    It would stay crushed, and the solver would spend every iteration on it; in a real tub it has been squeezed out."""
    out = np.zeros(len(p), bool)
    for ent, pts in ((float_ent, _fv), (car_ent, None if car_ent is None else np.asarray(car_mesh.vertices))):
        if ent is None:
            continue
        pos_, quat_ = pose(ent)[:2]
        if pos_[2] > 0.26:
            continue
        w = wxyz(quat_).apply(pts) + pos_
        lo_ = w[:, :2].min(0)
        nx_, ny_ = (np.ceil((w[:, :2].max(0) - lo_) / sp).astype(int) + 1).tolist()
        bot, top = np.full((nx_, ny_), np.inf), np.full((nx_, ny_), -np.inf)
        wi = ((w[:, :2] - lo_) / sp).astype(int)
        np.minimum.at(bot, (wi[:, 0], wi[:, 1]), w[:, 2]); np.maximum.at(top, (wi[:, 0], wi[:, 1]), w[:, 2])
        cand = np.flatnonzero((p[:, 0] >= lo_[0]) & (p[:, 1] >= lo_[1]) & (p[:, 0] < lo_[0] + nx_ * sp) & (p[:, 1] < lo_[1] + ny_ * sp) & (p[:, 2] < top[np.isfinite(top)].max()))
        if len(cand) == 0:
            continue
        ci_ = ((p[cand, :2] - lo_) / sp).astype(int)
        b_, t_ = bot[ci_[:, 0], ci_[:, 1]], top[ci_[:, 0], ci_[:, 1]]
        zs_, _ = tub_surface(p[cand, 0], p[cand, 1])
        # under the solid's inner part only: water beside it has room, and would flow in to be removed for ever
        from scipy.ndimage import binary_erosion
        zg_, _ = tub_surface(lo_[0] + (np.arange(nx_) + 0.5)[:, None].repeat(ny_, 1).ravel() * sp, lo_[1] + (np.arange(ny_) + 0.5)[None, :].repeat(nx_, 0).ravel() * sp)
        tight = binary_erosion(np.isfinite(bot) & (bot - zg_.reshape(nx_, ny_) < 1.5 * sp), iterations=1)
        no_room = tight[ci_[:, 0], ci_[:, 1]] & (p[cand, 2] < b_ + 0.5 * sp)
        out[cand[no_room]] = True
    return out


rows = []
t_sim = time.perf_counter()
active = active0.copy()
if a.mode == "run":
    (a.out / "particles").mkdir(exist_ok=True)
writer = None
total_frames = a.relax_frames if a.mode == "relax" else a.frames
first = 1
density_now = 998.0
if a.resume_from:
    first = a.resume_frame
    src_log = json.loads((a.resume_from / "sim_log.json").read_text())
    rows.extend(src_log["frames"][:first - 1])
    for k_ in range(1, first):
        link_ = a.out / "particles" / f"frame_{k_:04d}.npz"
        if not link_.exists():
            link_.symlink_to(os.path.relpath((a.resume_from / "particles" / f"frame_{k_:04d}.npz").resolve(), link_.parent.resolve()))
for f in range(first, total_frames + 1):
    t_f = time.perf_counter()
    if a.density_after is not None and density_now != a.density_after and (f - 1) / a.fps >= a.density_time - 1e-9:
        change_density(a.density_after)
        density_now = a.density_after
        print(f"density {a.density_after} kg/m3 from frame {f}", flush=True)
    if f > first:
        for _ in range(a.steps_per_frame):
            scene.step()
            if a.debug_from and f >= a.debug_from:
                _fp, _fq, _fv, _fw = pose(float_ent); _cp, _cq, _cv, _cw = pose(car_ent)
                print("STEP", f, "float z %.4f v %s w %s | car z %.4f v %s w %s | F %s | iters %s" % (_fp[2], np.round(_fv, 3), np.round(_fw, 2), _cp[2], np.round(_cv, 3), np.round(_cw, 2),
                      np.round(sph.body_Fp.to_numpy().reshape(-1, 3)[1:, 2], 1), sph.iter_counts), flush=True)
    p = liquid.get_particles_pos().cpu().numpy().reshape(-1, 3)
    v = liquid.get_particles_vel().cpu().numpy().reshape(-1, 3)
    if not (np.isfinite(p).all() and np.isfinite(v).all()):
        _bad = ~np.isfinite(p).all(1)
        print("NONFINITE", int(_bad.sum()), "float", pose(float_ent)[0], "car", pose(car_ent)[0], flush=True)
        raise RuntimeError(f"non-finite state at frame {f}")
    fp, fq, fv, fw = pose(float_ent); cp, cq, cv, cw = pose(car_ent)
    # water that leaves over the rim is gone: it would pile on the domain floor under the room's floor
    _, rim_now = tub_surface(p[:, 0], p[:, 1])
    gone = active & (((rim_now > 1.0) & (p[:, 2] < 0.58)) | trapped(p))
    if gone.any():
        active[gone] = False
        ids = torch.as_tensor(np.flatnonzero(gone), device=gs.device, dtype=gs.tc_int)
        liquid.set_particles_active(torch.zeros(len(ids), dtype=torch.bool, device=gs.device), ids)
        if float_ent: float_ent.set_dofs_velocity(np.r_[fv, fw].astype(np.float32))
        if car_ent: car_ent.set_dofs_velocity(np.r_[cv, cw].astype(np.float32))
        sph.body_measure = 0
    act = active
    s = np.linalg.norm(v[act], axis=1)
    level = far_surface(p[act], fp if float_ent else (cx, cy))
    it = sph.iter_counts; sub = max(1, it[2]); sph.iter_counts = [0, 0, 0, 0]
    F = sph.body_force_log / max(1, sph.body_force_n); sph.body_force_log = np.zeros_like(sph.body_force_log); sph.body_force_n = 0
    row = {"frame": f, "t": round((f - 1) / a.fps, 4), "rho": density_now, "level": round(level, 5), "vmax": round(float(s.max()), 3), "vp99": round(float(np.percentile(s, 99)), 4),
           "zmax": round(float(p[act, 2].max()), 4), "lost": int((~active).sum()),
           "iters_div_mom_pos": [round(it[0] / sub, 1), round(it[1] / sub, 1), round(it[3] / sub, 1)]}
    if float_ent:
        tilt = 2 * math.degrees(math.atan2(math.hypot(fq[1], fq[2]), math.hypot(fq[0], fq[3])))
        b_ = 1
        row.update(float_z=round(float(fp[2]), 5), float_vz=round(float(fv[2]), 3), tilt=round(tilt, 2), draft_mm=round((level - (fp[2] + zmin)) * 1e3, 2),
                   float_Fz_over_W=round(float(F[b_, 2]) / (a.float_mass * 9.81), 3))
    if car_ent:
        row.update(car_z=round(float(cp[2]), 5), car_vz=round(float(cv[2]), 3), car_Fz_over_W=round(float(F[-1, 2]) / (a.car_mass * 9.81), 3))
    row["sec"] = round(time.perf_counter() - t_f, 1)
    rows.append(row)
    print(json.dumps(row), flush=True)
    if a.mode == "relax":
        v_d = v * a.relax_damp
        liquid.set_particles_vel(v_d)
        if float_ent:
            float_ent.set_dofs_velocity((0.7 * np.r_[fv, fw]).astype(np.float32))
            sph.body_measure = 0
    else:
        if writer is not None:
            writer.join()
        writer = threading.Thread(target=np.savez, args=(a.out / "particles" / f"frame_{f:04d}.npz",), kwargs=dict(
            water_pos=p.astype(np.float32), water_vel=v.astype(np.float16), active=active, water_rest_density=np.float32(density_now),
            tray_pos=fp, tray_quat_wxyz=fq, tray_vel=fv, tray_ang=fw, robot_pos=cp, robot_quat_wxyz=cq, robot_vel=cv, robot_ang=cw))
        writer.start()
        if f in a.checkpoint_frames:
            np.savez(a.out / f"ckpt_{f:04d}.npz", water_pos=p.astype(np.float32), water_vel=v.astype(np.float32), active=active, dx=d,
                     float_pos=fp, float_quat=fq, float_vel=fv, float_ang=fw, car_pos=cp, car_quat=cq, car_vel=cv, car_ang=cw,
                     k_bar=sph.k_bar.to_numpy().reshape(-1).astype(np.float32))
    json.dump({"args": {k: (str(x) if isinstance(x, Path) else x) for k, x in vars(a).items()}, "n_fluid": n_fluid, "n_ghost": n_ghost,
               "build_sec": t_build, "archimedes_draft_float_m": draft0, "archimedes_draft_loaded_m": draft_car, "float_zmin_m": zmin,
               "sim_sec": time.perf_counter() - t_sim, "frames": rows}, open(a.out / "sim_log.json", "w"), indent=1)
if writer is not None:
    writer.join()
if a.mode == "relax":
    fp, fq, _, _ = pose(float_ent)
    np.savez(a.out / "settled.npz", water_pos=p.astype(np.float32), water_vel=np.zeros_like(p), float_pos=fp, float_quat=fq, dx=d,
             k_bar=sph.k_bar.to_numpy().reshape(-1).astype(np.float32))
print(f"done {time.perf_counter() - t_sim:.0f}s")
