"""Finite honey reservoir draining from a spoon fixed at a slight 15-degree tilt."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
import time
from pathlib import Path

import numpy as np
from spoon_reservoir_geometry import (
    SPOON_CENTER, BOWL_RX, BOWL_RY, BOWL_DEPTH, INITIAL_TILT,
    bowl_mesh, initial_reservoir, rotation_y, tilt_at,
)

FPS = 24
TOAST_CENTER = np.array((0.095, 0, 0.786))
TOAST_SIZE = np.array((0.130, 0.105, 0.022))
LOWER = np.array((-0.16,-0.13,0.742))
UPPER = np.array((0.28,0.13,1.04))


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--out", type=Path, required=True)
    p.add_argument("--frames", type=int, default=96)
    p.add_argument("--dx", type=float, default=0.0015)
    p.add_argument("--viscosity", type=float, default=0.008)
    p.add_argument("--surface-tension", type=float, default=0.0005)
    # 1.0: video frame i is the physical state at (i-1)/24 s (real time)
    p.add_argument("--time-scale", type=float, default=1.0)
    p.add_argument("--steps-per-frame", type=int, default=8)
    p.add_argument("--substeps", type=int, default=549)   # substep 1/(24*8*549) s = 9.49e-6 s
    p.add_argument("--plate-collision", type=Path,
                   help="Optional closed ceramic plate collision mesh in world coordinates")
    p.add_argument("--table-top", type=float, default=.755)
    p.add_argument("--table-size", nargs=2, type=float, default=(.40, .24))
    p.add_argument("--table-center", nargs=2, type=float, default=(.06, 0.))
    p.add_argument("--domain-lower", nargs=3, type=float, default=LOWER.tolist())
    p.add_argument("--domain-upper", nargs=3, type=float, default=UPPER.tolist())
    p.add_argument("--receiving-contact", type=Path,
                   help="Measured plate height profile for nonpenetration contact projection")
    p.add_argument("--toast-collision", type=Path,
                   help="Closed collider exported from the actual visible toast")
    p.add_argument("--toast-contact", type=Path,
                   help="Sampled visible toast height field, shared with reconstruction")
    args = p.parse_args()
    lower, upper = np.array(args.domain_lower), np.array(args.domain_upper)
    receiving = json.loads(args.receiving_contact.read_text()) if args.receiving_contact else None
    toast_surface = None
    if args.toast_contact:
        from receiver_surface import BreadSurface
        toast_surface = BreadSurface(args.toast_contact)
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/"particles").mkdir()
    import genesis as gs
    import trimesh
    gs.init(backend=gs.cuda, precision="32", seed=20261024, logging_level="warning")
    dt = args.time_scale / (FPS*args.steps_per_frame)
    verts, faces = bowl_mesh()
    bowl = trimesh.Trimesh(verts, faces, process=True)
    bowl.fix_normals()
    assert bowl.is_watertight
    bowl_path = args.out/"spoon_collision.obj"
    bowl.export(bowl_path)
    initial = initial_reservoir(args.dx)
    np.savez_compressed(args.out/"initial_reservoir.npz", honey_pos=initial)
    scene = gs.Scene(
        sim_options=gs.options.SimOptions(dt=dt, substeps=args.substeps,
            gravity=(0,0,-9.81), floor_height=0.70),
        rigid_options=gs.options.RigidOptions(dt=dt/args.substeps, enable_collision=True),
        sph_options=gs.options.SPHOptions(particle_size=args.dx, pressure_solver="DFSPH",
            lower_bound=tuple(lower), upper_bound=tuple(upper),
            max_divergence_error=0.1, max_density_error_percent=0.05),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_mpm=False, rigid_sph=True,
            rigid_pbd=False, rigid_fem=False, mpm_sph=False, mpm_pbd=False,
            fem_mpm=False, fem_sph=False), show_viewer=False,
    )
    def rigid_material(friction):
        return gs.materials.Rigid(rho=7800, needs_coup=True, friction=friction,
            coup_friction=friction, coup_softness=0.0005, coup_restitution=0,
            sdf_cell_size=0.00065, sdf_min_res=32, sdf_max_res=192)
    scene.add_entity(morph=gs.morphs.Box(pos=(*args.table_center,args.table_top-.005), size=(*args.table_size,.010),
        fixed=True, visualization=False), material=rigid_material(.5))
    if args.plate_collision:
        scene.add_entity(morph=gs.morphs.Mesh(file=str(args.plate_collision.resolve()),
            pos=(0,0,0), fixed=True, visualization=False, convexify=False,
            decimate=False, watertighten=None, batch_fixed_verts=True),
            material=rigid_material(.75))
    if args.toast_collision:
        scene.add_entity(morph=gs.morphs.Mesh(file=str(args.toast_collision.resolve()),
            pos=(0,0,0), fixed=True, visualization=False, convexify=False,
            decimate=False, watertighten=None, batch_fixed_verts=True),material=rigid_material(.75))
    else:
        scene.add_entity(morph=gs.morphs.Box(pos=tuple(TOAST_CENTER), size=tuple(TOAST_SIZE),
            fixed=True, visualization=False), material=rigid_material(.75))
    spoon = scene.add_entity(morph=gs.morphs.Mesh(file=str(bowl_path.resolve()),
        pos=tuple(SPOON_CENTER), euler=(0,INITIAL_TILT,0), fixed=True,
        visualization=False, convexify=False, decimate=False, watertighten=None,
        batch_fixed_verts=True), material=rigid_material(.18))
    honey = scene.add_entity(morph=gs.morphs.Nowhere(n_particles=len(initial)),
        material=gs.materials.SPH.Liquid(rho=1420, mu=args.viscosity,
            gamma=args.surface_tension, sampler="regular"))
    started = time.monotonic()
    scene.build()
    honey.set_particles_pos(initial)
    honey.set_particles_vel(np.zeros_like(initial))
    honey.set_particles_active(gs.ACTIVE)
    build_time = time.monotonic()-started
    rows = []
    contact_corrections = 0
    maximum_projection = 0.0
    receiving_corrections = 0
    receiving_maximum_projection = 0.0
    started = time.monotonic()
    for frame in range(1,args.frames+1):
        tick = time.monotonic()
        if frame > 1:
            for sub in range(args.steps_per_frame):
                t = ((frame-2)+(sub+1)/args.steps_per_frame)/FPS
                angle = tilt_at(t)
                scene.step()
                # Guard thin-wall contact with the same analytic inner bowl.
                # The spoon pose is fixed and its boundary velocity is zero.
                # This is a contact correction, never a prescribed fluid path.
                cp = honey.get_particles_pos().cpu().numpy().reshape(-1,3)
                cv = honey.get_particles_vel().cpu().numpy().reshape(-1,3)
                rot = rotation_y(angle)
                local = (cp-SPOON_CENTER) @ rot
                r2 = (local[:,0]/BOWL_RX)**2+(local[:,1]/BOWL_RY)**2
                floor = -BOWL_DEPTH*(1-r2)
                contact_height = floor+0.45*args.dx
                mask = ((r2 < 0.995**2) & (local[:,2] < contact_height) &
                        (local[:,2] > floor-0.005))
                if mask.any():
                    projection = contact_height[mask]-local[mask,2]
                    maximum_projection = max(maximum_projection,float(projection.max()))
                    contact_corrections += int(mask.sum())
                    local[mask,2] = contact_height[mask]
                    normals = np.stack((-2*BOWL_DEPTH*local[mask,0]/BOWL_RX**2,
                        -2*BOWL_DEPTH*local[mask,1]/BOWL_RY**2,
                        np.ones(mask.sum())),axis=1)
                    normals /= np.linalg.norm(normals,axis=1)[:,None]
                    normals = normals @ rot.T
                    cp[mask] = local[mask] @ rot.T + SPOON_CENTER
                    relative_v = cv[mask]
                    vn = np.sum(relative_v*normals,axis=1)
                    cv[mask] -= np.minimum(vn,0)[:,None]*normals
                    honey.set_particles_pos(cp)
                    honey.set_particles_vel(cv)
                if receiving is not None:
                    # Static unilateral contact, matching the existing bowl guard.
                    # Positions remain free in the fluid; only solid penetration is projected.
                    cp = honey.get_particles_pos().cpu().numpy().reshape(-1,3)
                    cv = honey.get_particles_vel().cpu().numpy().reshape(-1,3)
                    xy = cp[:, :2] - np.asarray(receiving['plate_center_xy_m'])
                    radius = np.linalg.norm(xy, axis=1)
                    rr, zz = np.asarray(receiving['radius_m']), np.asarray(receiving['height_m'])
                    plate_mask = radius <= rr[-1]
                    height = np.full(len(cp), receiving['table_top_m'])
                    height[plate_mask] = np.interp(radius[plate_mask], rr, zz)
                    slope = np.zeros(len(cp))
                    slope[plate_mask] = np.interp(radius[plate_mask], rr, np.gradient(zz, rr))
                    normals = np.c_[-slope[:,None]*xy/np.maximum(radius[:,None],1e-9), np.ones(len(cp))]
                    normals /= np.linalg.norm(normals,axis=1)[:,None]
                    if toast_surface is not None:
                        th,tn,tvalid = toast_surface.sample(cp[:,:2])
                        bread = tvalid & (th > height)
                        height[bread] = th[bread]
                        normals[bread] = tn[bread]
                    else:
                        bread = np.all(np.abs(cp[:,:2]-np.asarray(receiving['toast_center_xy_m']))
                                       <= np.asarray(receiving['toast_half_size_xy_m']), axis=1)
                        height[bread] = receiving['toast_top_m']
                        normals[bread] = (0,0,1)
                    floor = height + .45 * args.dx / np.maximum(normals[:,2],.2)
                    hit = cp[:,2] < floor
                    if hit.any():
                        receiving_corrections += int(hit.sum())
                        receiving_maximum_projection = max(receiving_maximum_projection,
                            float((floor[hit]-cp[hit,2]).max()))
                        cp[hit,2] = floor[hit]
                        n = normals[hit]
                        vn = np.einsum('ij,ij->i',cv[hit],n)
                        impulse = np.maximum(-vn,0)
                        tangent = cv[hit]-vn[:,None]*n
                        friction = np.where((plate_mask|bread)[hit],.75,.5)
                        scale = np.maximum(0,1-friction*impulse/np.maximum(np.linalg.norm(tangent,axis=1),1e-12))
                        cv[hit] = scale[:,None]*tangent+np.maximum(vn,0)[:,None]*n
                        honey.set_particles_pos(cp)
                        honey.set_particles_vel(cv)
        pos = honey.get_particles_pos().cpu().numpy().reshape(-1,3)
        vel = honey.get_particles_vel().cpu().numpy().reshape(-1,3)
        if not np.isfinite(pos).all() or not np.isfinite(vel).all():
            raise RuntimeError("nonfinite state")
        np.savez_compressed(args.out/"particles"/f"frame_{frame:04d}.npz",
            honey_pos=pos.astype(np.float32), honey_vel=vel.astype(np.float16))
        angle = tilt_at((frame-1)/FPS)
        local = (pos-SPOON_CENTER) @ rotation_y(angle)
        in_bowl = (((local[:,0]/BOWL_RX)**2+(local[:,1]/BOWL_RY)**2 < 1.05**2) &
                   (local[:,2] > -BOWL_DEPTH-args.dx) & (local[:,2] < .025))
        toast = ((np.abs(pos[:,0]-.095)<.067) & (np.abs(pos[:,1])<.055) &
                 (pos[:,2]>.794) & (pos[:,2]<.820))
        margin = np.minimum(pos-lower,upper-pos).min()
        row = dict(frame=frame, playback_time_s=(frame-1)/FPS,
            physics_time_s=(frame-1)*args.time_scale/FPS, spoon_tilt_deg=angle,
            spoon_quaternion_wxyz=spoon.get_quat().cpu().numpy().reshape(-1).tolist(),
            particle_count=len(pos), in_spoon_particles=int(in_bowl.sum()),
            on_toast_particles=int(toast.sum()), speed_max_m_s=float(np.linalg.norm(vel,axis=1).max()),
            bounds_m=[pos.min(0).tolist(),pos.max(0).tolist()],
            domain_margin_min_m=float(margin), compute_seconds=time.monotonic()-tick)
        rows.append(row)
        if frame==1 or frame%6==0 or frame==args.frames:
            print("FRAME",json.dumps(row),flush=True)
        if margin < args.dx*.25:
            raise RuntimeError("domain boundary reached")
    report = dict(status="complete", solver="Genesis 1.4.3 DFSPH", particles=len(initial),
        physics=dict(honey_density_kg_m3=1420, honey_kinematic_viscosity_m2_s=args.viscosity,
            honey_surface_tension_solver_units=args.surface_tension, gravity_m_s2=9.81,
            initial_velocity_m_s=0, initial_condition="all honey inside concave spoon bowl",
            spoon_motion="fixed at 15 degrees for the complete shot",
            contact_correction="analytic nonpenetration against the static inner bowl",
            contact_projection_count=contact_corrections,
            maximum_contact_projection_m=maximum_projection),
        receiving_contact=dict(profile=None if args.receiving_contact is None else str(args.receiving_contact),
            toast_surface=None if args.toast_contact is None else str(args.toast_contact.resolve()),
            projection_count=receiving_corrections,maximum_projection_m=receiving_maximum_projection,
            model='unilateral static heightfield contact plus Coulomb velocity projection; same friction as rigid proxies'),
        numerics=dict(fps=FPS,frames=args.frames,dx_m=args.dx,steps_per_frame=args.steps_per_frame,
            substeps_per_step=args.substeps,playback_time_scale=args.time_scale,
            domain_lower_m=lower.tolist(), domain_upper_m=upper.tolist()),
        geometry=dict(spoon_center_m=SPOON_CENTER.tolist(),
            bowl_collision_watertight=bool(bowl.is_watertight),
            spoon_uses_render_geometry=True, table_top_m=args.table_top,
            table_size_m=args.table_size, table_center_xy_m=args.table_center,
            plate_collision=None if args.plate_collision is None else str(args.plate_collision.resolve())),
        build_seconds=build_time, simulation_seconds=time.monotonic()-started,frames=rows)
    (args.out/"simulation_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("RESERVOIR_DONE",args.out,flush=True)


if __name__ == "__main__":
    main()
