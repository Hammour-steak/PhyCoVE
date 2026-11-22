#!/usr/bin/env python3
"""Matched Genesis FEM/IPC shell cases with an actual SI Young modulus.

The task-local Genesis IPC registration hook uses native NeoHookeanShell
instead of the stock strain-limiting BW membrane. No installed code is edited.
E is the only independent material edit; kappa = E*h**3/(24*(1-nu**2))
follows the same isotropic shell law. Air is prescribed one-way triangle drag.
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
import copy
import hashlib
import importlib.metadata
import json
import sys
import time
import types
from unittest.mock import patch
from pathlib import Path

import numpy as np
from wind_flag_config import SPEC, ASSETS, RUNTIME_DEPS, CASE_E, CASE_WIND_SPEED

PHYSICS = SPEC["physics"]
WIDTH, HEIGHT, TOP_Z = (PHYSICS[k] for k in ("flag_width_m", "flag_height_m", "flag_top_z_m"))
POLE_RADIUS, POLE_HEIGHT, HOIST_X = (PHYSICS[k] for k in ("pole_collision_proxy_radius_m", "pole_height_m", "hoist_x_m"))
# Four-millimetre collision proxy allowance protects the evaluated render
# subdivision against cutting into the measured 10.0562 mm visual shaft.
VISUAL_POLE_RADIUS = PHYSICS["pole_visual_radius_m"]
AIR_RHO, CD_NORMAL, CD_TANGENT = (PHYSICS[k] for k in ("air_density_kg_m3", "normal_Cd", "tangential_Cd"))
FULL_THICKNESS, DENSITY, NU = (PHYSICS[k] for k in ("full_thickness_m", "density_kg_m3", "poisson_ratio"))
PIN_TOLERANCE_M = SPEC["simulation_quality"]["pin_audit_tolerance_m"]


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf8")


def rest_mesh(nx, nz):
    xyz, uv, faces = [], [], []
    for j in range(nz):
        v = j / (nz - 1)
        for i in range(nx):
            u = i / (nx - 1)
            y = (0.0045 * np.sin(2*np.pi*u + .4) + .0018*np.sin(7*np.pi*u - .7))*np.sin(np.pi*v)
            xyz.append((HOIST_X + WIDTH*u, y, TOP_Z - HEIGHT*v))
            uv.append((u, 1-v))
    for j in range(nz-1):
        for i in range(nx-1):
            a = j*nx+i
            b, c, d = a+1, a+nx, a+nx+1
            faces.extend(((a,b,c),(b,d,c)) if (i+j)%2 else ((a,b,d),(a,d,c)))
    return np.array(xyz, np.float64), np.array(faces, np.int32), np.array(uv, np.float64)


def write_obj(path, xyz, faces, uv):
    with path.open("w") as stream:
        for p in xyz:
            stream.write("v " + " ".join(f"{x:.12g}" for x in p) + "\n")
        for p in uv:
            stream.write("vt " + " ".join(f"{x:.12g}" for x in p) + "\n")
        for f in faces:
            stream.write("f " + " ".join(f"{int(i)+1}/{int(i)+1}" for i in f) + "\n")


def air_velocity(pos, t, speed):
    x, z = pos[:,0], pos[:,2]
    a = 1.9*t - 3*x + 1.7*(z-3) + .4
    b = 4.8*t - 6.6*x + 4.1*(z-3) + 1.2
    c = 8.2*t - 11.3*x - 3*(z-3) + .7
    ux = np.full(len(pos), 1 + .08*np.sin(.68*t) + .04*np.sin(1.7*t+.3))
    uy = -.08 + .15*np.sin(a) + .06*np.sin(b) + .025*np.sin(c)
    uz = .025 + .04*np.sin(.73*b) - .03*np.sin(.56*a)
    return speed*np.column_stack((ux, uy, uz))


def triangle_forces(pos, vel, faces, t, speed):
    tri, tv = pos[faces], vel[faces]
    cross = np.cross(tri[:,1]-tri[:,0], tri[:,2]-tri[:,0])
    double_area = np.linalg.norm(cross, axis=1)
    normal = cross/np.maximum(double_area[:,None], 1e-12)
    relative = air_velocity(tri.mean(axis=1), t, speed) - tv.mean(axis=1)
    vn = np.sum(relative*normal, axis=1)[:,None]
    force = .25*AIR_RHO*double_area[:,None]*np.linalg.norm(relative,axis=1)[:,None]*(
        CD_NORMAL*vn*normal + CD_TANGENT*(relative-vn*normal))
    nodal = np.zeros_like(pos)
    for corner in range(3):
        np.add.at(nodal, faces[:,corner], force/3)
    return nodal


def material_config(E):
    kappa = E*FULL_THICKNESS**3/(24*(1-NU**2))
    return {"E_Pa": E, "nu": NU, "density_kg_m3": DENSITY,
            "full_thickness_m": FULL_THICKNESS, "ipc_thickness_radius_m": FULL_THICKNESS/2,
            "areal_density_kg_m2": DENSITY*FULL_THICKNESS,
            "bending_kappa_Nm_derived": kappa, "membrane": "NeoHookeanShell (UID 11)",
            "bending": "DiscreteShellBending (UID 17)",
            "bending_mapping": "kappa = E * h^3 / (24 * (1 - nu^2)); h = 2 * ipc radius"}


def triangle_radial_gap(pos, faces):
    tri = pos[faces,:2]
    edge = np.roll(tri,-1,axis=1)-tri
    t = np.clip(-np.sum(tri*edge,axis=2)/np.maximum(np.sum(edge*edge,axis=2),1e-24),0,1)
    dist2 = np.sum((tri+t[:,:,None]*edge)**2,axis=2).min(axis=1)
    other = np.roll(tri,-1,axis=1)
    crosses = tri[:,:,0]*other[:,:,1]-tri[:,:,1]*other[:,:,0]
    inside = ((crosses>=-1e-15).all(axis=1)|(crosses<=1e-15).all(axis=1))&(np.abs(crosses.sum(axis=1))>1e-14)
    dist2[inside] = 0
    return float(np.sqrt(dist2.min())-POLE_RADIUS)


class FlagWorld:
    def __init__(self, args, young, mesh_path):
        import genesis as gs
        import uipc
        from uipc.constitution import NeoHookeanShell, DiscreteShellBending, ElasticModuli2D, FiniteElementExternalForce
        from uipc.core import FiniteElementStateAccessorFeature
        from genesis.utils.misc import tensor_to_array

        self.gs, self.uipc, self.args, self.young = gs, uipc, args, young
        self.dt = 1/(args.fps*args.steps_per_frame)
        self.t, self.speed = 0.0, 2.0
        self.force_updates = 0
        self.min_clearance, self.max_pin_drift = float("inf"), 0.0
        self.min_triangle_clearance = float("inf")
        self.material = material_config(young)
        self.scene = gs.Scene(
            sim_options=gs.options.SimOptions(dt=self.dt, substeps=1, gravity=(0,0,-9.81)),
            coupler_options=gs.options.IPCCouplerOptions(
                contact_d_hat=.002, contact_resistance=1e8, contact_friction_enable=True,
                newton_max_iterations=128, newton_tolerance=.005,
                linear_system_tolerance=1e-6, newton_semi_implicit_enable=False,
                sanity_check_enable=True,
            ), show_viewer=False,
        )
        self.scene.add_entity(
            morph=gs.morphs.Cylinder(pos=(0,0,POLE_HEIGHT/2),radius=POLE_RADIUS,height=POLE_HEIGHT,
                                    fixed=True,collision=True,visualization=False),
            material=gs.materials.Rigid(needs_coup=True,coup_type="ipc_only",friction=.16),
        )
        self.cloth = self.scene.add_entity(
            morph=gs.morphs.Mesh(file=str(mesh_path.resolve()),decimate=False,convexify=False),
            material=gs.materials.FEM.Cloth(E=young,nu=NU,rho=DENSITY,thickness=FULL_THICKNESS/2,
                                          bending_stiffness=self.material["bending_kappa_Nm_derived"],friction_mu=.16),
        )
        self.coupler = self.scene.sim.coupler
        owner = self

        def register_shell(coupler):
            assert coupler.sim._B == 1
            assert len(coupler.fem_solver.entities) == 1
            ent = coupler.fem_solver.entities[0]
            xyz = tensor_to_array(ent.init_positions).astype(np.float64)
            faces = ent.surface_triangles.astype(np.int32)
            obj = coupler._ipc_objects.create("cloth_0_0")
            mesh = uipc.geometry.trimesh(xyz, faces)
            uipc.geometry.label_surface(mesh)
            contact = coupler._ipc_contact_tabular.create("cloth_contact_0")
            coupler._ipc_cloth_contacts[ent] = contact
            contact.apply_to(mesh)
            membrane, bend, external = NeoHookeanShell(), DiscreteShellBending(), FiniteElementExternalForce()
            for constitution in (membrane, bend, external):
                coupler._ipc_constitution_tabular.insert(constitution)
            membrane.apply_to(mesh,ElasticModuli2D.youngs_poisson(young,NU),DENSITY,FULL_THICKNESS/2)
            # The raw native coefficient avoids the v0.0.29 formula-overload's
            # documented factor-of-two bug, corrected upstream after that tag.
            bend.apply_to(mesh,bending_stiffness=owner.material["bending_kappa_Nm_derived"])
            external.apply_to(mesh,np.zeros(3),enable=True)
            owner.pinned = np.flatnonzero(np.abs(xyz[:,0]-HOIST_X) < 1e-5)
            assert len(owner.pinned) == args.nz
            owner.pin_positions = xyz[owner.pinned].copy()
            uipc.view(mesh.vertices().find(uipc.builtin.is_fixed))[owner.pinned] = 1
            for key, val in (("solver_type","cloth"),("entity_idx","0"),("env_idx","0")):
                mesh.meta().create(key,val)
            slot,rest_slot = obj.geometries().create(mesh)
            owner.mesh_slot, owner.faces, owner.initial = slot, faces, xyz
            owner.pending_force = np.zeros_like(xyz)

            def update_force(info):
                current = info.geo_slots()[0].geometry()
                uipc.view(current.vertices().find("external_force")).reshape(-1,3)[:] = owner.pending_force
                uipc.view(current.vertices().find("external_force/is_constrained"))[:] = 1
                owner.force_updates += 1
            coupler._ipc_animator.insert(obj,update_force)
            owner.native_constitutions = (membrane,bend,external)

        self.coupler._add_fem_entities_to_ipc = types.MethodType(register_shell,self.coupler)
        import genesis.engine.couplers.ipc_coupler.coupler as ipc_module
        original_config_builder = ipc_module.build_ipc_scene_config

        def build_task_config(*values):
            config = original_config_builder(*values)
            config["linear_system"]["fem_preconditioner"] = "mas"
            config["integrator"]["type"] = "bdf1"
            owner.native_scene_config = copy.deepcopy(config)
            return config

        with patch.object(ipc_module,"build_ipc_scene_config",build_task_config):
            self.scene.build()
        self.world = self.coupler._ipc_world
        assert self.world.is_valid(), "IPC world failed initialization"
        self.accessor = self.world.features().find(FiniteElementStateAccessorFeature)
        assert self.accessor is not None, "native FEM state accessor unavailable"
        assert self.accessor.vertex_count() == len(self.initial)
        self.state_geo = self.accessor.create_geometry()
        if self.state_geo.positions() is None:
            self.state_geo.vertices().create(uipc.builtin.position,np.zeros(3))
        if self.state_geo.vertices().find(uipc.builtin.velocity) is None:
            self.state_geo.vertices().create(uipc.builtin.velocity,np.zeros(3))
        self.positions, self.velocities = self.state()
        self.rest_faces = self.faces.copy()
        # Exact initial geometry/faces can be reordered by Genesis's mesh weld.
        self.uvs = np.column_stack(((self.initial[:,0]-HOIST_X)/WIDTH,(self.initial[:,2]-(TOP_Z-HEIGHT))/HEIGHT))
        self.edge_faces = {}
        for f, face in enumerate(self.faces):
            for a,b in ((face[0],face[1]),(face[1],face[2]),(face[2],face[0])):
                self.edge_faces.setdefault(tuple(sorted((int(a),int(b)))),[]).append(f)
        self.adjacent = np.array([p for p in self.edge_faces.values() if len(p)==2],np.int32)
        self.audit()

    def state(self):
        self.accessor.copy_to(self.state_geo)
        p = np.asarray(self.state_geo.positions().view()).reshape(-1,3).copy()
        v = np.asarray(self.uipc.view(self.state_geo.vertices().find(self.uipc.builtin.velocity))).reshape(-1,3).copy()
        return p,v

    def set_state(self,p,v):
        self.state_geo.positions().view().reshape(-1,3)[:] = p
        self.uipc.view(self.state_geo.vertices().find(self.uipc.builtin.velocity)).reshape(-1,3)[:] = v
        self.accessor.copy_from(self.state_geo)
        self.world.retrieve()
        self.positions,self.velocities = self.state()
        assert np.array_equal(self.positions,p) and np.array_equal(self.velocities,v), "checkpoint transfer altered state"
        self.audit()

    def audit(self):
        p = self.positions
        assert np.isfinite(p).all() and np.isfinite(self.velocities).all(), "nonfinite native IPC state"
        active = (p[:,2]>=0)&(p[:,2]<=POLE_HEIGHT)
        gap = np.linalg.norm(p[active,:2],axis=1)-POLE_RADIUS
        self.min_clearance = min(self.min_clearance,float(gap.min()))
        self.min_triangle_clearance = min(self.min_triangle_clearance,triangle_radial_gap(p,self.faces))
        drift = np.linalg.norm(p[self.pinned]-self.pin_positions,axis=1).max()
        self.max_pin_drift = max(self.max_pin_drift,float(drift))
        if not (self.min_clearance > 0 and self.min_triangle_clearance > 0 and self.max_pin_drift < PIN_TOLERANCE_M):
            native_fixed=np.asarray(self.uipc.view(self.mesh_slot.geometry().vertices().find(self.uipc.builtin.is_fixed))).copy()
            np.savez_compressed(self.args.out/"failure_state.npz",positions=p,velocities=self.velocities,
                                pinned=self.pinned,pin_positions=self.pin_positions,native_fixed=native_fixed)
            raise RuntimeError(f"pole/pin audit failed: node_gap={self.min_clearance}, triangle_gap={self.min_triangle_clearance}, "
                               f"pin_drift={self.max_pin_drift}, native_fixed_count={np.count_nonzero(native_fixed)}")

    def step(self,t,speed):
        self.pending_force[:] = triangle_forces(self.positions,self.velocities,self.faces,t,speed)
        self.scene.step()
        assert self.world.is_valid(), "invalid IPC solver state"
        self.positions,self.velocities = self.state()
        self.audit()

    def metrics(self):
        p, v, f = self.positions,self.velocities,self.faces
        tri = p[f]
        normals = np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
        normals /= np.maximum(np.linalg.norm(normals,axis=1)[:,None],1e-12)
        cos = np.sum(normals[self.adjacent[:,0]]*normals[self.adjacent[:,1]],axis=1)
        fly = np.flatnonzero(self.initial[:,0]>HOIST_X+WIDTH-.001)
        return {"fly_edge_mean_x_m":float(p[fly,0].mean()),"fly_edge_mean_z_m":float(p[fly,2].mean()),
                "fold_angle_mean_rad":float(np.arccos(np.clip(cos,-1,1)).mean()),
                "free_rms_speed_m_s":float(np.sqrt(np.mean(np.sum(v*v,axis=1))))}

    def actual_material(self):
        mesh = self.mesh_slot.geometry()
        def span(attrs,name):
            a = np.asarray(self.uipc.view(attrs.find(name)))
            return [float(a.min()),float(a.max())]
        report = dict(self.material)
        report.update({"native_mu_min_max_Pa":span(mesh.triangles(),"mu"),
                       "native_lambda_min_max_Pa":span(mesh.triangles(),"lambda"),
                       "native_kappa_min_max_Nm":span(mesh.edges(),"bending_stiffness"),
                       "native_thickness_radius_min_max_m":span(mesh.vertices(),"thickness")})
        mu = self.young/(2*(1+NU))
        lam = self.young*NU/(1-NU**2)
        assert np.allclose(report["native_mu_min_max_Pa"],mu)
        assert np.allclose(report["native_lambda_min_max_Pa"],lam)
        assert np.allclose(report["native_kappa_min_max_Nm"],self.material["bending_kappa_Nm_derived"])
        return report


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out-dir", "--out",dest="out",type=Path,required=True)
    p.add_argument("--case",default="source",choices=tuple(name for name in CASE_E if name!="wind_drop_at_2s"))
    p.add_argument("--E",type=float,help="Explicit SI override; preset young_stiff defaults to the accepted 100 MPa")
    p.add_argument("--frames",type=int,default=96)
    p.add_argument("--fps",type=int,default=24)
    p.add_argument("--steps-per-frame",type=int,default=8)
    p.add_argument("--settle-seconds",type=float,default=3)
    p.add_argument("--nx",type=int,default=61)
    p.add_argument("--nz",type=int,default=41)
    p.add_argument("--checkpoint",type=Path)
    p.add_argument("--from-rest",action="store_true",help="Explicitly generate a new warm state instead of reusing the frozen source initial condition")
    p.add_argument("--ipc-deps",type=Path,default=RUNTIME_DEPS)
    p.add_argument("--scenario-overrides-json",type=Path)
    p.add_argument("--emit-timed-branch",action="store_true")
    p.add_argument("--timed-branch-out",type=Path)
    args = p.parse_args()
    if args.E is None:
        args.E = CASE_E.get(args.case, 1e6)
    reference_speed = CASE_WIND_SPEED[args.case]
    if not np.isfinite(args.E) or args.E <= 0:
        p.error("E must be finite and positive")
    if args.from_rest and args.checkpoint:
        p.error("--from-rest and --checkpoint are mutually exclusive")
    if args.emit_timed_branch and (args.case != "source" or args.frames < 49 or args.fps != 24):
        p.error("native timed continuation requires source, 24 fps and at least 49 samples")
    if args.scenario_overrides_json:
        from edit_vocab import plans
        expected = next(item["physics_override"] for item in plans() if item["native_case"] == args.case)
        actual = json.loads(args.scenario_overrides_json.read_text())["physics"]
        if actual != expected or args.E != CASE_E[args.case]:
            p.error("scenario overrides do not match this frozen preset")
    if not args.from_rest and args.checkpoint is None:
        args.checkpoint = ASSETS / "initial_state.npz"
    if args.checkpoint and not args.checkpoint.is_file():
        p.error(f"Missing frozen initial state; set --checkpoint or provision {ASSETS}")
    if args.out.exists() and any(args.out.iterdir()):
        raise RuntimeError(f"Refusing to overwrite simulation output: {args.out}")
    if args.ipc_deps.is_dir():
        sys.path.insert(0,str(args.ipc_deps.resolve()))
    args.out.mkdir(parents=True,exist_ok=True)
    start = time.monotonic()
    import genesis as gs
    gs.init(backend=gs.gpu,precision="32",seed=4090,logging_level="warning")
    xyz,faces,uv = rest_mesh(args.nx,args.nz)
    mesh_path = args.out/"flag_rest.obj"
    write_obj(mesh_path,xyz,faces,uv)
    flag = FlagWorld(args,args.E,mesh_path)
    dt = flag.dt
    build_seconds = time.monotonic()-start
    print("BUILT",json.dumps(flag.actual_material()),flush=True)
    if args.checkpoint:
        common = np.load(args.checkpoint)
        assert np.array_equal(common["rest_positions"],flag.initial)
        assert np.array_equal(common["faces"],flag.faces)
        flag.set_state(common["positions"],common["velocities"])
    else:
        for i in range(round(args.settle_seconds/dt)):
            flag.step(i*dt,2.)
            if (i+1)%args.fps == 0:
                print("SETTLE",round((i+1)*dt,3),flag.metrics(),flush=True)
    pos0,vel0 = flag.state()
    np.savez_compressed(args.out/"initial_state.npz",positions=pos0,velocities=vel0,
                        rest_positions=flag.initial,faces=flag.faces)
    positions,velocities,measurements = [],[],[]
    frame_at_2s = None
    audit_at_2s = None
    for frame in range(args.frames):
        t = frame/args.fps
        if frame:
            for sub in range(args.steps_per_frame):
                t_start = (frame-1)/args.fps+sub*dt
                flag.step(args.settle_seconds+t_start,reference_speed)
        positions.append(flag.positions.copy())
        velocities.append(flag.velocities.copy())
        measurements.append({"t_s":t,"wind_reference_speed_m_s":reference_speed,**flag.metrics()})
        if frame%12==0 or frame==args.frames-1:
            print(args.case,frame+1,measurements[-1],flush=True)
        if frame==48:
            np.savez_compressed(args.out/"state_at_2s.npz",positions=flag.positions,velocities=flag.velocities,
                                rest_positions=flag.initial,faces=flag.faces)
            if args.emit_timed_branch:
                assert flag.world.dump(), "Native IPC checkpoint dump failed"
                frame_at_2s = flag.world.frame()
                audit_at_2s = (flag.min_clearance,flag.min_triangle_clearance,flag.max_pin_drift)
    positions,velocities = np.array(positions),np.array(velocities)
    np.savez_compressed(args.out/"genesis_flag_cache.npz",vertices=positions.astype(np.float32),faces=flag.faces,
                        uvs=flag.uvs.astype(np.float32),physical_positions=positions,physical_velocities=velocities,
                        physical_faces=flag.faces,pinned=flag.pinned,rest_positions=flag.initial,fps=args.fps)
    config = {"case":args.case,"physics":{"material":flag.actual_material(),
              "air":{"reference_speed_m_s":reference_speed,
                     "event_at_2s_m_s":None,
                     "model":"one-way prescribed relative-air triangle drag", "rho_kg_m3":AIR_RHO,
                     "normal_Cd":CD_NORMAL,"tangential_Cd":CD_TANGENT},
              "pole_collision_proxy_radius_m":POLE_RADIUS,"pole_visual_radius_m":VISUAL_POLE_RADIUS,
              "pole_height_m":POLE_HEIGHT,"hoist_x_m":HOIST_X,
              "flag_geometry":{"width_m":WIDTH,"height_m":HEIGHT,"top_z_m":TOP_Z}},
              "quality":{"solver":"Genesis FEM + native IPC NeoHookeanShell / DiscreteShellBending",
                         "dt_s":dt,"steps_per_frame":args.steps_per_frame,"nx":args.nx,"nz":args.nz,
                         "frames":args.frames,"fps":args.fps,"source_settle_seconds":args.settle_seconds,
                         "newton_max_iter":128,"newton_velocity_tol":.005,"linear_tol":1e-6,
                         "pin_audit_tolerance_m":PIN_TOLERANCE_M,
                         "contact_d_hat_m":.002,"contact_resistance":1e8,"semi_implicit":False,
                         "native_ipc_scene_config":flag.native_scene_config},
              "runtime":{"genesis":gs.__version__,"pyuipc":importlib.metadata.version("pyuipc")},
              "initial_state_sha256":hashlib.sha256(pos0.tobytes()+vel0.tobytes()).hexdigest()}
    save_json(args.out/"resolved_config.json",config)
    save_json(args.out/"simulation_report.json",{"config":config,"measurements":measurements,
              "min_all_step_particle_pole_gap_m":flag.min_clearance,"max_all_step_pin_drift_m":flag.max_pin_drift,
              "min_all_step_triangle_pole_proxy_gap_m":flag.min_triangle_clearance,
              "native_force_callback_count":flag.force_updates,"build_wall_seconds":build_seconds,
              "total_wall_seconds":time.monotonic()-start})
    print("COMPLETE",args.case,round(time.monotonic()-start,2),flush=True)
    if args.emit_timed_branch:
        assert args.case=="source" and frame_at_2s is not None
        flag.world.recover(frame_at_2s)
        flag.world.retrieve()
        flag.positions,flag.velocities = flag.state()
        assert flag.world.frame()==frame_at_2s
        assert np.array_equal(flag.positions,positions[48])
        assert np.array_equal(flag.velocities,velocities[48])
        flag.min_clearance,flag.min_triangle_clearance,flag.max_pin_drift = audit_at_2s
        branch_positions,branch_velocities = list(positions[:49].copy()),list(velocities[:49].copy())
        branch_measurements = copy.deepcopy(measurements[:49])
        for frame in range(49,args.frames):
            for sub in range(args.steps_per_frame):
                t_start = (frame-1)/args.fps+sub*dt
                flag.step(args.settle_seconds+t_start,.5)
            branch_positions.append(flag.positions.copy())
            branch_velocities.append(flag.velocities.copy())
            branch_measurements.append({"t_s":frame/args.fps,"wind_reference_speed_m_s":.5,**flag.metrics()})
            if frame%12==0 or frame==args.frames-1:
                print("wind_drop_at_2s",frame+1,branch_measurements[-1],flush=True)
        branch_positions,branch_velocities = np.array(branch_positions),np.array(branch_velocities)
        assert np.array_equal(branch_positions[:49],positions[:49])
        assert np.array_equal(branch_velocities[:49],velocities[:49])
        out = args.timed_branch_out or args.out.parent/"wind_drop_at_2s"
        if out.exists() and any(out.iterdir()):
            raise RuntimeError(f"Refusing to overwrite timed branch: {out}")
        out.mkdir(parents=True,exist_ok=True)
        np.savez_compressed(out/"genesis_flag_cache.npz",vertices=branch_positions.astype(np.float32),faces=flag.faces,
                            uvs=flag.uvs.astype(np.float32),physical_positions=branch_positions,
                            physical_velocities=branch_velocities,physical_faces=flag.faces,pinned=flag.pinned,
                            rest_positions=flag.initial,fps=args.fps)
        branch_config = copy.deepcopy(config)
        branch_config["case"] = "wind_drop_at_2s"
        branch_config["physics"]["air"]["event_at_2s_m_s"] = .5
        save_json(out/"resolved_config.json",branch_config)
        save_json(out/"simulation_report.json",{"config":branch_config,"measurements":branch_measurements,
                  "min_all_step_particle_pole_gap_m":flag.min_clearance,"max_all_step_pin_drift_m":flag.max_pin_drift,
                  "min_all_step_triangle_pole_proxy_gap_m":flag.min_triangle_clearance,
                  "prefix_through_2s_positions_and_velocities_bitwise_identical":True,
                  "continuation_method":"Native IPC World.dump/recover; all backend state restored at source t=2 s",
                  "native_checkpoint_frame":frame_at_2s,"total_wall_seconds":time.monotonic()-start})
        print("COMPLETE wind_drop_at_2s",round(time.monotonic()-start,2),flush=True)


if __name__=="__main__":
    main()
