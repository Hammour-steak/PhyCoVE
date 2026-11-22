"""Simulate the PCVE elastic-duck/pool scene and reconstruct its surfaces.

The accepted pressure operator is consolidated here. Defaults reproduce the
selected upright base's spatial and temporal settings.
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
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import shutil
import struct
import time

LAST_SOLVER = None


def save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf8')
    temporary.replace(path)


def digest(path):
    value = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            value.update(block)
    return value.hexdigest()


def _import_data_runtime():
    global np, cKDTree
    import numpy as np
    from scipy.spatial import cKDTree


def _import_runtime():
    global gs, qd, torch
    _import_data_runtime()
    import genesis as gs
    import quadrants as qd
    import torch
    if hasattr(gs,'qd_float'):
        _load_solver_base()


def _load_solver_base():
    global SPHSolver
    from genesis.engine.solvers.sph_solver import SPHSolver


def affine_weights(points, ghosts, ids, positive_weights, scale):
    points = np.asarray(points, dtype=np.float64)
    ghosts = np.asarray(ghosts, dtype=np.float64)
    ids = np.asarray(ids)
    positive = np.asarray(positive_weights, dtype=np.float64)
    assert scale > 0 and np.all(positive > 0)
    positive = positive / positive.sum(axis=1)[:, None]
    delta = (points[ids] - ghosts[:, None, :]) / scale
    P = np.concatenate([np.ones((*positive.shape, 1)), delta], axis=2)
    gram = np.einsum('gki,gk,gkj->gij', P, positive, P)
    eigen = np.linalg.eigvalsh(gram)
    condition = eigen[:, -1] / eigen[:, 0]
    if not np.isfinite(condition).all() or eigen[:, 0].min() <= 1e-08 or condition.max() > 100000.0:
        raise RuntimeError('Reject rank-deficient or ill-conditioned affine material map.')
    rhs = np.tile([1.0, 0.0, 0.0, 0.0], (len(ghosts), 1))
    weights = positive * np.einsum('gki,gi->gk', P, np.linalg.solve(gram, rhs[..., None])[..., 0])
    if not np.isfinite(weights).all() or np.abs(weights).sum(1).max() > 8:
        raise RuntimeError('Reject unbounded material extrapolation; never clip shape functions.')
    weights32 = weights.astype(np.float32)
    check = weights32.astype(np.float64)
    partition_error = np.abs(check.sum(1) - 1).max()
    position_error = np.linalg.norm(np.einsum('gk,gkd->gd', check, points[ids]) - ghosts, axis=1).max()
    if partition_error > 1e-06 or position_error > 1e-06:
        raise RuntimeError('Float32 material map does not reproduce the rest boundary.')
    return (weights32, {'condition_max': float(condition.max()), 'weight_min': float(weights.min()), 'weight_max': float(weights.max()), 'absolute_weight_sum_max': float(np.abs(weights).sum(1).max()), 'negative_weight_fraction': float(np.mean(weights < 0)), 'rest_partition_error_max': float(partition_error), 'rest_position_error_max_m': float(position_error), 'original_positive_map_force_arm_error_max_m': float(np.linalg.norm(np.einsum('gk,gkd->gd', positive, points[ids]) - ghosts, axis=1).max())})


def create_boundary_solver():
    """The accepted pressure operator, including its conservation and convergence checks."""
    @qd.data_oriented
    class PressureBoundarySPH(SPHSolver):

        def build(self):
            global LAST_SOLVER
            super().build()
            self.n_fluid = self.entities[0].n_particles
            self.n_ghost = self.n_particles - self.n_fluid
            assert self.n_ghost > 0 and len(self.entities) == 2
            self.mpm = self.sim.mpm_solver
            self.relaxation = 0.5
            self.feedback = True
            self.enabled = True
            self.boundary_ready = False
            self.original_id = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.near_boundary = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.impulse = qd.Vector.field(3, dtype=gs.qd_float, shape=(self.n_ghost, self._B))
            self.boundary_inv_mass = qd.field(gs.qd_float, shape=(self.n_ghost, self._B))
            self.map_ids = qd.field(gs.qd_int, shape=(self.n_ghost, 16))
            self.map_weights = qd.field(gs.qd_float, shape=(self.n_ghost, 16))
            self.map_offsets = qd.Vector.field(3, dtype=gs.qd_float, shape=(self.n_ghost, 16))
            self.grid_ids = qd.Vector.field(3, dtype=gs.qd_int, shape=(self.n_ghost, 27, self._B))
            self.grid_weights = qd.field(gs.qd_float, shape=(self.n_ghost, 27, self._B))
            self.audit = qd.Vector.field(3, dtype=qd.f64, shape=(3,))
            self.current_frame = 0
            self.reset_iteration_diagnostics()
            LAST_SOLVER = self
            self.mapping_rejections = qd.field(qd.i32, shape=())
            self.floor_observation = qd.Vector.field(2, dtype=qd.f64, shape=())
            self.boundary_relaxation = 0.1
            LAST_SOLVER = self
            self.boundary_volume = qd.field(gs.qd_float, shape=(self.n_ghost, self._B))
            self.boundary_volume_rate = qd.field(gs.qd_float, shape=(self.n_ghost, self._B))
            self.invalid_boundary_volume = qd.field(qd.i32, shape=())
            self.boundary_volume.fill(self._particle_size ** 3)
            self.contact_failure_examples = []
            LAST_SOLVER = self
            assert self._B == 1, 'Contact-cap sampling currently supports this single-environment experiment only.'
            self._df_max_div_iters = 400
            self._df_max_den_iters = 400
            self.cap_examples = []
            self.error_particle_id = qd.field(qd.i32, shape=())
            self.error_particle_sample = qd.Vector.field(12, gs.qd_float, shape=())
            self._df_max_div_iters = 100
            self._df_max_den_iters = 100
            assert not self.mpm.enable_CPIC and (not self.mpm._ffs)
            assert not self.mpm._constraints_initialized
            LAST_SOLVER = self
            self.allocate_material_fields()
            LAST_SOLVER = self

        def initialize_mapping(self):
            assert not self.sim.coupler._rigid_mpm and (not self.sim.coupler._fem_mpm)
            assert not self.sim.coupler._mpm_pbd and (not self.sim.coupler._mpm_sph)
            assert not self.sim.coupler.tool_solver.is_active
            rest = self.mpm.particles.pos.to_numpy()[0, :, 0]
            ghost = self.particles.pos.to_numpy()[self.n_fluid:, 0]
            (distances, ids) = cKDTree(rest).query(ghost, k=16)
            weights = 1 / (distances ** 2 + 0.003 ** 2)
            weights /= weights.sum(axis=1)[:, None]
            self.map_ids.from_numpy(ids.astype(np.int32))
            self.map_weights.from_numpy(weights.astype(np.float32))
            self.map_offsets.from_numpy((ghost[:, None, :] - rest[ids]).astype(np.float32))
            self.boundary_ready = True
            result = {'ghost_particles': self.n_ghost, 'max_material_map_support_m': float(distances.max()), 'pressure_jacobi_relaxation': self.relaxation, 'boundary_particle_volume_m3': self._particle_size ** 3, 'equal_opposite_impulses': True, 'solid_velocity_updated_each_pressure_iteration': True, 'native_genesis_mpm_sph_disabled': True}
            result['shared_grid_response_preconditioner'] = 'square_of_sum_of_boundary_response_norms_upper_bound'
            result['original_minimum_pressure_sweeps_retained'] = {'divergence': 2, 'density': 3}
            result = result
            result.update(observed_grid_velocity_matches_existing_native_cube_boundary=True, no_new_floor_or_duck_pose_constraint=True, invalid_ghost_stencils_rejected_before_grid_or_hash_access=True)
            result = result
            result['boundary_adjacent_pressure_relaxation'] = self.boundary_relaxation
            result['non_boundary_pressure_relaxation'] = self.relaxation
            result = result
            result.update(boundary_volume_follows_material_jacobian=True, boundary_volume_rate_in_density_prediction=True, volume_reference='Same original rest quadrature volume; no rest-volume normalization change.', pressure_volume_derivative_treatment='Explicit from native MPM old/next deformation, frozen during each pressure solve.')
            result = result
            result['pressure_maximum_iterations'] = {'divergence': 400, 'density': 400}
            result['convergence_tolerances_and_minimum_sweeps_unchanged'] = True
            result = result
            result.update(boundary_velocity_predicts_same_native_next_material_position=True, pressure_scatter_uses_transpose_of_native_material_G2P_weights=True, duplicate_grid_weights_coalesced_before_inverse_mass=True, next_F_and_volume_rate_remain_explicit=True, local_material_grid_span_safety_limit_cells=self.local_width, pressure_maximum_iterations={'divergence': 100, 'density': 100})
            result = result
            rest = self.mpm.particles.pos.to_numpy()[0, :, 0]
            ghost = self.particles.pos.to_numpy()[self.n_fluid:, 0]
            (weights, diagnostic) = affine_weights(rest, ghost, self.map_ids.to_numpy(), self.map_weights.to_numpy(), self.mpm.dx)
            self.affine_weights.from_numpy(weights)
            result.update(affine_embedding=diagnostic, boundary_position='sum_k(N_gk*x_k); fixed reference affine-exact MLS shape functions', boundary_velocity='sum_k(N_gk*native_next_position_rate_k)', pressure_scatter='transpose of same signed/coalesced material G2P map', signed_weights_preserved=True, pressure_first_moment_checked_every_substep=True, boundary_position_uses_F_offsets=False, next_F_and_volume_rate_remain_explicit=True, volume_interpolation='Original positive weights, unchanged scalar J/J-rate rule', angular_impulse_preserved_before_existing_external_boundary_projection=True, no_added_rotation_lock_ballast_or_pose_force=True)
            return result

        @qd.func
        def is_fluid(self, index, batch):
            return self.original_id[index, batch] < self.n_fluid

        @qd.func
        def volume(self, index, batch):
            result = self._particle_volume
            if not self.is_fluid(index, batch):
                result = self.boundary_volume[self.original_id[index, batch] - self.n_fluid, batch]
            return result

        def update_boundary_positions(self, f):
            self.coalesced_weights.fill(0.0)
            self.assemble_material_mapping(f)
            if int(self.mapping_rejections[None]):
                raise RuntimeError('Reject invalid material-grid support; no pose or deformation clamp added.')
            self.compact_material_mapping(f)
            if float(self.mapping_weight_error[None]) > 2e-05:
                raise RuntimeError('Reject incomplete native material-grid pressure support; no renormalized substitute.')
            if self.update_material_volumes(f):
                raise RuntimeError('Reject invalid material Jacobian; no volume/deformation clipping.')
            self.predict_native_material_position_rates(f)
            self.gather_material_ghost_velocities(f, 0)
            if float(self.mapping_moment_error[None]) > 2e-05:
                raise RuntimeError('Reject incomplete pressure moment support; no pose/rotation correction applied.')

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
        def _task_compute_DFSPH_factor(self, i, j, ret: qd.template(), i_b):
            gradient = -self.volume(j, i_b) * self.cubic_kernel_derivative(self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos)
            if self.is_fluid(j, i_b):
                ret[3] += gradient.norm_sqr()
            elif self.feedback:
                ghost = self.original_id[j, i_b] - self.n_fluid
                ret[3] += self.particles_info_reordered[i, i_b].mass * self.boundary_inv_mass[ghost, i_b] * gradient.norm_sqr()
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
            ret.drho += self.volume(j, batch) * difference.dot(gradient) + self.volume_rate_density_term(i, j, batch)
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
            ret += self.volume_rate_density_term(i, j, batch)

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
                ghost = self.original_id[j, batch] - self.n_fluid
                impulse = self.particles_info_reordered[i, batch].mass * dv
                self.impulse[ghost, batch] -= impulse
                self.audit[0] += impulse
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

        @qd.kernel
        def _kernel_density_solve_iteration(self):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    stiffness = (self.particles_reordered[i, batch].drho - 1.0) * self.particles_reordered[i, batch].dfsph_factor
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=stiffness)
                    self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self.density_solve_iteration_task, batch)
                    self.particles_reordered[i, batch].vel += ret.dv
                    self.particles_reordered[i, batch].p -= stiffness * self._density0

        def pressure_to_mpm(self, f):
            self.scatter_material_pressure_impulses(f)
            self.predict_native_material_position_rates(f)
            self.gather_material_ghost_velocities(f, 1)

        def _divergence_solver_iteration(self):
            self._kernel_divergence_solver_iteration()
            self.pressure_to_mpm(self.current_frame)
            self._kernel_compute_density_time_derivative()
            return self._kernel_compute_density_error(0.0) / self.n_fluid

        def _density_solve_iteration(self):
            self._kernel_density_solve_iteration()
            self.pressure_to_mpm(self.current_frame)
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
            eta = self._df_max_error_div * 0.01 / self._substep_dt
            converged = False
            for iteration in range(self._df_max_div_iters):
                average = self._divergence_solver_iteration() / self._density0
                local = self.maximum_contact_error(0.0)
                self.iteration_counts['divergence'] += 1
                if iteration >= 1 and average <= eta and (local <= eta):
                    converged = True
                    break
            d = self.iteration_diagnostics
            d['divergence_solves'] += 1
            d['divergence_iteration_cap_hits'] += int(not converged)
            d['maximum_final_divergence_global_tolerance_ratio'] = max(d['maximum_final_divergence_global_tolerance_ratio'], average / eta)
            d['maximum_final_divergence_contact_tolerance_ratio'] = max(d['maximum_final_divergence_contact_tolerance_ratio'], local / eta)
            if not converged:
                self.record_cap_example('divergence', f, average, local, eta)

        def _density_solve(self, f):
            self._kernel_compute_density_star()
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor, 1 / self._substep_dt ** 2)
            eta = self._df_max_error_den * 0.01
            converged = False
            for iteration in range(self._df_max_den_iters):
                average = self._density_solve_iteration() / self._density0
                local = self.maximum_contact_error(1.0)
                self.iteration_counts['density'] += 1
                if iteration >= 2 and average <= eta and (local <= 0.005):
                    converged = True
                    break
            d = self.iteration_diagnostics
            d['density_solves'] += 1
            d['density_iteration_cap_hits'] += int(not converged)
            d['maximum_final_density_global_tolerance_ratio'] = max(d['maximum_final_density_global_tolerance_ratio'], average / eta)
            d['maximum_final_density_contact_tolerance_ratio'] = max(d['maximum_final_density_contact_tolerance_ratio'], local / 0.005)
            if not converged:
                self.record_cap_example('density', f, average, local, eta)

        @qd.func
        def _task_compute_non_pressure_forces(self, i, j, ret: qd.template(), i_b):
            if self.is_fluid(j, i_b):
                d = self.particles_reordered[i, i_b].pos - self.particles_reordered[j, i_b].pos
                v = self.particles_reordered[i, i_b].vel - self.particles_reordered[j, i_b].vel
                mass = self.particles_info_reordered[j, i_b].mass
                viscosity = self.particles_info_reordered[i, i_b].mu
                density = self.particles_reordered[j, i_b].rho
                ret += 10 * viscosity * (mass / qd.max(density, 1e-06)) * v.dot(d) / (d.norm_sqr() + 0.01 * self._support_radius ** 2) * self.cubic_kernel_derivative(d)

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
        def _kernel_advect_position(self, f: qd.i32):
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    pos = self.particles_reordered[i, batch].pos + self._substep_dt * self.particles_reordered[i, batch].vel
                    (pos, velocity) = self.boundary.impose_pos_vel(pos, self.particles_reordered[i, batch].vel)
                    self.particles_reordered[i, batch].pos = pos
                    self.particles_reordered[i, batch].vel = velocity

        def substep_pre_coupling(self, f):
            if not self.boundary_ready:
                return super().substep_pre_coupling(f)
            self.current_frame = f
            self.update_boundary_positions(f)
            self._kernel_reorder_particles(f)
            self.reorder_original_ids()
            self.near_boundary.fill(0)
            self._kernel_compute_rho(f)
            self._kernel_compute_DFSPH_factor(f)
            self._divergence_solve(f)
            self._kernel_compute_non_pressure_forces(f, self._sim.cur_t)
            self._kernel_predict_velocity(f)
            self._density_solve(f)

        def reset_iteration_diagnostics(self):
            self.iteration_counts = {'divergence': 0, 'density': 0}
            self.iteration_diagnostics = {'divergence_solves': 0, 'density_solves': 0, 'divergence_iteration_cap_hits': 0, 'density_iteration_cap_hits': 0, 'maximum_final_divergence_global_tolerance_ratio': 0.0, 'maximum_final_divergence_contact_tolerance_ratio': 0.0, 'maximum_final_density_global_tolerance_ratio': 0.0, 'maximum_final_density_contact_tolerance_ratio': 0.0}

        @qd.func
        def factor_pair(self, i, j, ret: qd.template(), batch):
            gradient = -self.volume(j, batch) * self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos)
            if self.is_fluid(j, batch):
                ret[3] += gradient.norm_sqr()
            elif self.feedback:
                ghost = self.original_id[j, batch] - self.n_fluid
                coefficient = self.particles_info_reordered[i, batch].mass * self.boundary_inv_mass[ghost, batch]
                ret[4] += qd.sqrt(qd.max(coefficient, 0.0)) * gradient.norm()
            for k in qd.static(range(3)):
                ret[k] -= gradient[k]

        @qd.func
        def projected_grid_velocity(self, f, grid, batch):
            mass = self.mpm.grid[f, grid, batch].mass
            velocity = self.mpm.grid[f, grid, batch].vel_in / mass + self._substep_dt * self.mpm._gravity[batch]
            point = (grid + self.mpm.grid_offset) * self.mpm.dx
            (_, projected) = self.mpm.boundary.impose_pos_vel(point, velocity)
            difference = (projected - velocity).norm()
            if difference > 1e-06:
                self.floor_observation[None][0] += 1.0
                qd.atomic_max(self.floor_observation[None][1], qd.cast(difference, qd.f64))
            return projected

        @qd.kernel
        def _update_contact_consistent_boundary_positions(self, f: qd.i32) -> qd.i32:
            self.mapping_rejections[None] = 0
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                point = qd.Vector.zero(gs.qd_float, 3)
                active = False
                for k in qd.static(range(16)):
                    particle = self.map_ids[ghost, k]
                    active = active or self.mpm.particles_ng[f, particle, batch].active
                    point += self.map_weights[ghost, k] * (self.mpm.particles[f, particle, batch].pos + self.mpm.particles[f, particle, batch].F @ self.map_offsets[ghost, k])
                base = qd.floor(point * self.mpm.inv_dx - 0.5).cast(gs.qd_int)
                grid_base = base - self.mpm.grid_offset
                valid = True
                for d in qd.static(range(3)):
                    valid = valid and (not qd.math.isnan(point[d])) and (not qd.math.isinf(point[d]))
                    valid = valid and grid_base[d] >= 0 and (grid_base[d] + 2 < self.mpm.grid_res[d])
                    valid = valid and point[d] >= self._lower_bound[d] and (point[d] <= self._upper_bound[d])
                if not valid:
                    self.mapping_rejections[None] += 1
                else:
                    self.particles[ghost + self.n_fluid, batch].pos = point
                    self.particles_ng[ghost + self.n_fluid, batch].active = active and self.enabled
                    fx = point * self.mpm.inv_dx - base.cast(gs.qd_float)
                    w = [0.5 * (1.5 - fx) ** 2, 0.75 - (fx - 1) ** 2, 0.5 * (fx - 0.5) ** 2]
                    total = gs.qd_float(0.0)
                    for offset in qd.static(qd.grouped(qd.ndrange(3, 3, 3))):
                        index = offset[0] * 9 + offset[1] * 3 + offset[2]
                        grid = grid_base + offset
                        weight = w[offset[0]][0] * w[offset[1]][1] * w[offset[2]][2]
                        if self.mpm.grid[f, grid, batch].mass <= 1e-08:
                            weight = 0.0
                        self.grid_ids[ghost, index, batch] = grid
                        self.grid_weights[ghost, index, batch] = weight
                        total += weight
                    velocity = qd.Vector.zero(gs.qd_float, 3)
                    inverse_mass = gs.qd_float(0.0)
                    for k in qd.static(range(27)):
                        weight = self.grid_weights[ghost, k, batch] / qd.max(total, 1e-12)
                        self.grid_weights[ghost, k, batch] = weight
                        grid = self.grid_ids[ghost, k, batch]
                        mass = self.mpm.grid[f, grid, batch].mass
                        if weight > 0.0:
                            velocity += weight * self.projected_grid_velocity(f, grid, batch)
                            inverse_mass += weight * weight * self.mpm.particle_volume_scale / mass
                    self.particles[ghost + self.n_fluid, batch].vel = velocity
                    self.boundary_inv_mass[ghost, batch] = inverse_mass
            return self.mapping_rejections[None]

        @qd.kernel
        def update_material_volumes(self, f: qd.i32) -> qd.i32:
            self.invalid_boundary_volume[None] = 0
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                current = gs.qd_float(0.0)
                following = gs.qd_float(0.0)
                for k in qd.static(range(16)):
                    particle = self.map_ids[ghost, k]
                    weight = self.map_weights[ghost, k]
                    current += weight * self.mpm.particles[f, particle, batch].F.determinant()
                    following += weight * self.mpm.particles[f + 1, particle, batch].F.determinant()
                if qd.math.isnan(current) or qd.math.isinf(current) or qd.math.isnan(following) or qd.math.isinf(following) or (current <= 0.05) or (following <= 0.05):
                    self.invalid_boundary_volume[None] += 1
                else:
                    self.boundary_volume[ghost, batch] = self._particle_size ** 3 * current
                    self.boundary_volume_rate[ghost, batch] = self._particle_size ** 3 * (following - current) / self._substep_dt
            return self.invalid_boundary_volume[None]

        @qd.func
        def volume_rate_density_term(self, i, j, batch):
            result = gs.qd_float(0.0)
            if not self.is_fluid(j, batch):
                ghost = self.original_id[j, batch] - self.n_fluid
                result = self.boundary_volume_rate[ghost, batch] * self.cubic_kernel((self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos).norm())
            return result

        @qd.func
        def sampled_density_components(self, i, j, ret: qd.template(), batch):
            delta = self.particles_reordered[i, batch].vel - self.particles_reordered[j, batch].vel
            spatial = self.volume(j, batch) * delta.dot(self.cubic_kernel_derivative(self.particles_reordered[i, batch].pos - self.particles_reordered[j, batch].pos))
            if self.is_fluid(j, batch):
                ret[0] += spatial
            else:
                ret[1] += spatial
                ret[2] += self.volume_rate_density_term(i, j, batch)
                ret[3] += 1.0

        @qd.kernel
        def locate_worst_contact_particle(self, offset: gs.qd_float, maximum: gs.qd_float):
            self.error_particle_id[None] = self.n_particles
            for (i, batch) in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch) and self.near_boundary[i, batch]:
                    if self.particles_reordered[i, batch].drho - offset == maximum:
                        qd.atomic_min(self.error_particle_id[None], i)

        @qd.kernel
        def capture_worst_contact_particle(self):
            i = self.error_particle_id[None]
            if i < self.n_particles:
                batch = 0
                ret = qd.Vector.zero(gs.qd_float, 4)
                self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self.sampled_density_components, batch)
                position = self.particles_reordered[i, batch].pos
                self.error_particle_sample[None] = qd.Vector([qd.cast(self.original_id[i, batch], gs.qd_float), position[0], position[1], position[2], self.particles_reordered[i, batch].rho / self._density0, self.particles_reordered[i, batch].drho, self.particles_reordered[i, batch].dfsph_factor, ret[0], ret[1], ret[2], ret[3], self.particles_reordered[i, batch].vel.norm()])

        def record_cap_example(self, kind, f, average, local, eta):
            if sum((row['kind'] == kind for row in self.cap_examples)) >= 8:
                return
            self.locate_worst_contact_particle(0.0 if kind == 'divergence' else 1.0, local)
            self.capture_worst_contact_particle()
            sample = self.error_particle_sample.to_numpy().tolist()
            row = {'kind': kind, 'native_mpm_substep_index': int(f), 'solve_ordinal': self.iteration_diagnostics[kind + '_solves'], 'maximum_iterations': 100, 'global_error_over_tolerance': average / eta, 'contact_error_over_tolerance': local / (eta if kind == 'divergence' else 0.005), 'worst_contact_original_fluid_id': int(sample[0]), 'worst_contact_position_m': sample[1:4], 'current_density_over_rest': sample[4], 'predicted_density_or_divergence': sample[5], 'DFSPH_factor_after_stage_scaling': sample[6], 'fluid_spatial_density_rate_s_inv': sample[7], 'boundary_spatial_density_rate_s_inv': sample[8], 'boundary_volume_density_rate_s_inv': sample[9], 'boundary_neighbor_count': int(sample[10]), 'fluid_speed_mps': sample[11]}
            self.cap_examples.append(row)
            print('PRESSURE_CAP_SAMPLE', row, flush=True)

        def allocate_material_fields(self):
            self.local_width = 16
            self.material_grid_base = qd.Vector.field(3, gs.qd_int, shape=(self.n_ghost, self._B))
            self.coalesced_weights = qd.field(gs.qd_float, shape=(self.n_ghost, self.local_width ** 3, self._B))
            self.grid_ids = qd.Vector.field(3, gs.qd_int, shape=(self.n_ghost, 432, self._B))
            self.grid_weights = qd.field(gs.qd_float, shape=(self.n_ghost, 432, self._B))
            self.grid_count = qd.field(gs.qd_int, shape=(self.n_ghost, self._B))
            self.material_position_rate = qd.Vector.field(3, gs.qd_float, shape=(self.mpm.n_particles, self._B))
            self.mapping_weight_error = qd.field(gs.qd_float, shape=())
            self.affine_weights = qd.field(gs.qd_float, shape=(self.n_ghost, 16))
            self.mapping_moment_error = qd.field(gs.qd_float, shape=())
            self.mapping_moment_error_peak = qd.field(gs.qd_float, shape=())

        @qd.kernel
        def assemble_material_mapping(self, f: qd.i32):
            self.mapping_rejections[None] = 0
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                point = qd.Vector.zero(gs.qd_float, 3)
                minimum = qd.Vector([2147483647, 2147483647, 2147483647])
                maximum = qd.Vector([-2147483647, -2147483647, -2147483647])
                active = False
                for k in range(16):
                    p = self.map_ids[ghost, k]
                    x = self.mpm.particles[f, p, batch].pos
                    active = active or self.mpm.particles_ng[f, p, batch].active
                    point += self.affine_weights[ghost, k] * x
                    base = qd.floor(x * self.mpm.inv_dx - 0.5).cast(gs.qd_int) - self.mpm.grid_offset
                    minimum = qd.min(minimum, base)
                    maximum = qd.max(maximum, base + 2)
                valid = True
                for d in qd.static(range(3)):
                    valid = valid and minimum[d] >= 0 and (maximum[d] < self.mpm.grid_res[d])
                    valid = valid and maximum[d] - minimum[d] < self.local_width
                    valid = valid and (not qd.math.isnan(point[d])) and (not qd.math.isinf(point[d]))
                    valid = valid and point[d] >= self._lower_bound[d] and (point[d] <= self._upper_bound[d])
                if not valid:
                    self.mapping_rejections[None] += 1
                else:
                    self.material_grid_base[ghost, batch] = minimum
                    self.particles[ghost + self.n_fluid, batch].pos = point
                    self.particles_ng[ghost + self.n_fluid, batch].active = active and self.enabled
                    for k in range(16):
                        p = self.map_ids[ghost, k]
                        x = self.mpm.particles[f, p, batch].pos
                        base = qd.floor(x * self.mpm.inv_dx - 0.5).cast(gs.qd_int)
                        fx = x * self.mpm.inv_dx - base.cast(gs.qd_float)
                        w = [0.5 * (1.5 - fx) ** 2, 0.75 - (fx - 1) ** 2, 0.5 * (fx - 0.5) ** 2]
                        for offset in qd.static(qd.grouped(qd.ndrange(3, 3, 3))):
                            grid = base - self.mpm.grid_offset + offset
                            weight = self.affine_weights[ghost, k] * w[offset[0]][0] * w[offset[1]][1] * w[offset[2]][2]
                            if self.mpm.grid[f, grid, batch].mass > gs.EPS:
                                local = grid - minimum
                                flat = (local[0] * self.local_width + local[1]) * self.local_width + local[2]
                                self.coalesced_weights[ghost, flat, batch] += weight

        @qd.kernel
        def compact_material_mapping(self, f: qd.i32):
            self.mapping_weight_error[None] = 0.0
            self.mapping_moment_error[None] = 0.0
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                count = 0
                total = gs.qd_float(0.0)
                inverse = gs.qd_float(0.0)
                first_moment = qd.Vector.zero(gs.qd_float, 3)
                for flat in range(self.local_width ** 3):
                    weight = self.coalesced_weights[ghost, flat, batch]
                    if weight != 0.0:
                        offset = qd.Vector([flat // self.local_width ** 2, flat // self.local_width % self.local_width, flat % self.local_width])
                        grid = self.material_grid_base[ghost, batch] + offset
                        self.grid_ids[ghost, count, batch] = grid
                        self.grid_weights[ghost, count, batch] = weight
                        inverse += weight ** 2 * self.mpm.particle_volume_scale / self.mpm.grid[f, grid, batch].mass
                        total += weight
                        first_moment += weight * (grid + self.mpm.grid_offset) * self.mpm.dx
                        count += 1
                self.grid_count[ghost, batch] = count
                self.boundary_inv_mass[ghost, batch] = inverse
                qd.atomic_max(self.mapping_weight_error[None], qd.abs(total - 1.0))
                error = (first_moment - self.particles[ghost + self.n_fluid, batch].pos).norm()
                qd.atomic_max(self.mapping_moment_error[None], error)
                qd.atomic_max(self.mapping_moment_error_peak[None], error)

        @qd.kernel
        def predict_native_material_position_rates(self, f: qd.i32):
            for (p, batch) in qd.ndrange(self.mpm.n_particles, self._B):
                if self.mpm.particles_ng[f, p, batch].active:
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
        def gather_material_ghost_velocities(self, f: qd.i32, reordered: qd.i32):
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                velocity = qd.Vector.zero(gs.qd_float, 3)
                for k in range(16):
                    p = self.map_ids[ghost, k]
                    velocity += self.affine_weights[ghost, k] * self.material_position_rate[p, batch]
                if reordered:
                    if self.particles_ng[ghost + self.n_fluid, batch].active:
                        index = self.particles_ng[ghost + self.n_fluid, batch].reordered_idx
                        self.particles_reordered[index, batch].vel = velocity
                else:
                    self.particles[ghost + self.n_fluid, batch].vel = velocity

        @qd.kernel
        def scatter_material_pressure_impulses(self, f: qd.i32):
            for (ghost, batch) in qd.ndrange(self.n_ghost, self._B):
                if self.feedback:
                    for k in range(self.grid_count[ghost, batch]):
                        weight = self.grid_weights[ghost, k, batch]
                        grid = self.grid_ids[ghost, k, batch]
                        self.mpm.grid[f, grid, batch].vel_in += weight * self.impulse[ghost, batch] * self.mpm.particle_volume_scale
                        self.audit[1] += weight * self.impulse[ghost, batch]
                self.impulse[ghost, batch] = qd.Vector.zero(gs.qd_float, 3)
    return PressureBoundarySPH


def create_timed_density_solver():
    """Keep the original operator before the event; use live rest density afterwards.

    Quadrants captures Python floats in compiled kernels. Merely assigning
    ``_density0`` at t would leave three already-compiled pressure kernels at
    the old density. The event-only kernels below read particle material fields
    instead. Untimed cases never instantiate this subclass.
    """
    base = create_boundary_solver()

    @qd.data_oriented
    class TimedDensityPressureBoundarySPH(base):
        def build(self):
            self.density_switch_applied = False
            super().build()

        @qd.kernel
        def _kernel_switch_uniform_density(self, rho: gs.qd_float, nu: gs.qd_float, ratio: gs.qd_float):
            for i in range(self.n_particles):
                self.particles_info[i].rho = rho
                self.particles_info[i].mass = self._particle_volume * rho
                self.particles_info[i].mu = nu
            for i, batch in qd.ndrange(self.n_particles, self._B):
                self.particles_info_reordered[i, batch].rho = rho
                self.particles_info_reordered[i, batch].mass = self._particle_volume * rho
                self.particles_info_reordered[i, batch].mu = nu
                # Positions, velocities and all solid fields are deliberately untouched.
                self.particles[i, batch].rho *= ratio
                self.particles_reordered[i, batch].rho *= ratio
                self.particles[i, batch].p = 0.0
                self.particles_reordered[i, batch].p = 0.0
                self.particles[i, batch].dfsph_factor = 0.0
                self.particles_reordered[i, batch].dfsph_factor = 0.0
                self.particles[i, batch].drho = 0.0
                self.particles_reordered[i, batch].drho = 0.0
                self.particles[i, batch].acc = qd.Vector.zero(gs.qd_float, 3)
                self.particles_reordered[i, batch].acc = qd.Vector.zero(gs.qd_float, 3)

        def switch_uniform_density(self, rho, dynamic_viscosity):
            assert not self.density_switch_applied and 0 < rho < self._density0
            old = float(self._density0)
            nu = dynamic_viscosity / rho
            assert self._substep_dt <= self._stable_dt_coef * .01 * self._support_radius**2 / nu
            self._kernel_switch_uniform_density(rho, nu, rho/old)
            self._density0 = float(rho)  # Host-side convergence tolerances.
            self.density_switch_applied = True

        @qd.kernel
        def _kernel_compute_density_star_live(self):
            for i, batch in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    density = gs.qd_float(1.0)
                    if self.is_fluid(i, batch):
                        delta = gs.qd_float(0.0)
                        self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, delta, self._task_compute_density_star, batch)
                        rho0 = self.particles_info_reordered[i, batch].rho
                        density = qd.max(self.particles_reordered[i, batch].rho/rho0 + self._substep_dt*delta, 1.0)
                    self.particles_reordered[i, batch].drho = density

        @qd.kernel
        def _kernel_density_solve_iteration_live(self):
            for i, batch in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active and self.is_fluid(i, batch):
                    stiffness = (self.particles_reordered[i, batch].drho-1.0)*self.particles_reordered[i, batch].dfsph_factor
                    ret = qd.Struct(dv=qd.Vector.zero(gs.qd_float, 3), k_i=stiffness)
                    self.sh.for_all_neighbors(i, self.particles_reordered.pos, self._support_radius, ret, self.density_solve_iteration_task, batch)
                    self.particles_reordered[i, batch].vel += ret.dv
                    self.particles_reordered[i, batch].p -= stiffness*self.particles_info_reordered[i, batch].rho

        @qd.kernel
        def _kernel_compute_density_error_live(self, offset: gs.qd_float) -> gs.qd_float:
            error = gs.qd_float(0.0)
            for i, batch in qd.ndrange(self.n_particles, self._B):
                if self.particles_ng_reordered[i, batch].active:
                    error += self.particles_info_reordered[i, batch].rho*self.particles_reordered[i, batch].drho-offset
            return error

        # Kernel descriptors cache a bound function on the instance. Do not
        # dispatch by overriding a kernel's own name: the first call by that name
        # would shadow that Python dispatcher. Dispatch from these host loops.
        def _divergence_solver_iteration(self):
            if not self.density_switch_applied:
                return super()._divergence_solver_iteration()
            self._kernel_divergence_solver_iteration()
            self.pressure_to_mpm(self.current_frame)
            self._kernel_compute_density_time_derivative()
            return self._kernel_compute_density_error_live(0.0)/self.n_fluid

        def _density_solve_iteration(self):
            if not self.density_switch_applied:
                return super()._density_solve_iteration()
            self._kernel_density_solve_iteration_live()
            self.pressure_to_mpm(self.current_frame)
            self._kernel_compute_density_star_live()
            return self._kernel_compute_density_error_live(self._density0)/self.n_fluid

        def _density_solve(self, f):
            if not self.density_switch_applied:
                return super()._density_solve(f)
            self._kernel_compute_density_star_live()
            self._kernel_multiply_time_step(self.particles_reordered.dfsph_factor,1/self._substep_dt**2)
            eta = self._df_max_error_den*.01
            converged = False
            for iteration in range(self._df_max_den_iters):
                average = self._density_solve_iteration()/self._density0
                local = self.maximum_contact_error(1.0)
                self.iteration_counts['density'] += 1
                if iteration >= 2 and average <= eta and local <= .005:
                    converged = True
                    break
            d = self.iteration_diagnostics
            d['density_solves'] += 1
            d['density_iteration_cap_hits'] += int(not converged)
            d['maximum_final_density_global_tolerance_ratio'] = max(d['maximum_final_density_global_tolerance_ratio'],average/eta)
            d['maximum_final_density_contact_tolerance_ratio'] = max(d['maximum_final_density_contact_tolerance_ratio'],local/.005)
            if not converged:
                self.record_cap_example('density',f,average,local,eta)

    return TimedDensityPressureBoundarySPH


def duck_present(physics):
    presence = physics.get('duck_presence', [1])
    assert presence in ([0], [1]), 'Only whole-clip duck presence is supported.'
    return bool(presence[0])


def water_present(physics):
    presence = physics.get('water_presence', [1])
    assert presence in ([0], [1]), 'Only whole-clip water presence is supported.'
    return bool(presence[0])


def create_mass_preserving_mpm_solver(target_mass_kg, density_kg_m3):
    """Refine quadrature without changing total mass, volume or E/rho."""
    from genesis.engine.solvers.mpm_solver import MPMSolver

    @qd.data_oriented
    class MassPreservingMPM(MPMSolver):
        def build(self):
            assert len(self.entities) == 1 and target_mass_kg > 0 and density_kg_m3 > 0
            count = sum(entity.n_particles for entity in self.entities)
            self._particle_volume_real = target_mass_kg/density_kg_m3/count
            self._particle_volume = self._particle_volume_real*self._particle_volume_scale
            super().build()

    return MassPreservingMPM


def empty_pool_floor_tolerance(spec):
    """Bound grid-contact discretization error, not a particle-position clamp.

    Native rigid/MPM contact filters grid velocities before G2P. It does not
    project each material point onto the rigid plane. Require the error to
    remain below 5% of a grid cell, 10% of particle spacing and one quarter
    of the existing contact softness (0.5 mm for this accepted scene).
    """
    if 'numerical_repair' not in spec:
        return 2e-6
    q = spec['simulation_quality']
    return min(.05/q['mpm_grid_density_per_m'],.1*q['mpm_particle_size_m'],
               .25*spec['empty_pool_contact']['softness_m'])


def validate_empty_pool_floor_contact(gap, spec):
    tolerance = empty_pool_floor_tolerance(spec)
    assert math.isfinite(gap) and gap >= -tolerance, {
        'particle_floor_clearance_m':float(gap),'allowed_discretization_error_m':tolerance,
        'contact_method':'Native grid-velocity contact; no particle or visual-position projection.'}


def simulate_without_water(case, frames=96, max_wall_seconds=1800):
    """Native deformable MPM in the empty pool, without any fluid entities."""
    wall_start = time.monotonic()
    _import_runtime()
    spec, assets, manifest = load_case(case)
    p, q = spec['physics'], spec['simulation_quality']
    assert duck_present(p) and not water_present(p)
    assert spec['counterfactual']['deleted_objects'] == ['water']
    assert not spec['counterfactual'].get('timed_edits')
    alignment = spec['numerical_boundary_alignment']
    floor = alignment['pool_floor_top_z_m']
    repaired = 'duck_quadrature_target_mass_kg' in q
    contact = spec.get('empty_pool_contact')
    if repaired:
        assert contact['kind'] == 'rigid_plane' and contact['plane_z_m'] == floor
        assert q['mpm_lower_bound_m'][2]+3/q['mpm_grid_density_per_m'] < floor-.05
        assert q['duck_quadrature_target_mass_kg'] == manifest['base_actual']['duck_discrete_mass_kg']
    else:
        assert math.isclose(q['mpm_lower_bound_m'][2]+3/q['mpm_grid_density_per_m'], floor)
    assert math.isclose(q['step_dt_seconds']*q['steps_per_video_frame'], 1/spec['render']['fps'])
    out = case/'runs/source'
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Simulation already exists; use a fresh case directory.')
    (out/'particles').mkdir(parents=True, exist_ok=True)
    gs.init(backend=gs.cuda, precision='32', seed=20261011, logging_level='warning')
    if repaired:
        import genesis.engine.simulator as simulator
        simulator.MPMSolver = create_mass_preserving_mpm_solver(
            q['duck_quadrature_target_mass_kg'],p['duck_density_kg_m3'])
    sim_options = gs.options.SimOptions(dt=q['step_dt_seconds'], substeps=q['substeps_per_step'],
        gravity=p['gravity_mps2'], floor_height=q['sph_lower_bound_m'][2], requires_grad=False)
    mpm_options = gs.options.MPMOptions(grid_density=q['mpm_grid_density_per_m'],
        particle_size=q['mpm_particle_size_m'], lower_bound=q['mpm_lower_bound_m'], upper_bound=q['mpm_upper_bound_m'])
    sph_options = gs.options.SPHOptions(particle_size=q['sph_particle_size_m'], pressure_solver='DFSPH',
        lower_bound=q['sph_lower_bound_m'], upper_bound=q['sph_upper_bound_m'])
    coupler_options = gs.options.LegacyCouplerOptions(rigid_mpm=repaired, rigid_sph=False,
        rigid_pbd=False, rigid_fem=False, mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False)
    scene = gs.Scene(sim_options=sim_options, mpm_options=mpm_options, sph_options=sph_options,
                     coupler_options=coupler_options, show_viewer=False)
    duck = scene.add_entity(morph=gs.morphs.Mesh(file=str(case/'duck_solid.obj'),
        pos=p['duck_initial_reference_m'], scale=1., euler=(0.,0.,0.), decimate=False, convexify=False),
        material=gs.materials.MPM.Elastic(E=p['young_modulus_pa'], nu=p['poisson_ratio'],
            rho=p['duck_density_kg_m3'], model=p['constitutive_model'], sampler='regular'),
        surface=gs.surfaces.Default(color=(.9,.8,.2,1.), vis_mode='particle'))
    floor_entity = None
    if repaired:
        floor_entity = scene.add_entity(morph=gs.morphs.Plane(pos=(0.,0.,floor)),
            material=gs.materials.Rigid(coup_friction=contact['friction'],
                coup_restitution=contact['restitution'],coup_softness=contact['softness_m']))
    tick = time.monotonic()
    scene.build(n_envs=0)
    build_seconds = time.monotonic()-tick
    assert scene.sim.sph_solver.n_particles == 0 and not scene.sim.sph_solver.is_active
    assert len(scene.entities) == (2 if repaired else 1) and scene.sim.mpm_solver.is_active
    if repaired:
        assert float(duck.solver.boundary.lower[2]) < floor-.05
        duck.set_particles_vel(np.broadcast_to(np.asarray(p['duck_initial_velocity_mps'],dtype=np.float32),
            (duck.n_particles,3)).copy())
    else:
        assert math.isclose(float(duck.solver.boundary.lower[2]), floor, abs_tol=1e-7)
        duck.set_velocity(p['duck_initial_velocity_mps'])
    rest = cpu(duck.get_state().pos)[0].astype(np.float64)
    with np.load(assets/'duck_reference_particles.npz') as reference:
        if not repaired:
            assert np.array_equal(rest, reference['duck_rest']), 'Initial material points differ from the selected base.'
    assert (duck.n_particles > manifest['base_actual']['duck_particles']) if repaired else (
        duck.n_particles == manifest['base_actual']['duck_particles'])
    api_mass = float(cpu(duck.get_mass())[0])
    actual_mass = (float(np.asarray(duck.solver.particles_info.mass.to_numpy(),dtype=np.float64).sum()/
                         duck.solver._particle_volume_scale) if repaired else api_mass)
    assert abs(actual_mass/manifest['base_actual']['duck_discrete_mass_kg']-1) < 2e-6
    empty = np.empty((0,3), dtype=np.float32)
    np.savez_compressed(out/'initial_particles.npz', duck_rest=rest, water_rest=empty, water_initial_velocity=empty)
    sub_dt = q['step_dt_seconds']/q['substeps_per_step']
    wave_speed = math.sqrt(p['young_modulus_pa']*(1-p['poisson_ratio'])/
        (p['duck_density_kg_m3']*(1+p['poisson_ratio'])*(1-2*p['poisson_ratio'])))
    report = {'scene_id':'elastic_fluid_duck','case_id':spec['counterfactual']['id'],
        'status':'simulating','physics':p,'simulation_quality':q,'water_present':False,'duck_present':True,
        'counterfactual':spec['counterfactual'],
        'asset_manifest_sha256':digest(assets/'asset_manifest.json'),
        'versions':{'genesis':importlib.metadata.version('genesis-world'),
            'quadrants':importlib.metadata.version('quadrants'),'torch':torch.__version__},
        'device':torch.cuda.get_device_name(),'seed':20261011,
        'coupling':{'enabled':False,'ghost_particles':0,'buoyancy_present':False,
            'fluid_pressure_present':False,'fluid_drag_present':False,'prescribed_duck_trajectory':False,
            'reason':'Pool water and its complete SPH/pressure-ghost representation deleted before initialization.'},
        'actual':{'sim_options':sim_options.model_dump(mode='json'),
            'mpm_options':mpm_options.model_dump(mode='json'),'sph_options':sph_options.model_dump(mode='json'),
            'coupler_options':coupler_options.model_dump(mode='json'),
            'duck_particles':duck.n_particles,'water_particles':0,'ghost_particles':0,
            'mpm_active':True,'sph_active':False,'sph_entities':0,
            'duck_discrete_mass_kg':actual_mass,'water_discrete_mass_kg':0.,
            'mpm_grid_spacing_m':duck.solver.dx,
            'duck_mass_api_float32_reduction_kg':api_mass,
            'rest_quadrature_volume_m3':duck.solver._particle_volume_real*duck.n_particles,
            'rigid_plane_contact':contact if repaired else None,
            'native_safety_boundary_is_not_physical_floor':repaired,
            'physical_contact_lower_m':duck.solver.boundary.lower.tolist(),
            'physical_contact_upper_m':duck.solver.boundary.upper.tolist(),
            'floor_restitution':float(duck.solver.boundary.restitution)},
        'numerical_boundary_alignment':alignment,
        'floor_contact_model':('Fixed rigid-plane SDF contact at the rendered pool floor, zero friction/restitution as before. Safety boundary is below the floor; refined MPM quadrature preserves mass and reference volume.' if repaired else
            'Native MPM grid nonpenetration and particle safety projection; free-slip, zero boundary restitution. Elastic deformation and rebound arise from the unchanged MPM material.'),
        'build_seconds':build_seconds,'water_settle_compute_seconds':0.,
        'time_step_diagnostic':{'actual_substep_dt_seconds':sub_dt,
            'mpm_rest_longitudinal_wave_speed_mps':wave_speed},'frames':[]}
    start = time.monotonic()
    try:
        for frame in range(1, frames+1):
            tick = time.monotonic()
            if frame > 1:
                for _ in range(q['steps_per_video_frame']):
                    scene.step()
            state = duck.get_state()
            x, F, velocity = cpu(state.pos)[0], cpu(state.F)[0], cpu(state.vel)[0]
            affine_velocity = cpu(state.C)[0] if repaired else None
            assert all(np.isfinite(v).all() for v in (x,F,velocity)), 'Non-finite MPM state.'
            J = np.linalg.det(F)
            assert J.min() > .05, 'Collapsed or inverted material.'
            speed = np.linalg.norm(velocity, axis=1)
            t = (frame-1)/spec['render']['fps']
            analytic_center = rest.mean(axis=0)+np.asarray(p['duck_initial_velocity_mps'])*t+.5*np.asarray(p['gravity_mps2'])*t*t
            row = {'frame':frame,'time_seconds':t,
                'duck_center_m':x.astype(np.float64).mean(axis=0).tolist(),'duck_mean_velocity_mps':velocity.astype(np.float64).mean(axis=0).tolist(),
                'duck_bounds_m':[x.min(axis=0).tolist(),x.max(axis=0).tolist()],
                'duck_deformation':deformation(rest,x.astype(np.float64)),'jacobian_min':float(J.min()),'jacobian_max':float(J.max()),
                'duck_speed_max_mps':float(speed.max()),
                'mpm_rest_wave_cfl':float((wave_speed+speed.max())*sub_dt*q['mpm_grid_density_per_m']),
                'floor_particle_clearance_m':float(x[:,2].min()-floor),
                'pre_contact_free_fall_center_error_m':float(np.linalg.norm(x.astype(np.float64).mean(axis=0)-analytic_center)) if t<=.375 else None,
                'frame_compute_seconds':time.monotonic()-tick}
            assert row['mpm_rest_wave_cfl'] < .9
            validate_empty_pool_floor_contact(row['floor_particle_clearance_m'],spec)
            extra = {'duck_C':affine_velocity} if repaired else {}
            np.savez(out/'particles'/f'frame_{frame:04d}.npz',duck_pos=x,duck_F=F,duck_vel=velocity,
                     water_pos=empty,water_vel=empty,**extra)
            report['frames'].append(row)
            report['minimum_jacobian'] = min(r['jacobian_min'] for r in report['frames'])
            report['peak_deformation_rms_m'] = max(r['duck_deformation']['rms_m'] for r in report['frames'])
            report['simulation_seconds'] = time.monotonic()-start
            report['wall_seconds'] = time.monotonic()-wall_start
            save(out/'simulation_report.json',report)
            if frame == 1 or frame%4 == 0:
                print('WATER_DELETED_MPM_FRAME',frame,'z',row['duck_center_m'][2],
                      'floor_clearance',row['floor_particle_clearance_m'],'Jmin',row['jacobian_min'],flush=True)
            if report['wall_seconds'] > max_wall_seconds and frame < frames:
                raise TimeoutError('Simulation safety time limit reached; partial output is preserved.')
        report['status'] = 'simulated_awaiting_coupling_and_visual_review' if frames == 96 else 'diagnostic_partial_not_accepted'
    except BaseException as error:
        report.update(status='failed_partial_not_accepted',error=repr(error))
        raise
    finally:
        report['wall_seconds'] = time.monotonic()-wall_start
        save(out/'simulation_report.json',report)


def material_neighbor_reference(rest, nominal_spacing):
    distances, ids = cKDTree(rest).query(rest,k=7)
    delta = rest[ids[:,1:]]-rest[:,None,:]
    mask = (distances[:,1:]>.9*nominal_spacing)&(distances[:,1:]<1.1*nominal_spacing)
    mask &= np.sum(np.abs(delta)>nominal_spacing*.1,axis=2)==1
    i, slot = np.nonzero(mask)
    j = ids[:,1:][i,slot]
    DX = rest[j]-rest[i]
    assert len(i)>3*len(rest), 'Insufficient connected reference-lattice material neighbors.'
    return i,j,DX,np.linalg.norm(DX,axis=1)


def material_continuity_observation(reference, positions, deformation_gradients):
    i,j,DX,lengths = reference
    delta = positions[j]-positions[i]
    ratios = np.linalg.norm(delta,axis=1)/lengths
    errors = np.linalg.norm(delta-np.einsum('nij,nj->ni',deformation_gradients[i],DX),axis=1)
    return {'material_neighbor_pairs':len(i),'maximum_neighbor_ratio':float(ratios.max()),
        'p99_neighbor_ratio':float(np.percentile(ratios,99)),
        'neighbor_pairs_over_4x':int(np.sum(ratios>4)),
        'maximum_F_consistency_error_m':float(errors.max()),
        'p99_F_consistency_error_m':float(np.percentile(errors,99))}


def audit_repaired_empty_pool(case, spec, assets, manifest):
    run = case/'runs/source'
    r = json.loads((run/'simulation_report.json').read_text())
    p,q,actual = r['physics'],r['simulation_quality'],r['actual']
    assert r['status']=='simulated_awaiting_coupling_and_visual_review' and len(r['frames'])==96
    assert p==spec['physics'] and q==spec['simulation_quality']
    assert not water_present(p) and duck_present(p)
    assert not r['coupling']['enabled'] and not r['coupling']['prescribed_duck_trajectory']
    assert not any(r['coupling'][k] for k in ('buoyancy_present','fluid_pressure_present','fluid_drag_present'))
    assert actual['water_particles']==actual['ghost_particles']==actual['sph_entities']==0
    assert actual['sph_active'] is False and actual['mpm_active'] is True
    assert actual['duck_particles']>manifest['base_actual']['duck_particles']
    assert abs(actual['duck_discrete_mass_kg']/manifest['base_actual']['duck_discrete_mass_kg']-1)<2e-6
    assert math.isclose(actual['rest_quadrature_volume_m3'],
        manifest['base_actual']['duck_discrete_mass_kg']/p['duck_density_kg_m3'],rel_tol=2e-6)
    for key in ('sim_options','sph_options'):
        assert actual[key]==manifest['base_actual'][key]
    assert actual['mpm_options']==dict(manifest['base_actual']['mpm_options'],
        lower_bound=q['mpm_lower_bound_m'],particle_size=q['mpm_particle_size_m'])
    assert actual['coupler_options']==dict(manifest['base_actual']['coupler_options'],rigid_mpm=True)
    assert actual['rigid_plane_contact']==spec['empty_pool_contact']
    assert actual['native_safety_boundary_is_not_physical_floor']
    repair = spec['numerical_repair']
    frozen = json.loads((assets/'scene_spec.json').read_text())
    assert repair['before']==frozen['simulation_quality'] and repair['after']==q
    for key in repair['unchanged_physical_parameters']:
        assert p[key]==frozen['physics'][key]
    assert spec['counterfactual']['changes']=={'water_presence':{'before':[1],'after':[0]}}
    limits = repair['continuity_limits']
    grid_dx = 1/q['mpm_grid_density_per_m']
    floor = spec['empty_pool_contact']['plane_z_m']
    with np.load(run/'initial_particles.npz') as initial:
        rest = initial['duck_rest']
        assert initial['water_rest'].shape==initial['water_initial_velocity'].shape==(0,3)
    reference = material_neighbor_reference(rest,q['mpm_particle_size_m'])
    mass = actual['duck_discrete_mass_kg']
    volume = actual['rest_quadrature_volume_m3']/len(rest)
    mu = p['young_modulus_pa']/(2*(1+p['poisson_ratio']))
    lam = p['young_modulus_pa']*p['poisson_ratio']/((1+p['poisson_ratio'])*(1-2*p['poisson_ratio']))
    initial_energy = mass*(.5*np.sum(np.asarray(p['duck_initial_velocity_mps'])**2)+9.81*(rest[:,2].mean()-floor))
    rows,transforms = [],[]
    for entry in r['frames']:
        frame = entry['frame']
        with np.load(run/'particles'/f'frame_{frame:04d}.npz') as data:
            x,F,v,C = [data[k].astype(np.float64) for k in ('duck_pos','duck_F','duck_vel','duck_C')]
            assert data['water_pos'].shape==data['water_vel'].shape==(0,3)
        assert len(x)==actual['duck_particles'] and all(np.isfinite(a).all() for a in (x,F,v,C))
        assert np.all(x>=np.asarray(actual['physical_contact_lower_m'])-2e-6)
        assert np.all(x<=np.asarray(actual['physical_contact_upper_m'])+2e-6)
        validate_empty_pool_floor_contact(float(x[:,2].min()-floor),spec)
        J = np.linalg.det(F)
        assert J.min()>.05 and entry['mpm_rest_wave_cfl']<.9
        if frame==1:
            assert np.array_equal(x,rest)
            assert np.array_equal(v,np.broadcast_to(np.asarray(p['duck_initial_velocity_mps']),v.shape))
            assert np.array_equal(F,np.broadcast_to(np.eye(3),F.shape)) and not np.any(C)
        if entry['pre_contact_free_fall_center_error_m'] is not None:
            assert entry['pre_contact_free_fall_center_error_m']<.003
        continuity = material_continuity_observation(reference,x,F)
        assert continuity['maximum_neighbor_ratio']<=limits['maximum_rest_neighbor_ratio'], continuity
        assert continuity['maximum_F_consistency_error_m']<=limits['maximum_F_consistency_error_grid_cells']*grid_dx, continuity
        assert continuity['p99_F_consistency_error_m']<=limits['maximum_p99_F_consistency_error_grid_cells']*grid_dx, continuity
        logJ = np.log(J)
        elastic = float(volume*np.sum(.5*mu*(np.sum(F*F,axis=(1,2))-3)-mu*logJ+.5*lam*logJ**2))
        kinetic = float(.5*mass*np.mean(np.sum(v*v,axis=1)))
        # Quadratic B-spline APIC has D_p=(dx^2/4)I away from the safety box.
        affine_kinetic = float(.5*mass*grid_dx**2/4*np.mean(np.sum(C*C,axis=(1,2))))
        energy = elastic+kinetic+affine_kinetic+mass*9.81*(x[:,2].mean()-floor)
        assert energy/initial_energy<=limits['maximum_sampled_energy_over_initial'], (frame,energy/initial_energy)
        assert np.linalg.norm(x[:,:2].mean(0)-rest[:,:2].mean(0))<.01, 'Unexplained lateral COM drift on a frictionless floor.'
        rotation = np.asarray(entry['duck_deformation']['rotation_matrix_row_vectors'])
        matrix = np.eye(4)
        matrix[:3,:3] = rotation.T
        matrix[:3,3] = x.mean(0)-rotation.T@(rest.mean(0)-np.asarray(p['duck_initial_reference_m']))
        rows.append({'frame':frame,'time_seconds':entry['time_seconds'],**continuity,
            'duck_center_z_m':float(x[:,2].mean()),'floor_particle_clearance_m':float(x[:,2].min()-floor),
            'sampled_mechanical_energy_j':float(energy),'sampled_energy_over_initial':float(energy/initial_energy),
            'apic_affine_kinetic_energy_j':affine_kinetic,'elastic_energy_j':elastic,
            'jacobian_min':float(J.min()),'non_rigid_rms_m':entry['duck_deformation']['rms_m']})
        transforms.append({'frame':frame,'time_seconds':entry['time_seconds'],
            'duck':{'present':True,'matrix_world_best_fit':matrix.tolist(),'deformation_source':'actual MPM particles and F'},
            'water':{'present':False}})
    contact_rows = [row for row in rows if row['floor_particle_clearance_m']<grid_dx]
    assert contact_rows
    validation = {'status':'numerical_checks_passed_visual_review_pending','all_96_frames_checked':True,
        'water_deleted_from_simulation':True,'no_hidden_water_or_pressure_boundary':True,
        'pressure_solver_present':False,'pressure_converged':None,
        'material_continuity_checked_all_frames':True,
        'no_rotation_lock_or_prescribed_pose':True,'same_duck_mass_material_pose_and_initial_velocity':True,
        'same_grid_spacing_and_time_step':True,'mass_preserving_particle_quadrature_refinement':True,
        'numerical_repair':repair,'pool_floor_top_z_m':floor,
        'first_sampled_floor_contact_frame':contact_rows[0]['frame'],
        'maximum_neighbor_ratio':max(row['maximum_neighbor_ratio'] for row in rows),
        'maximum_F_consistency_error_m':max(row['maximum_F_consistency_error_m'] for row in rows),
        'maximum_sampled_energy_over_initial':max(row['sampled_energy_over_initial'] for row in rows),
        'particle_floor_contact_numerical_tolerance_m':empty_pool_floor_tolerance(spec),
        'minimum_particle_floor_clearance_m':min(row['floor_particle_clearance_m'] for row in rows),
        'energy_scope':'24-fps snapshots of gravity, compressible Neo-Hookean strain, translational and APIC-affine kinetic energy; not a per-substep conservation proof.',
        'minimum_jacobian':min(row['jacobian_min'] for row in rows),
        'physics_changes':spec['counterfactual']['changes'],
        'simulation_report_sha256':digest(run/'simulation_report.json'),
        'accepted_as_calibrated_ground_truth':False,'frames':rows}
    save(case/'benchmark_validation.json',validation)
    save(case/'ground_truth_transforms.json',{'schema_version':3,'scene_id':'elastic_fluid_duck',
        'interaction_category':'elastic_fluid','deleted_objects':['water'],'frames':transforms})
    save(case/'scenario_metadata.json',{'scene_id':'elastic_fluid_duck','case_id':spec['counterfactual']['id'],
        'physics':p,'simulation_quality':q,'render':spec['render'],'asset':spec['asset'],'actual':actual,
        'solver':'Mass-preserving refined MPM elastic quadrature with explicit rigid-plane pool-floor contact, no SPH',
        'object_presence':{'duck':True,'water':False},'source_video_sha256':manifest['selected_base_video_sha256']})
    print('REPAIRED_EMPTY_POOL_NUMERICAL_CHECKS_PASSED',validation['maximum_neighbor_ratio'],flush=True)


def audit_without_water(case, spec, assets, manifest):
    if 'numerical_repair' in spec:
        return audit_repaired_empty_pool(case,spec,assets,manifest)
    run = case/'runs/source'
    report = json.loads((run/'simulation_report.json').read_text())
    p, q, actual = report['physics'], report['simulation_quality'], report['actual']
    assert report['status'] == 'simulated_awaiting_coupling_and_visual_review' and len(report['frames']) == 96
    assert p == spec['physics'] and q == spec['simulation_quality'] and not water_present(p) and duck_present(p)
    assert actual['water_particles'] == actual['ghost_particles'] == actual['sph_entities'] == 0
    assert actual['sph_active'] is False and actual['mpm_active'] is True and report['coupling']['enabled'] is False
    assert not any(report['coupling'][k] for k in ('buoyancy_present','fluid_pressure_present','fluid_drag_present','prescribed_duck_trajectory'))
    assert actual['duck_particles'] == manifest['base_actual']['duck_particles']
    assert abs(actual['duck_discrete_mass_kg']/manifest['base_actual']['duck_discrete_mass_kg']-1) < 2e-6
    for key in ('sim_options','sph_options','coupler_options'):
        assert actual[key] == manifest['base_actual'][key]
    expected_mpm = dict(manifest['base_actual']['mpm_options'], lower_bound=q['mpm_lower_bound_m'])
    assert actual['mpm_options'] == expected_mpm
    original = json.loads((assets/'scene_spec.json').read_text())['simulation_quality']
    assert {k:(original[k],v) for k,v in q.items() if v!=original[k]} == {
        'mpm_lower_bound_m':(spec['numerical_boundary_alignment']['before']['mpm_lower_bound_m'],q['mpm_lower_bound_m'])}
    with np.load(run/'initial_particles.npz') as initial, np.load(assets/'duck_reference_particles.npz') as reference:
        rest = initial['duck_rest']
        assert np.array_equal(rest, reference['duck_rest'])
        assert initial['water_rest'].shape == initial['water_initial_velocity'].shape == (0,3)
    rows, transforms = [], []
    floor = spec['numerical_boundary_alignment']['pool_floor_top_z_m']
    for row in report['frames']:
        with np.load(run/'particles'/f'frame_{row["frame"]:04d}.npz') as state:
            x,F,v = [state[key] for key in ('duck_pos','duck_F','duck_vel')]
            assert state['water_pos'].shape == state['water_vel'].shape == (0,3)
        assert len(x) == actual['duck_particles'] and all(np.isfinite(a).all() for a in (x,F,v))
        assert np.all(x>=np.asarray(actual['physical_contact_lower_m'])-2e-6)
        assert np.all(x<=np.asarray(actual['physical_contact_upper_m'])+2e-6)
        assert np.linalg.det(F).min() > .05 and row['mpm_rest_wave_cfl'] < .9
        if row['pre_contact_free_fall_center_error_m'] is not None:
            assert row['pre_contact_free_fall_center_error_m'] < .003
        rotation = np.asarray(row['duck_deformation']['rotation_matrix_row_vectors'])
        matrix = np.eye(4)
        matrix[:3,:3] = rotation.T
        matrix[:3,3] = np.asarray(row['duck_center_m'])-rotation.T@(rest.mean(axis=0)-np.asarray(p['duck_initial_reference_m']))
        rows.append({'frame':row['frame'],'time_seconds':row['time_seconds'],
            'water_present':False,'duck_center_z_m':row['duck_center_m'][2],
            'floor_particle_clearance_m':float(x[:,2].min()-floor)})
        transforms.append({'frame':row['frame'],'time_seconds':row['time_seconds'],
            'duck':{'present':True,'matrix_world_best_fit':matrix.tolist(),'deformation_source':'actual MPM particles and F'},
            'water':{'present':False}})
    contact = [r for r in rows if r['floor_particle_clearance_m'] < 1/q['mpm_grid_density_per_m']]
    assert contact, 'The duck never reached the empty pool floor.'
    validation = {'status':'numerical_checks_passed_visual_review_pending','all_96_frames_checked':True,
        'water_deleted_from_simulation':True,'no_hidden_water_or_pressure_boundary':True,
        'pressure_solver_present':False,'pressure_converged':None,
        'same_initial_duck_particles_mass_material_and_velocity':True,
        'same_grid_spacing_particle_sampling_and_time_step':True,
        'numerical_boundary_alignment':spec['numerical_boundary_alignment'],
        'pool_floor_top_z_m':floor,'first_sampled_floor_contact_frame':contact[0]['frame'],
        'maximum_pre_contact_free_fall_center_error_m':max(r['pre_contact_free_fall_center_error_m'] for r in report['frames'] if r['pre_contact_free_fall_center_error_m'] is not None),
        'minimum_jacobian':report['minimum_jacobian'],'physics_changes':spec['counterfactual']['changes'],
        'simulation_report_sha256':digest(run/'simulation_report.json'),
        'accepted_as_calibrated_ground_truth':False,'frames':rows}
    save(case/'benchmark_validation.json',validation)
    save(case/'ground_truth_transforms.json',{'schema_version':3,'scene_id':'elastic_fluid_duck',
        'interaction_category':'elastic_fluid','deleted_objects':['water'],'frames':transforms})
    save(case/'scenario_metadata.json',{'scene_id':'elastic_fluid_duck','case_id':spec['counterfactual']['id'],
        'physics':p,'simulation_quality':q,'render':spec['render'],'asset':spec['asset'],'actual':actual,
        'solver':'Native MPM elastic duck with empty-pool floor contact; no SPH solver active',
        'object_presence':{'duck':True,'water':False},'source_video_sha256':manifest['selected_base_video_sha256']})
    print('DELETE_WATER_PHYSICS_CHECKS_PASSED',validation['first_sampled_floor_contact_frame'],flush=True)


def verify_empty_pool_surface(case):
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    assert not water_present(spec['physics'])
    with np.load(case/'runs/source/visual_deformation.npz') as data:
        positions = data['positions']
        assert list(map(int,data['frame_numbers'])) == list(range(1,97))
    assert np.isfinite(positions).all()
    floor = spec['numerical_boundary_alignment']['pool_floor_top_z_m']
    gaps = positions[:,:,2].min(axis=1)-floor
    # The visual surface is interpolated from finite material points; retain
    # and report its discretization-scale error, never move render poses.
    assert float(gaps.min()) >= -.02, ('Visible floor penetration',float(gaps.min()))
    if 'numerical_repair' in spec:
        assert float(gaps[8:].min()) <= .02, 'Actual skinned duck never contacts the floor.'
        assert float(gaps.min()) >= -.01, 'Visible floor penetration in repaired contact.'
    else:
        assert float(np.median(gaps[72:])) <= .035, ('Visible duck floats above the empty floor',float(np.median(gaps[72:])))
    path = case/'benchmark_validation.json'
    validation = json.loads(path.read_text())
    validation.update(empty_pool_skinned_surface_checked=True,
        minimum_skinned_floor_clearance_m=float(gaps.min()),
        final_second_median_skinned_floor_clearance_m=float(np.median(gaps[72:])),
        render_pose_translation_or_clamping=False)
    save(path,validation)
    print('EMPTY_POOL_SKIN_CONTACT_VERIFIED',float(gaps.min()),float(np.median(gaps[72:])),flush=True)


def create_fluid_only_solver():
    """The same fluid operators, with no MPM material or ghost boundary allocated."""
    base = create_boundary_solver()

    @qd.data_oriented
    class FluidOnlyDFSPH(base):
        def build(self):
            global LAST_SOLVER
            SPHSolver.build(self)
            assert len(self.entities) == 1 and self.sim.mpm_solver.n_particles == 0
            self.n_fluid = self.n_particles
            self.n_ghost = 0
            self.relaxation = .5
            self.boundary_relaxation = .1
            self.feedback = False
            self.enabled = False
            self.original_id = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.near_boundary = qd.field(gs.qd_int, shape=(self.n_particles, self._B))
            self.error_particle_id = qd.field(qd.i32, shape=())
            self.error_particle_sample = qd.Vector.field(12, gs.qd_float, shape=())
            self._df_max_div_iters = self._df_max_den_iters = 100
            self.cap_examples = []
            self.current_frame = 0
            self.reset_iteration_diagnostics()
            LAST_SOLVER = self

        @qd.func
        def is_fluid(self, index, batch):
            return True

        @qd.func
        def volume(self, index, batch):
            return self._particle_volume

        @qd.func
        def volume_rate_density_term(self, i, j, batch):
            return gs.qd_float(0.)

        @qd.func
        def factor_pair(self, i, j, ret: qd.template(), batch):
            gradient = -self._particle_volume * self.cubic_kernel_derivative(
                self.particles_reordered[i, batch].pos-self.particles_reordered[j, batch].pos)
            ret[3] += gradient.norm_sqr()
            for k in qd.static(range(3)):
                ret[k] -= gradient[k]

        @qd.func
        def pressure_pair(self, i, j, stiffness, scale, batch):
            gradient = -self._particle_volume * self.cubic_kernel_derivative(
                self.particles_reordered[i, batch].pos-self.particles_reordered[j, batch].pos)
            return -scale * stiffness * gradient

        def pressure_to_mpm(self, f):
            # There is no solid to receive pressure. Do not retain an invisible duck.
            pass

        def substep_pre_coupling(self, f):
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

    return FluidOnlyDFSPH


def mesh_water(case, tag, frames, smoothing_iters=None, mesh_tag=None, cube_size=0.8):
    import pysplashsurf
    run = case / 'runs' / tag
    report = json.loads((run / 'simulation_report.json').read_text())
    q = report['simulation_quality']
    if smoothing_iters is None:
        smoothing_iters = q.get('mesh_smoothing_iters', 25)
    settings = {'particle_radius_m': q['sph_particle_size_m'] / 2, 'smoothing_length_radius_factor': 2.0, 'cube_size_radius_factor': cube_size, 'iso_surface_threshold': 0.6, 'mesh_smoothing_iters': smoothing_iters, 'mesh_smoothing_weights': True, 'normals_smoothing_iters': 10, 'mesh_cleanup': True}
    suffix = '' if mesh_tag is None else '_' + mesh_tag
    out = run / ('meshes' + suffix)
    out.mkdir(exist_ok=True)
    log_path = run / ('meshing_report' + suffix + '.json')
    log = json.loads(log_path.read_text()) if log_path.exists() else {'settings': settings, 'frames': {}, 'compute_seconds': 0.0}
    assert log['settings'] == settings
    start = time.monotonic()
    for frame in frames:
        target = out / f'water_{frame:04d}.npz'
        if target.exists():
            assert str(frame) in log['frames']
            continue
        frame_start = time.monotonic()
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as particles:
            positions = np.ascontiguousarray(particles['water_pos'], dtype=np.float64)
        tick = time.monotonic()
        (mesh_data, _) = pysplashsurf.reconstruction_pipeline(positions, particle_radius=settings['particle_radius_m'], smoothing_length=2.0, cube_size=cube_size, iso_surface_threshold=0.6, mesh_smoothing_weights=True, mesh_smoothing_iters=smoothing_iters, normals_smoothing_iters=10, mesh_cleanup=True, compute_normals=True, multi_threading=True)
        vertices = np.asarray(mesh_data.mesh.vertices, dtype=np.float32)
        triangles = np.asarray(mesh_data.mesh.triangles, dtype=np.int32)
        assert len(vertices) and len(triangles) and np.isfinite(vertices).all()
        assert triangles.min() >= 0 and triangles.max() < len(vertices)
        p = vertices[triangles].astype(np.float64)
        volume = float(np.einsum('ij,ij->i', p[:, 0], np.cross(p[:, 1], p[:, 2])).sum() / 6)
        assert volume > 0, 'Surface winding/volume needs inspection'
        normals = np.array(mesh_data.point_attributes['normals'], dtype=np.float32, copy=True)
        assert normals.shape == vertices.shape
        bad_normals = ~np.isfinite(normals).all(axis=1) | (np.linalg.norm(normals, axis=1) < 0.1)
        fallback_count = int(bad_normals.sum())
        radial_count = 0
        if fallback_count:
            geometry_normals = np.asarray(mesh_data.mesh.vertex_normals_parallel(), dtype=np.float32)
            normals[bad_normals] = geometry_normals[bad_normals]
            remaining = ~np.isfinite(normals).all(axis=1) | (np.linalg.norm(normals, axis=1) < 0.1)
            radial_count = int(remaining.sum())
            if radial_count:
                (_, nearest) = cKDTree(positions).query(vertices[remaining])
                radial = vertices[remaining] - positions[nearest]
                lengths = np.linalg.norm(radial, axis=1)
                assert np.min(lengths) > 1e-09
                normals[remaining] = radial / lengths[:, None]
        assert fallback_count < 0.01 * len(vertices), fallback_count
        assert np.isfinite(normals).all()
        assert np.min(np.linalg.norm(normals, axis=1)) > 0.1
        np.savez(target, vertices=vertices, triangles=triangles, normals=normals)
        log['frames'][str(frame)] = {'vertices': len(vertices), 'triangles': len(triangles), 'bounds_m': [vertices.min(axis=0).tolist(), vertices.max(axis=0).tolist()], 'signed_volume_diagnostic_m3': volume, 'smoothed_normals_exported': True, 'geometric_normal_fallback_vertices': fallback_count, 'radial_normal_fallback_vertices': radial_count, 'seconds': time.monotonic() - frame_start}
        log['compute_seconds'] = sum((r['seconds'] for r in log['frames'].values()))
        log['timing_scope'] = 'Sum of completed frame load/reconstruction/export times; failed exploratory attempts and worker startup excluded.'
        save(log_path, log)
        if frame == 1 or frame % 4 == 0:
            print('SPH_MESH', frame, len(vertices), len(triangles), volume, flush=True)
    log['compute_seconds'] = sum((r['seconds'] for r in log['frames'].values()))
    save(log_path, log)

def skin_duck(case, tag, selected=None):
    run = case / 'runs' / tag
    report = json.loads((run / 'simulation_report.json').read_text())
    minimum = report.get('minimum_jacobian', min((r['jacobian_min'] for r in report['frames'])))
    assert len(report['frames']) >= 2 and minimum > 0.05
    assert report['coupling']['enabled'] or (
        report.get('water_present') is False and report['actual']['mpm_active'] is True
        and report['actual']['water_particles'] == report['actual']['ghost_particles'] == 0)
    geometry = dict(np.load(case / 'render_geometry.npz'))
    rest = np.load(run / 'initial_particles.npz')['duck_rest']
    visual = geometry['visual_rest'] + np.asarray(report['physics']['duck_initial_reference_m'])
    (distances, ids) = cKDTree(rest).query(visual, k=16)
    weights = 1 / (distances ** 2 + 0.003 ** 2)
    weights /= weights.sum(axis=1)[:, None]
    offsets = visual[:, None, :] - rest[ids]
    frames = []
    count = len(report['frames'])
    frame_numbers = selected or list(range(1, count + 1))
    assert frame_numbers[0] == 1 and all((1 <= f <= count for f in frame_numbers))
    for frame in frame_numbers:
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
            predicted = data['duck_pos'][ids] + np.einsum('nkij,nkj->nki', data['duck_F'][ids], offsets)
            frames.append((weights[:, :, None] * predicted).sum(axis=1))
    poses = np.asarray(frames, dtype=np.float32)
    times = (np.asarray(frame_numbers, dtype=np.float64) - 1) / 24
    assert np.isfinite(poses).all()
    rest_error = float(np.abs(poses[0] - visual).max())
    assert rest_error < 1e-05, rest_error
    suffix = '_probe' if selected else ''
    np.savez_compressed(run / ('visual_deformation' + suffix + '.npz'), positions=poses, times=times, frame_numbers=frame_numbers)
    with (run / ('duck_visual' + suffix + '.mdd')).open('wb') as stream:
        stream.write(struct.pack('>ii', len(times), len(visual)))
        stream.write(np.asarray(times, dtype='>f4').tobytes())
        stream.write(np.asarray(poses, dtype='>f4').tobytes())
    save(run / ('skinning_report' + suffix + '.json'), {'method': 'Static 16-neighbor material-affine interpolation x_i + F_i (X-x_i_rest)', 'manual_deformation_animation': False, 'visual_vertices': len(visual), 'rest_max_error_m': rest_error, 'source': 'actual MPM particle positions and deformation gradients', 'support_radius_max_m': float(distances.max()), 'frames': len(frame_numbers), 'frame_numbers': frame_numbers, 'partial_diagnostic_only': selected is not None})
    print('MPM_SKIN_COMPLETE', len(visual), rest_error, flush=True)


def load_case(case):
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    assets = Path(spec['runtime_assets']['path'])
    manifest_path = assets/'asset_manifest.json'
    assert digest(manifest_path) == spec['runtime_assets']['manifest_sha256'], 'Asset manifest changed.'
    manifest = json.loads(manifest_path.read_text())
    for name, record in manifest['files'].items():
        assert digest(assets/name) == record['sha256'], name
    assert digest(case/'duck_solid.obj') == manifest['files']['duck_solid.obj']['sha256']
    assert digest(case/'render_geometry.npz') == manifest['files']['render_geometry.npz']['sha256']
    assert spec['physics'] == spec['counterfactual']['after']
    changes = {key:{'before':spec['counterfactual']['before'][key], 'after':value}
               for key,value in spec['physics'].items() if value != spec['counterfactual']['before'][key]}
    assert changes == spec['counterfactual']['changes']
    return spec, assets, manifest


def cpu(value):
    return value.detach().cpu().numpy()


def deformation(rest, current):
    a = rest-rest.mean(axis=0)
    b = current-current.mean(axis=0)
    u, _, vt = np.linalg.svd(a.T@b)
    rotation = u@np.diag([1., 1., np.linalg.det(u@vt)])@vt
    error = np.linalg.norm(b-a@rotation, axis=1)
    return {'rms_m':float(np.sqrt(np.mean(error**2))), 'maximum_m':float(error.max()),
            'rotation_matrix_row_vectors':rotation.tolist()}


def boundary_observations(solver):
    return {
        'material_mapping_observation':{
            'maximum_weight_sum_error_at_exit':float(solver.mapping_weight_error[None]),
            'maximum_grid_nodes_per_ghost_at_exit':int(solver.grid_count.to_numpy().max()),
            'invalid_material_stencils_at_exit':int(solver.mapping_rejections[None]),
            'maximum_first_moment_error_at_exit_m':float(solver.mapping_moment_error[None]),
            'peak_first_moment_error_all_substeps_m':float(solver.mapping_moment_error_peak[None]),
        },
        'pressure_diagnostics_at_exit_including_partial_substeps':dict(solver.iteration_diagnostics),
        'pressure_cap_examples':list(solver.cap_examples),
    }


def _is_field(value):
    import torch
    return (hasattr(value, 'to_numpy') and hasattr(value, 'from_numpy') and hasattr(value, 'shape')
            and not isinstance(value, (np.ndarray, torch.Tensor)))


def _is_plain(value, depth=0):
    if value is None or isinstance(value, (bool, int, float, str, np.integer, np.floating)):
        return True
    if depth > 6:
        return False
    if isinstance(value, (list, tuple)):
        return all(_is_plain(item, depth+1) for item in value)
    if isinstance(value, dict):
        return all(isinstance(key, (str, int)) and _is_plain(item, depth+1) for key, item in value.items())
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
    every torch tensor attribute and every plain-data Python attribute (step counters, diagnostics)."""

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
                            raise RuntimeError(f'cannot copy {type(obj).__name__}.{name}: {error}') from error
                        self.skipped.append(f'{type(obj).__name__}.{name}')
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
                    bad.append(f'{type(obj).__name__}.{name}')
            for name, tensor in tensors.items():
                if not torch.equal(getattr(obj, name), tensor):
                    bad.append(f'{type(obj).__name__}.{name}')
            for name, value in plain.items():
                if json.dumps(getattr(obj, name), sort_keys=True, default=str) != json.dumps(value, sort_keys=True, default=str):
                    bad.append(f'{type(obj).__name__}.{name}')
        return bad

    def summary(self):
        return {'objects': [type(obj).__name__ for obj, *_ in self.items],
                'fields': sum(len(f) for _, f, _, _ in self.items),
                'plain_attributes': sum(len(p) for _, _, p, _ in self.items),
                'tensors': sum(len(t) for _, _, _, t in self.items),
                'field_megabytes': round(sum(_nbytes(a) for _, f, _, _ in self.items for a in f.values())/2**20, 1),
                'skipped': self.skipped}


def state_holders(scene):
    holders = [scene.sim, scene.sim.coupler]
    for part in (scene.sim.mpm_solver, scene.sim.sph_solver):
        if part.is_active:
            holders.append(part)
            for name in ('sh', 'boundary'):
                if getattr(part, name, None) is not None:
                    holders.append(getattr(part, name))
    return holders + list(scene.sim.entities)


def state_required(scene):
    return [part for part in (scene.sim.mpm_solver, scene.sim.sph_solver) if part.is_active] + list(scene.sim.entities)


def simulate(case, frames=96, max_wall_seconds=7200, source_branch_case=None):
    physics = json.loads((case/'mpm_sph_experiment.json').read_text())['physics']
    if not water_present(physics):
        return simulate_without_water(case, frames, max_wall_seconds)
    if not duck_present(physics):
        return simulate_without_duck(case, frames, max_wall_seconds)
    wall_start = time.monotonic()
    _import_runtime()
    spec, assets, manifest = load_case(case)
    timed = spec['counterfactual'].get('timed_edits', [])
    if source_branch_case is not None:
        assert timed, '--source-branch-case needs a timed edit'
        source_branch_case = Path(source_branch_case).resolve()
        assert source_branch_case != case
    if timed:
        assert len(timed) == 1 and set(timed[0]['params']) == {'water_density_kg_m3'}
        assert 2 <= timed[0]['frame'] <= 96 and timed[0]['params']['water_density_kg_m3'] == 185.
        assert math.isclose((timed[0]['frame']-1)/spec['render']['fps'],spec['counterfactual']['trigger_time_seconds'])
    p = spec['counterfactual']['initial_physics'] if timed else spec['physics']
    q = spec['simulation_quality']
    assert q['water_settle_seconds'] == 0 and q['water_initial_z_scale'] == 1
    assert math.isclose(q['step_dt_seconds']*q['steps_per_video_frame'], 1/spec['render']['fps'])
    out = case/'runs/source'
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Simulation already exists; use a fresh case directory.')
    (out/'particles').mkdir(parents=True, exist_ok=True)
    gs.init(backend=gs.cuda, precision='32', seed=20261011, logging_level='warning')
    _load_solver_base()
    import genesis.engine.simulator as simulator
    simulator.SPHSolver = create_timed_density_solver() if timed else create_boundary_solver()
    sim_options = gs.options.SimOptions(dt=q['step_dt_seconds'], substeps=q['substeps_per_step'],
        gravity=p['gravity_mps2'], floor_height=q['sph_lower_bound_m'][2], requires_grad=False)
    mpm_options = gs.options.MPMOptions(grid_density=q['mpm_grid_density_per_m'],
        particle_size=q['mpm_particle_size_m'], lower_bound=q['mpm_lower_bound_m'], upper_bound=q['mpm_upper_bound_m'])
    sph_options = gs.options.SPHOptions(particle_size=q['sph_particle_size_m'], pressure_solver='DFSPH',
        lower_bound=q['sph_lower_bound_m'], upper_bound=q['sph_upper_bound_m'])
    coupler_options = gs.options.LegacyCouplerOptions(rigid_mpm=False, rigid_sph=False,
        rigid_pbd=False, rigid_fem=False, mpm_sph=False, mpm_pbd=False, fem_mpm=False, fem_sph=False)
    scene = gs.Scene(sim_options=sim_options, mpm_options=mpm_options, sph_options=sph_options,
                     coupler_options=coupler_options, show_viewer=False)
    water_nu = p['water_dynamic_viscosity_pa_s']/p['water_density_kg_m3']
    water = scene.add_entity(morph=gs.morphs.Box(pos=p['water_box_center_m'], size=p['water_box_size_m']),
        material=gs.materials.SPH.Liquid(rho=p['water_density_kg_m3'], mu=water_nu,
            gamma=p['water_surface_tension_n_m'], sampler='regular'),
        surface=gs.surfaces.Default(color=(.2,.6,1.,1.), vis_mode='particle'))
    duck = scene.add_entity(morph=gs.morphs.Mesh(file=str(case/'duck_solid.obj'),
        pos=p['duck_initial_reference_m'], scale=1., euler=(0.,0.,0.), decimate=False, convexify=False),
        material=gs.materials.MPM.Elastic(E=p['young_modulus_pa'], nu=p['poisson_ratio'],
            rho=p['duck_density_kg_m3'], model=p['constitutive_model'], sampler='regular'),
        surface=gs.surfaces.Default(color=(.9,.8,.2,1.), vis_mode='particle'))
    scene.add_entity(morph=gs.morphs.Mesh(file=str(case/'duck_solid.obj'),
        pos=p['duck_initial_reference_m'], scale=1., euler=(0.,0.,0.), decimate=False, convexify=False),
        material=gs.materials.SPH.Liquid(rho=p['water_density_kg_m3'], mu=water_nu, gamma=0., sampler='regular'),
        surface=gs.surfaces.Default(color=(1.,0.,1.,1.), vis_mode='particle'))
    tick = time.monotonic()
    scene.build(n_envs=0)
    build_seconds = time.monotonic()-tick
    solver = scene.sim.sph_solver
    mapping = solver.initialize_mapping()
    with np.load(assets/'water_initial_state.npz') as state:
        assert len(state['water_pos']) == water.n_particles
        assert not np.any(state['water_vel'])
        water.set_particles_pos(state['water_pos'])
        water.set_particles_vel(state['water_vel'])
    water.set_particles_vel(np.zeros((water.n_particles,3), dtype=np.float32))
    duck.set_velocity(p['duck_initial_velocity_mps'])
    rest = cpu(duck.get_state().pos)[0].astype(np.float64)
    with np.load(assets/'duck_reference_particles.npz') as reference:
        assert np.array_equal(rest, reference['duck_rest']), 'Initial material points differ from the selected base.'
    assert duck.n_particles == manifest['base_actual']['duck_particles']
    assert water.n_particles == manifest['base_actual']['water_particles']
    actual_mass = float(cpu(duck.get_mass())[0])
    expected_mass = manifest['base_actual']['duck_discrete_mass_kg']*p['duck_density_kg_m3']/200.
    assert abs(actual_mass/expected_mass-1) < 2e-6
    water_mass = water.n_particles*water.solver.particle_volume*p['water_density_kg_m3']
    observed_water_rho = float(solver._density0)
    observed_water_masses = np.asarray(solver.particles_info.mass.to_numpy()[:water.n_particles],dtype=np.float64)
    assert math.isclose(observed_water_rho,p['water_density_kg_m3'],rel_tol=2e-6)
    assert abs(observed_water_masses.sum()/water_mass-1)<2e-6, 'Density did not reach the native liquid-particle masses.'
    wx0 = cpu(water.get_particles_pos())
    wv0 = cpu(water.get_particles_vel())
    assert hashlib.sha256(wx0.tobytes()).hexdigest() == manifest['initial_water_positions_sha256']
    assert not np.any(wv0)
    np.savez_compressed(out/'initial_particles.npz', duck_rest=rest, water_rest=wx0, water_initial_velocity=wv0)
    sub_dt = q['step_dt_seconds']/q['substeps_per_step']
    wave_speed = math.sqrt(p['young_modulus_pa']*(1-p['poisson_ratio'])/
        (p['duck_density_kg_m3']*(1+p['poisson_ratio'])*(1-2*p['poisson_ratio'])))
    viscosity_cfl = water_nu*sub_dt/q['sph_particle_size_m']**2
    assert viscosity_cfl < .125, 'Explicit viscosity step exceeds the retained diagnostic bound.'
    native_viscosity_dt = solver._stable_dt_coef*.01*solver._support_radius**2/water_nu
    assert sub_dt <= native_viscosity_dt, 'Explicit viscosity exceeds the Genesis SPH stability bound.'
    report = {
        'scene_id':'elastic_fluid_duck', 'status':'simulating', 'tag':'source',
        'case_id':spec['counterfactual']['id'], 'physics':spec['physics'], 'simulation_quality':q,
        'counterfactual':spec['counterfactual'],
        'asset_manifest_sha256':digest(assets/'asset_manifest.json'),
        'versions':{'genesis':importlib.metadata.version('genesis-world'),
            'quadrants':importlib.metadata.version('quadrants'), 'torch':torch.__version__},
        'device':torch.cuda.get_device_name(), 'seed':20261011,
        'material_assumptions':spec['material_assumptions'],
        'coupling':{'enabled':True, 'prescribed_duck_trajectory':False,
            'native_genesis_mpm_sph':False, 'pressure_boundary':mapping,
            'implementation':'Affine-exact material boundary with matching pressure transpose',
            'fluid_fluid_viscosity_present':True, 'fluid_solid_tangential_viscous_traction':False},
        'actual':{'sim_options':sim_options.model_dump(mode='json'),
            'mpm_options':mpm_options.model_dump(mode='json'), 'sph_options':sph_options.model_dump(mode='json'),
            'coupler_options':coupler_options.model_dump(mode='json'),
            'duck_particles':duck.n_particles, 'water_particles':water.n_particles,
            'duck_discrete_mass_kg':actual_mass, 'water_discrete_mass_kg':water_mass,
            'water_material_mu_argument_m2_s':water_nu, 'water_support_radius_m':water.solver._support_radius,
            'observed_water_rest_density_kg_m3':observed_water_rho,
            'observed_water_particle_mass_mean_kg':float(observed_water_masses.mean()),
            'observed_water_discrete_mass_kg':float(observed_water_masses.sum()),
            'mpm_grid_spacing_m':duck.solver.dx},
        'build_seconds':build_seconds, 'water_settle_compute_seconds':0.,
        'water_initialization':{'pre_roll_seconds':0., 'velocities_zeroed_once_at_t0':True,
            'copied_initial_water_from':str(assets/'water_initial_state.npz'),
            'initial_water_positions_sha256':hashlib.sha256(wx0.tobytes()).hexdigest(),
            'initial_water_velocities_sha256':hashlib.sha256(wv0.tobytes()).hexdigest()},
        'time_step_diagnostic':{'actual_substep_dt_seconds':sub_dt,
            'mpm_rest_longitudinal_wave_speed_mps':wave_speed, 'explicit_viscosity_cfl':viscosity_cfl,
            'native_viscosity_stable_dt_seconds':native_viscosity_dt,
            'native_viscosity_dt_ratio':sub_dt/native_viscosity_dt},
        'frames':[],
    }
    if timed:
        report['initial_physics'] = p
        report['initial_actual'] = dict(report['actual'])
        report['timed_edit_events'] = []
        report['timed_density_operator'] = {
            'genesis_operator_unchanged':True,
            'original_kernels_used_until_trigger':True,
            'post_trigger_rest_density_read_from_live_particle_fields':True}
    current_water_density = p['water_density_kg_m3']
    solver.reset_iteration_diagnostics()
    solver.audit.fill(0)
    start = time.monotonic()

    def record_frame(frame, tick, ctx):
        """Read, check and store output frame `frame` (state after its steps) into ctx['report'] / ctx['out']."""
        rep, out_dir = ctx['report'], ctx['out']
        water_mass, current_water_density = ctx['water_mass'], ctx['density']
        state = duck.get_state()
        x, F, velocity = cpu(state.pos)[0], cpu(state.F)[0], cpu(state.vel)[0]
        wx, wv = cpu(water.get_particles_pos()), cpu(water.get_particles_vel())
        if ctx['timed'] and frame == timed[0]['frame']:
            before_state = (x.copy(),F.copy(),velocity.copy(),wx.copy(),wv.copy())
            rotation = np.asarray(deformation(rest,x)['rotation_matrix_row_vectors'])
            trigger_checks = spec['counterfactual']['trigger_state_checks']
            window = [r['duck_center_m'][2] for r in rep['frames']
                      if r['time_seconds'] >= (frame-1)/spec['render']['fps']-trigger_checks['window_seconds']]
            window.append(float(x[:,2].mean()))
            observed = {'center_z_range_m':float(np.ptp(window)),
                        'vertical_velocity_mps':float(velocity[:,2].mean()),
                        'tilt_degrees':float(np.degrees(np.arccos(np.clip(rotation[2,2],-1.,1.))))}
            assert observed['center_z_range_m'] <= trigger_checks['maximum_center_z_range_m'], observed
            assert abs(observed['vertical_velocity_mps']) <= trigger_checks['maximum_absolute_vertical_velocity_mps'], observed
            assert observed['tilt_degrees'] <= trigger_checks['maximum_tilt_degrees'], observed
            old_mass = water_mass
            current_water_density = timed[0]['params']['water_density_kg_m3']
            solver.switch_uniform_density(current_water_density,p['water_dynamic_viscosity_pa_s'])
            water_mass = water.n_particles*solver.particle_volume*current_water_density
            updated = duck.get_state()
            after_state = (cpu(updated.pos)[0],cpu(updated.F)[0],cpu(updated.vel)[0],
                           cpu(water.get_particles_pos()),cpu(water.get_particles_vel()))
            assert all(np.array_equal(a,b) for a,b in zip(before_state,after_state)), 'Timed parameter switch changed kinematic state.'
            native_rho = solver.particles_info.rho.to_numpy()
            native_mass = solver.particles_info.mass.to_numpy()
            native_mu = solver.particles_info.mu.to_numpy()
            assert np.allclose(native_rho,current_water_density,rtol=2e-6)
            assert np.allclose(native_mass,solver.particle_volume*current_water_density,rtol=2e-6)
            assert np.allclose(native_mu,p['water_dynamic_viscosity_pa_s']/current_water_density,rtol=2e-6)
            event = {'frame':frame,'time_seconds':(frame-1)/spec['render']['fps'],
                'rest_density_before_kg_m3':p['water_density_kg_m3'],'rest_density_after_kg_m3':current_water_density,
                'water_mass_before_kg':old_mass,'water_mass_after_kg':water_mass,
                'external_mass_change_kg':water_mass-old_mass,
                'external_momentum_change_kg_m_s':((water_mass-old_mass)*wv.astype(np.float64).mean(axis=0)).tolist(),
                'external_kinetic_energy_change_j':float(.5*(water_mass-old_mass)*np.mean(np.sum(wv.astype(np.float64)**2,axis=1))),
                'positions_velocities_and_deformation_bitwise_unchanged':True,
                'duck_mass_unchanged_kg':actual_mass,'dynamic_viscosity_unchanged_pa_s':p['water_dynamic_viscosity_pa_s'],
                'trigger_stability_observation':observed,'native_material_fields_verified':True,
                'pressure_scratch_reset_and_recomputed_next_substep':True}
            rep['timed_edit_events'].append(event)
            rep['actual'].update(water_discrete_mass_kg=water_mass,
                water_material_mu_argument_m2_s=p['water_dynamic_viscosity_pa_s']/current_water_density,
                observed_water_rest_density_kg_m3=float(solver._density0),
                observed_water_particle_mass_mean_kg=float(native_mass[:water.n_particles].mean()),
                observed_water_discrete_mass_kg=float(native_mass[:water.n_particles].astype(np.float64).sum()))
            save(out_dir/'simulation_report.json',rep)
            print('TIMED_DENSITY_SWITCH_APPLIED',json.dumps(event),flush=True)
            ctx['water_mass'], ctx['density'] = water_mass, current_water_density
        assert all(np.isfinite(value).all() for value in (x,F,velocity,wx,wv)), 'Non-finite state.'
        J = np.linalg.det(F)
        assert J.min() > .05, 'Collapsed or inverted material.'
        deform = deformation(rest, x)
        water_speed = np.linalg.norm(wv, axis=1)
        impulses = solver.audit.to_numpy()
        local = wx[(np.abs(wx[:,0])<.75)&(np.abs(wx[:,1])<.75)]
        record = {
            'frame':frame, 'time_seconds':(frame-1)/spec['render']['fps'],
            'duck_center_m':x.mean(axis=0).tolist(), 'duck_mean_velocity_mps':velocity.mean(axis=0).tolist(),
            'duck_bounds_m':[x.min(axis=0).tolist(),x.max(axis=0).tolist()],
            'duck_deformation':deform, 'jacobian_min':float(J.min()), 'jacobian_max':float(J.max()),
            'water_bounds_m':[wx.min(axis=0).tolist(),wx.max(axis=0).tolist()],
            'local_water_z_max_m':float(local[:,2].max()), 'water_velocity_max_mps':float(water_speed.max()),
            'water_speed_p95_mps':float(np.percentile(water_speed,95)),
            'water_kinetic_energy_j':float(.5*water_mass*np.mean(np.sum(wv.astype(np.float64)**2,axis=1))),
            'sph_advective_cfl':float(water_speed.max()*sub_dt/q['sph_particle_size_m']),
            'mpm_rest_wave_cfl':float((wave_speed+np.linalg.norm(velocity,axis=1).max())*sub_dt*q['mpm_grid_density_per_m']),
            'coupling_momentum_diagnostic':{'fluid_boundary_impulse_kg_m_s':impulses[0].tolist(),
                'mpm_boundary_impulse_kg_m_s':impulses[1].tolist(),
                'equal_opposite_residual_kg_m_s':float(np.linalg.norm(impulses[0]+impulses[1]))},
            'pressure_iteration_diagnostics':dict(solver.iteration_diagnostics),
            'pressure_iteration_counts_cumulative':dict(solver.iteration_counts),
            'frame_compute_seconds':time.monotonic()-tick,
        }
        if ctx['timed']:
            record.update(water_rest_density_kg_m3=current_water_density,water_discrete_mass_kg=water_mass)
        np.savez(out_dir/'particles'/f'frame_{frame:04d}.npz', duck_pos=x, duck_F=F,
                 duck_vel=velocity, water_pos=wx, water_vel=wv)
        rep['frames'].append(record)
        rep['simulation_seconds'] = time.monotonic()-start
        rep['wall_seconds'] = time.monotonic()-wall_start
        save(out_dir/'simulation_report.json', rep)
        if frame == 1 or frame % 4 == 0:
            print('MPM_SPH_FRAME', frame, 'z', record['duck_center_m'][2], 'Jmin', record['jacobian_min'], flush=True)
        pressure = solver.iteration_diagnostics
        assert pressure['divergence_iteration_cap_hits'] == pressure['density_iteration_cap_hits'] == 0, 'Pressure failed to converge.'
        assert record['sph_advective_cfl'] < .4 and record['mpm_rest_wave_cfl'] < .9
        if rep['wall_seconds'] > max_wall_seconds and frame < frames:
            raise TimeoutError('Simulation safety time limit reached; partial output is preserved.')

    def advance():
        for _ in range(q['steps_per_video_frame']):
            scene.step()

    def run_source_branch(frame, tick):
        """At the trigger frame, before the switch: copy the complete solver state, run the unedited source to the
        end into source_branch_case, then restore the copy (bit-exact) so the edit continues from the same state."""
        snapshot = SolverSnapshot(state_holders(scene), state_required(scene))
        unstable = snapshot.mismatched()
        assert not unstable, f'state copy is not stable: {unstable}'
        source_spec, _, _ = load_case(source_branch_case)
        assert source_spec['simulation_quality'] == spec['simulation_quality']
        assert source_spec['physics'] == spec['counterfactual']['initial_physics'] and not source_spec['counterfactual'].get('timed_edits')
        source_out = source_branch_case/'runs/source'
        if source_out.exists() and any(source_out.iterdir()):
            raise FileExistsError('Source branch simulation already exists; use a fresh case directory.')
        (source_out/'particles').mkdir(parents=True, exist_ok=True)
        shutil.copy2(out/'initial_particles.npz', source_out/'initial_particles.npz')
        for shared in range(1, frame):
            shutil.copy2(out/'particles'/f'frame_{shared:04d}.npz', source_out/'particles'/f'frame_{shared:04d}.npz')
        source_report = copy.deepcopy(report)
        for key in ('initial_physics', 'initial_actual', 'timed_edit_events', 'timed_density_operator'):
            source_report.pop(key, None)
        source_report.update(case_id=source_spec['counterfactual']['id'], physics=source_spec['physics'],
                             counterfactual=source_spec['counterfactual'], status='simulating')
        for record in source_report['frames']:
            record.pop('water_rest_density_kg_m3', None)
            record.pop('water_discrete_mass_kg', None)
        branch = {'branch_frame': frame, 'branch_time_seconds': (frame-1)/spec['render']['fps'], 'shared_frames': [1, frame],
                  'state_copy': snapshot.summary(), 'restore_exact': True,
                  'method': 'One run: complete solver state copied at the trigger frame before the edit is applied; the '
                            'source runs on, the copy is restored bit-exactly and the edit runs on. Frames up to the '
                            'trigger frame are the same state in both cases.'}
        source_report['same_run_branch'] = dict(branch, role='source', other_branch=str(case))
        source_ctx = {'report': source_report, 'out': source_out, 'water_mass': ctx['water_mass'],
                      'density': ctx['density'], 'timed': False}
        try:
            record_frame(frame, tick, source_ctx)
            for later in range(frame+1, frames+1):
                started = time.monotonic()
                advance()
                record_frame(later, started, source_ctx)
            source_report['status'] = ('simulated_awaiting_coupling_and_visual_review' if frames == 96
                                       else 'diagnostic_partial_not_accepted')
        except BaseException as error:
            source_report['status'] = 'failed_partial_not_accepted'
            source_report['error'] = repr(error)
            raise
        finally:
            source_report.update(boundary_observations(solver))
            source_report['minimum_jacobian'] = min(row['jacobian_min'] for row in source_report['frames'])
            source_report['peak_deformation_rms_m'] = max(row['duck_deformation']['rms_m'] for row in source_report['frames'])
            source_report['wall_seconds'] = time.monotonic()-wall_start
            save(source_out/'simulation_report.json', source_report)
        snapshot.restore()
        wrong = snapshot.mismatched()
        assert not wrong, f'state restore is not exact: {wrong}'
        report['same_run_branch'] = dict(branch, role='edit', other_branch=str(source_branch_case))

    ctx = {'report': report, 'out': out, 'water_mass': water_mass, 'density': current_water_density, 'timed': bool(timed)}
    if source_branch_case is not None:      # copy/restore self-test before any frame is spent
        probe = SolverSnapshot(state_holders(scene), state_required(scene))
        probe.restore()
        wrong = probe.mismatched()
        assert not wrong, f'state copy/restore self-test failed: {wrong}'
        print('BRANCH_SELFTEST ok', json.dumps(probe.summary()), flush=True)
        del probe
    try:
        for frame in range(1, frames+1):
            tick = time.monotonic()
            if frame > 1:
                advance()
            if source_branch_case is not None and frame == timed[0]['frame']:
                run_source_branch(frame, tick)
            record_frame(frame, tick, ctx)
        report['status'] = ('simulated_awaiting_coupling_and_visual_review' if frames == 96
                            else 'diagnostic_partial_not_accepted')
        if timed and frames == 96:
            assert len(report['timed_edit_events']) == 1
    except BaseException as error:
        report['status'] = 'failed_partial_not_accepted'
        report['error'] = repr(error)
        raise
    finally:
        report.update(boundary_observations(solver))
        report['minimum_jacobian'] = min(row['jacobian_min'] for row in report['frames']) if report['frames'] else None
        report['peak_deformation_rms_m'] = max((row['duck_deformation']['rms_m'] for row in report['frames']), default=0.)
        report['wall_seconds'] = time.monotonic()-wall_start
        save(out/'simulation_report.json', report)


def simulate_without_duck(case, frames=96, max_wall_seconds=7200):
    wall_start = time.monotonic()
    _import_runtime()
    spec, assets, manifest = load_case(case)
    p, q = spec['physics'], spec['simulation_quality']
    assert not duck_present(p) and spec['counterfactual']['deleted_objects'] == ['duck']
    assert q['water_settle_seconds'] == 0 and q['water_initial_z_scale'] == 1
    assert math.isclose(q['step_dt_seconds']*q['steps_per_video_frame'], 1/spec['render']['fps'])
    out = case/'runs/source'
    if out.exists() and any(out.iterdir()):
        raise FileExistsError('Simulation already exists; use a fresh case directory.')
    (out/'particles').mkdir(parents=True,exist_ok=True)
    gs.init(backend=gs.cuda,precision='32',seed=20261011,logging_level='warning')
    _load_solver_base()
    import genesis.engine.simulator as simulator
    simulator.SPHSolver = create_fluid_only_solver()
    sim_options = gs.options.SimOptions(dt=q['step_dt_seconds'],substeps=q['substeps_per_step'],
        gravity=p['gravity_mps2'],floor_height=q['sph_lower_bound_m'][2],requires_grad=False)
    mpm_options = gs.options.MPMOptions(grid_density=q['mpm_grid_density_per_m'],
        particle_size=q['mpm_particle_size_m'],lower_bound=q['mpm_lower_bound_m'],upper_bound=q['mpm_upper_bound_m'])
    sph_options = gs.options.SPHOptions(particle_size=q['sph_particle_size_m'],pressure_solver='DFSPH',
        lower_bound=q['sph_lower_bound_m'],upper_bound=q['sph_upper_bound_m'])
    coupler_options = gs.options.LegacyCouplerOptions(rigid_mpm=False,rigid_sph=False,
        rigid_pbd=False,rigid_fem=False,mpm_sph=False,mpm_pbd=False,fem_mpm=False,fem_sph=False)
    scene = gs.Scene(sim_options=sim_options,mpm_options=mpm_options,sph_options=sph_options,
        coupler_options=coupler_options,show_viewer=False)
    water_nu = p['water_dynamic_viscosity_pa_s']/p['water_density_kg_m3']
    water = scene.add_entity(morph=gs.morphs.Box(pos=p['water_box_center_m'],size=p['water_box_size_m']),
        material=gs.materials.SPH.Liquid(rho=p['water_density_kg_m3'],mu=water_nu,
            gamma=p['water_surface_tension_n_m'],sampler='regular'),
        surface=gs.surfaces.Default(color=(.2,.6,1.,1.),vis_mode='particle'))
    tick = time.monotonic()
    scene.build(n_envs=0)
    build_seconds = time.monotonic()-tick
    solver = scene.sim.sph_solver
    assert scene.sim.mpm_solver.n_particles == 0
    assert len(solver.entities) == 1 and solver.n_ghost == 0
    with np.load(assets/'water_initial_state.npz') as state:
        water.set_particles_pos(state['water_pos'])
        water.set_particles_vel(state['water_vel'])
    wx0, wv0 = cpu(water.get_particles_pos()), cpu(water.get_particles_vel())
    assert water.n_particles == manifest['base_actual']['water_particles']
    assert hashlib.sha256(wx0.tobytes()).hexdigest() == manifest['initial_water_positions_sha256']
    assert not np.any(wv0)
    empty = np.empty((0,3),dtype=np.float32)
    np.savez_compressed(out/'initial_particles.npz',duck_rest=empty,water_rest=wx0,water_initial_velocity=wv0)
    water_mass = water.n_particles*solver.particle_volume*p['water_density_kg_m3']
    sub_dt = q['step_dt_seconds']/q['substeps_per_step']
    native_viscosity_dt = .01*solver._support_radius**2/water_nu
    assert sub_dt <= native_viscosity_dt
    report = {'status':'simulating','physics':p,'simulation_quality':q,
        'duck_present':False,
        'coupling':{'enabled':False,'reason':'Duck deleted before initialization.',
            'ghost_particles':0,'implementation':'Same fluid-only DFSPH pressure, advection and viscosity operators; no solid or ghost entities.'},
        'actual':{'sim_options':sim_options.model_dump(mode='json'),
            'mpm_options':mpm_options.model_dump(mode='json'),'sph_options':sph_options.model_dump(mode='json'),
            'coupler_options':coupler_options.model_dump(mode='json'),
            'duck_particles':0,'ghost_particles':0,'mpm_active':False,'sph_entities':1,
            'water_particles':water.n_particles,'duck_discrete_mass_kg':0.,'water_discrete_mass_kg':water_mass,
            'water_material_mu_argument_m2_s':water_nu,'water_support_radius_m':solver._support_radius},
        'build_seconds':build_seconds,'water_settle_compute_seconds':0.,
        'water_initialization':{'pre_roll_seconds':0.,'initial_water_positions_sha256':hashlib.sha256(wx0.tobytes()).hexdigest(),
            'copied_initial_water_from':str(assets/'water_initial_state.npz'),'initial_velocities_zero':True},
        'time_step_diagnostic':{'actual_substep_dt_seconds':sub_dt,'native_viscosity_stable_dt_seconds':native_viscosity_dt,
            'native_viscosity_dt_ratio':sub_dt/native_viscosity_dt},'frames':[]}
    solver.reset_iteration_diagnostics()
    start = time.monotonic()
    try:
        for frame in range(1,frames+1):
            tick = time.monotonic()
            if frame > 1:
                for _ in range(q['steps_per_video_frame']):
                    scene.step()
            wx, wv = cpu(water.get_particles_pos()), cpu(water.get_particles_vel())
            assert np.isfinite(wx).all() and np.isfinite(wv).all()
            speed = np.linalg.norm(wv,axis=1)
            local = wx[(np.abs(wx[:,0])<.75)&(np.abs(wx[:,1])<.75)]
            record = {'frame':frame,'time_seconds':(frame-1)/spec['render']['fps'],'duck_present':False,
                'water_bounds_m':[wx.min(axis=0).tolist(),wx.max(axis=0).tolist()],
                'local_water_z_max_m':float(local[:,2].max()),'water_velocity_max_mps':float(speed.max()),
                'water_speed_p95_mps':float(np.percentile(speed,95)),
                'water_kinetic_energy_j':float(.5*water_mass*np.mean(np.sum(wv.astype(np.float64)**2,axis=1))),
                'sph_advective_cfl':float(speed.max()*sub_dt/q['sph_particle_size_m']),
                'pressure_iteration_diagnostics':dict(solver.iteration_diagnostics),
                'pressure_iteration_counts_cumulative':dict(solver.iteration_counts),
                'frame_compute_seconds':time.monotonic()-tick}
            np.savez(out/'particles'/f'frame_{frame:04d}.npz',duck_pos=empty,duck_F=np.empty((0,3,3),dtype=np.float32),
                duck_vel=empty,water_pos=wx,water_vel=wv)
            report['frames'].append(record)
            report['simulation_seconds'] = time.monotonic()-start
            report['wall_seconds'] = time.monotonic()-wall_start
            save(out/'simulation_report.json',report)
            if frame==1 or frame%4==0:
                print('DUCK_DELETED_SPH_FRAME',frame,'water_KE',record['water_kinetic_energy_j'],flush=True)
            d = solver.iteration_diagnostics
            assert d['divergence_iteration_cap_hits']==d['density_iteration_cap_hits']==0
            assert record['sph_advective_cfl']<.4
            if report['wall_seconds']>max_wall_seconds and frame<frames:
                raise TimeoutError('Simulation safety time limit reached; partial output is preserved.')
        report['status'] = 'simulated_awaiting_coupling_and_visual_review' if frames==96 else 'diagnostic_partial_not_accepted'
    except BaseException as error:
        report.update(status='failed_partial_not_accepted',error=repr(error))
        raise
    finally:
        report['pressure_diagnostics_at_exit_including_partial_substeps'] = dict(solver.iteration_diagnostics)
        report['pressure_cap_examples'] = list(solver.cap_examples)
        report['wall_seconds'] = time.monotonic()-wall_start
        save(out/'simulation_report.json',report)


def audit_without_duck(case, spec, assets, manifest):
    run = case/'runs/source'
    r = json.loads((run/'simulation_report.json').read_text())
    p, q, actual = r['physics'],r['simulation_quality'],r['actual']
    assert r['status']=='simulated_awaiting_coupling_and_visual_review' and len(r['frames'])==96
    assert p==spec['physics'] and q==spec['simulation_quality'] and not duck_present(p)
    assert actual['duck_particles']==actual['ghost_particles']==0 and actual['duck_discrete_mass_kg']==0
    assert actual['mpm_active'] is False and actual['sph_entities']==1 and r['coupling']['enabled'] is False
    for key in ('sim_options','mpm_options','sph_options','coupler_options'):
        assert actual[key]==manifest['base_actual'][key]
    assert actual['water_particles']==manifest['base_actual']['water_particles']
    with np.load(run/'initial_particles.npz') as initial,np.load(assets/'water_initial_state.npz') as water:
        assert initial['duck_rest'].shape==(0,3)
        assert np.array_equal(initial['water_rest'],water['water_pos'])
        assert np.array_equal(initial['water_initial_velocity'],water['water_vel'])
    surface = float(np.percentile(initial_water_positions(assets)[:,2],99.5))
    rows, transforms = [],[]
    for row in r['frames']:
        frame = row['frame']
        with np.load(run/'particles'/f'frame_{frame:04d}.npz') as state:
            assert state['duck_pos'].shape==(0,3) and state['duck_F'].shape==(0,3,3) and state['duck_vel'].shape==(0,3)
            wx,wv = state['water_pos'],state['water_vel']
        assert len(wx)==actual['water_particles'] and np.isfinite(wx).all() and np.isfinite(wv).all()
        assert np.all(wx>=np.asarray(q['sph_lower_bound_m'])-2e-6) and np.all(wx<=np.asarray(q['sph_upper_bound_m'])+2e-6)
        assert row['sph_advective_cfl']<.4
        local=(np.abs(wx[:,0])<.75)&(np.abs(wx[:,1])<.75)
        rows.append({'frame':frame,'time_seconds':row['time_seconds'],'duck_present':False,
            'central_splash_particles':int(np.sum(local&(wx[:,2]>surface+.1))),
            'water_kinetic_energy_j':row['water_kinetic_energy_j']})
        transforms.append({'frame':frame,'time_seconds':row['time_seconds'],'duck':{'present':False}})
    pressure=r['pressure_diagnostics_at_exit_including_partial_substeps']
    assert pressure['divergence_solves']==pressure['density_solves']==95*q['steps_per_video_frame']*q['substeps_per_step']
    assert pressure['divergence_iteration_cap_hits']==pressure['density_iteration_cap_hits']==0
    validation={'status':'numerical_checks_passed_visual_review_pending','all_96_frames_checked':True,
        'same_initial_water_particles_and_velocities':True,'same_spatial_temporal_quality':True,
        'pressure_converged':True,'duck_deleted_from_simulation':True,'no_hidden_duck_or_ghost_collision_boundary':True,
        'duck_actual_mass_kg':0.,'physics_changes':spec['counterfactual']['changes'],
        'initial_surface_proxy_z_m':surface,'peak_central_splash_particles':max(row['central_splash_particles'] for row in rows),
        'simulation_report_sha256':digest(run/'simulation_report.json'),
        'accepted_as_calibrated_ground_truth':False,'frames':rows}
    save(case/'benchmark_validation.json',validation)
    save(case/'ground_truth_transforms.json',{'schema_version':3,'scene_id':'elastic_fluid_duck',
        'interaction_category':'elastic_fluid','deleted_objects':['duck'],'frames':transforms})
    save(case/'scenario_metadata.json',{'scene_id':'elastic_fluid_duck','case_id':spec['counterfactual']['id'],
        'physics':p,'simulation_quality':q,'render':spec['render'],'asset':spec['asset'],'actual':actual,
        'solver':'Same DFSPH fluid operators, no elastic object','object_presence':{'duck':False,'water':True},
        'source_video_sha256':manifest['selected_base_video_sha256']})
    print('DELETE_DUCK_PHYSICS_CHECKS_PASSED',validation['peak_central_splash_particles'],flush=True)


def audit(case):
    _import_data_runtime()
    spec, assets, manifest = load_case(case)
    if not water_present(spec['physics']):
        return audit_without_water(case,spec,assets,manifest)
    if not duck_present(spec['physics']):
        return audit_without_duck(case,spec,assets,manifest)
    run = case/'runs/source'
    report = json.loads((run/'simulation_report.json').read_text())
    assert report['status'] == 'simulated_awaiting_coupling_and_visual_review'
    assert len(report['frames']) == 96 and report['physics'] == spec['physics']
    assert report['simulation_quality'] == spec['simulation_quality']
    p, q, actual = report['physics'], report['simulation_quality'], report['actual']
    timed = spec['counterfactual'].get('timed_edits', [])
    if timed:
        assert report['initial_physics'] == spec['counterfactual']['before']
        assert report['initial_actual']['observed_water_rest_density_kg_m3'] == 1000.
        assert len(report['timed_edit_events']) == 1
        event = report['timed_edit_events'][0]
        trigger_frame = timed[0]['frame']
        assert event['frame'] == trigger_frame
        assert event['time_seconds'] == spec['counterfactual']['trigger_time_seconds'] == (trigger_frame-1)/spec['render']['fps']
        assert event['positions_velocities_and_deformation_bitwise_unchanged']
        assert event['native_material_fields_verified']
        assert report['timed_density_operator']['genesis_operator_unchanged']
        for record in report['frames']:
            expected_rho = 1000. if record['frame'] < trigger_frame else 185.
            assert record['water_rest_density_kg_m3'] == expected_rho
            expected_mass = manifest['base_actual']['water_discrete_mass_kg']*expected_rho/1000.
            assert abs(record['water_discrete_mass_kg']/expected_mass-1)<2e-6
    if 'water_density_kg_m3' in spec['counterfactual']['changes']:
        assert math.isclose(actual['observed_water_rest_density_kg_m3'],p['water_density_kg_m3'],rel_tol=2e-6)
        assert abs(actual['observed_water_discrete_mass_kg']/actual['water_discrete_mass_kg']-1)<2e-6
        expected_liquid_mass = manifest['base_actual']['water_discrete_mass_kg'] * p['water_density_kg_m3']/1000.
        assert abs(actual['water_discrete_mass_kg']/expected_liquid_mass-1)<2e-6
        assert p['water_dynamic_viscosity_pa_s']==spec['counterfactual']['before']['water_dynamic_viscosity_pa_s']
    assert actual['duck_particles'] == manifest['base_actual']['duck_particles']
    assert actual['water_particles'] == manifest['base_actual']['water_particles']
    assert actual['sim_options'] == manifest['base_actual']['sim_options']
    assert actual['mpm_options'] == manifest['base_actual']['mpm_options']
    assert actual['sph_options'] == manifest['base_actual']['sph_options']
    assert actual['coupler_options'] == manifest['base_actual']['coupler_options']
    with np.load(run/'initial_particles.npz') as initial, np.load(assets/'water_initial_state.npz') as water:
        assert np.array_equal(initial['water_rest'],water['water_pos'])
        assert np.array_equal(initial['water_initial_velocity'],water['water_vel'])
        rest = initial['duck_rest'].copy()
    with np.load(assets/'duck_reference_particles.npz') as reference:
        assert np.array_equal(rest,reference['duck_rest'])
    surface = float(np.percentile(initial_water_positions(assets)[:,2],99.5))
    sub_dt = q['step_dt_seconds']/q['substeps_per_step']
    water_nu = p['water_dynamic_viscosity_pa_s']/p['water_density_kg_m3']
    native_viscosity_dt = .01*actual['water_support_radius_m']**2/water_nu
    assert sub_dt <= native_viscosity_dt, 'Cached simulation exceeds the native explicit-viscosity bound.'
    mpm_low = np.asarray(q['mpm_lower_bound_m'])+3/q['mpm_grid_density_per_m']
    mpm_high = np.asarray(q['mpm_upper_bound_m'])-3/q['mpm_grid_density_per_m']
    rows = []
    transforms = []
    for record in report['frames']:
        frame = record['frame']
        with np.load(run/'particles'/f'frame_{frame:04d}.npz') as state:
            x,F,v,wx,wv = [state[name] for name in ('duck_pos','duck_F','duck_vel','water_pos','water_vel')]
        assert len(x) == actual['duck_particles'] and len(wx) == actual['water_particles']
        assert all(np.isfinite(value).all() for value in (x,F,v,wx,wv))
        assert np.all(x >= mpm_low-2e-6) and np.all(x <= mpm_high+2e-6)
        assert np.all(wx >= np.asarray(q['sph_lower_bound_m'])-2e-6) and np.all(wx <= np.asarray(q['sph_upper_bound_m'])+2e-6)
        assert np.linalg.det(F).min() > .05
        assert record['sph_advective_cfl'] < .4 and record['mpm_rest_wave_cfl'] < .9
        rotation = np.asarray(record['duck_deformation']['rotation_matrix_row_vectors'])
        tilt = float(np.degrees(np.arccos(np.clip(rotation[2,2],-1,1))))
        local = (np.abs(wx[:,0])<.75)&(np.abs(wx[:,1])<.75)
        splash = int(np.sum(local&(wx[:,2]>surface+.1)))
        rows.append({'frame':frame, 'time_seconds':record['time_seconds'], 'duck_tilt_degrees':tilt,
            'duck_center_z_m':record['duck_center_m'][2], 'duck_z_max_m':float(x[:,2].max()),
            'duck_fully_submerged':bool(x[:,2].max()<surface), 'central_splash_particles':splash,
            'water_kinetic_energy_j':float(.5*record.get('water_discrete_mass_kg',actual['water_discrete_mass_kg'])*np.mean(np.sum(wv.astype(np.float64)**2,axis=1)))})
        matrix = np.eye(4)
        matrix[:3,:3] = rotation.T
        matrix[:3,3] = np.asarray(record['duck_center_m'])-rotation.T@(rest.mean(axis=0)-np.asarray(p['duck_initial_reference_m']))
        transforms.append({'frame':frame, 'time_seconds':record['time_seconds'],
            'duck':{'matrix_world_best_fit':matrix.tolist(), 'center_of_mass_m':record['duck_center_m'],
                    'non_rigid_rms_m':record['duck_deformation']['rms_m']}})
    pressure = report['pressure_diagnostics_at_exit_including_partial_substeps']
    assert pressure['divergence_solves'] == pressure['density_solves'] == 95*q['steps_per_video_frame']*q['substeps_per_step']
    assert pressure['divergence_iteration_cap_hits'] == pressure['density_iteration_cap_hits'] == 0
    mapping = report['material_mapping_observation']
    assert mapping['invalid_material_stencils_at_exit'] == 0
    assert mapping['maximum_weight_sum_error_at_exit'] < 2e-5
    assert mapping['peak_first_moment_error_all_substeps_m'] < 2e-5
    if spec['counterfactual']['changes'] == {}:
        assert max(row['duck_tilt_degrees'] for row in rows) < 60
        assert max(row['duck_tilt_degrees'] for row in rows[72:]) < 15
    result = {'status':'numerical_checks_passed_visual_review_pending', 'all_96_frames_checked':True,
        'same_initial_material_points':True, 'same_initial_water_particles_and_velocities':True,
        'same_spatial_temporal_quality':True, 'pressure_converged':True,
        'physics_changes':spec['counterfactual']['changes'], 'duck_actual_mass_kg':actual['duck_discrete_mass_kg'],
        'initial_surface_proxy_z_m':surface, 'peak_central_splash_particles':max(r['central_splash_particles'] for r in rows),
        'last_second_fully_submerged':all(r['duck_fully_submerged'] for r in rows[72:]),
        'last_second_maximum_tilt_degrees':max(r['duck_tilt_degrees'] for r in rows[72:]),
        'simulation_report_sha256':digest(run/'simulation_report.json'),
        'accepted_as_calibrated_ground_truth':False, 'frames':rows}
    save(case/'benchmark_validation.json',result)
    if timed:
        trigger = rows[trigger_frame-1]
        descent = trigger['duck_center_z_m']-min(r['duck_center_z_m'] for r in rows[trigger_frame:])
        target = spec['counterfactual']['post_edit_motion_target']
        assert descent >= target['minimum_center_descent_m'], 'Timed density edit did not produce visible descent.'
        result['timed_density_edit'] = {'frame':trigger_frame,'time_seconds':event['time_seconds'],
            'before_density_kg_m3':1000.,'after_density_kg_m3':185.,
            'initial_physics_preserved_until_trigger':True,
            'continuous_positions_velocities_and_deformation':True,
            'trigger_stability_observation':event['trigger_stability_observation'],
            'post_trigger_center_descent_m':descent,
            'pre_trigger_duck_still_at_surface':trigger['duck_z_max_m']>surface,
            'external_intervention_mass_change_kg':event['external_mass_change_kg']}
        assert result['timed_density_edit']['pre_trigger_duck_still_at_surface']
        save(case/'benchmark_validation.json',result)
    if 'sinking_target' in spec['counterfactual']:
        assert result['last_second_fully_submerged'], 'Low-density sinking target failed: duck material resurfaces in the last second.'
    save(case/'ground_truth_transforms.json',{'schema_version':3, 'scene_id':'elastic_fluid_duck',
        'interaction_category':'elastic_fluid', 'transform_interpretation':'Best-fit rigid transform of a deforming MPM body; full deformation is preserved in particle caches.',
        'source_particle_cache':str(run/'particles'), 'frames':transforms})
    save(case/'scenario_metadata.json',{'scene_id':'elastic_fluid_duck', 'case_id':spec['counterfactual']['id'],
        'physics':p, 'simulation_quality':q, 'render':spec['render'], 'asset':spec['asset'],
        'actual':actual, 'solver':'MPM + DFSPH pressure boundary', 'source_video_sha256':manifest['selected_base_video_sha256']})
    print('PHYSICS_CHECKS_PASSED',spec['counterfactual']['id'],result['peak_central_splash_particles'],flush=True)


def measure_visible_immersion(case):
    """Diagnostic only: actual deformed geometry against the local rendered water surface."""
    _import_data_runtime()
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    sinking = 'sinking_target' in spec['counterfactual']
    target = spec['counterfactual'].get('sinking_target' if sinking else 'immersion_target')
    assert target and duck_present(spec['physics'])
    run = case/'runs/source'
    report = json.loads((run/'simulation_report.json').read_text())
    with np.load(run/'visual_deformation.npz') as data:
        poses = data['positions']
        assert list(map(int,data['frame_numbers'])) == list(range(1,97))
    rows = []
    for record in report['frames']:
        frame = record['frame']
        duck = poses[frame-1]
        center_xy = np.asarray(record['duck_center_m'][:2])
        with np.load(run/'meshes_smooth25'/f'water_{frame:04d}.npz') as mesh:
            vertices,normals = mesh['vertices'],mesh['normals']
        radius = np.linalg.norm(vertices[:,:2]-center_xy,axis=1)
        selected = (radius>=.45)&(radius<=.8)&(normals[:,2]>.5)
        assert selected.sum()>=32, 'Local liquid-surface proxy has insufficient samples.'
        surface = float(np.median(vertices[selected,2]))
        low,high = float(duck[:,2].min()),float(duck[:,2].max())
        assert high>low and np.isfinite([surface,low,high]).all()
        raw = (surface-low)/(high-low)
        rotation=np.asarray(record['duck_deformation']['rotation_matrix_row_vectors'])
        rows.append({'frame':frame,'time_seconds':record['time_seconds'],
            'local_liquid_surface_proxy_z_m':surface,'duck_z_min_m':low,'duck_z_max_m':high,
            'duck_world_z_height_m':high-low,'height_fraction_submerged':float(np.clip(raw,0.,1.)),
            'unclamped_height_fraction':float(raw),'liquid_surface_samples':int(selected.sum()),
            'duck_tilt_degrees':float(np.degrees(np.arccos(np.clip(rotation[2,2],-1.,1.))))})
    late = [row for row in rows if row['time_seconds']>=3.]
    fractions=np.asarray([row['height_fraction_submerged'] for row in late])
    assert len(late)==24
    result={'status':'diagnostic_complete_visual_waterline_review_required',
        'definition':'Fraction of world-Z extent of actual MPM-skinned duck below a local rendered-surface proxy; not a volume fraction or screen-pixel segmentation.',
        'surface_proxy':'Median reconstructed liquid vertices with upward normals (nz > 0.5) in a 0.45–0.8 m ring around the duck center.',
        'no_pose_or_rotation_control':True,'late_window_seconds':[3.,4.],
        'late_median_height_fraction':float(np.median(fractions)),
        'late_minimum_height_fraction':float(fractions.min()),'late_maximum_height_fraction':float(fractions.max()),
        'late_maximum_tilt_degrees':max(row['duck_tilt_degrees'] for row in late),
        'late_median_near_half_diagnostic':bool(.4<=np.median(fractions)<=.6),
        'simulation_report_sha256':digest(run/'simulation_report.json'),'frames':rows,
        'accepted_as_calibrated_ground_truth':False}
    save(case/'immersion_diagnostic.json',result)
    if sinking:
        clearance = min(row['local_liquid_surface_proxy_z_m']-row['duck_z_max_m'] for row in late)
        result.update(target_kind='sinking',late_minimum_surface_clearance_m=clearance,
                      late_entire_visual_duck_below_surface=bool(clearance>=target['minimum_surface_clearance_m']))
        result.pop('late_median_near_half_diagnostic')
        save(case/'immersion_diagnostic.json',result)
        assert result['late_entire_visual_duck_below_surface'], 'Rendered-geometry sinking target failed: late duck mesh reaches the liquid surface.'
    print('VISIBLE_IMMERSION_DIAGNOSTIC',result['late_median_height_fraction'],
        result['late_minimum_height_fraction'],result['late_maximum_height_fraction'],flush=True)


def initial_water_positions(assets):
    with np.load(assets/'water_initial_state.npz') as data:
        return data['water_pos'].copy()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir',type=Path,required=True)
    parser.add_argument('--stage',choices=('simulate','surface','audit'),default='simulate')
    parser.add_argument('--frames',type=int,default=96,help='Default is the complete four-second clip.')
    parser.add_argument('--max-wall-seconds',type=float,default=7200)
    parser.add_argument('--source-branch-case',type=Path,
                        help='Timed edit only: a prepared source case directory; the same run also simulates the unedited '
                             'source from the trigger state (complete solver state copied and restored), so the frames up to '
                             'the trigger are identical in both cases.')
    args = parser.parse_args()
    assert 2 <= args.frames <= 96 and args.max_wall_seconds > 0
    case = args.case_dir.resolve()
    if args.stage == 'simulate':
        simulate(case,args.frames,args.max_wall_seconds,args.source_branch_case)
    else:
        audit(case)
        if args.stage == 'surface':
            if duck_present(json.loads((case/'mpm_sph_experiment.json').read_text())['physics']):
                skin_duck(case,'source')
            if water_present(json.loads((case/'mpm_sph_experiment.json').read_text())['physics']):
                mesh_water(case,'source',list(range(1,97)),smoothing_iters=25,mesh_tag='smooth25',cube_size=.8)
            else:
                verify_empty_pool_surface(case)
            if {'immersion_target','sinking_target'} & json.loads((case/'mpm_sph_experiment.json').read_text())['counterfactual'].keys():
                measure_visible_immersion(case)


if __name__ == '__main__':
    main()
