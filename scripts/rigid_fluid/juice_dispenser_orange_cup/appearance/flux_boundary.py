"""Conservative fixed-aperture inlet for the pinned Blender 4.3.2 solver.

Particle births integrate A*v*dt. A uniform level-set isovalue correction
preserves this volume before pressure projection and during surface
reconstruction. Native FLIP advection, pressure, gravity, viscosity and rigid
collisions remain active. Finished meshes and videos are never scaled.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import ctypes
import inspect
import json
import math
import re
from pathlib import Path

import manta
import numpy as np

from simulate_juice_dispenser_orange_cup import speed_at_time, integrated_speed

PROTOCOL = 'fixed_aperture_conservative_surface_inlet_6'


def grid_view(grid, vector=False, integer=False):
    address = int(grid.getDataPointer().replace(',', ''), 16)
    size = (grid.getSizeZ(), grid.getSizeY(), grid.getSizeX())
    if vector:
        size += (3,)
    pointer = ctypes.cast(address, ctypes.POINTER(ctypes.c_int32 if integer else ctypes.c_float))
    return np.ctypeslib.as_array(pointer, shape=(math.prod(size),)).reshape(size)


def mesh_volume(mesh, dx):
    # These accessors expose std::vector headers, not the arrays themselves.
    # Read only. Layout is fixed by Blender 4.3.2's mesh.h: Node=28, Triangle=16.
    def vector_data(pointer_string, stride):
        address = int(pointer_string.replace(',', ''), 16)
        begin, end, capacity = (ctypes.c_void_p * 3).from_address(address)
        if begin is None:
            return None, 0
        if not begin <= end <= capacity or (end-begin) % stride:
            raise RuntimeError('Unexpected native Mantaflow mesh-vector layout')
        count = (end-begin)//stride
        if count > 20000000:
            raise RuntimeError('Unexpected Mantaflow mesh size')
        raw = np.ctypeslib.as_array((ctypes.c_ubyte * (count*stride)).from_address(begin))
        return raw, count
    nodes, node_count = vector_data(mesh.getNodesDataPointer(), 28)
    triangles, triangle_count = vector_data(mesh.getTrisDataPointer(), 16)
    if not triangle_count:
        return 0.0
    points = nodes.view(np.float32).reshape(node_count, 7)[:, 1:4].astype(np.float64)
    indices = triangles.view(np.int32).reshape(triangle_count, 4)[:, :3]
    if indices.min() < 0 or indices.max() >= node_count or not np.isfinite(points).all():
        raise RuntimeError('Invalid native liquid surface')
    tri = points[indices]
    return abs(float(np.einsum('ij,ij->i', tri[:,0], np.cross(tri[:,1],tri[:,2])).sum()))/6.0*dx**3


class FluxBoundary:
    def __init__(self, *, domain_min, emitter_min_z, center_xy, radius_m, speed_m_s,
                 start_sec, end_sec, report_path, speed_change_sec=None, speed_after_m_s=None, aperture_mode="binary", target_area_m2=None, target_plane_z_m=None):
        self.aperture_mode = aperture_mode
        self.target_area_m2 = target_area_m2
        self.target_plane_z_m = target_plane_z_m
        self.protocol = PROTOCOL if aperture_mode == "binary" else "fixed_fractional_aperture_conservative_surface_inlet_7"
        self.domain_min = np.asarray(domain_min, dtype=float)
        self.emitter_min_z = float(emitter_min_z)
        self.center_xy = np.asarray(center_xy, dtype=float)
        self.radius = float(radius_m)
        self.speed = float(speed_m_s)
        self.speed_change = speed_change_sec
        self.speed_after = speed_after_m_s
        if (self.speed_change is None) != (self.speed_after is None):
            raise ValueError('Provide both speed_change_sec and speed_after_m_s')
        self.start = float(start_sec)
        self.end = float(end_sec)
        self.report_path = Path(report_path)
        self.contexts = {}
        self.records = []
        self.generated_particles = 0
        self.target_particle_count = 0.0
        self.cumulative_volume_m3 = 0.0
        self.emission_covered_until_sec = self.start
        self.frame_budgets = {}
        self.volume_records = []
        self.native_sample = manta.sampleLevelsetWithParticles
        self.native_pressure = manta.solvePressure
        self.native_extrapolate = manta.extrapolateLsSimple

    def install(self):
        import bpy
        if bpy.app.version != (4, 3, 2):
            raise RuntimeError('The conservative native inlet requires Blender 4.3.2')
        owner = self

        def sample_hook(*args, **kwargs):
            scope = inspect.currentframe().f_back.f_globals
            caller = inspect.currentframe().f_back.f_code.co_name
            match = re.fullmatch(r'liquid_adaptive_step_(\d+)', caller)
            if match:
                suffix = match.group(1)
                owner.inject(scope, suffix, kwargs['parts'])
                result = None
            else:
                result = owner.native_sample(*args, **kwargs)
            owner.enforce(scope, caller, 'pre_advection')
            return result

        def pressure_hook(*args, **kwargs):
            scope = inspect.currentframe().f_back.f_globals
            caller = inspect.currentframe().f_back.f_code.co_name
            match = re.fullmatch(r'liquid_step_(\d+)', caller)
            if match:
                owner.correct_simulation_volume(scope, match.group(1))
            result = owner.native_pressure(*args, **kwargs)
            owner.enforce(scope, caller, 'post_pressure')
            return result

        def extrapolate_hook(*args, **kwargs):
            caller = inspect.currentframe().f_back
            match = re.fullmatch(r'liquid_adaptive_step_(\d+)', caller.f_code.co_name)
            if match:
                suffix = match.group(1)
                scope = caller.f_globals
                if kwargs.get('phi') is scope.get('phiIn_s'+suffix):
                    # Disable native volumetric stamping. Only the controlled
                    # particle parcels below introduce new liquid volume.
                    kwargs['phi'].setConst(9999.0)
                    return None
            result = owner.native_extrapolate(*args, **kwargs)
            match = re.fullmatch(r'liquid_step_mesh_(\d+)', caller.f_code.co_name)
            if match and not kwargs.get('inside', False):
                suffix = match.group(1)
                scope = caller.f_globals
                if kwargs.get('phi') is scope.get('phi_sm'+suffix):
                    owner.correct_mesh_volume(scope, suffix, caller)
            return result

        manta.sampleLevelsetWithParticles = sample_hook
        manta.solvePressure = pressure_hook
        manta.extrapolateLsSimple = extrapolate_hook

    def prepare(self, scope, suffix):
        vel = scope['vel_s'+suffix]
        dx = float(scope['ratioMetersToRes_s'+suffix])
        scale = float(scope['ratioResToBLength_s'+suffix])*float(scope['ratioBTimeToTimestep_s'+suffix])
        nx, ny, nz = vel.getSizeX(), vel.getSizeY(), vel.getSizeZ()
        weights = np.zeros((ny, nx), dtype=np.float32)
        # The canonical N160 protocol uses full MAC faces at the target speed.
        # The N96 effect preset integrates circle/face intersections; partial
        # faces carry area-averaged velocity. Both report their physical area.
        yy = self.domain_min[1]+(np.arange(ny)+0.5)*dx-self.center_xy[1]
        xx = self.domain_min[0]+(np.arange(nx)+0.5)*dx-self.center_xy[0]
        weights[:] = (yy[:,None]**2+xx[None,:]**2 <= self.radius**2)
        centroids = {}
        if self.aperture_mode == "fractional_circle":
            nodes, quadrature = np.polynomial.legendre.leggauss(64)
            weights[:] = 0.0
            for j in range(ny):
                y0 = self.domain_min[1] + j*dx - self.center_xy[1]
                y1 = y0+dx
                if y0 >= self.radius or y1 <= -self.radius: continue
                for i in range(nx):
                    x0 = max(-self.radius, self.domain_min[0]+i*dx-self.center_xy[0])
                    x1 = min(self.radius, self.domain_min[0]+(i+1)*dx-self.center_xy[0])
                    if x1 <= x0: continue
                    xx = (nodes+1)*(x1-x0)*0.5+x0
                    yy = np.sqrt(np.maximum(0.0,self.radius*self.radius-xx*xx))
                    low = np.maximum(-yy,y0);high = np.minimum(yy,y1)
                    height = np.maximum(0.0,high-low)
                    area = float(np.dot(quadrature,height))*(x1-x0)*0.5
                    if area < dx*dx*1e-7: continue
                    weights[j,i] = area/(dx*dx)
                    cx = float(np.dot(quadrature,height*xx))*(x1-x0)*0.5/area
                    cy = float(np.dot(quadrature,np.where(high>low,(high*high-low*low)*0.5,0.0)))*(x1-x0)*0.5/area
                    centroids[(j,i)] = ((cx+self.center_xy[0]-self.domain_min[0])/dx-i,(cy+self.center_xy[1]-self.domain_min[1])/dx-j)
            desired = self.target_area_m2 or math.pi*self.radius**2
            difference = desired/(dx*dx)-float(weights.sum())
            partial = (weights>0.0)&(weights<0.999999)
            capacity = np.where(partial,(1.0-weights) if difference>0 else weights,0.0)
            weights += difference*capacity/float(capacity.sum())
            assert weights.min() >= -1e-7 and weights.max() <= 1.000001
        target_area = float(weights.sum())*dx*dx
        plane = math.floor((self.emitter_min_z-self.domain_min[2])/dx)-1
        if self.target_plane_z_m is not None:
            plane = int(round((self.target_plane_z_m-self.domain_min[2])/dx))
        if not 3 <= plane < nz-3:
            raise RuntimeError('The outlet boundary is too close to a domain wall')
        result = {'scope': scope, 'dx': dx, 'scale': scale, 'weights': weights,
                  'plane': plane, 'shape': (nz, ny, nx), 'seconds_per_manta_time': float(scope['ratioBTimeToTimestep_s'+suffix]),
                  'area': target_area, 'aperture_cells': np.argwhere(weights > 0.0), 'centroids':centroids}
        result['aperture_cdf'] = np.cumsum(weights[weights>0.0].astype(float))
        self.contexts[suffix] = result
        print('[flux-boundary]', json.dumps({'protocol': self.protocol, 'solver_id': suffix,
              'plane_z_m': self.domain_min[2]+plane*dx, 'aperture_area_m2': target_area,
              'target_flux_ml_s': target_area*self.speed*1e6}), flush=True)
        return result

    def inject(self, scope, suffix, parts):
        ctx = self.contexts.get(suffix) or self.prepare(scope, suffix)
        solver = scope['s'+suffix]
        time_sec = float(solver.timeTotal)*ctx['seconds_per_manta_time']
        dt = float(solver.timestep)*ctx['seconds_per_manta_time']
        # Match the solver's maintained interior particle density (8..16/cell).
        particles_per_cell = 12.0
        particle_volume_m3 = ctx['dx']**3/particles_per_cell
        interval_end = min(time_sec+dt, self.end)
        interval_start = max(time_sec, self.start, self.emission_covered_until_sec)
        dt = max(0.0, interval_end-interval_start)
        self.emission_covered_until_sec = max(self.emission_covered_until_sec, interval_end)
        if self.speed_change is None or interval_end <= self.speed_change:
            # Retain the original arithmetic before the intervention.
            travel = self.speed*dt
            supplied_volume = ctx['area']*self.speed*dt
        else:
            travel = integrated_speed(interval_start, interval_end, self.speed, self.speed_change, self.speed_after)
            supplied_volume = ctx['area']*travel
        self.target_particle_count += supplied_volume/particle_volume_m3
        self.cumulative_volume_m3 += supplied_volume
        self.frame_budgets[int(solver.frame)] = self.cumulative_volume_m3
        count = math.floor(self.target_particle_count)-self.generated_particles
        start = parts.pySize()
        cells = ctx['aperture_cells']
        thickness_cells = travel/ctx['dx']
        origin_index = (np.arange(count, dtype=np.int64)+self.generated_particles)
        for index in origin_index:
            if self.aperture_mode == "fractional_circle":
                sample = ((float(index)*0.7548776662466927)%1.0)*ctx['aperture_cdf'][-1]
                cell_index = min(len(cells)-1,int(np.searchsorted(ctx['aperture_cdf'],sample)))
            else:
                cell_index = int(index % len(cells))
            j, i = cells[cell_index]
            u = (float(index)*0.6180339887498949) % 1.0
            v = (float(index)*0.4142135623730951) % 1.0
            w = (float(index)*0.7320508075688772) % 1.0
            if self.aperture_mode == "fractional_circle":
                for attempt in range(128):
                    px = self.domain_min[0]+(i+u)*ctx['dx']-self.center_xy[0]
                    py = self.domain_min[1]+(j+v)*ctx['dx']-self.center_xy[1]
                    if px*px+py*py <= self.radius*self.radius: break
                    u = (u+0.6180339887498949)%1.0
                    v = (v+0.4142135623730951)%1.0
                else:
                    u,v=ctx['centroids'][(int(j),int(i))]
            parts.addParticle(manta.vec3(float(i)+u, float(j)+v, float(ctx['plane'])+w*thickness_cells))
        stop = parts.pySize()
        assert stop-start == count
        if count:
            pdata = scope['pVel_pp'+suffix]
            birth_speed = speed_at_time(interval_start, self.speed, self.speed_change, self.speed_after)
            pdata.setConstRange(manta.vec3(0.0, 0.0, -birth_speed*ctx['scale']), start, stop)
        self.generated_particles += count

    def project_volume(self, phi, dx, target, *, mesh, mask):
        array = grid_view(phi)
        valid = np.isfinite(array) & (array < 8.0)
        valid &= mask
        array[~mask] = np.maximum(array[~mask], 0.5)
        values = array[valid].copy()
        def volume(offset):
            array[valid] = values+offset
            phi.createMesh(mesh)
            return mesh_volume(mesh, dx)
        before = volume(0.0)
        if target <= 0:
            array[:] = 9999.0
            return before, 0.0, 9999.0
        lo, hi = (-0.5, 0.0) if before < target else (0.0, 0.5)
        vlo = volume(lo) if lo else before
        vhi = volume(hi) if hi else before
        while vlo < target and lo > -4.0:
            lo *= 2.0
            vlo = volume(lo)
        while vhi > target and hi < 8.0:
            hi *= 2.0
            vhi = volume(hi)
        if vlo < target or vhi > target:
            raise RuntimeError('Could not bracket the conservative level-set isovalue')
        after, offset = before, 0.0
        for unused in range(18):
            fraction = (vlo-target)/max(vlo-vhi, 1e-30)
            fraction = min(0.9, max(0.1, fraction))
            offset = lo+(hi-lo)*fraction
            after = volume(offset)
            if abs(after-target) <= max(1e-12, target*0.0001):
                break
            if after > target:
                lo, vlo = offset, after
            else:
                hi, vhi = offset, after
        return before, after, offset

    def correct_simulation_volume(self, scope, suffix):
        ctx = self.contexts[suffix]
        flags = scope['flags_s'+suffix]
        allowed = (grid_view(flags, integer=True) & int(manta.CellType_TypeObstacle)) == 0
        if 'projection_mesh' not in ctx:
            ctx['projection_mesh'] = scope['s'+suffix].create(manta.Mesh)
        before, after, offset = self.project_volume(scope['phi_s'+suffix], ctx['dx'],
            self.cumulative_volume_m3, mesh=ctx['projection_mesh'], mask=allowed)
        flags.updateFromLevelset(scope['phi_s'+suffix])
        # Closed inflow can skip native emission; preserve the last volume
        # budget for every pressure/mesh frame after the stop.
        self.frame_budgets[int(scope['s'+suffix].frame)] = self.cumulative_volume_m3
        self.volume_records.append({'phase': 'simulation', 'frame': int(scope['s'+suffix].frame),
            'target_ml': self.cumulative_volume_m3*1e6, 'before_ml': before*1e6,
            'after_ml': after*1e6, 'offset_cells': offset})

    def correct_mesh_volume(self, scope, suffix, caller):
        frame = None
        walker = caller
        stack_frames = []
        while walker:
            if 'framenr' in walker.f_locals:
                frame = int(walker.f_locals['framenr'])
                break
            stack_frames.append(walker.f_code.co_name)
            walker = walker.f_back
        if frame is None:
            frame = int(scope['s'+suffix].frame)
        if frame not in self.frame_budgets:
            raise RuntimeError(f'No injected-volume budget for mesh frame {frame}; frames={list(self.frame_budgets)}, stack={stack_frames}')
        target = self.frame_budgets[frame]
        ctx = self.contexts[suffix]
        upres = float(scope['upres_sm'+suffix])
        allowed = (grid_view(scope['flags_s'+suffix], integer=True) & int(manta.CellType_TypeObstacle)) == 0
        allowed = np.repeat(np.repeat(np.repeat(allowed, int(upres), axis=0), int(upres), axis=1), int(upres), axis=2)
        before, after, offset = self.project_volume(scope['phi_sm'+suffix], ctx['dx']/upres,
            target, mesh=scope['mesh_sm'+suffix], mask=allowed)
        self.volume_records.append({'phase': 'mesh', 'frame': frame,
            'target_ml': target*1e6, 'before_ml': before*1e6, 'after_ml': after*1e6,
            'offset_cells': offset})

    def enforce(self, scope, caller, phase):
        match = re.fullmatch(r'liquid_(?:adaptive_step|step)_(\d+)', caller)
        if not match:
            return
        suffix = match.group(1)
        ctx = self.contexts.get(suffix) or self.prepare(scope, suffix)
        vel = grid_view(scope['vel_s'+suffix], vector=True)
        solver = scope['s'+suffix]
        time_sec = float(solver.timeTotal)*ctx['seconds_per_manta_time']
        active = self.start <= time_sec < self.end
        speed = speed_at_time(time_sec, self.speed, self.speed_change, self.speed_after) if active else 0.0
        plane = ctx['plane']
        # A short plug-flow section prevents advection from skipping the face.
        vel[plane-1:plane+2, :, :, :] = 0.0
        vel[plane-1:plane+2, :, :, 2] = -speed*ctx['scale']*ctx['weights'][None, :, :]
        if phase == 'post_pressure':
            phi = grid_view(scope['phi_s'+suffix])
            wet = (phi[plane-1]+phi[plane])*0.5 < 0.0
            normal = -vel[plane, :, :, 2]/ctx['scale']
            q = float(normal.sum())*ctx['dx']**2*1e6
            wet_q = float((normal*wet).sum())*ctx['dx']**2*1e6
            self.records.append({'frame': int(solver.frame), 'time_sec': time_sec,
                'dt_sec': float(solver.timestep)*ctx['seconds_per_manta_time'],
                'grid_flux_ml_s': q, 'liquid_occupied_flux_ml_s': wet_q,
                'target_flux_ml_s': ctx['area']*speed*1e6, 'target_speed_m_s': speed,
                'generated_particles': self.generated_particles, 'cumulative_volume_ml': self.cumulative_volume_m3*1e6})

    def close(self):
        manta.sampleLevelsetWithParticles = self.native_sample
        manta.solvePressure = self.native_pressure
        manta.extrapolateLsSimple = self.native_extrapolate
        for ctx in self.contexts.values():
            ctx['scope']['sampleLevelsetWithParticles'] = self.native_sample
            ctx['scope']['solvePressure'] = self.native_pressure
            ctx['scope']['extrapolateLsSimple'] = self.native_extrapolate
        apertures = [{'area_m2': ctx['area'], 'cell_size_m': ctx['dx'],
                      'area_relative_error': ctx['area']/(math.pi*self.radius**2)-1.0,
                      'boundary_plane_z_m': self.domain_min[2]+ctx['plane']*ctx['dx']}
                     for ctx in self.contexts.values()]
        report = {'protocol': self.protocol, 'aperture_mode': self.aperture_mode, 'prescribed_area_m2':self.target_area_m2, 'speed_m_s': self.speed, 'radius_m': self.radius,
                  'target_flux_ml_s': math.pi*self.radius**2*self.speed*1e6,
                  'speed_schedule': [] if self.speed_change is None else [{'at_sec':self.speed_change,'before_m_s':self.speed,'after_m_s':self.speed_after}],
                  'discrete_apertures': apertures,
                  'generated_particles': self.generated_particles, 'target_particle_count': self.target_particle_count,
                  'cumulative_volume_ml': self.cumulative_volume_m3*1e6,
                  'volume_records': self.volume_records,
                  'records': self.records}
        self.report_path.write_text(json.dumps(report, indent=2)+'\n')
        self.contexts.clear()
        if not self.records:
            raise RuntimeError('The outlet boundary hook was not called by the solver')
