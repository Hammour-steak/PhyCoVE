"""Two-way coupled faucet stream on the resting elastic duck (Genesis 1.4.3, MPM duck + DFSPH water).

Duck: neo-Hookean MPM solid (density 200 kg/m3), settled on the basin floor before the tap opens. Water: DFSPH
from the measured aerator at 4.5 L/min. Coupling: the pool scene's accepted pressure operator
(create_boundary_solver in ../elastic_fluid_duck/simulate_elastic_fluid_duck.py: ghost SPH particles carried by
the MPM duck through an affine material map, equal and opposite pressure impulses scattered back onto the MPM
grid); Genesis's built-in MPM-SPH coupler stays off. Changes to the operator: its convergence error is averaged
over the water emitted so far, water-water cohesion and a momentum-conserving water-duck viscous coupling are
restored, and the stencil checks run with float32-sized tolerances (see the constants).

Defaults are the base case (2 kPa duck, 4.5 L/min). The edits change --young or --inflow-velocity; the MPM
substeps follow the elastic wave speed (CFL 0.19, at least 16):
    python simulate_bathroom_sink_duck_neospace.py --duck-solid duck_solid_world.obj \
        --ghost-mesh duck_shell_world.obj --out genesis_sim.npz [--young 6e4]
"""
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
import copy
import importlib.util
import json
import math
import time
from pathlib import Path

import numpy as np


FPS = 24
BASIN_FLOOR_Z = 0.8052
BASIN_INTERIOR = ((0.545, 1.370), (0.853, 1.965))
SPH_TOP_Z = 1.010
AERATOR_XYZ = (0.588, 1.674, 0.981)
STREAM_DIAMETER_M = 0.013
FLOW_L_MIN = 4.5
STREAM_SPEED = FLOW_L_MIN / 60000.0 / (math.pi * (STREAM_DIAMETER_M / 2) ** 2)
WATER_DENSITY = 1000.0
WATER_KINEMATIC_VISCOSITY = 1.0e-6

SPH_PARTICLE_M = 0.0015
# A 1.5 mm SPH stream cannot resolve surface tension, so cohesion alone leaves it in loose beads; a higher
# viscosity and viscous coupling to the duck keep it whole.
WATER_SPH_VISCOSITY = 3.0e-4
WATER_COHESION = 5.0e-4
BOUNDARY_FRICTION = 0.5
MPM_GRID_M = 0.003
MPM_PARTICLE_M = 0.003            # default quadrature: one particle per grid cell
YOUNG_MODULUS_PA = 2.0e3
POISSON_RATIO = 0.45
DUCK_DENSITY = 200.0
STEPS_PER_FRAME = 100
MPM_CFL = 0.19
# At 2 kPa, 4 substeps (CFL-sufficient) let the stream peel the forehead's surface particles within 1.7 s.
MIN_SUBSTEPS = 16
MPM_PADDING_CELLS = 3
MPM_MARGIN_M = 0.05                # room around the resting duck for it to sag and spread into
WALL_INSET_M = 0.002               # the duck's side walls stand this far inside the water's, so its ghosts stay in
SETTLE_SECONDS = 0.5
CONTACT_LAYER_M = 1.5 * MPM_GRID_M
VELOCITY_RETAINED_PER_SECOND = 0.3
# Simulate near the origin: the operator checks its material map to 2e-5 m in float32, and at ~1.7 m from the
# origin the weights' rounding alone exceeds that. Everything is shifted by SIM_ORIGIN and shifted back on output.
SIM_ORIGIN = np.array([0.699, 1.6675, BASIN_FLOOR_Z])
# The pool operator rejects a material map whose weights miss partition of unity / first-moment exactness by
# 2e-5. Its tolerances were set for a 12.5 mm MPM grid with ghost particles sparser than material particles;
# here (3 mm grid, denser ghosts, map condition ~34) float32 rounding alone reaches ~2e-5, so the same checks
# run with 1e-4 (3% of a cell for the moment) and their peaks are reported. (Eight duck particles per cell,
# --mpm-particle 0.0015, exceed it once the stream lands: 2e-4 at 0.1 s; that quadrature also runs 4.4x slower.)
MAP_WEIGHT_TOLERANCE = 1.0e-4
MAP_LOCAL_WIDTH = 20              # stencil box (cells); a soft or soft-cored duck stretches a ghost's stencil past 8-12
# Water deeper inside the duck than its ghost boundary means the boundary has opened up. Water at the duck's surface
# has at most ~73 duck particles within 9 mm in the 2 kPa runs, the duck's interior ~107.
INSIDE_RADIUS_M = 0.009
INSIDE_NEIGHBOURS = 90
ADHESION_HOLDER = [0.0]          # read by the solver's kernel at compile time
FRICTION_HOLDER = [0.0]
MAP_MOMENT_TOLERANCE_M = 1.0e-4


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pool-simulate", type=Path, default=Path(__file__).resolve().parent.parent / "elastic_fluid_duck" / "simulate_elastic_fluid_duck.py",
                        help="module providing create_boundary_solver()")
    parser.add_argument("--duck-solid", type=Path, required=True)
    parser.add_argument("--ghost-mesh", type=Path, help="closed shell under the duck surface for the ghost boundary (default: the solid)")
    parser.add_argument("--gamma", type=float, default=WATER_COHESION, help="water-water cohesion (Genesis SPH surface tension coefficient)")
    parser.add_argument("--adhesion", type=float, default=0.0, help="water-duck adhesion (Akinci 2013 kernel, momentum conserving)")
    parser.add_argument("--mu", type=float, default=WATER_SPH_VISCOSITY, help="SPH kinematic viscosity (m^2/s)")
    parser.add_argument("--sph-particle", type=float, default=SPH_PARTICLE_M)
    parser.add_argument("--boundary-friction", type=float, default=BOUNDARY_FRICTION, help="water-duck viscous coupling, as a multiple of the water viscosity")
    parser.add_argument("--young", type=float, default=YOUNG_MODULUS_PA, help="duck Young modulus (Pa)")
    parser.add_argument("--inflow-velocity", type=float, default=STREAM_SPEED,
                        help="outlet speed of the 13 mm stream (m/s); the flow rate scales with it")
    parser.add_argument("--inflow-change-frame", type=int,
                        help="first output frame integrated with --inflow-velocity-after (1-based; frame 49 starts at 2 s)")
    parser.add_argument("--inflow-velocity-after", type=float,
                        help="outlet speed from --inflow-change-frame onward; zero closes the inlet without freezing existing water")
    parser.add_argument("--no-duck", action="store_true", help="DELETE duck: the stream alone")
    parser.add_argument("--no-water", action="store_true", help="DELETE water: the faucet releases nothing")
    parser.add_argument("--core-young", type=float,
                        help="Young modulus (Pa) of the duck below its skin; default: the same as --young (one material)")
    parser.add_argument("--skin-thickness", type=float, default=0.010,
                        help="particles shallower than this keep --young when --core-young is given (m)")
    parser.add_argument("--poisson", type=float, default=POISSON_RATIO, help="duck Poisson ratio (rubber is nearly incompressible, ~0.49)")
    parser.add_argument("--substeps", type=int, help="substeps per 1/2400 s step (default: from the elastic wave speed)")
    parser.add_argument("--mpm-particle", type=float, default=MPM_PARTICLE_M,
                        help="duck particle spacing on the 3 mm grid; 0.0015 puts 8 particles in a cell, which keeps a "
                             "stretched cell from emptying (numerical fracture)")
    parser.add_argument("--mpm-mass", type=float,
                        help="total duck mass (kg) to keep when refining the particles (the default spacing gives 0.0927)")
    parser.add_argument("--map-width", type=int, default=MAP_LOCAL_WIDTH,
                        help="stencil box of the ghost material map (cells); large collapses need more")
    parser.add_argument("--settle-seconds", type=float, default=SETTLE_SECONDS, help="duck settles on the floor before the tap opens")
    parser.add_argument("--seconds", type=float, default=4.0)
    parser.add_argument("--out", type=Path, default=Path("genesis_sim.npz"))
    parser.add_argument("--source-branch-out", type=Path,
                        help="timed inlet edit only: also write the unedited continuation (the source case) to this .npz. "
                             "Both come from one run: the complete solver state at the start of --inflow-change-frame is "
                             "copied, the source runs on, the copy is restored and the edit runs on, so output frames "
                             "1..k-1 are the same data in both files")
    parser.add_argument("--branch-replay-frames", type=int, default=2,
                        help="with --source-branch-out: restore the copied state this many times and re-run the first "
                             "branched source frame, to check the restore against the live source (and against GPU "
                             "run-to-run variation)")
    return parser.parse_args()


def _is_field(value):
    import torch
    return (hasattr(value, "to_numpy") and hasattr(value, "from_numpy") and hasattr(value, "shape")
            and not isinstance(value, (np.ndarray, torch.Tensor)))


def _is_plain(value, depth=0):
    if value is None or isinstance(value, (bool, int, float, str, np.integer, np.floating)):
        return True
    if depth > 6:
        return False
    if isinstance(value, (list, tuple)):
        return all(_is_plain(item, depth + 1) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, (str, int)) and _is_plain(item, depth + 1) for key, item in value.items())
    return False


def _same(a, b):
    if isinstance(a, dict) or isinstance(b, dict):
        return isinstance(a, dict) and isinstance(b, dict) and a.keys() == b.keys() and all(_same(a[k], b[k]) for k in a)
    a, b = np.asarray(a), np.asarray(b)
    return a.shape == b.shape and a.dtype == b.dtype and a.tobytes() == b.tobytes()


def _nbytes(a):
    return sum(_nbytes(v) for v in a.values()) if isinstance(a, dict) else np.asarray(a).nbytes


class SolverSnapshot:
    """The complete state of the given objects: every quadrants field (to_numpy/from_numpy, all local substep frames),
    every torch tensor attribute and every plain-data Python attribute (counters, emitter cursor, diagnostics)."""

    def __init__(self, holders, required):
        import torch
        self.items, self.skipped = [], []
        for obj in holders:
            fields, plain, tensors = {}, {}, {}
            for name, value in list(vars(obj).items()):
                if _is_field(value):
                    try:
                        fields[name] = value.to_numpy()
                    except Exception as error:      # e.g. an unallocated field of a disabled coupling
                        if any(obj is r for r in required):
                            raise RuntimeError(f"cannot copy {type(obj).__name__}.{name}: {error}") from error
                        self.skipped.append(f"{type(obj).__name__}.{name}")
                elif isinstance(value, torch.Tensor):
                    tensors[name] = value.detach().clone()
                elif _is_plain(value):
                    plain[name] = copy.deepcopy(value)
            self.items.append((obj, fields, plain, tensors))

    def restore(self):
        for obj, fields, plain, tensors in self.items:
            for name, array in fields.items():
                getattr(obj, name).from_numpy(array)
            for name, tensor in tensors.items():
                getattr(obj, name).copy_(tensor)
            for name, value in plain.items():
                setattr(obj, name, copy.deepcopy(value))

    def mismatched(self):
        import torch
        bad = []
        for obj, fields, plain, tensors in self.items:
            for name, array in fields.items():
                if not _same(getattr(obj, name).to_numpy(), array):
                    bad.append(f"{type(obj).__name__}.{name}")
            for name, tensor in tensors.items():
                if not torch.equal(getattr(obj, name), tensor):
                    bad.append(f"{type(obj).__name__}.{name}")
            for name, value in plain.items():
                now = json.dumps(getattr(obj, name), sort_keys=True, default=str)
                if now != json.dumps(value, sort_keys=True, default=str):
                    bad.append(f"{type(obj).__name__}.{name}")
        return bad

    def summary(self):
        return {"objects": [type(obj).__name__ for obj, *_ in self.items],
                "fields": sum(len(f) for _, f, _, _ in self.items),
                "plain_attributes": sum(len(p) for _, _, p, _ in self.items),
                "tensors": sum(len(t) for _, _, _, t in self.items),
                "field_megabytes": round(sum(_nbytes(a) for _, f, _, _ in self.items for a in f.values()) / 2 ** 20, 1),
                "skipped": self.skipped}


def chunked_signed_distance(signed_distance, chunk=5000):
    """igl.signed_distance in slices of points: Genesis samples a mesh's particles with one call whose memory grows with
    points x faces (about 60 GB for the duck at 1.5 mm); the result is identical, and Genesis caches it."""
    def wrapped(points, *args, **kwargs):
        if len(points) <= chunk:
            return signed_distance(points, *args, **kwargs)
        parts = [signed_distance(points[i:i + chunk], *args, **kwargs) for i in range(0, len(points), chunk)]
        return tuple(np.concatenate([part[j] for part in parts]) for j in range(len(parts[0])))
    return wrapped


def mpm_substeps(young, poisson):
    wave_speed = math.sqrt(young * (1 - poisson) / (DUCK_DENSITY * (1 + poisson) * (1 - 2 * poisson)))
    step_dt = 1.0 / FPS / STEPS_PER_FRAME
    return max(MIN_SUBSTEPS, math.ceil(step_dt * wave_speed / (MPM_CFL * MPM_GRID_M)))


def rigid_rotation_deg(a, b):
    a = a - a.mean(0)
    b = b - b.mean(0)
    u, _, vt = np.linalg.svd(a.T @ b)
    r = (u @ vt).T
    return float(np.degrees(np.arccos(np.clip((np.trace(r) - 1) / 2, -1, 1))))


def emitter_boundary_solver(pool, adhesion=0.0):
    """The pool operator, with convergence averaged over the emitted (active) water particles."""
    qd, gs = pool.qd, pool.gs
    base = pool.create_boundary_solver()

    @qd.data_oriented
    class EmitterPressureBoundarySPH(base):
        def allocate_material_fields(self):
            # Same fields as the pool operator, with a MAP_LOCAL_WIDTH stencil box instead of 16: at a 3 mm
            # MPM grid the 16 mapped particles' stencils span 6 cells at rest (7-8 under the stream at 2 kPa),
            # and the operator still rejects any ghost whose support would not fit.
            super().allocate_material_fields()
            self.local_width = MAP_LOCAL_WIDTH
            self.coalesced_weights = qd.field(gs.qd_float, shape=(self.n_ghost, self.local_width ** 3, self._B))
            self.material_grid_extent = qd.Vector.field(3, gs.qd_int, shape=(self.n_ghost, self._B))

        def build(self):
            super().build()
            self.n_active_fluid = 1
            self.referenced = qd.field(qd.i32, shape=(self.mpm.n_particles,))
            self.map_error_peaks = [0.0, 0.0]

        def initialize_mapping(self):
            result = super().initialize_mapping()
            used = np.zeros(self.mpm.n_particles, dtype=np.int32)
            used[np.unique(self.map_ids.to_numpy())] = 1
            self.referenced.from_numpy(used)
            result['material_particles_referenced_by_ghosts'] = int(used.sum())
            return result

        @qd.func
        def _task_compute_non_pressure_forces(self, i, j, ret: qd.template(), i_b):
            # The pool operator keeps only the water-water viscosity here, which drops Genesis's surface tension
            # term. At this scale cohesion and wetting hold the stream and the film together, so both return:
            # water-water cohesion with Genesis's own form, and the same form toward the duck's ghost boundary.
            d = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            effective = qd.max(d.norm(), self._particle_size)
            mass_i = self.particles_info_reordered[i, i_b].mass
            mass_j = self.particles_info_reordered[j, i_b].mass
            if self.is_fluid(j, i_b):
                v = self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
                viscosity = self.particles_info_reordered[i, i_b].mu
                density = self.particles_reordered[j, i_b].rho
                ret += 10 * viscosity * (mass_j / qd.max(density, 1e-06)) * v.dot(d) / (d.norm_sqr() + 0.01 * self._support_radius ** 2) * self.cubic_kernel_derivative(d)
                ret -= self.particles_info_reordered[i, i_b].gamma * mass_j / mass_i * d * self.cubic_kernel(effective)
            else:
                # Akinci et al. 2013 adhesion: attracts only between half and one support radius, so it never
                # pulls water into the boundary; the equal and opposite impulse goes to the duck through the
                # same ghost-to-material scatter as the pressure impulses (momentum is conserved).
                r = d.norm()
                h = self._support_radius
                acc = qd.Vector.zero(gs.qd_float, 3)
                if r > 0.5 * h and r <= h:
                    shape = 0.007 / h ** 3.25 * qd.pow(qd.max(-4.0 * r * r / h + 6.0 * r - 2.0 * h, 0.0), 0.25)
                    acc = -ADHESION_HOLDER[0] * mass_j * shape * d / r
                # Viscous coupling to the moving duck surface (no-slip tendency), same form as the water viscosity.
                v = self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
                acc += FRICTION_HOLDER[0] * 10 * self.particles_info_reordered[i, i_b].mu * (mass_j / self._density0) * v.dot(d) / (d.norm_sqr() + 0.01 * self._support_radius ** 2) * self.cubic_kernel_derivative(d)
                ret += acc
                ghost = self.original_id[j, i_b] - self.n_fluid
                self.impulse[ghost, i_b] -= mass_i * acc * self._substep_dt

        # Performance-only overrides; the arithmetic is the pool operator's.
        @qd.kernel
        def scatter_material_pressure_impulses(self, f: qd.i32):
            # Ghosts away from the water carry no impulse; skipping them changes no sum.
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                impulse = self.impulse[ghost, batch]
                if self.feedback and impulse.norm_sqr() > 0.0:
                    for k in range(self.grid_count[ghost, batch]):
                        weight = self.grid_weights[ghost, k, batch]
                        grid = self.grid_ids[ghost, k, batch]
                        self.mpm.grid[f, grid, batch].vel_in += weight * impulse * self.mpm.particle_volume_scale
                        self.audit[1] += weight * impulse
                self.impulse[ghost, batch] = qd.Vector.zero(gs.qd_float, 3)

        @qd.kernel
        def predict_native_material_position_rates(self, f: qd.i32):
            # Only material particles that some ghost interpolates from are ever read back.
            for (p, batch) in qd.ndrange(self.mpm.n_particles, self._B):
                if self.referenced[p] and self.mpm.particles_ng[f, p, batch].active:
                    x = self.mpm.particles[f, p, batch].pos
                    base = qd.floor(x * self.mpm.inv_dx - 0.5).cast(gs.qd_int)
                    fx = x * self.mpm.inv_dx - base.cast(gs.qd_float)
                    w = [0.5 * (1.5 - fx) ** 2, 0.75 - (fx - 1) ** 2, 0.5 * (fx - 0.5) ** 2]
                    velocity = qd.Vector.zero(gs.qd_float, 3)
                    for offset in qd.static(qd.grouped(qd.ndrange(3, 3, 3))):
                        grid = base - self.mpm.grid_offset + offset
                        weight = w[offset[0]][0] * w[offset[1]][1] * w[offset[2]][2]
                        if self.mpm.grid[f, grid, batch].mass > gs.EPS:
                            velocity += weight * self.projected_grid_velocity(f, grid, batch)
                    candidate = x + self._substep_dt * velocity
                    (projected, _) = self.mpm.boundary.impose_pos_vel(candidate, velocity)
                    for d in qd.static(range(3)):
                        if projected[d] != candidate[d]:
                            velocity[d] = (projected[d] - x[d]) / self._substep_dt
                    self.material_position_rate[p, batch] = velocity

        @qd.kernel
        def measure_material_extent(self, f: qd.i32):
            # The stencil box each ghost's weights occupy, as assemble_material_mapping lays it out.
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                minimum = qd.Vector([2147483647, 2147483647, 2147483647])
                maximum = qd.Vector([-2147483647, -2147483647, -2147483647])
                for k in range(16):
                    x = self.mpm.particles[f, self.map_ids[ghost, k], batch].pos
                    base = qd.floor(x * self.mpm.inv_dx - 0.5).cast(gs.qd_int) - self.mpm.grid_offset
                    minimum = qd.min(minimum, base)
                    maximum = qd.max(maximum, base + 2)
                self.material_grid_extent[ghost, batch] = qd.min(maximum - minimum, self.local_width - 1)

        @qd.kernel
        def compact_material_mapping(self, f: qd.i32):
            # The pool operator's compaction, visiting only each ghost's own stencil box (same entries in the same
            # order) and clearing what it read, so the weights need no full clear before the next assembly.
            self.mapping_weight_error[None] = 0.0
            self.mapping_moment_error[None] = 0.0
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                count = 0
                total = gs.qd_float(0.0)
                inverse = gs.qd_float(0.0)
                first_moment = qd.Vector.zero(gs.qd_float, 3)
                extent = self.material_grid_extent[ghost, batch]
                for lx in range(extent[0] + 1):
                    for ly in range(extent[1] + 1):
                        for lz in range(extent[2] + 1):
                            flat = (lx * self.local_width + ly) * self.local_width + lz
                            weight = self.coalesced_weights[ghost, flat, batch]
                            if weight != 0.0:
                                grid = self.material_grid_base[ghost, batch] + qd.Vector([lx, ly, lz])
                                self.grid_ids[ghost, count, batch] = grid
                                self.grid_weights[ghost, count, batch] = weight
                                inverse += weight ** 2 * self.mpm.particle_volume_scale / self.mpm.grid[f, grid, batch].mass
                                total += weight
                                first_moment += weight * (grid + self.mpm.grid_offset) * self.mpm.dx
                                count += 1
                                self.coalesced_weights[ghost, flat, batch] = 0.0
                self.grid_count[ghost, batch] = count
                self.boundary_inv_mass[ghost, batch] = inverse
                qd.atomic_max(self.mapping_weight_error[None], qd.abs(total - 1.0))
                error = (first_moment - self.particles[ghost + self.n_fluid, batch].pos).norm()
                qd.atomic_max(self.mapping_moment_error[None], error)
                qd.atomic_max(self.mapping_moment_error_peak[None], error)

        def update_boundary_positions(self, f):
            self.assemble_material_mapping(f)     # the weights were cleared by the previous compaction
            if int(self.mapping_rejections[None]):
                raise RuntimeError('Reject invalid material-grid support; no pose or deformation clamp added.')
            self.measure_material_extent(f)
            self.compact_material_mapping(f)
            weight_error = float(self.mapping_weight_error[None])
            self.map_error_peaks[0] = max(self.map_error_peaks[0], weight_error)
            if weight_error > MAP_WEIGHT_TOLERANCE:
                raise RuntimeError(f'Reject incomplete material-grid pressure support ({weight_error:.2e}).')
            if self.update_material_volumes(f):
                raise RuntimeError('Reject invalid material Jacobian; no volume/deformation clipping.')
            self.predict_native_material_position_rates(f)
            self.gather_material_ghost_velocities(f, 0)
            moment_error = float(self.mapping_moment_error[None])
            self.map_error_peaks[1] = max(self.map_error_peaks[1], moment_error)
            if moment_error > MAP_MOMENT_TOLERANCE_M:
                raise RuntimeError(f'Reject incomplete pressure moment support ({moment_error:.2e} m).')

        @qd.kernel
        def count_active_fluid(self) -> qd.i32:
            count = 0
            for (i, batch) in qd.ndrange(self.n_fluid, self._B):
                if self.particles_ng[i, batch].active:
                    count += 1
            return count

        def substep_pre_coupling(self, f):
            if self.boundary_ready:
                self.n_active_fluid = max(int(self.count_active_fluid()), 1)
            return super().substep_pre_coupling(f)

        def _divergence_solver_iteration(self):
            self._kernel_divergence_solver_iteration()
            self.pressure_to_mpm(self.current_frame)
            self._kernel_compute_density_time_derivative()
            return self._kernel_compute_density_error(0.0) / self.n_active_fluid

        def _density_solve_iteration(self):
            self._kernel_density_solve_iteration()
            self.pressure_to_mpm(self.current_frame)
            self._kernel_compute_density_star()
            return self._kernel_compute_density_error(self._density0) / self.n_active_fluid

    return EmitterPressureBoundarySPH


def emitter_fluid_only_solver(pool):
    """The same water operators with no duck: no MPM material or ghost boundary (as the pool scene's DELETE duck)."""
    qd, gs = pool.qd, pool.gs
    from genesis.engine.solvers.sph_solver import SPHSolver

    @qd.data_oriented
    class EmitterFluidOnlySPH(emitter_boundary_solver(pool)):
        def build(self):
            SPHSolver.build(self)
            assert len(self.entities) == 1 and self.sim.mpm_solver.n_particles == 0
            self.n_fluid, self.n_ghost = self.n_particles, 0
            self.relaxation, self.boundary_relaxation = 0.5, 0.1
            self.feedback = self.enabled = self.boundary_ready = False
            self.original_id = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.near_boundary = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.impulse = qd.Vector.field(3, dtype=gs.qd_float, shape=(1, self._B))   # compiled, never reached
            self.error_particle_id = qd.field(qd.i32, shape=())
            self.error_particle_sample = qd.Vector.field(12, gs.qd_float, shape=())
            self._df_max_div_iters = self._df_max_den_iters = 100
            self.cap_examples = []
            self.current_frame = 0
            self.reset_iteration_diagnostics()
            self.n_active_fluid = 1
            self.map_error_peaks = [0.0, 0.0]

        @qd.func
        def is_fluid(self, index, batch):
            return True

        @qd.func
        def volume(self, index, batch):
            return self._particle_volume

        @qd.func
        def volume_rate_density_term(self, i, j, batch):
            return gs.qd_float(0.0)

        @qd.func
        def factor_pair(self, i, j, ret: qd.template(), batch):
            gradient = -self._particle_volume * self.cubic_kernel_derivative(
                self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            ret[3] += gradient.norm_sqr()
            for k in qd.static(range(3)):
                ret[k] -= gradient[k]

        @qd.func
        def pressure_pair(self, i, j, stiffness, scale, batch):
            gradient = -self._particle_volume * self.cubic_kernel_derivative(
                self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            return -scale * stiffness * gradient

        def pressure_to_mpm(self, f):
            pass                                            # no solid to receive pressure

        def substep_pre_coupling(self, f):
            # The coupled sequence without the boundary update.
            self.n_active_fluid = max(int(self.count_active_fluid()), 1)
            self.current_frame = f
            self._kernel_reorder_particles(f)
            self.reorder_original_ids()
            self.near_boundary.fill(0)
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self._kernel_predict_velocity(f)
            self._density_solve(f)

    return EmitterFluidOnlySPH


def main():
    global MAP_LOCAL_WIDTH
    args = parse_args()
    if (args.inflow_change_frame is None) != (args.inflow_velocity_after is None):
        raise ValueError("--inflow-change-frame and --inflow-velocity-after must be given together")
    if args.inflow_velocity < 0 or (args.inflow_velocity_after is not None and args.inflow_velocity_after < 0):
        raise ValueError("Inlet speeds must be nonnegative")
    if args.inflow_change_frame is not None:
        if args.no_water or not 1 <= args.inflow_change_frame <= int(round(args.seconds * FPS)):
            raise ValueError("A timed inlet edit requires water and a frame inside the clip")
    if args.source_branch_out is not None:
        if args.inflow_change_frame is None or args.inflow_change_frame < 2:
            raise ValueError("--source-branch-out needs a timed inlet edit at frame 2 or later")
        if args.source_branch_out.expanduser().resolve() == args.out.expanduser().resolve():
            raise ValueError("--source-branch-out must differ from --out")
    MAP_LOCAL_WIDTH = args.map_width
    substeps = args.substeps or mpm_substeps(args.young, args.poisson)
    spec = importlib.util.spec_from_file_location("pool_simulate", args.pool_simulate)
    pool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pool)

    import genesis as gs
    import genesis.engine.entities.particle_entity as particle_entity
    import genesis.utils.particle as particle_sampling
    import torch

    gs.init(backend=gs.cuda, precision="32", seed=20261019, logging_level="warning")
    pool._import_runtime()
    particle_sampling.igl.signed_distance = chunked_signed_distance(particle_sampling.igl.signed_distance)
    # Genesis skins an elastic body's visual mesh onto its particles with a dense vertices x particles distance
    # matrix (30 GB at 2 mm particles). The duck is skinned in surface_* instead, so use the path Genesis
    # takes for liquids: no visual vertices.
    entity_init = particle_entity.ParticleEntity.__init__
    def init_without_skinning(self, *args, need_skinning=True, **kwargs):
        entity_init(self, *args, need_skinning=False, **kwargs)
    particle_entity.ParticleEntity.__init__ = init_without_skinning
    import genesis.engine.simulator as simulator
    ADHESION_HOLDER[0] = args.adhesion
    FRICTION_HOLDER[0] = args.boundary_friction
    has_duck, has_water = not args.no_duck, not args.no_water
    assert has_duck or has_water, "nothing to simulate"
    if has_water:                       # with no water Genesis's own (empty) SPH solver is left in place
        simulator.SPHSolver = emitter_boundary_solver(pool) if has_duck else emitter_fluid_only_solver(pool)
    if args.mpm_mass:
        # As the pool scene's refined-quadrature case: the same total mass spread over the finer particles.
        @pool.qd.data_oriented
        class MassPreservingMPM(simulator.MPMSolver):
            def build(self):
                count = sum(entity.n_particles for entity in self.entities)
                self._particle_volume_real = args.mpm_mass / DUCK_DENSITY / count
                self._particle_volume = self._particle_volume_real * self._particle_volume_scale
                super().build()
        simulator.MPMSolver = MassPreservingMPM

    vertices = np.array([list(map(float, l.split()[1:4])) for l in args.duck_solid.read_text().splitlines() if l.startswith("v ")]) - SIM_ORIGIN
    mpm_lower = vertices.min(0) - MPM_MARGIN_M
    mpm_upper = vertices.max(0) + MPM_MARGIN_M
    mpm_lower[2] = -MPM_PADDING_CELLS * MPM_GRID_M
    # The basin's side walls bound the duck too: the MPM domain (whose usable region starts MPM_PADDING_CELLS in)
    # never reaches past the water's. Only a duck that collapses sideways ever meets them.
    padding = MPM_PADDING_CELLS * MPM_GRID_M
    for axis in (0, 1):
        mpm_lower[axis] = max(mpm_lower[axis], BASIN_INTERIOR[0][axis] - SIM_ORIGIN[axis] + WALL_INSET_M - padding)
        mpm_upper[axis] = min(mpm_upper[axis], BASIN_INTERIOR[1][axis] - SIM_ORIGIN[axis] - WALL_INSET_M + padding)
    floor_z = 0.0
    sph_lower = tuple(np.array([BASIN_INTERIOR[0][0], BASIN_INTERIOR[0][1], BASIN_FLOOR_Z]) - SIM_ORIGIN)
    sph_upper = tuple(np.array([BASIN_INTERIOR[1][0], BASIN_INTERIOR[1][1], SPH_TOP_Z]) - SIM_ORIGIN)
    aerator = tuple(np.array(AERATOR_XYZ) - SIM_ORIGIN)
    duck_pos_offset = tuple(-SIM_ORIGIN)
    step_dt = 1.0 / FPS / STEPS_PER_FRAME
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=step_dt, substeps=substeps, gravity=(0.0, 0.0, -9.81), requires_grad=False),
        mpm_options=gs.options.MPMOptions(grid_density=1.0 / MPM_GRID_M, particle_size=args.mpm_particle,
                                          lower_bound=tuple(mpm_lower), upper_bound=tuple(mpm_upper)),
        sph_options=gs.options.SPHOptions(particle_size=args.sph_particle, pressure_solver="DFSPH",
                                          lower_bound=sph_lower, upper_bound=sph_upper),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_mpm=False, rigid_sph=False, rigid_pbd=False,
                                                        rigid_fem=False, mpm_sph=False, mpm_pbd=False,
                                                        fem_mpm=False, fem_sph=False),
        show_viewer=False)
    flow_l_min = args.inflow_velocity * math.pi * (STREAM_DIAMETER_M / 2) ** 2 * 60000.0
    # Keep the source's capacity when turning the tap off: changing allocation before the edit would also
    # change the pre-edit solver. A faster timed inlet needs capacity for its peak speed.
    peak_flow_l_min = max(flow_l_min, (args.inflow_velocity_after or 0.0) * math.pi * (STREAM_DIAMETER_M / 2) ** 2 * 60000.0)
    max_particles = int(peak_flow_l_min / 60000.0 * args.seconds / args.sph_particle ** 3 * 1.5) + 2000
    # Order matters for the operator: water (the emitter) first, then the duck's ghost boundary particles.
    faucet = duck = None
    if has_water:
        faucet = scene.add_emitter(material=gs.materials.SPH.Liquid(rho=WATER_DENSITY, mu=args.mu,
                                                                    gamma=args.gamma, sampler="regular"),
                                   max_particles=max_particles)
    if has_duck and has_water:
        # Ghost boundary particles only in a shell under the surface: water sees them within one kernel radius (4 mm).
        scene.add_entity(morph=gs.morphs.Mesh(file=str(args.ghost_mesh or args.duck_solid), pos=duck_pos_offset, scale=1.0, decimate=False, convexify=False),
                         material=gs.materials.SPH.Liquid(rho=WATER_DENSITY, mu=WATER_KINEMATIC_VISCOSITY, gamma=0.0, sampler="regular"))
    if has_duck:
        duck = scene.add_entity(
            morph=gs.morphs.Mesh(file=str(args.duck_solid), pos=duck_pos_offset, scale=1.0, decimate=False, convexify=False),
            material=gs.materials.MPM.Elastic(E=args.young, nu=args.poisson, rho=DUCK_DENSITY,
                                              model="neohooken", sampler="regular"))
    core_young = args.young if args.core_young is None else args.core_young
    if args.core_young is not None and has_duck:
        # A second material for the same particles: registered with the solver before it compiles, assigned below.
        core_material = gs.materials.MPM.Elastic(E=args.core_young, nu=args.poisson, rho=DUCK_DENSITY,
                                                 model="neohooken", sampler="regular")
        scene.sim.mpm_solver.add_material(core_material)
    tick = time.monotonic()
    scene.build(n_envs=0)
    n_core = 0
    if args.core_young is not None and has_duck:
        # Skin and core are one particle set (the same sampling as the one-material duck); particles deeper than
        # the skin thickness below the duck's surface switch to the core material.
        import igl
        solid = [l.split() for l in args.duck_solid.read_text().splitlines() if l[:2] in ("v ", "f ")]
        verts = np.array([[float(x) for x in l[1:4]] for l in solid if l[0] == "v"]) - SIM_ORIGIN
        polygons = [[int(x.split("/")[0]) - 1 for x in l[1:]] for l in solid if l[0] == "f"]
        faces = np.array([[poly[0], poly[i], poly[i + 1]] for poly in polygons for i in range(1, len(poly) - 1)])
        local = duck.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float64)
        depth = -chunked_signed_distance(igl.signed_distance)(local, verts, faces)[0]
        mpm = scene.sim.mpm_solver
        material_idx = mpm.particles_info.material_idx.to_numpy()
        core = np.zeros(len(material_idx), dtype=bool)
        core[duck._particle_start:duck._particle_start + duck.n_particles] = depth >= args.skin_thickness
        material_idx[core] = core_material.idx
        mpm.particles_info.material_idx.from_numpy(material_idx)
        n_core = int(core.sum())
    solver = scene.sim.sph_solver
    coupled = has_duck and has_water
    mapping = solver.initialize_mapping() if coupled else {"ghost_particles": 0, "max_material_map_support_m": None,
                                                           "material_particles_referenced_by_ghosts": 0,
                                                           "affine_embedding": {"condition_max": 0.0}}
    build_seconds = time.monotonic() - tick

    def duck_pos():
        return duck.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float64) + SIM_ORIGIN

    def duck_contact_and_damping():
        if duck is None:
            return
        vel = duck.get_particles_vel().cpu().numpy().reshape(-1, 3)
        pos = duck_pos()
        vel *= VELOCITY_RETAINED_PER_SECOND ** step_dt
        vel[pos[:, 2] < BASIN_FLOOR_Z + CONTACT_LAYER_M, :2] = 0.0
        duck.set_particles_vel(torch.as_tensor(vel, dtype=torch.float32, device="cuda"))

    print(f"BUILD {build_seconds:.1f}s  E {args.young:g} Pa (core {core_young:g} Pa, {n_core} core particles)  nu {args.poisson}  inflow {args.inflow_velocity:.3f} m/s ({flow_l_min:.2f} L/min)  substeps {substeps}  duck MPM {duck.n_particles if duck else 0}  ghost {mapping['ghost_particles']}  water capacity {max_particles if faucet else 0}  "
          f"affine map cond max {mapping['affine_embedding']['condition_max']:.1f}", flush=True)
    def mapping_report():
        """Which of the operator's ghost-support conditions fail, recomputed from the current duck particles."""
        local = duck_pos() - SIM_ORIGIN
        ids, weights = solver.map_ids.to_numpy(), solver.affine_weights.to_numpy()
        ghost = (weights[..., None] * local[ids]).sum(1)
        base = np.floor(local[ids] / solver.mpm.dx - 0.5).astype(np.int64) - solver.mpm._lower_bound_cell
        lo, hi = base.min(1), base.max(1) + 2
        res = solver.mpm._grid_res
        return {"outside_mpm_grid": int(((lo < 0) | (hi >= res)).any(1).sum()),
                "span_over_box": int((hi - lo >= MAP_LOCAL_WIDTH).any(1).sum()),
                "outside_sph_domain": int(((ghost < solver._lower_bound) | (ghost > solver._upper_bound)).any(1).sum()),
                "below_floor": int((ghost[:, 2] < solver._lower_bound[2]).sum()),
                "non_finite": int((~np.isfinite(ghost)).any(1).sum()),
                "duck_height_mm": float(np.ptp(local[:, 2]) * 1000), "duck_xy_extent_mm": (np.ptp(local[:, :2], 0) * 1000).round(1).tolist()}

    initial = duck_pos() if duck else None
    tick = time.monotonic()
    try:
        for step in range(int(round(args.settle_seconds / step_dt)) if duck else 0):
            duck_contact_and_damping()
            scene.step()
    except RuntimeError as error:
        print(f"STOPPED while settling at t={step * step_dt:.3f}s: {error}\nMAPPING {json.dumps(mapping_report() if coupled else {})}", flush=True)
        np.savez_compressed(args.out, initial=initial, settling=duck_pos())
        raise
    print(f"SETTLE took {time.monotonic() - tick:.1f}s", flush=True)
    rest = duck_pos() if duck else None
    if duck:
        print(f"SETTLED  duck min z {rest[:, 2].min():.4f}", flush=True)

    frames = int(round(args.seconds * FPS))
    map_ids = solver.map_ids.to_numpy() if coupled else None
    from scipy.spatial import cKDTree
    if duck:
        neighbours = cKDTree(rest).query(rest, k=7)[1][:, 1:]
        rest_gaps = np.linalg.norm(rest[neighbours] - rest[:, None], axis=2)

    def new_store():
        return {"trajectory": [], "water": {}, "wvel": {}, "rows": [], "intervention": None, "failure": None}

    def copy_store(store):
        return {"trajectory": list(store["trajectory"]), "water": dict(store["water"]), "wvel": dict(store["wvel"]),
                "rows": [dict(row) for row in store["rows"]], "intervention": store["intervention"], "failure": store["failure"]}

    def run_frames(first, last, timed, store, out_path):
        """Simulate output frames first+1..last into store; timed applies --inflow-change-frame."""
        trajectory, water_frames, water_velocities, rows = store["trajectory"], store["water"], store["wvel"], store["rows"]
        inflow_speed = args.inflow_velocity
        if timed and args.inflow_change_frame is not None and first + 1 > args.inflow_change_frame:
            inflow_speed = args.inflow_velocity_after
        for frame in range(first, last):
            tick = time.monotonic()
            before = dict(solver.iteration_diagnostics) if faucet else {}
            counts_before = dict(solver.iteration_counts) if faucet else {}
            if timed and frame + 1 == args.inflow_change_frame:
                intervention = {"frame": frame + 1, "time_s": frame / FPS,
                                "before": {"inflow_velocity_m_s": inflow_speed,
                                           "flow_l_min": inflow_speed * math.pi * (STREAM_DIAMETER_M / 2) ** 2 * 60000.0},
                                "after": {"inflow_velocity_m_s": args.inflow_velocity_after,
                                          "flow_l_min": args.inflow_velocity_after * math.pi * (STREAM_DIAMETER_M / 2) ** 2 * 60000.0},
                                "existing_particle_positions_or_velocities_modified": False,
                                "method": "Change inlet speed; skip emission at zero. Continue native MPM/DFSPH and two-way coupling."}
                store["intervention"] = intervention
                inflow_speed = args.inflow_velocity_after
                print("INFLOW_INTERVENTION " + json.dumps(intervention), flush=True)
            try:
                for _ in range(STEPS_PER_FRAME):
                    if faucet and inflow_speed > 0.0:
                        faucet.emit(droplet_shape="circle", droplet_size=STREAM_DIAMETER_M, pos=aerator,
                                    direction=(0.0, 0.0, -1.0), speed=inflow_speed)
                    duck_contact_and_damping()
                    t_step = time.monotonic()
                    scene.step()
                    if frame == 0 and _ in (0, 1, 2, 3, 4, 10, 50):
                        print(f"  step {_}: {1000 * (time.monotonic() - t_step):.0f} ms", flush=True)
            except RuntimeError as error:      # keep the finished frames
                print(f"STOPPED in frame {frame + 1}: {error}\nMAPPING {json.dumps(mapping_report() if coupled else {})}", flush=True)
                store["failure"] = error
                break
            seconds = time.monotonic() - tick
            if faucet:
                active = faucet._entity.get_particles_active().cpu().numpy().reshape(-1).astype(bool)
                water = faucet._entity.get_particles_pos().cpu().numpy().reshape(-1, 3)[active] + SIM_ORIGIN
                water_velocity = faucet._entity.get_particles_vel().cpu().numpy().reshape(-1, 3)[active].astype(np.float32)
                d = solver.iteration_diagnostics
                caps = (d["divergence_iteration_cap_hits"] - before["divergence_iteration_cap_hits"],
                        d["density_iteration_cap_hits"] - before["density_iteration_cap_hits"])
                solves = d["density_solves"] - before["density_solves"]
                iters = (solver.iteration_counts["divergence"] - counts_before["divergence"],
                         solver.iteration_counts["density"] - counts_before["density"])
            else:
                water, water_velocity = np.zeros((0, 3)), np.zeros((0, 3), dtype=np.float32)
                caps, solves, iters = (0, 0), 0, (0, 0)
            water_frames[frame + 1], water_velocities[frame + 1] = water, water_velocity
            corner = int(((water[:, :2] <= np.array(BASIN_INTERIOR[0]) + 1e-5) | (water[:, :2] >= np.array(BASIN_INTERIOR[1]) - 1e-5)).any(1).sum())
            row = {"frame": frame + 1, "seconds": seconds, "water": len(water), "solves": solves,
                   "inflow_velocity_m_s": inflow_speed,
                   "mean_iterations": (iters[0] / max(solves, 1), iters[1] / max(solves, 1)), "cap_hits": caps,
                   "water_at_side_walls": corner, "map_error_peaks": list(solver.map_error_peaks) if coupled else None}
            pos = None
            if duck:
                pos = duck_pos()
                trajectory.append(pos)
                row.update(tilt_deg=rigid_rotation_deg(rest, pos), centroid_dz_mm=float((pos.mean(0)[2] - rest.mean(0)[2]) * 1000),
                           stretch_max=float((np.linalg.norm(pos[neighbours] - pos[:, None], axis=2) / rest_gaps).max()))   # worst local stretch
                if coupled:
                    base = np.floor((pos - SIM_ORIGIN) / solver.mpm.dx - 0.5).astype(np.int64)[map_ids]
                    row["stencil_span_cells"] = int((base.max(1) + 2 - base.min(1)).max())
                    row["water_inside_duck"] = int((cKDTree(pos).query_ball_point(water, INSIDE_RADIUS_M, return_length=True) >= INSIDE_NEIGHBOURS).sum())
            rows.append(row)
            duck_text = f"tilt {row['tilt_deg']:5.2f} deg  dz {row['centroid_dz_mm']:+.2f} mm" if duck else "no duck"
            tail = (f"  span {row['stencil_span_cells']}/{MAP_LOCAL_WIDTH}" if coupled else "") + \
                   (f"  stretch {row['stretch_max']:.2f}" if duck else "") + (f"  inside {row['water_inside_duck']}" if coupled else "")
            print(f"FRAME {frame + 1:3d}  {seconds:6.2f}s  water {row['water']:5d}  {duck_text}  "
                  f"iters/solve div {row['mean_iterations'][0]:.1f} den {row['mean_iterations'][1]:.1f}  cap hits {caps}  at walls {corner}{tail}", flush=True)
            progress = out_path.with_suffix(".progress.json")
            temporary = progress.with_suffix(".tmp")
            temporary.write_text(json.dumps({"frames_completed": len(rows), "frames_expected": frames,
                                              "inflow_intervention": store["intervention"], "rows": rows}, indent=2) + "\n")
            temporary.replace(progress)
            if duck and not np.isfinite(pos).all():
                print("NON-FINITE duck positions, stopping", flush=True)
                break
        return store

    def write_outputs(store, out_path, timed, extra=None):
        rows = store["rows"]
        duck_arrays = {"initial": initial, "rest": rest, "trajectory": np.array(store["trajectory"])} if duck else {}
        np.savez_compressed(out_path, **duck_arrays, **{f"water_{k:03d}": v for k, v in store["water"].items()},
                            **{f"wvel_{k:03d}": v for k, v in store["wvel"].items()})
        report = {"build_seconds": build_seconds, "frames": len(rows), "seconds_per_frame": float(np.mean([r["seconds"] for r in rows])),
                  "physics": {"duck_presence": [int(has_duck)], "water_presence": [int(has_water)],
                              "duck_young_modulus_pa": args.young, "duck_core_young_modulus_pa": core_young,
                              "duck_skin_thickness_m": args.skin_thickness if args.core_young is not None else None,
                              "duck_poisson_ratio": args.poisson, "duck_density_kg_m3": DUCK_DENSITY,
                              "water_density_kg_m3": WATER_DENSITY, "water_sph_viscosity_m2_s": args.mu, "water_cohesion": args.gamma,
                              "water_duck_friction": args.boundary_friction, "water_duck_adhesion": args.adhesion,
                              "faucet_inflow_velocity_m_s": args.inflow_velocity, "faucet_flow_l_min": round(flow_l_min, 12),
                              "stream_diameter_m": STREAM_DIAMETER_M},
                  "numerics": {"sph_particle_m": args.sph_particle, "mpm_grid_m": MPM_GRID_M, "mpm_particle_m": args.mpm_particle, "fps": FPS,
                               "steps_per_frame": STEPS_PER_FRAME, "substeps": substeps, "settle_seconds": args.settle_seconds,
                               "map_local_width": MAP_LOCAL_WIDTH, "seconds": args.seconds},
                  "rows": rows, "mapping": {k: mapping[k] for k in ("ghost_particles", "max_material_map_support_m", "material_particles_referenced_by_ghosts")}}
        if timed and args.inflow_change_frame is not None:
            report["physics"]["timed_edits"] = [{"frame": args.inflow_change_frame,
                "params": {"faucet_inflow_velocity_m_s": args.inflow_velocity_after}}]
            report["inflow_intervention"] = store["intervention"]
        report.update(extra or {})
        out_path.with_suffix(".json").write_text(json.dumps(report, indent=2) + "\n")
        print("PCVE_GENESIS_SIM " + json.dumps({"out": str(out_path), **{k: report[k] for k in ("build_seconds", "frames", "seconds_per_frame")}}), flush=True)

    if args.source_branch_out is None:
        store = run_frames(0, frames, True, new_store(), args.out)
        write_outputs(store, args.out, True)
        if store["failure"] is not None:
            raise store["failure"]
        return

    # One run, two branches: the shared frames 1..k-1, then the source and the timed edit from one copied state.
    k = args.inflow_change_frame
    holders = [scene.sim, scene.sim.coupler]
    required = []
    for part in (scene.sim.mpm_solver, scene.sim.sph_solver):
        if part.is_active:
            holders.append(part)
            required.append(part)
            for name in ("sh", "boundary"):
                if getattr(part, name, None) is not None:
                    holders.append(getattr(part, name))
    holders += list(scene.sim.entities) + ([faucet] if faucet is not None else [])
    required += list(scene.sim.entities)
    probe = SolverSnapshot(holders, required)          # copy/restore self-test before any frame is spent
    probe.restore()
    wrong = probe.mismatched()
    if wrong:
        raise RuntimeError(f"state copy/restore self-test failed: {wrong}")
    print("BRANCH_SELFTEST ok " + json.dumps(probe.summary()), flush=True)
    del probe
    shared = run_frames(0, k - 1, True, new_store(), args.out)
    if shared["failure"] is not None or len(shared["rows"]) != k - 1:
        write_outputs(shared, args.out, True)
        raise shared["failure"] or RuntimeError("the shared frames stopped early")
    snapshot = SolverSnapshot(holders, required)
    unstable = snapshot.mismatched()
    if unstable:
        raise RuntimeError(f"state copy is not stable: {unstable}")
    print("BRANCH_STATE " + json.dumps({"frame": k, **snapshot.summary()}), flush=True)
    source = run_frames(k - 1, frames, False, copy_store(shared), args.source_branch_out)
    replays = []
    for index in range(max(args.branch_replay_frames, 0)):
        snapshot.restore()
        wrong = snapshot.mismatched()
        if wrong:
            raise RuntimeError(f"state restore is not exact: {wrong}")
        replays.append(run_frames(k - 1, k, False, new_store(), args.out.with_name(args.out.stem + f"_replay{index + 1}.npz")))
    snapshot.restore()
    wrong = snapshot.mismatched()
    if wrong:
        raise RuntimeError(f"state restore is not exact: {wrong}")
    edit = run_frames(k - 1, frames, True, copy_store(shared), args.out)

    def duck_at_k(store):          # a replay store holds frame k only; a branch store holds frames 1..
        return store["trajectory"][k - 1] if len(store["trajectory"]) >= k else store["trajectory"][0]

    def frame_difference(a, b):
        result = {"water_counts": [len(a["water"][k]), len(b["water"][k])]}
        if len(a["water"][k]) == len(b["water"][k]):
            result["water_max_abs_m"] = float(np.abs(a["water"][k] - b["water"][k]).max()) if len(a["water"][k]) else 0.0
        if duck:
            result["duck_max_abs_m"] = float(np.abs(duck_at_k(a) - duck_at_k(b)).max())
        return result

    replay_check = {"frame": k, "live_source_vs_replay": [frame_difference(source, replay) for replay in replays],
                    "replay_vs_replay": [frame_difference(replays[0], replay) for replay in replays[1:]],
                    "note": "each replay restores the copied state and re-runs frame k of the source; GPU float atomics make "
                            "repeated runs differ slightly, so live-vs-replay is judged against replay-vs-replay"}
    print("BRANCH_REPLAY_CHECK " + json.dumps(replay_check), flush=True)
    branch_info = {"branch_frame": k, "shared_frames": [1, k - 1], "state_copy": snapshot.summary(),
                   "restore_exact": True, "replay_check": replay_check}
    write_outputs(source, args.source_branch_out, False,
                  {"same_run_branch": dict(branch_info, role="source", other_branch=str(args.out))})
    write_outputs(edit, args.out, True,
                  {"same_run_branch": dict(branch_info, role="edit", other_branch=str(args.source_branch_out))})
    for store in (source, edit):
        if store["failure"] is not None:
            raise store["failure"]


if __name__ == "__main__":
    main()
