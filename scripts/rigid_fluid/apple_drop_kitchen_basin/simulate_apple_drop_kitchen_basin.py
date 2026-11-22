"""Genesis DFSPH kitchen basin with a rigid apple coupled through a pressure boundary.

The apple-into-kitchen-basin scene on the bowling pool-drop solver. `settle` fills the basin
to 10 cm and lets the water come to rest once; `run` drops the apple into that water and writes every
frame's particles. The apple is a rigid sphere represented by concentric shells of boundary
("ghost") particles. Pressure and viscous impulses act on it inside every DFSPH iteration, so
buoyancy, drag, bobbing and the splash all come from one two-way simulation. A smooth sphere under
pressure has no torque, so the apple only translates. The basin wall and bottom are an axisymmetric
solid enforced in the advection step; the counter around it is the domain floor, so water that
splashes over the rim lands there.
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
import json
import math
import sys
import threading
import time
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
FPS = 24
FRAMES = 96
STEPS_PER_FRAME = 10
# The basin as placed in the kitchen, measured on the BlenderKit model (probe_scene.py): a thin-walled,
# straight-sided round bowl standing on the counter.
COUNTER_Z = 2.1466
BASIN_CENTER = (-1.80, 1.92)
BASIN_CX, BASIN_CY = BASIN_CENTER
BASIN_INNER_RADIUS = 0.2075
BASIN_OUTER_RADIUS = 0.215
BASIN_BOTTOM_Z = 2.1557
BASIN_RIM_Z = 2.2823
WATER_DEPTH = 0.10
FLOOR = BASIN_BOTTOM_Z
WATERLINE = BASIN_BOTTOM_Z + WATER_DEPTH
DOMAIN_HALF = 0.42          # the counter around the basin, for water that spills over the rim
DOMAIN_LOWER = (BASIN_CENTER[0] - DOMAIN_HALF, BASIN_CENTER[1] - DOMAIN_HALF, COUNTER_Z)
DOMAIN_TOP = 3.0
# The rigid sphere is the apple: 8 cm across, 850 kg/m^3, released at rest (with the original slight
# sideways drift) 0.37 m above the water.
LIQUID_DENSITY = 998.2
LIQUID_NU = 1.004e-6
BALL_RADIUS = 0.04
BALL_MASS = 850.0 * 4 / 3 * math.pi * BALL_RADIUS ** 3
BALL_START = (BASIN_CENTER[0] + 0.018, BASIN_CENTER[1] - 0.012, 2.6676)
BALL_VELOCITY = (-0.025, 0.018, 0.0)
GRAVITY = 9.81
RESTITUTION = 0.08
FRICTION = 0.45
REST_COMPRESSION = 0.8  # Genesis SPH particle volume is 0.8 * size**3
SEED = 20261021


def save_json(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + '.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf8')
    temporary.replace(path)


def fibonacci_sphere(count, radius, phase):
    index = np.arange(count) + 0.5
    polar = np.arccos(1.0 - 2.0 * index / count)
    azimuth = math.pi * (1.0 + 5 ** 0.5) * index + phase
    return radius * np.stack([np.cos(azimuth) * np.sin(polar), np.sin(azimuth) * np.sin(polar), np.cos(polar)], 1)


def ghost_shells(radius, spacing):
    """Concentric boundary shells; the outer shell sits half a spacing inside the surface."""
    offsets, volumes, shell, outer = [], [], 0, radius
    while True:
        middle = radius - (shell + 0.5) * spacing
        if middle < 0.5 * spacing:
            break
        inner = middle - 0.5 * spacing
        count = max(4, int(round(4 * math.pi * middle ** 2 / spacing ** 2)))
        offsets.append(fibonacci_sphere(count, middle, 2.399963 * shell))
        volumes.append(np.full(count, 4 / 3 * math.pi * (outer ** 3 - inner ** 3) / count))
        outer, shell = inner, shell + 1
    offsets.append(np.zeros((1, 3)))
    volumes.append(np.array([4 / 3 * math.pi * outer ** 3]))
    offsets, volumes = np.concatenate(offsets), np.concatenate(volumes)
    assert abs(volumes.sum() / (4 / 3 * math.pi * radius ** 3) - 1) < 1e-9
    return offsets, volumes, shell


def free_fall(time_s):
    start, velocity = np.array(BALL_START), np.array(BALL_VELOCITY)
    gravity = np.array([0.0, 0.0, -GRAVITY])
    return start + velocity * time_s + 0.5 * gravity * time_s ** 2, velocity + gravity * time_s


def create_solver(SPHSolver, gs, qd):
    @qd.data_oriented
    class RigidBallSPH(SPHSolver):

        def build(self):
            super().build()
            assert len(self.entities) == 2 and self._B == 1
            self.n_fluid = self.entities[0].n_particles
            self.n_ghost = self.n_particles - self.n_fluid
            assert self.n_ghost > 0
            self.relaxation = 0.5
            self.boundary_relaxation = 0.1
            self._df_max_div_iters = 100
            self._df_max_den_iters = 100
            self.original_id = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.near_boundary = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.ghost_offset = qd.Vector.field(3, dtype=gs.qd_float, shape=(self.n_ghost,))
            self.ghost_volume = qd.field(gs.qd_float, shape=(self.n_ghost,))
            self.ball = qd.Vector.field(3, dtype=qd.f64, shape=(2,))
            self.ball_lower = qd.Vector.field(3, dtype=qd.f64, shape=())
            self.ball_upper = qd.Vector.field(3, dtype=qd.f64, shape=())
            self.ball_scalars = qd.field(qd.f64, shape=(4,))
            self.ball_dynamic = qd.field(qd.i32, shape=())
            self.factor_inverse_mass = qd.field(gs.qd_float, shape=())
            self.pressure_impulse = qd.Vector.field(3, dtype=qd.f64, shape=())
            self.viscous_force = qd.Vector.field(3, dtype=qd.f64, shape=())
            self.audit = qd.Vector.field(3, dtype=qd.f64, shape=(4,))
            self.fluid_damping = qd.field(gs.qd_float, shape=())
            self.film_floor = qd.field(gs.qd_float, shape=())
            self.contacts = qd.field(qd.i32, shape=())
            self.minimum_sweeps = {'divergence': 2, 'density': 3}
            # Warm start: half of each particle's accumulated stiffness from the previous substep,
            # stored by original particle id because particles are re-sorted every substep.
            self.warm_start = False
            self.kappa_previous = qd.field(gs.qd_float, shape=(2, self.n_particles))
            self.kappa_current = qd.field(gs.qd_float, shape=(2, self.n_particles))
            self.warm_stiffness = qd.field(gs.qd_float, shape=(self.n_particles, self._B))
            self.reset_iteration_diagnostics()

        def configure_ball(self, center, velocity, mass, offsets, volumes, dynamic, damping=1.0, film_band=1.0,
                           contact_gap=0.5):
            offset = np.zeros((self.n_ghost, 3), np.float32)
            volume = np.zeros(self.n_ghost, np.float32)
            assert len(offsets) <= self.n_ghost
            offset[:len(offsets)] = offsets
            volume[:len(volumes)] = volumes
            self.ghost_offset.from_numpy(offset)
            self.ghost_volume.from_numpy(volume)
            self.ball.from_numpy(np.array([center, velocity], np.float64))
            self.ball_scalars.from_numpy(np.array([1.0 / mass, BALL_RADIUS, RESTITUTION, FRICTION], np.float64))
            # Rest one uncompressed particle layer above the floor; squeezing it costs pressure sweeps.
            reach = BASIN_INNER_RADIUS - BALL_RADIUS   # the apple stays inside the basin wall
            self.ball_lower[None] = [BASIN_CENTER[0] - reach, BASIN_CENTER[1] - reach,
                                     FLOOR + contact_gap * self._particle_size]
            self.ball_upper[None] = [BASIN_CENTER[0] + reach, BASIN_CENTER[1] + reach, DOMAIN_TOP]
            self.ball_dynamic[None] = int(dynamic)
            self.factor_inverse_mass[None] = 1.0 / mass if dynamic else 0.0
            self.fluid_damping[None] = damping
            self.film_floor[None] = FLOOR + film_band * self._particle_size
            self.audit.fill(0)

        def reset_iteration_diagnostics(self):
            self.iteration_counts = {'divergence': 0, 'density': 0}
            self.iteration_diagnostics = {'divergence_solves': 0, 'density_solves': 0,
                'divergence_iteration_cap_hits': 0, 'density_iteration_cap_hits': 0,
                'maximum_final_divergence_global_tolerance_ratio': 0.0,
                'maximum_final_divergence_contact_tolerance_ratio': 0.0,
                'maximum_final_density_global_tolerance_ratio': 0.0,
                'maximum_final_density_contact_tolerance_ratio': 0.0}

        @qd.func
        def is_fluid(self, index, batch):
            return self.original_id[index, batch] < self.n_fluid

        @qd.func
        def volume(self, index, batch):
            result = self._particle_volume
            if not self.is_fluid(index, batch):
                result = self.ghost_volume[self.original_id[index, batch] - self.n_fluid]
            return result

        @qd.kernel
        def place_ghosts(self):
            for ghost in range(self.n_ghost):
                index = self.n_fluid + ghost
                self.particles[index, 0].pos = self.ball[0].cast(gs.qd_float) + self.ghost_offset[ghost]
                self.particles[index, 0].vel = self.ball[1].cast(gs.qd_float)
                self.particles_ng[index, 0].active = True

        @qd.kernel
        def reorder_original_ids(self):
            for (index, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng[index, batch].active:
                    self.original_id[self.particles_ng[index, batch].reordered_idx, batch] = index

        @qd.func
        def _task_compute_rho(self, i, j, ret: qd.template(), i_b):
            ret += self.volume(j, i_b) * self.cubic_kernel((self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos).norm())
            if not self.is_fluid(j, i_b):
                self.near_boundary[i, i_b] = 1

        @qd.func
        def factor_pair(self, i, j, ret: qd.template(), batch):
            gradient = -self.volume(j, batch) * self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            if self.is_fluid(j, batch):
                ret[3] += gradient.norm_sqr()
            else:
                coefficient = self.particles_info_reordered[i, batch].mass * self.factor_inverse_mass[None]
                ret[4] += qd.sqrt(qd.max(coefficient, 0.0)) * gradient.norm()
            for k in qd.static(range(3)):
                ret[k] -= gradient[k]

        @qd.kernel
        def _kernel_compute_DFSPH_factor(self, f: qd.i32):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    self.particles_reordered[i, batch].p = 0.0
                    self.particles_reordered[i, batch].acc = qd.Vector.zero(gs.qd_float, 3)
                    factor = gs.qd_float(0.0)
                    if self.is_fluid(i, batch):
                        ret = qd.Vector.zero(gs.qd_float, 5)
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self.factor_pair, batch)
                        denominator = ret[3] + ret[4] ** 2 + ret[0] ** 2 + ret[1] ** 2 + ret[2] ** 2
                        if denominator > 1e-06:
                            relaxation = self.relaxation
                            if self.near_boundary[i, batch]:
                                relaxation = self.boundary_relaxation
                            factor = -relaxation / denominator
                    self.particles_reordered[i, batch].dfsph_factor = factor

        @qd.func
        def _task_compute_density_time_derivative(self, i, j, ret: qd.template(), batch):
            difference = self.particles_reordered[i, batch].vel - self.particles_reordered[j, batch].vel
            gradient = self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            ret.drho += self.volume(j, batch) * difference.dot(gradient)
            ret.num_neighbors += 1

        @qd.kernel
        def _kernel_compute_density_time_derivative(self):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    divergence = gs.qd_float(0.0)
                    if self.is_fluid(i, batch):
                        ret = qd.Struct(drho=0.0, num_neighbors=0)
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self._task_compute_density_time_derivative, batch)
                        if ret.num_neighbors >= 20:
                            divergence = qd.max(ret.drho, 0.0)
                    self.particles_reordered[i, batch].drho = divergence

        @qd.func
        def _task_compute_density_star(self, i, j, ret: qd.template(), batch):
            difference = self.particles_reordered[i, batch].vel - self.particles_reordered[j, batch].vel
            ret += self.volume(j, batch) * difference.dot(self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos))

        @qd.kernel
        def _kernel_compute_density_star(self):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    density = gs.qd_float(1.0)
                    if self.is_fluid(i, batch):
                        delta = gs.qd_float(0.0)
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, delta, self._task_compute_density_star, batch)
                        density = qd.max(self.particles_reordered[i, batch].rho / self._density0 + self._substep_dt * delta, 1.0)
                    self.particles_reordered[i, batch].drho = density

        @qd.func
        def pressure_pair(self, i, j, stiffness, scale, batch):
            gradient = -self.volume(j, batch) * self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            dv = -scale * stiffness * gradient
            if not self.is_fluid(j, batch):
                impulse = (self.particles_info_reordered[i, batch].mass * dv).cast(qd.f64)
                self.audit[0] += impulse
                # Sub-resolution film: the last particle layer on the floor cannot carry the ball.
                if self.particles_reordered[i, batch].pos[2] > self.film_floor[None]:
                    self.pressure_impulse[None] -= impulse
                else:
                    self.audit[3] -= impulse
            return dv

        @qd.func
        def _task_divergence_solver_iteration(self, i, j, ret: qd.template(), i_b):
            stiffness = ret.k_i
            if self.is_fluid(j, i_b):
                stiffness += self.particles_reordered[j, i_b].drho * self.particles_reordered[j, i_b].dfsph_factor
            ret.dv += self.pressure_pair(i, j, stiffness, 1.0, i_b)

        @qd.func
        def density_solve_iteration_task(self, i, j, ret: qd.template(), i_b):
            stiffness = ret.k_i
            if self.is_fluid(j, i_b):
                stiffness += (self.particles_reordered[j, i_b].drho - 1.0) * self.particles_reordered[j, i_b].dfsph_factor
            ret.dv += self.pressure_pair(i, j, stiffness, self._substep_dt, i_b)

        @qd.kernel
        def _kernel_divergence_solver_iteration(self):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    stiffness = self.particles_reordered[i, batch].drho * self.particles_reordered[i, batch].dfsph_factor
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=stiffness)
                    self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self._task_divergence_solver_iteration, batch)
                    self.particles_reordered[i, batch].vel += ret.dv
                    self.kappa_current[0, self.original_id[i, batch]] += stiffness

        @qd.kernel
        def _kernel_density_solve_iteration(self):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    stiffness = (self.particles_reordered[i, batch].drho - 1.0) * self.particles_reordered[i, batch].dfsph_factor
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=stiffness)
                    self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self.density_solve_iteration_task, batch)
                    self.particles_reordered[i, batch].vel += ret.dv
                    self.particles_reordered[i, batch].p -= stiffness * self._density0
                    self.kappa_current[1, self.original_id[i, batch]] += stiffness

        @qd.kernel
        def gather_warm_stiffness(self, stage: qd.i32):
            # Reuse half the previous stiffness only where the current state still needs correction.
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                stiffness = gs.qd_float(0.0)
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    needed = self.particles_reordered[i, batch].drho > 0.0
                    if stage == 1:
                        needed = self.particles_reordered[i, batch].drho > 1.0
                    if needed:
                        stiffness = 0.5 * self.kappa_previous[stage, self.original_id[i, batch]]
                self.warm_stiffness[i, batch] = stiffness

        @qd.func
        def _task_warm_divergence(self, i, j, ret: qd.template(), i_b):
            stiffness = ret.k_i
            if self.is_fluid(j, i_b):
                stiffness += self.warm_stiffness[j, i_b]
            ret.dv += self.pressure_pair(i, j, stiffness, 1.0, i_b)

        @qd.func
        def _task_warm_density(self, i, j, ret: qd.template(), i_b):
            stiffness = ret.k_i
            if self.is_fluid(j, i_b):
                stiffness += self.warm_stiffness[j, i_b]
            ret.dv += self.pressure_pair(i, j, stiffness, self._substep_dt, i_b)

        @qd.kernel
        def apply_warm_stiffness(self, stage: qd.i32):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    stiffness = self.warm_stiffness[i, batch]
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=stiffness)
                    if stage == 0:
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self._task_warm_divergence, batch)
                    else:
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self._task_warm_density, batch)
                        self.particles_reordered[i, batch].p -= stiffness * self._density0
                    self.particles_reordered[i, batch].vel += ret.dv
                    self.kappa_current[stage, self.original_id[i, batch]] += stiffness

        @qd.kernel
        def rotate_stiffness(self):
            for (stage, index) in qd.ndrange(2, self.n_particles):
                self.kappa_previous[stage, index] = self.kappa_current[stage, index]
                self.kappa_current[stage, index] = 0.0

        def warm(self, stage):
            if self.warm_start:
                self.gather_warm_stiffness(stage)
                self.apply_warm_stiffness(stage)
                self.apply_ball_impulse()
                if stage == 0:
                    self._kernel_compute_density_time_derivative()
                else:
                    self._kernel_compute_density_star()

        @qd.kernel
        def apply_ball_impulse(self):
            impulse = self.pressure_impulse[None]
            if self.ball_dynamic[None]:
                self.ball[1] += impulse * self.ball_scalars[0]
            self.audit[1] += impulse
            self.pressure_impulse[None] = qd.Vector.zero(qd.f64, 3)
            for ghost in range(self.n_ghost):
                index = self.n_fluid + ghost
                if self.particles_ng[index, 0].active:
                    self.particles_reordered[self.particles_ng[index, 0].reordered_idx, 0].vel = self.ball[1].cast(gs.qd_float)

        def _divergence_solver_iteration(self):
            self._kernel_divergence_solver_iteration()
            self.apply_ball_impulse()
            self._kernel_compute_density_time_derivative()
            return self._kernel_compute_density_error(0.0) / self.n_fluid

        def _density_solve_iteration(self):
            self._kernel_density_solve_iteration()
            self.apply_ball_impulse()
            self._kernel_compute_density_star()
            return self._kernel_compute_density_error(self._density0) / self.n_fluid

        @qd.kernel
        def maximum_contact_error(self, offset: gs.qd_float) -> gs.qd_float:
            error = gs.qd_float(0.0)
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch) and self.near_boundary[i, batch]:
                    qd.atomic_max(error, self.particles_reordered[i, batch].drho - offset)
            return error

        def _divergence_solve(self, f):
            self._kernel_compute_density_time_derivative()
            self.warm(0)
            eta = self._df_max_error_div * 0.01 / self._substep_dt
            converged = False
            for iteration in range(self._df_max_div_iters):
                average = self._divergence_solver_iteration() / self._density0
                local = self.maximum_contact_error(0.0)
                self.iteration_counts['divergence'] += 1
                if iteration + 1 >= self.minimum_sweeps['divergence'] and average <= eta and local <= eta:
                    converged = True
                    break
            d = self.iteration_diagnostics
            d['divergence_solves'] += 1
            d['divergence_iteration_cap_hits'] += int(not converged)
            d['maximum_final_divergence_global_tolerance_ratio'] = max(d['maximum_final_divergence_global_tolerance_ratio'], average / eta)
            d['maximum_final_divergence_contact_tolerance_ratio'] = max(d['maximum_final_divergence_contact_tolerance_ratio'], local / eta)

        def _density_solve(self, f):
            self._kernel_compute_density_star()
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor, 1 / self._substep_dt ** 2)
            self.warm(1)
            eta = self._df_max_error_den * 0.01
            converged = False
            for iteration in range(self._df_max_den_iters):
                average = self._density_solve_iteration() / self._density0
                local = self.maximum_contact_error(1.0)
                self.iteration_counts['density'] += 1
                if iteration + 1 >= self.minimum_sweeps['density'] and average <= eta and local <= 0.005:
                    converged = True
                    break
            d = self.iteration_diagnostics
            d['density_solves'] += 1
            d['density_iteration_cap_hits'] += int(not converged)
            d['maximum_final_density_global_tolerance_ratio'] = max(d['maximum_final_density_global_tolerance_ratio'], average / eta)
            d['maximum_final_density_contact_tolerance_ratio'] = max(d['maximum_final_density_contact_tolerance_ratio'], local / 0.005)

        @qd.func
        def _task_compute_non_pressure_forces(self, i, j, ret: qd.template(), i_b):
            d = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
            v = self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
            weight = 10 * self.particles_info_reordered[i, i_b].mu * v.dot(d) / (d.norm_sqr() + 0.01 * self._support_radius ** 2)
            if self.is_fluid(j, i_b):
                mass = self.particles_info_reordered[j, i_b].mass
                density = self.particles_reordered[j, i_b].rho
                ret += weight * (mass / qd.max(density, 1e-06)) * self.cubic_kernel_derivative(d)
                # Surface tension as Genesis' own cohesion between water particles (gamma per material).
                ret -= (self.particles_info_reordered[i, i_b].gamma / self.particles_info_reordered[i, i_b].mass * mass
                        * d * self.cubic_kernel(qd.max(d.norm(), self._particle_size)))
            else:
                acceleration = weight * self.volume(j, i_b) * self.cubic_kernel_derivative(d)
                ret += acceleration
                if self.particles_reordered[i, i_b].pos[2] > self.film_floor[None]:
                    self.viscous_force[None] -= (self.particles_info_reordered[i, i_b].mass * acceleration).cast(qd.f64)

        @qd.kernel
        def _kernel_compute_non_pressure_forces(self, f: qd.i32, t: qd.f32):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    acceleration = qd.Vector.zero(gs.qd_float, 3)
                    if self.is_fluid(i, batch):
                        acceleration = self._gravity[batch]
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, acceleration, self._task_compute_non_pressure_forces, batch)
                    self.particles_reordered[i, batch].acc = acceleration

        @qd.kernel
        def apply_ball_external(self):
            force = self.viscous_force[None]
            step = qd.cast(self._substep_dt, qd.f64)
            if self.ball_dynamic[None]:
                self.ball[1] += step * (self._gravity[0].cast(qd.f64) + force * self.ball_scalars[0])
            self.audit[2] += step * force
            self.viscous_force[None] = qd.Vector.zero(qd.f64, 3)
            for ghost in range(self.n_ghost):
                index = self.n_fluid + ghost
                if self.particles_ng[index, 0].active:
                    self.particles_reordered[self.particles_ng[index, 0].reordered_idx, 0].vel = self.ball[1].cast(gs.qd_float)

        @qd.kernel
        def _kernel_advect_position(self, f: qd.i32):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    velocity = self.particles_reordered[i, batch].vel * self.fluid_damping[None]
                    pos = self.particles_reordered[i, batch].pos + self._substep_dt * velocity
                    (pos, velocity) = self.boundary.impose_pos_vel(pos, velocity)
                    # The basin solid in (r, z): the wall ring inner..outer radius up to the rim, and the
                    # bottom slab below the inner floor. Points inside move to the nearest face and lose the
                    # velocity into it; a second pass settles the inner bottom corner.
                    for _ in qd.static(range(2)):
                        ox = pos[0] - BASIN_CX
                        oy = pos[1] - BASIN_CY
                        r = qd.sqrt(ox * ox + oy * oy)
                        if pos[2] < BASIN_RIM_Z and r < BASIN_OUTER_RADIUS:
                            if r < BASIN_INNER_RADIUS:
                                if pos[2] < BASIN_BOTTOM_Z:
                                    pos[2] = BASIN_BOTTOM_Z
                                    velocity[2] = qd.max(velocity[2], 0.0)
                            else:
                                to_inner = r - BASIN_INNER_RADIUS
                                to_outer = BASIN_OUTER_RADIUS - r
                                to_top = BASIN_RIM_Z - pos[2]
                                ux = ox / r
                                uy = oy / r
                                radial = velocity[0] * ux + velocity[1] * uy
                                if to_inner <= to_outer and to_inner <= to_top:
                                    pos[0] -= to_inner * ux
                                    pos[1] -= to_inner * uy
                                    if radial > 0:
                                        velocity[0] -= radial * ux
                                        velocity[1] -= radial * uy
                                elif to_outer <= to_top:
                                    pos[0] += to_outer * ux
                                    pos[1] += to_outer * uy
                                    if radial < 0:
                                        velocity[0] -= radial * ux
                                        velocity[1] -= radial * uy
                                else:
                                    pos[2] = BASIN_RIM_Z
                                    velocity[2] = qd.max(velocity[2], 0.0)
                    self.particles_reordered[i, batch].pos = pos
                    self.particles_reordered[i, batch].vel = velocity

        @qd.kernel
        def advance_ball(self):
            if self.ball_dynamic[None]:
                step = qd.cast(self._substep_dt, qd.f64)
                velocity = self.ball[1]
                center = self.ball[0] + step * velocity
                radius = self.ball_scalars[1]
                restitution = self.ball_scalars[2]
                friction = self.ball_scalars[3]
                lower = self.ball_lower[None]
                upper = self.ball_upper[None]
                for d in qd.static(range(3)):
                    if center[d] - radius < lower[d]:
                        center[d] = lower[d] + radius
                        if velocity[d] < 0.0:
                            change = -(1.0 + restitution) * velocity[d]
                            velocity[d] = -restitution * velocity[d]
                            self.contacts[None] += 1
                            if qd.static(d == 2):
                                tangential = qd.sqrt(velocity[0] ** 2 + velocity[1] ** 2)
                                if tangential > 1e-12:
                                    scale = qd.max(0.0, 1.0 - friction * change / tangential)
                                    velocity[0] *= scale
                                    velocity[1] *= scale
                    if center[d] + radius > upper[d]:
                        center[d] = upper[d] - radius
                        if velocity[d] > 0.0:
                            velocity[d] = -restitution * velocity[d]
                            self.contacts[None] += 1
                self.ball[0] = center
                self.ball[1] = velocity

        def substep_pre_coupling(self, f):
            self.place_ghosts()
            self._kernel_reorder_particles(f)
            self.reorder_original_ids()
            self.near_boundary.fill(0)
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self.apply_ball_external()
            self._kernel_predict_velocity(f)
            self._density_solve(f)
            self.rotate_stiffness()

        def substep_post_coupling(self, f):
            self._kernel_advect_position(f)
            self._kernel_copy_from_reordered(f)
            self.advance_ball()

    return RigidBallSPH


def sampled_spacing(length, dx):
    count = int(round(length / dx))
    return (length - dx) / (count - 1)


def lattice_density(spacing, dx):
    """Bulk density / rest density of an infinite lattice under the Genesis cubic kernel."""
    support = 2 * dx
    axes = [np.arange(-math.ceil(support / s), math.ceil(support / s) + 1) * s for s in spacing]
    x, y, z = np.meshgrid(*axes, indexing='ij')
    q = np.sqrt(x * x + y * y + z * z) / support
    w = np.where(q <= 0.5, 6 * q ** 3 - 6 * q ** 2 + 1, np.where(q <= 1, 2 * (1 - q) ** 3, 0.0))
    return REST_COMPRESSION * dx ** 3 * 8 / (math.pi * support ** 3) * float(w.sum())


def water_lattice(dx, extra_layers=0, initial_density=0.99):
    """Vertical spacing that starts the bulk slightly under-dense, and the layer count for the waterline.

    DFSPH removes any compression within one substep, so an over-dense start explodes;
    starting under-dense lets gravity compact the column gently instead.
    """
    sx = sy = sampled_spacing(2 * BASIN_INNER_RADIUS, dx)
    low, high = 0.5 * dx, 1.2 * dx
    for _ in range(60):
        middle = 0.5 * (low + high)
        if lattice_density((sx, sy, middle), dx) > initial_density:
            low = middle
        else:
            high = middle
    sz = 0.5 * (low + high)
    layers = int(round((WATERLINE - FLOOR) / (initial_density * sz))) + extra_layers
    return layers, sz


def water_cylinder(path, height):
    """Closed cylinder filling the basin from its floor up to height, as an OBJ file. Genesis samples it
    on the lattice of its bounding box, so the layers match a Box of that size."""
    import trimesh
    cylinder = trimesh.creation.cylinder(radius=BASIN_INNER_RADIUS, height=height, sections=128)
    cylinder.apply_translation((BASIN_CX, BASIN_CY, FLOOR + height / 2))
    assert cylinder.is_watertight and cylinder.volume > 0
    cylinder.export(path)
    return str(path)


def build_scene(args, liquid_density, liquid_nu):
    import genesis as gs
    gs.init(backend=gs.cuda, precision='32', seed=SEED, logging_level='warning')
    import quadrants as qd
    from genesis.engine.solvers.sph_solver import SPHSolver
    import genesis.engine.simulator as simulator
    simulator.SPHSolver = create_solver(SPHSolver, gs, qd)
    dx = args.dx
    sub_dt = 1.0 / (FPS * STEPS_PER_FRAME * args.substeps)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=1.0 / (FPS * STEPS_PER_FRAME), substeps=args.substeps,
            gravity=(0.0, 0.0, -GRAVITY), floor_height=COUNTER_Z, requires_grad=False),
        sph_options=gs.options.SPHOptions(particle_size=dx, pressure_solver='DFSPH',
            lower_bound=DOMAIN_LOWER, upper_bound=(BASIN_CX + DOMAIN_HALF, BASIN_CY + DOMAIN_HALF, DOMAIN_TOP),
            max_divergence_error=args.divergence_error, max_density_error_percent=args.density_error),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_mpm=False, rigid_sph=False, rigid_pbd=False,
            rigid_fem=False, mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False),
        show_viewer=False)
    height = water_lattice(dx, args.extra_layers)[0] * dx
    Path(args.out).mkdir(parents=True, exist_ok=True)
    water = scene.add_entity(
        morph=gs.morphs.Mesh(file=water_cylinder(Path(args.out) / 'water_cylinder.obj', height)),
        material=gs.materials.SPH.Liquid(rho=liquid_density, mu=liquid_nu, gamma=args.surface_tension, sampler='regular'),
        surface=gs.surfaces.Default(color=(0.2, 0.6, 1.0, 1.0), vis_mode='particle'))
    offsets, volumes, shells = ghost_shells(BALL_RADIUS, dx)
    side = (math.ceil(len(offsets) ** (1 / 3)) + 1) * dx
    ghosts = scene.add_entity(
        morph=gs.morphs.Box(pos=BALL_START, size=(side, side, side)),
        material=gs.materials.SPH.Liquid(rho=liquid_density, mu=liquid_nu, gamma=0.0, sampler='regular'),
        surface=gs.surfaces.Default(color=(1.0, 0.0, 1.0, 1.0), vis_mode='particle'))
    tick = time.monotonic()
    scene.build(n_envs=0)
    build_seconds = time.monotonic() - tick
    solver = scene.sim.sph_solver
    info = {'dx_m': dx, 'substep_dt_s': sub_dt, 'substeps_per_frame': STEPS_PER_FRAME * args.substeps,
            'water_particles': water.n_particles, 'ghost_slots': ghosts.n_particles,
            'ghost_particles': int(len(offsets)), 'ghost_shells': shells,
            'ghost_outer_shell_radius_m': float(BALL_RADIUS - 0.5 * dx),
            'support_radius_m': float(solver._support_radius), 'particle_volume_m3': float(solver._particle_volume),
            'hash_grid_res': [int(v) for v in solver.sh.grid_res], 'build_seconds': build_seconds,
            'divergence_error': args.divergence_error, 'density_error_percent': args.density_error,
            'domain_top_m': DOMAIN_TOP, 'domain_half_m': DOMAIN_HALF, 'counter_z_m': COUNTER_Z,
            'basin': {'center_m': list(BASIN_CENTER), 'inner_radius_m': BASIN_INNER_RADIUS,
                      'outer_radius_m': BASIN_OUTER_RADIUS, 'bottom_z_m': BASIN_BOTTOM_Z, 'rim_z_m': BASIN_RIM_Z},
            'apple': {'radius_m': BALL_RADIUS, 'mass_kg': BALL_MASS, 'start_m': list(BALL_START),
                      'start_velocity_m_s': list(BALL_VELOCITY)},
            'liquid_density': liquid_density, 'liquid_nu': liquid_nu, 'surface_tension_gamma': args.surface_tension,
            'native_viscosity_stable_dt_s': float(solver._stable_dt_coef * 0.01 * solver._support_radius ** 2 / liquid_nu),
            'explicit_viscosity_number': float(liquid_nu * sub_dt / dx ** 2)}
    return gs, scene, solver, water, offsets, volumes, info


def surface_level(positions, dx):
    cell = np.floor(positions[:, :2] / dx).astype(np.int64)
    key = cell[:, 0] * 100000 + cell[:, 1]
    order = np.argsort(key, kind='stable')
    key, z = key[order], positions[order, 2]
    starts = np.flatnonzero(np.r_[True, key[1:] != key[:-1]])
    tops = np.maximum.reduceat(z, starts)
    return float(np.median(tops) + 0.5 * REST_COMPRESSION * dx)


def settle(args):
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    gs, scene, solver, water, offsets, volumes, info = build_scene(args, LIQUID_DENSITY, args.liquid_nu or LIQUID_NU)
    layers, spacing = water_lattice(args.dx, args.extra_layers)
    positions = water.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float64)
    layer = np.rint((positions[:, 2] - positions[:, 2].min()) / args.dx)
    assert layer.max() == layers - 1
    positions[:, 2] = FLOOR + (layer + 0.5) * spacing
    water.set_particles_pos(positions.astype(np.float32))
    info.update(initial_layers=layers, initial_vertical_spacing_m=spacing,
                initial_bulk_density_ratio=lattice_density((sampled_spacing(2 * BASIN_INNER_RADIUS, args.dx),) * 2
                                                           + (spacing,), args.dx))
    water.set_particles_vel(np.zeros_like(positions, dtype=np.float32))
    park = (BASIN_CX, BASIN_CY, DOMAIN_TOP - BALL_RADIUS - 0.05)
    solver.configure_ball(park, (0.0, 0.0, 0.0), BALL_MASS, offsets, volumes, dynamic=False, damping=args.damping)
    report = {'mode': 'settle', 'info': info, 'initial_surface_m': surface_level(positions, args.dx), 'samples': []}
    start = time.monotonic()
    damped_frames = int(round(args.settle_seconds * FPS))
    free_frames = int(round(args.check_seconds * FPS))
    for frame in range(1, damped_frames + free_frames + 1):
        if frame == damped_frames + 1:
            solver.fluid_damping[None] = 1.0
        for _ in range(STEPS_PER_FRAME):
            scene.step()
        if frame % 6 == 0 or frame == damped_frames + free_frames:
            wx = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
            wv = water.get_particles_vel().cpu().numpy().reshape(-1, 3)
            speed = np.linalg.norm(wv, axis=1)
            row = {'time_s': frame / FPS, 'damped': frame <= damped_frames, 'max_speed': float(speed.max()),
                   'p99_speed': float(np.percentile(speed, 99)), 'mean_speed': float(speed.mean()),
                   'surface_m': surface_level(wx, args.dx), 'z_min': float(wx[:, 2].min()),
                   'wall_s': time.monotonic() - start, 'iterations': dict(solver.iteration_counts),
                   'caps': solver.iteration_diagnostics['density_iteration_cap_hits'] + solver.iteration_diagnostics['divergence_iteration_cap_hits']}
            report['samples'].append(row)
            print('SETTLE', json.dumps(row), flush=True)
            save_json(out / 'settle_report.json', report)
    wx = water.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float32)
    wv = water.get_particles_vel().cpu().numpy().reshape(-1, 3)
    speed = np.linalg.norm(wv, axis=1)
    level = surface_level(wx, args.dx)
    wall = BASIN_INNER_RADIUS - np.hypot(wx[:, 0] - BASIN_CX, wx[:, 1] - BASIN_CY)
    regions = {'surface_layer': wx[:, 2] > level - 2 * args.dx, 'floor_layer': wx[:, 2] < FLOOR + 2 * args.dx,
               'wall_layer': wall < 2 * args.dx}
    regions['bulk'] = ~(regions['surface_layer'] | regions['floor_layer'] | regions['wall_layer'])
    report['final_speed_by_region'] = {name: {'count': int(mask.sum()), 'mean': float(speed[mask].mean()),
        'p99': float(np.percentile(speed[mask], 99))} for name, mask in regions.items()}
    report.update(final_surface_m=level, final_max_speed=float(speed.max()), final_mean_speed=float(speed.mean()),
                  settle_wall_seconds=time.monotonic() - start)
    np.savez(out / 'water_state.npz', water_pos=wx, dx=args.dx, surface_m=level, liquid_nu=args.liquid_nu or 1.0e-6,
             extra_layers=args.extra_layers, basin=np.array([BASIN_CX, BASIN_CY, BASIN_INNER_RADIUS, BASIN_BOTTOM_Z]))
    save_json(out / 'settle_report.json', report)
    print('SETTLED', json.dumps({k: report[k] for k in ('final_surface_m', 'final_max_speed', 'final_mean_speed',
          'final_speed_by_region', 'settle_wall_seconds')}), flush=True)


def local_submersion(positions, center, dx):
    radial = np.hypot(positions[:, 0] - center[0], positions[:, 1] - center[1])
    ring = (radial > 1.4 * BALL_RADIUS) & (radial < 3.0 * BALL_RADIUS) & (np.abs(positions[:, 2] - center[2]) < 0.6)
    if ring.sum() < 50:
        return None, None
    angle = np.arctan2(positions[ring, 1] - center[1], positions[ring, 0] - center[0])
    bins = np.floor((angle + math.pi) / (2 * math.pi) * 16).astype(int) % 16
    tops = [positions[ring, 2][bins == b].max() for b in range(16) if np.any(bins == b)]
    level = float(np.median(tops) + 0.5 * REST_COMPRESSION * dx)
    depth = min(max(level - (center[2] - BALL_RADIUS), 0.0), 2 * BALL_RADIUS)
    fraction = depth ** 2 * (3 * BALL_RADIUS - depth) / (4 * BALL_RADIUS ** 3)
    return level, float(fraction)


def run(args):
    physics = {'ball_mass': BALL_MASS, 'liquid_density': LIQUID_DENSITY, 'liquid_nu': LIQUID_NU}
    for key in ('ball_mass', 'liquid_density', 'liquid_nu'):
        if getattr(args, key) is not None:
            physics[key] = getattr(args, key)
    out = Path(args.out)
    if (out / 'simulation_report.json').exists():
        raise FileExistsError(out)
    (out / 'particles').mkdir(parents=True, exist_ok=True)
    wall_start = time.monotonic()
    gs, scene, solver, water, offsets, volumes, info = build_scene(args, physics['liquid_density'], physics['liquid_nu'])
    with np.load(args.water_state) as state:
        assert math.isclose(float(state['dx']), args.dx)
        assert int(state['extra_layers']) == args.extra_layers if 'extra_layers' in state else args.extra_layers == 0
        assert 'basin' in state and np.allclose(state['basin'], [BASIN_CX, BASIN_CY, BASIN_INNER_RADIUS, BASIN_BOTTOM_Z]), \
            'water settled in another basin'
        settled = state['water_pos']
        info['settled_surface_m'] = float(state['surface_m'])
    assert len(settled) == water.n_particles
    water.set_particles_pos(settled)
    water.set_particles_vel(np.zeros_like(settled))
    ball_volume = 4 / 3 * math.pi * BALL_RADIUS ** 3
    first = 1
    while args.skip_air:
        center, _ = free_fall(first / FPS)
        if center[2] - BALL_RADIUS < WATERLINE + 3 * args.dx or first >= FRAMES:
            break
        first += 1
    center, velocity = free_fall((first - 1) / FPS)
    solver.configure_ball(center, velocity, physics['ball_mass'], offsets, volumes, dynamic=True, film_band=args.film_band,
                          contact_gap=args.contact_gap)
    solver.minimum_sweeps = dict(zip(('divergence', 'density'), (int(v) for v in args.min_sweeps.split(','))))
    solver.warm_start = args.warm_start
    info.update(film_band_dx=args.film_band, contact_gap_dx=args.contact_gap, minimum_sweeps=dict(solver.minimum_sweeps),
                warm_start=args.warm_start)
    report = {'mode': 'run', 'physics': physics, 'info': info,
              'ball_density': physics['ball_mass'] / ball_volume,
              'expected_floating_fraction': (physics['ball_mass'] / ball_volume) / physics['liquid_density'],
              'analytic_frames_before_coupling': first - 1, 'setup_seconds': time.monotonic() - wall_start, 'frames': []}
    writer = None
    sub_dt = info['substep_dt_s']
    last_counts = dict(solver.iteration_counts)
    sim_start = time.monotonic()
    for frame in range(1, args.frames + 1):
        tick = time.monotonic()
        if frame < first:
            center, velocity = free_fall((frame - 1) / FPS)
            wx, wv = settled, np.zeros_like(settled)
        else:
            if frame > first:
                for _ in range(STEPS_PER_FRAME):
                    scene.step()
            state = solver.ball.to_numpy()
            center, velocity = state[0], state[1]
            wx = water.get_particles_pos().cpu().numpy().reshape(-1, 3)
            wv = water.get_particles_vel().cpu().numpy().reshape(-1, 3)
        compute = time.monotonic() - tick
        if writer is not None:
            writer.join()
        writer = threading.Thread(target=np.savez, args=(out / 'particles' / f'frame_{frame:04d}.npz',),
            kwargs={'water_pos': wx.astype(np.float32), 'water_vel': wv.astype(np.float16),
                    'ball_center': np.asarray(center), 'ball_velocity': np.asarray(velocity)})
        writer.start()
        speed = np.linalg.norm(wv, axis=1)
        level, fraction = local_submersion(wx, center, args.dx)
        counts = dict(solver.iteration_counts)
        diag = solver.iteration_diagnostics
        audit = solver.audit.to_numpy()
        row = {'frame': frame, 'time_s': (frame - 1) / FPS, 'ball_center': [float(v) for v in center],
               'ball_velocity': [float(v) for v in velocity], 'local_surface_m': level, 'submerged_fraction': fraction,
               'max_speed': float(speed.max()), 'p99_speed': float(np.percentile(speed, 99)),
               'kinetic_energy_j': float(0.5 * physics['liquid_density'] * info['particle_volume_m3'] * np.sum(speed.astype(np.float64) ** 2)),
               'water_z_max': float(wx[:, 2].max()), 'advective_cfl': float(speed.max() * sub_dt / args.dx),
               'divergence_iterations': counts['divergence'] - last_counts['divergence'],
               'density_iterations': counts['density'] - last_counts['density'],
               'cap_hits_total': diag['divergence_iteration_cap_hits'] + diag['density_iteration_cap_hits'],
               'fluid_pressure_impulse': audit[0].tolist(), 'ball_pressure_impulse': audit[1].tolist(),
               'ball_viscous_impulse': audit[2].tolist(), 'floor_contacts': int(solver.contacts[None]),
               'frame_compute_s': compute}
        last_counts = counts
        report['frames'].append(row)
        report['simulation_seconds'] = time.monotonic() - sim_start
        report['wall_seconds'] = time.monotonic() - wall_start
        report['iteration_diagnostics'] = dict(diag)
        save_json(out / 'simulation_report.json', report)
        if frame == 1 or frame % 4 == 0:
            print('FRAME', frame, 'z %.4f vz %.3f sub %s cfl %.3f it %d/%d %.1fs' % (
                center[2], velocity[2], 'n/a' if fraction is None else '%.3f' % fraction, row['advective_cfl'],
                row['divergence_iterations'], row['density_iterations'], compute), flush=True)
        assert np.isfinite(wx).all() and np.isfinite(center).all(), 'Non-finite state'
    if writer is not None:
        writer.join()
    report['status'] = 'complete'
    save_json(out / 'simulation_report.json', report)
    print('DONE', json.dumps({'simulation_seconds': report['simulation_seconds'], 'wall_seconds': report['wall_seconds']}), flush=True)


def main():
    global DOMAIN_TOP
    parser = argparse.ArgumentParser()
    parser.add_argument('mode', choices=('settle', 'run'))
    parser.add_argument('--domain-top', type=float, default=DOMAIN_TOP)
    parser.add_argument('--out', required=True)
    parser.add_argument('--dx', type=float, default=0.003)
    parser.add_argument('--substeps', type=int, default=20, help='Genesis substeps per 1/240 s step.')
    parser.add_argument('--divergence-error', type=float, default=0.1)
    parser.add_argument('--density-error', type=float, default=0.05)
    parser.add_argument('--extra-layers', type=int, default=2,
                        help='Layers that make up the floor and wall compaction while settling '
                             '(calibrated by settling; see settle_report.json).')
    parser.add_argument('--film-band', type=float, default=1.0,
                        help='Floor band (in particle sizes) whose fluid pressure does not carry the ball.')
    parser.add_argument('--min-sweeps', default='2,3', help='Minimum divergence,density pressure sweeps.')
    parser.add_argument('--contact-gap', type=float, default=0.5,
                        help='Ball rest gap above the floor, in particle sizes.')
    parser.add_argument('--warm-start', action='store_true',
                        help='Start each pressure solve from half of the previous substep stiffness.')
    parser.add_argument('--skip-air', action='store_true',
                        help='Start the coupled solve just before entry; earlier frames reuse the settled water.')
    parser.add_argument('--damping', type=float, default=0.995)
    parser.add_argument('--settle-seconds', type=float, default=0.5)
    parser.add_argument('--check-seconds', type=float, default=0.25)
    parser.add_argument('--water-state')
    parser.add_argument('--ball-mass', type=float)
    parser.add_argument('--liquid-density', type=float)
    parser.add_argument('--liquid-nu', type=float)
    parser.add_argument('--surface-tension', type=float, default=0.,
                        help='Cohesion coefficient gamma of the water (Genesis SPH; calibrate_surface_tension_apple_drop_kitchen_basin.py).')
    parser.add_argument('--frames', type=int, default=FRAMES, help='Frames to simulate (a shorter test run).')
    args = parser.parse_args()
    DOMAIN_TOP = args.domain_top
    if args.mode == 'settle':
        settle(args)
    else:
        assert args.water_state, '--water-state is required'
        run(args)


if __name__ == '__main__':
    main()
