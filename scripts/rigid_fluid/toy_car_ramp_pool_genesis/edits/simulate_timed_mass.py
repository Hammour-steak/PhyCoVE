"""Genesis 1.4.3 rigid-car + DFSPH shallow-pool simulation.

The orange track, pool floor and closed measured pool shell are fixed Genesis rigid
bodies.  The toy car is a free rigid cuboid with the measured mass and size.
Water is Genesis DFSPH and uses the native two-way rigid/SPH coupler, including
the pressure-force patch present in the project's Genesis environment.
"""

from __future__ import annotations

import argparse
import json
import math
import threading
import time
import hashlib
import importlib.metadata
from pathlib import Path

import numpy as np

FPS = 24
SEED = 20261021
GRAVITY = 9.81

CAR_SIZE = np.array((0.160, 0.071, 0.055), dtype=np.float64)
CAR_MASS = 0.420
CAR_DENSITY = CAR_MASS / float(np.prod(CAR_SIZE))
RAMP_ANGLE_DEG = 18.0
RAMP_START_X = -1.00
RAMP_END_X = -0.20
RAMP_DECK_CENTER_END_Z = 0.217
RAMP_WIDTH = 0.205
RAMP_THICKNESS = 0.008

DOMAIN_LOWER = (-0.25, -0.44, 0.0)
DOMAIN_UPPER = (1.31, 0.44, 0.52)
WATER_XY_CENTER = (0.54, 0.0)
WATER_XY_SIZE = (1.28, 0.60)
WATER_BOTTOM = 0.030


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=("settle", "run"))
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--water-state", type=Path)
    parser.add_argument("--frames", type=int, default=96)
    parser.add_argument("--dx", type=float, default=0.010)
    parser.add_argument("--steps-per-frame", type=int, default=8)
    parser.add_argument("--substeps", type=int, default=4)
    parser.add_argument("--settle-frames", type=int, default=24)
    parser.add_argument("--fluid-damping", type=float, default=0.985)
    parser.add_argument("--preview-frames", type=int, default=0)
    parser.add_argument("--water-height", type=float, default=0.090)
    parser.add_argument("--basin-collider",type=Path,required=True)
    parser.add_argument("--initial-volume",type=Path,required=True)
    parser.add_argument("--basin-profile",type=Path,required=True)
    parser.add_argument("--floor-projection",action='store_true')
    parser.add_argument("--wall-projection",action='store_true')
    parser.add_argument('--car-mass',type=float,default=.420)
    parser.add_argument('--water-density',type=float,default=998.)
    parser.add_argument('--water-viscosity',type=float,default=1.004e-6)
    parser.add_argument('--no-car',action='store_true')
    parser.add_argument('--no-water',action='store_true',help='Leave the water out (DELETE water): an empty pool')
    parser.add_argument('--mass-change-time',type=float)
    parser.add_argument('--mass-multiplier',type=int,default=3)
    return parser.parse_args()


def save_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2) + "\n")
    tmp.replace(path)


def ramp_center():
    angle = math.radians(RAMP_ANGLE_DEG)
    length = (RAMP_END_X - RAMP_START_X) / math.cos(angle)
    x = 0.5 * (RAMP_START_X + RAMP_END_X)
    z = RAMP_DECK_CENTER_END_Z + (RAMP_END_X - x) * math.tan(angle)
    return (x, 0.0, z), (length, RAMP_WIDTH, RAMP_THICKNESS)


def ramp_surface_z(x):
    angle = math.radians(RAMP_ANGLE_DEG)
    return RAMP_DECK_CENTER_END_Z + (RAMP_END_X - x) * math.tan(angle) + 0.5 * RAMP_THICKNESS / math.cos(angle)


def add_fixed_box(scene, gs, name, center, size, friction, coupling=True):
    entity = scene.add_entity(
        morph=gs.morphs.Box(pos=center, size=size, fixed=True, visualization=False),
        material=gs.materials.Rigid(
            rho=900.0,
            friction=friction,
            needs_coup=coupling,
            coup_friction=0.10,
            coup_softness=0.004,
            coup_restitution=0.0,
            sdf_cell_size=0.004,
            sdf_min_res=24,
            sdf_max_res=96,
        ),
    )
    return entity


def build_scene(args, car_fixed):
    import genesis as gs

    gs.init(backend=gs.cuda, precision="32", seed=SEED, logging_level="warning")
    step_dt = 1.0 / (FPS * args.steps_per_frame)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(
            dt=step_dt,
            substeps=args.substeps,
            gravity=(0.0, 0.0, -GRAVITY),
            floor_height=-0.10,
            requires_grad=False,
        ),
        rigid_options=gs.options.RigidOptions(
            dt=step_dt / args.substeps,
            enable_collision=True,
            enable_joint_limit=True,
        ),
        sph_options=gs.options.SPHOptions(
            particle_size=args.dx,
            pressure_solver="DFSPH",
            lower_bound=DOMAIN_LOWER,
            upper_bound=DOMAIN_UPPER,
            max_divergence_error=0.1,
            max_density_error_percent=0.05,
        ),
        coupler_options=gs.options.LegacyCouplerOptions(
            rigid_mpm=False,
            rigid_sph=True,
            rigid_pbd=False,
            rigid_fem=False,
            mpm_sph=False,
            mpm_pbd=False,
            fem_mpm=False,
            fem_sph=False,
        ),
        show_viewer=False,
    )

    # Closed pool collision tub.  Boxes overlap at the corners so neither the
    # shallow water nor the car can escape through a numerical seam.
    add_fixed_box(scene, gs, "pool_bottom", (0.53, 0.0, 0.015), (1.56, 0.88, 0.03), 0.45)
    # Use the closed, non-convex authoring mesh so the corners and three rings
    # participate in physical coupling, as well as in final render containment.
    scene.add_entity(
        morph=gs.morphs.Mesh(file=str(args.basin_collider.resolve()),fixed=True,
            convexify=False,decimate=False,watertighten=None,align=False,visualization=False),
        material=gs.materials.Rigid(rho=900.,friction=.45,needs_coup=True,
            coup_friction=.10,coup_softness=.004,coup_restitution=0.,
            sdf_cell_size=.004,sdf_min_res=24,sdf_max_res=384))

    rc, rs = ramp_center()
    ramp = scene.add_entity(
        morph=gs.morphs.Box(pos=rc, size=rs, euler=(0.0, RAMP_ANGLE_DEG, 0.0), fixed=True, visualization=False),
        material=gs.materials.Rigid(
            rho=900.0,
            friction=0.07,
            needs_coup=False,
            coup_friction=0.0,
            coup_softness=0.002,
            sdf_cell_size=0.003,
            sdf_min_res=24,
            sdf_max_res=96,
        ),
    )

    angle = math.radians(RAMP_ANGLE_DEG)
    contact_x = -0.94
    surface = np.array((contact_x, 0.0, ramp_surface_z(contact_x)), dtype=np.float64)
    normal = np.array((math.sin(angle), 0.0, math.cos(angle)), dtype=np.float64)
    car_center = surface + normal * (0.5 * CAR_SIZE[2] + 0.001)
    car = None if args.no_car else scene.add_entity(
        morph=gs.morphs.Box(
            pos=tuple(car_center),
            size=tuple(CAR_SIZE),
            euler=(0.0, RAMP_ANGLE_DEG, 0.0),
            fixed=car_fixed,
            visualization=False,
        ),
        material=gs.materials.Rigid(
            rho=CAR_DENSITY,
            friction=0.10,
            friction_rolling=0.0003,
            friction_torsional=0.001,
            needs_coup=not car_fixed,
            coup_friction=0.10,
            coup_softness=0.003,
            coup_restitution=0.0,
            sdf_cell_size=0.003,
            sdf_min_res=28,
            sdf_max_res=96,
        ),
    )

    if not 0.03 <= args.water_height <= 0.17:
        raise ValueError("--water-height must be between 0.03 and 0.17 m")
    water_center = (*WATER_XY_CENTER, WATER_BOTTOM + 0.5 * args.water_height)
    water_size = (*WATER_XY_SIZE, args.water_height)
    import trimesh
    fill_bounds=trimesh.load(args.initial_volume,process=False).bounds
    water_center=tuple((fill_bounds[0]+fill_bounds[1])/2)
    water_size=tuple(fill_bounds[1]-fill_bounds[0])
    water = None if args.no_water else scene.add_entity(
        morph=gs.morphs.Mesh(file=str(args.initial_volume.resolve()),convexify=False,
            decimate=False,align=False),
        material=gs.materials.SPH.Liquid(rho=args.water_density, mu=args.water_viscosity, gamma=0.0, sampler="regular"),
        surface=gs.surfaces.Default(color=(0.2, 0.6, 1.0, 1.0), vis_mode="particle"),
    )
    tick = time.monotonic()
    scene.build(n_envs=0)
    material_runtime={'car_present':car is not None,
        'car_mass_kg':float(car.get_mass().sum().item()) if car is not None else None,
        'water_rho_min_max':[], 'water_nu_min_max':[]}
    if water is not None:
        for key,field in [('water_rho_min_max',water._solver.particles_info.rho),('water_nu_min_max',water._solver.particles_info.mu)]:
            values=field.to_numpy();material_runtime[key]=[float(values.min()),float(values.max())]
        assert np.allclose(material_runtime['water_rho_min_max'],args.water_density,rtol=1e-5)
        assert np.allclose(material_runtime['water_nu_min_max'],args.water_viscosity,rtol=1e-5)
    if car is not None:assert math.isclose(material_runtime['car_mass_kg'],CAR_MASS,rel_tol=1e-4)
    config=actual_configuration(args);config['runtime_materials']=material_runtime
    save_json(args.out/'actual_configuration.json',config)
    return gs, scene, car, water, time.monotonic() - tick, car_center, water_center, water_size


def particle_state(entity):
    if entity is None:
        return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.float32)
    pos = entity.get_particles_pos().cpu().numpy().reshape(-1, 3).astype(np.float32)
    vel = entity.get_particles_vel().cpu().numpy().reshape(-1, 3).astype(np.float32)
    return pos, vel

def step_with_boundary(scene,water,args):
    scene.step()
    if water is not None and (args.floor_projection or args.wall_projection):
        # Fixed-floor nonpenetration: native velocity coupling alone permits a
        # small cumulative gravity-step penetration while resting on the floor.
        pos=water.get_particles_pos();vel=water.get_particles_vel()
        import torch
        below=pos[...,2]<(WATER_BOTTOM+.5*args.dx)
        changed=False
        if args.floor_projection and below.any().item():
            pos[...,2]=pos[...,2].clamp(min=WATER_BOTTOM+.5*args.dx)
            vel[...,2]=torch.where(below,vel[...,2].clamp(min=0),vel[...,2]);changed=True
        if args.wall_projection:
            if not hasattr(args,'_profile_tensors'):
                with np.load(args.basin_profile) as pr:
                    args._profile_tensors=(torch.as_tensor(pr['z'],device=pos.device,dtype=pos.dtype),
                        torch.as_tensor(pr['radius'],device=pos.device,dtype=pos.dtype),
                        torch.as_tensor(pr['center_xy'],device=pos.device,dtype=pos.dtype),float(pr['lip_z']))
            z,r,center,lip=args._profile_tensors;p=pos.reshape(-1,3);v=vel.reshape(-1,3)
            xy=p[:,:2]-center;rho=torch.linalg.vector_norm(xy,dim=1);angle=torch.remainder(torch.atan2(xy[:,1],xy[:,0]),2*math.pi)
            af=angle/(2*math.pi)*r.shape[1];raw_ai=torch.floor(af).long();aw=af-raw_ai;ai=raw_ai%r.shape[1];aj=(ai+1)%r.shape[1]
            zi=torch.clamp(torch.searchsorted(z,p[:,2].contiguous(),right=True)-1,0,len(z)-2)
            zw=torch.clamp((p[:,2]-z[zi])/(z[zi+1]-z[zi]),0,1)
            r0=r[zi,ai]*(1-aw)+r[zi,aj]*aw;r1=r[zi+1,ai]*(1-aw)+r[zi+1,aj]*aw
            allowed=r0*(1-zw)+r1*zw-.002
            outside=(rho>allowed)&(p[:,2]<lip-.004)
            if outside.any().item():
                er=xy/torch.clamp(rho[:,None],min=1e-8);et=torch.stack((-er[:,1],er[:,0]),dim=1)
                rt=((r[zi,aj]-r[zi,ai])*(1-zw)+(r[zi+1,aj]-r[zi+1,ai])*zw)/(2*math.pi/r.shape[1])
                rz=(r1-r0)/(z[zi+1]-z[zi])
                normal=torch.cat((er-et*(rt/torch.clamp(rho,min=1e-8))[:,None],-rz[:,None]),dim=1)
                normal=normal/torch.clamp(torch.linalg.vector_norm(normal,dim=1)[:,None],min=1e-8)
                p[outside,:2]=center+er[outside]*allowed[outside,None]
                outward=torch.clamp((v*normal).sum(1),min=0)
                v[outside]-=normal[outside]*outward[outside,None];changed=True
        if changed:water.set_particles_pos(pos);water.set_particles_vel(vel)

def boundary_metrics(pos,args):
    with np.load(args.basin_profile) as profile:
        z=profile['z'];r=profile['radius'];cx,cy=profile['center_xy'];lip=float(profile['lip_z'])
    xy=pos[:,:2]-np.array([cx,cy]);angle=np.mod(np.arctan2(xy[:,1],xy[:,0]),2*np.pi)
    af=angle/(2*np.pi)*r.shape[1];raw_ai=np.floor(af).astype(int);aw=af-raw_ai;ai=raw_ai%r.shape[1];aj=(ai+1)%r.shape[1]
    zi=np.clip(np.searchsorted(z,pos[:,2],side='right')-1,0,len(z)-2)
    zw=np.clip((pos[:,2]-z[zi])/(z[zi+1]-z[zi]),0,1)
    r0=r[zi,ai]*(1-aw)+r[zi,aj]*aw;r1=r[zi+1,ai]*(1-aw)+r[zi+1,aj]*aw
    excess=np.linalg.norm(xy,axis=1)-(r0*(1-zw)+r1*zw)
    submerged=pos[:,2]<lip-.012
    leak=submerged&(excess>.010)
    return {'below_rim_outside_10mm_count':int(leak.sum()),
        'below_rim_max_excess_m':float(max(0.,excess[submerged].max())) if submerged.any() else 0.,
        'outside_count_fraction':float(leak.mean())}

def actual_configuration(args):
    package=Path(__import__('genesis').__file__).parent
    coupler=package/'engine/couplers/legacy_coupler.py'
    return {'physics':{'car_mass_kg':CAR_MASS,'car_size_m':CAR_SIZE.tolist(),
        'car_present':not args.no_car,**({'water_present':False} if args.no_water else {}),'water_density_kg_m3':args.water_density,'water_kinematic_viscosity_m2_s':args.water_viscosity,
        'mass_event':None if args.mass_change_time is None else {
            'time_s':args.mass_change_time,'multiplier':args.mass_multiplier,
            'initial_mass_kg':CAR_MASS,'final_mass_kg':CAR_MASS*args.mass_multiplier,
            'inertia_multiplier':args.mass_multiplier,'instantaneous_velocity_policy':'continuous',
            'implementation':'RigidEntity.set_mass; scales mass and inertia together'},
        'gravity_m_s2':GRAVITY,'initial_fill_height_m':args.water_height,
        'ramp_angle_degrees':RAMP_ANGLE_DEG,'ramp_friction':.07,'car_friction':.10},
      'simulation_quality':{'dx_m':args.dx,'steps_per_frame':args.steps_per_frame,'substeps':args.substeps,
        'dt_step_s':1/(FPS*args.steps_per_frame),'dt_substep_s':1/(FPS*args.steps_per_frame*args.substeps),
        'basin_sdf_cell_m':.004,'basin_sdf_max_res':384,'settle_frames':args.settle_frames},
      'boundary':{'collider':str(args.basin_collider.resolve()),'initial_volume':str(args.initial_volume.resolve()),
        'collider_sha256':hashlib.sha256(args.basin_collider.read_bytes()).hexdigest(),
        'initial_volume_sha256':hashlib.sha256(args.initial_volume.read_bytes()).hexdigest(),
        'pool_mesh_convexification':False,'original_bottom_box_retained':True,
        'fixed_floor_particle_projection':args.floor_projection,'floor_particle_center_min_z_m':WATER_BOTTOM+.5*args.dx,
        'fixed_wall_particle_projection':args.wall_projection,'wall_particle_center_inset_m':.002},
      'runtime':{'genesis_version':importlib.metadata.version('genesis-world'),
        'pressure_coupler_source':str(coupler)}}


def rigid_state(car):
    if car is None:
        # Compatibility placeholder only; the scene contains no car entity.
        return np.array([-10.,-10.,-10.]),np.array([1.,0.,0.,0.]),np.zeros(3),np.zeros(3)
    pos = car.get_pos().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    quat = car.get_quat().cpu().numpy().reshape(-1, 4)[0].astype(np.float64)
    vel = car.get_vel().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    ang = car.get_ang().cpu().numpy().reshape(-1, 3)[0].astype(np.float64)
    return pos, quat, vel, ang


def inertial_snapshot(car):
    pos,quat,vel,ang=rigid_state(car)
    return {'mass_kg':float(car.get_mass().item()),
        'inertia_kg_m2':car.get_links_inertia().cpu().numpy().tolist(),
        'inverse_weights':car.get_links_invweight().cpu().numpy().tolist(),
        'mass_matrix':car.get_mass_mat().cpu().numpy().tolist(),
        'dofs_velocity':car.get_dofs_velocity().cpu().numpy().tolist(),
        'pos':pos.tolist(),'quat_wxyz':quat.tolist(),'vel':vel.tolist(),'ang':ang.tolist()}


def apply_mass_event(car,args,step_index):
    before=inertial_snapshot(car)
    car.set_mass(CAR_MASS*args.mass_multiplier)
    after=inertial_snapshot(car)
    diagnostic={'before':before,'after':after,'max_abs_delta':{key:float(np.max(np.abs(np.array(after[key])-before[key]))) for key in ('pos','quat_wxyz','vel','ang','dofs_velocity')}}
    save_json(args.out/'mass_event_diagnostic.json',diagnostic)
    assert math.isclose(after['mass_kg'],CAR_MASS*args.mass_multiplier,rel_tol=1e-5)
    for key in ('inertia_kg_m2','mass_matrix'):
        assert np.allclose(after[key],np.array(before[key])*args.mass_multiplier,rtol=1e-4,atol=1e-8),(key,before[key],after[key])
    assert np.allclose(after['inverse_weights'],np.array(before['inverse_weights'])/args.mass_multiplier,rtol=1e-4,atol=1e-7)
    assert np.array_equal(before['dofs_velocity'],after['dofs_velocity']),'Generalized velocity changed during property edit'
    for key in ('pos','quat_wxyz','vel','ang'):
        assert np.allclose(before[key],after[key],rtol=0,atol=1e-6),('Discontinuous property edit',key,diagnostic)
    result={'time_s':step_index/(FPS*args.steps_per_frame),'integration_step':step_index,
        'multiplier':args.mass_multiplier,'before':before,'after':after,
        'mass_inertia_and_inverse_weights_verified':True,'pose_and_velocity_continuous':True,
        'continuity_absolute_tolerance':1e-6,'continuity_max_abs_delta':diagnostic['max_abs_delta']}
    print('MASS_EVENT',json.dumps(result),flush=True)
    save_json(args.out/'mass_event.json',result)
    return result


def settle(args):
    args.out.mkdir(parents=True, exist_ok=False)
    save_json(args.out/'actual_configuration.json',actual_configuration(args))
    gs, scene, car, water, build_seconds, car_center, water_center, water_size = build_scene(args, car_fixed=True)
    if args.water_state:
        with np.load(args.water_state) as state:
            water.set_particles_pos(state['water_pos']);water.set_particles_vel(state['water_vel'])
    init_pos,_=particle_state(water)
    print('INITIAL_SEED',json.dumps({'particles':len(init_pos),'bounds':[init_pos.min(0).tolist(),init_pos.max(0).tolist()]}),flush=True)
    samples = []
    for frame in range(1, args.settle_frames + 1):
        for _ in range(args.steps_per_frame):
            step_with_boundary(scene,water,args)
        pos, vel = particle_state(water)
        vel *= args.fluid_damping
        water.set_particles_vel(vel)
        speed = np.linalg.norm(vel, axis=1)
        if frame == 1 or frame % 6 == 0 or frame == args.settle_frames:
            row = {"frame": frame, "max_speed": float(speed.max()), "p99_speed": float(np.percentile(speed, 99)),
                   "z_p99_5":float(np.percentile(pos[:,2],99.5)),
                   "z_min": float(pos[:, 2].min()), "z_max": float(pos[:, 2].max())}
            samples.append(row)
            row.update(boundary_metrics(pos,args))
            print("SETTLE", json.dumps(row), flush=True)
    pos, vel = particle_state(water)
    np.savez_compressed(
        args.out / "water_state.npz",
        water_pos=pos,
        water_vel=np.zeros_like(vel),
        dx=args.dx,
        water_height=args.water_height,
    )
    report = {"solver": "Genesis 1.4.3 native rigid + DFSPH", "mode": "settle", "build_seconds": build_seconds,
              "water_particles": len(pos), "car_center": car_center.tolist(),
              "water_initial_center_m": list(water_center), "water_initial_size_m": list(water_size),
              "samples": samples}
    save_json(args.out / "settle_report.json", report)


def run(args):
    if args.water_state is None and not args.no_water:
        raise ValueError("--water-state is required for run mode")
    args.out.mkdir(parents=True, exist_ok=False)
    save_json(args.out/'actual_configuration.json',actual_configuration(args))
    (args.out / "particles").mkdir()
    gs, scene, car, water, build_seconds, car_center, water_center, water_size = build_scene(args, car_fixed=False)
    if water is not None:
        with np.load(args.water_state) as state:
            if not math.isclose(float(state["dx"]), args.dx):
                raise ValueError("water state particle spacing mismatch")
            if "water_height" in state and not math.isclose(float(state["water_height"]), args.water_height):
                raise ValueError("water state height mismatch")
            water.set_particles_pos(state["water_pos"])
            water.set_particles_vel(state["water_vel"])
    frames = min(args.frames, args.preview_frames) if args.preview_frames else args.frames
    rows = []
    writer = None
    step_index=0
    event=None
    event_step=None if args.mass_change_time is None else round(args.mass_change_time*FPS*args.steps_per_frame)
    started = time.monotonic()
    for frame in range(1, frames + 1):
        tick = time.monotonic()
        if frame > 1:
            for _ in range(args.steps_per_frame):
                if event_step is not None and step_index==event_step and event is None:
                    event=apply_mass_event(car,args,step_index)
                step_with_boundary(scene,water,args)
                step_index+=1
        # At t=2.00, switch properties after reaching that instant and before
        # integrating beyond it. Frame 49 has the continuous state and new mass.
        if event_step is not None and step_index==event_step and event is None:
            event=apply_mass_event(car,args,step_index)
        pos, vel = particle_state(water)
        cpos, quat, cvel, cang = rigid_state(car)
        mass_kg=float(car.get_mass().item()) if car is not None else 0.
        if writer is not None:
            writer.join()
        target = args.out / "particles" / f"frame_{frame:04d}.npz"
        writer = threading.Thread(
            target=np.savez_compressed,
            args=(target,),
            kwargs={"water_pos": pos, "water_vel": vel.astype(np.float16), "car_pos": cpos,
                    "car_quat_wxyz": quat, "car_vel": cvel, "car_ang": cang,"car_present":not args.no_car,
                    'car_mass_kg':mass_kg,'mass_event_applied':event is not None},
        )
        writer.start()
        speed = np.linalg.norm(vel, axis=1)
        row = {"frame": frame, "time_s": (frame - 1) / FPS, "car_mass_kg":mass_kg,"mass_event_applied":event is not None,"car_pos": cpos.tolist(),
               "car_quat_wxyz": quat.tolist(), "car_vel": cvel.tolist(), "car_ang": cang.tolist(),
               "water_z_max": float(pos[:, 2].max()) if len(pos) else None, "water_speed_max": float(speed.max()) if len(pos) else None,
               "water_speed_p99": float(np.percentile(speed, 99)) if len(pos) else None, "compute_seconds": time.monotonic() - tick}
        rows.append(row)
        if len(pos):
            row.update(boundary_metrics(pos,args))
        if frame == 1 or frame % 4 == 0:
            print("FRAME", frame, "car", np.round(cpos, 4).tolist(), "v", np.round(cvel, 3).tolist(),
                  "water zmax", None if row["water_z_max"] is None else round(row["water_z_max"], 4), flush=True)
        if not np.isfinite(pos).all() or not np.isfinite(cpos).all():
            raise RuntimeError("non-finite Genesis state")
    if writer is not None:
        writer.join()
    report = {
        "status": "complete",
        "solver": "Genesis 1.4.3 native rigid body + DFSPH liquid with two-way rigid_sph coupling",
        "coupling": "Genesis native two-way rigid/SPH momentum transfer and pressure buoyancy",
        "physics": {"car_mass_kg": CAR_MASS,"mass_event":actual_configuration(args)['physics']['mass_event'], "car_size_m": CAR_SIZE.tolist(), "car_present": not args.no_car,**({"water_present": False} if args.no_water else {}),"water_density_kg_m3": args.water_density,
                    "water_kinematic_viscosity_m2_s": args.water_viscosity, "gravity_m_s2": GRAVITY},
        "numerics": {"fps": FPS, "frames": frames, "dx_m": args.dx, "steps_per_frame": args.steps_per_frame,
                     "substeps_per_step": args.substeps},
        "build_seconds": build_seconds,
        "simulation_seconds": time.monotonic() - started,
        "water_particles": int(len(pos)),
        "water_initial_center_m": list(water_center),
        "water_initial_size_m": list(water_size),
        "water_initial_geometry":"Measured three-dimensional basin fill, replacing rectangular seed volume",
        "actual_configuration":actual_configuration(args),
        "initial_car_center": car_center.tolist(),
        "frames": rows,
        "mass_event":event,
    }
    if event_step is not None:
        assert event is not None,'Requested mass event outside simulation duration'
        assert event['time_s']==args.mass_change_time
    save_json(args.out / "simulation_report.json", report)
    print("GENESIS_DONE", json.dumps({"frames": frames, "seconds": report["simulation_seconds"]}), flush=True)


def main():
    args = parse_args()
    global CAR_MASS,CAR_DENSITY
    CAR_MASS=args.car_mass;CAR_DENSITY=CAR_MASS/float(np.prod(CAR_SIZE))
    assert CAR_MASS>0 and args.water_density>0 and args.water_viscosity>0
    if args.mass_change_time is not None:
        assert args.mode=='run' and not args.no_car
        assert args.mass_change_time>0 and args.mass_multiplier>=2
        assert math.isclose(args.mass_change_time*FPS*args.steps_per_frame,round(args.mass_change_time*FPS*args.steps_per_frame),abs_tol=1e-9)
    stable_dt=.01*(2*args.dx)**2/args.water_viscosity
    actual_dt=1/(FPS*args.steps_per_frame*args.substeps)
    assert actual_dt<=stable_dt,('Explicit viscosity time step too large',actual_dt,stable_dt)
    if args.mode == "settle":
        settle(args)
    else:
        run(args)


if __name__ == "__main__":
    main()
