"""Finite honey reservoir draining from a spoon fixed at a slight 15-degree tilt."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
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
    args = p.parse_args()
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
            lower_bound=tuple(LOWER), upper_bound=tuple(UPPER),
            max_divergence_error=0.1, max_density_error_percent=0.05),
        coupler_options=gs.options.LegacyCouplerOptions(rigid_mpm=False, rigid_sph=True,
            rigid_pbd=False, rigid_fem=False, mpm_sph=False, mpm_pbd=False,
            fem_mpm=False, fem_sph=False), show_viewer=False,
    )
    def rigid_material(friction):
        return gs.materials.Rigid(rho=7800, needs_coup=True, friction=friction,
            coup_friction=friction, coup_softness=0.0005, coup_restitution=0,
            sdf_cell_size=0.00065, sdf_min_res=32, sdf_max_res=192)
    scene.add_entity(morph=gs.morphs.Box(pos=(.06,0,.750), size=(.40,.24,.010),
        fixed=True, visualization=False), material=rigid_material(.5))
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
        margin = np.minimum(pos-LOWER,UPPER-pos).min()
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
        numerics=dict(fps=FPS,frames=args.frames,dx_m=args.dx,steps_per_frame=args.steps_per_frame,
            substeps_per_step=args.substeps,playback_time_scale=args.time_scale),
        geometry=dict(spoon_center_m=SPOON_CENTER.tolist(),
            bowl_collision_watertight=bool(bowl.is_watertight),
            spoon_uses_render_geometry=True),
        build_seconds=build_time, simulation_seconds=time.monotonic()-started,frames=rows)
    (args.out/"simulation_report.json").write_text(json.dumps(report,indent=2)+"\n")
    print("RESERVOIR_DONE",args.out,flush=True)


if __name__ == "__main__":
    main()
