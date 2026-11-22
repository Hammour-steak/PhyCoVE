"""Implicit symmetric strain-rate viscosity on active MAC faces.

Solve (M + alpha * B.T B) v_new = M v_old. B contains sqrt(2) normal
strain and volume-weighted mixed strain. Fluid/air boundaries have natural
zero traction; stationary obstacle faces have zero velocity. This binary
cut-cell approximation is an explicit simulation-quality choice.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import json
import time
from pathlib import Path
import numpy as np
import scipy
from scipy import sparse
from scipy.sparse import linalg
import manta
from flux_boundary import grid_view


def strain_system(fluid, obstacle):
    fluid = np.asarray(fluid,dtype=bool)
    obstacle = np.asarray(obstacle,dtype=bool)
    shape = fluid.shape
    ids = np.full(shape+(3,),-1,dtype=np.int32)
    known = np.empty(shape+(3,),dtype=bool)
    masses = []
    count = 0
    for comp,axis in enumerate((2,1,0)):
        previous = np.roll(fluid,1,axis=axis)
        previous_obstacle = np.roll(obstacle,1,axis=axis)
        boundary = [slice(None)]*3
        boundary[axis] = 0
        previous[tuple(boundary)] = False
        previous_obstacle[tuple(boundary)] = True
        wall = obstacle | previous_obstacle
        active = (fluid | previous) & ~wall
        ids[...,comp][active] = np.arange(count,count+np.count_nonzero(active))
        count += np.count_nonzero(active)
        known[...,comp] = active | wall
        masses.append((0.5*(fluid.astype(float)+previous.astype(float)))[active])
    mass = np.concatenate(masses)
    rows,columns,values = [],[],[]
    row_count = 0

    def add_term(fields,coefficients,valid,weight):
        nonlocal row_count
        selected = [field[valid] for field in fields]
        n = len(selected[0])
        if not n:
            return
        row = np.arange(row_count,row_count+n)
        scale = np.sqrt(weight[valid])
        for field,coefficient in zip(selected,coefficients):
            unknown = field >= 0
            rows.append(row[unknown])
            columns.append(field[unknown])
            values.append(coefficient*scale[unknown])
        row_count += n

    # Normal strain at each liquid cell center.
    for comp,axis in enumerate((2,1,0)):
        left = ids[...,comp]
        right = np.roll(left,-1,axis=axis)
        add_term((left,right),(-1.0,1.0),fluid,np.full(shape,2.0))

    # Mixed strain at grid edges. Omit terms crossing an unknown free surface,
    # giving a natural traction boundary rather than fictitious air drag.
    for a,b in ((0,1),(0,2),(1,2)):
        axis_a,axis_b = (2,1,0)[a],(2,1,0)[b]
        fields = (ids[...,a],np.roll(ids[...,a],1,axis=axis_b),
                  ids[...,b],np.roll(ids[...,b],1,axis=axis_a))
        valid = (known[...,a] & np.roll(known[...,a],1,axis=axis_b)
                 & known[...,b] & np.roll(known[...,b],1,axis=axis_a))
        weight = 0.25*(fluid.astype(float)+np.roll(fluid,1,axis=axis_a).astype(float)
                       +np.roll(fluid,1,axis=axis_b).astype(float)
                       +np.roll(np.roll(fluid,1,axis=axis_a),1,axis=axis_b).astype(float))
        valid &= weight > 0
        for axis in (axis_a,axis_b):
            boundary = [slice(None)]*3
            boundary[axis] = 0
            valid[tuple(boundary)] = False
        add_term(fields,(1.0,-1.0,1.0,-1.0),valid,weight)
    if not count:
        return ids,mass,sparse.csr_matrix((0,0))
    strain = sparse.coo_matrix((np.concatenate(values),
                               (np.concatenate(rows),np.concatenate(columns))),
                              shape=(row_count,count)).tocsr()
    return ids,mass,strain


class CoupledViscosity:
    def __init__(self,report_path,tolerance=1e-7,max_iterations=1500):
        self.report_path = Path(report_path)
        self.tolerance = tolerance
        self.max_iterations = max_iterations
        self.records = []
        self.failure = None

    def save(self):
        self.report_path.write_text(json.dumps({
            'implementation':'implicit_symmetric_strain_rate_active_mac',
            'boundary_discretization':'binary_liquid_cells; natural free-surface traction; stationary no-slip obstacle faces',
            'scipy_version':scipy.__version__,'relative_cg_tolerance':self.tolerance,
            'cg_max_iterations':self.max_iterations,'callback_failure':self.failure,
            'records':self.records},indent=2)+'\n')

    def __call__(self,flags,grid,alpha,frame=None):
        started = time.perf_counter()
        f = grid_view(flags,integer=True)
        fluid = (f & int(manta.CellType_TypeFluid)) != 0
        obstacle = (f & int(manta.CellType_TypeObstacle)) != 0
        fluid &= ~obstacle
        # Domain boundary cells are rigid for this closed dispenser scene.
        for axis in (0,1,2):
            for index in (0,-1):
                sl = [slice(None)]*3
                sl[axis] = index
                fluid[tuple(sl)] = False
                obstacle[tuple(sl)] = True
        ids,mass,strain = strain_system(fluid,obstacle)
        vel = grid_view(grid,vector=True)
        if not len(mass):
            vel[:] = 0.0
            return
        old = np.empty(len(mass),dtype=np.float64)
        for comp in range(3):
            active = ids[...,comp] >= 0
            old[ids[...,comp][active]] = vel[...,comp][active]
        stiffness = strain.T @ strain
        matrix = sparse.diags(mass,format='csr')+float(alpha)*stiffness
        rhs = mass*old
        inverse_diagonal = 1.0/matrix.diagonal()
        preconditioner = linalg.LinearOperator(matrix.shape,matvec=lambda x:inverse_diagonal*x)
        iterations = 0
        def count_iteration(unused):
            nonlocal iterations
            iterations += 1
        new,info = linalg.cg(matrix,rhs,x0=old,tol=self.tolerance,atol=1e-11,
                            maxiter=self.max_iterations,M=preconditioner,callback=count_iteration)
        residual = float(np.linalg.norm(matrix@new-rhs)/max(1e-12,np.linalg.norm(rhs)))
        energy_before = float(np.dot(mass,old*old))
        energy_after = float(np.dot(mass,new*new))
        entry = {'frame':frame,'fluid_cells':int(fluid.sum()),'velocity_dofs':len(mass),
                 'strain_samples':strain.shape[0],'alpha':float(alpha),'iterations':iterations,
                 'cg_info':int(info),'relative_residual':residual,
                 'kinetic_energy_before_native':energy_before,'kinetic_energy_after_native':energy_after,
                 'total_seconds':time.perf_counter()-started}
        self.records.append(entry)
        if (info != 0 or residual > 3*self.tolerance or not np.isfinite(new).all()
                or energy_after > energy_before*(1+1e-7)+1e-9):
            self.failure = entry
            self.save()
            raise RuntimeError('Implicit viscous solve failed convergence/energy checks: '+str(entry))
        vel[:] = 0.0
        for comp in range(3):
            active = ids[...,comp] >= 0
            vel[...,comp][active] = new[ids[...,comp][active]]
        if len(self.records)%16 == 0:
            self.save()
