"""Gravity release of two 6-DOF spheres and tension-only endpoint ropes."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"simulate")
# PCVE_UNIFIED_ENTRY_END
import argparse
import csv
import json
from pathlib import Path
import platform
import time
import numpy as np
from scene_config import scenario,initial_state,construction,length_ledger,signature
from rigid_solver import Body,World,SOLVER_VERSION

def write_json(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,indent=2,ensure_ascii=False,
        default=lambda x:x.item() if isinstance(x,np.generic) else x.tolist())+"\n")

def export_csv(path,result):
    with Path(path).open("w") as f:
        w=csv.writer(f);w.writerow(["time_sec","object_id","x","y","z","qx","qy","qz","qw",
            "vx","vy","vz","wx","wy","wz","energy_J","rope_present","rope_length_m",
            "endpoint_distance_m","tension_N","slack_m","anchor_to_center_m"])
        for s in result["trajectory_samples"]:
            for name,b in s["objects"].items():
                r=b["rope"];w.writerow([s["time_sec"],name,*b["location"],*b["quaternion_xyzw"],
                    *b["linear_velocity"],*b["angular_velocity"],b["energy_J"],r["present"],
                    r["length_m"],r["endpoint_distance_m"],r["tension_N"],r["slack_m"],r["anchor_to_center_m"]])

def summarize_turns(samples,events,cfg):
    ball=[e for e in events if e["kind"]=="ball_ball"]
    start=ball[0]["time_sec"]+.025 if ball else .05
    turns={name:[] for name in samples[0]["objects"]}
    for prev,cur in zip(samples,samples[1:]):
        if cur["time_sec"]<start:continue
        for name,b in cur["objects"].items():
            a=prev["objects"][name];va=a["linear_velocity"][0];vb=b["linear_velocity"][0]
            if va*vb<0 and abs(va-vb)<.15:
                rope=cfg["physics"]["ropes"][name]
                zero=rope["anchor_m"][2]-rope["length_m"]-rope["attachment_local_m"][2]
                turns[name].append({"time_sec":cur["time_sec"],"location":b["location"],
                    "height_above_initial_lowest_center_m":b["location"][2]-zero,
                    "incoming_horizontal_direction":"left" if va<0 else "right",
                    "linear_velocity":b["linear_velocity"],"angular_velocity":b["angular_velocity"]})
    return turns

def simulate(cfg,progress=False):
    begin=time.perf_counter();ph=cfg["physics"];sq=cfg["simulation_quality"];rd=cfg["render"]
    fps=rd["fps"];sub=sq["substeps_per_frame"];dt=1/(fps*sub);nframes=round(fps*rd["duration_sec"])
    sample_stride=round(1/(sq["trajectory_hz"]*dt))
    assert abs(sample_stride*dt*sq["trajectory_hz"]-1)<1.e-10
    bodies=[Body(name,b,*initial_state(cfg,name),ph["ropes"][name]) for name,b in ph["balls"].items() if b["present"]]
    world=World(bodies,construction(cfg),ph,sq,dt);refz=ph["fixture"]["table_top_z_m"]
    energy0=sum(b.energy(world.g,refz) for b in bodies);maxenergy=energy0;maxstep=0.;lastenergy=energy0
    maxy=0.;min_tension=0.;samples=[];frames=[];events=[];maxspeed=0.;slack_steps={b.name:0 for b in bodies}

    def snapshot(step):
        objects={}
        for b in bodies:
            r=ph["ropes"][b.name];dist=float(np.linalg.norm(b.endpoint()-b.anchor))
            objects[b.name]={"location":b.p.tolist(),"quaternion_xyzw":b.q.tolist(),
                "linear_velocity":b.v.tolist(),"angular_velocity":b.w.tolist(),
                "energy_J":b.energy(world.g,refz),"inertia_diagonal_kg_m2":[b.inertia]*3,
                "rope":{"present":bool(b.rope),"length_m":r["length_m"] if b.rope else None,
                    "anchor_m":r["anchor_m"],"attachment_world_m":b.endpoint().tolist(),
                    "endpoint_distance_m":dist,"anchor_to_center_m":float(np.linalg.norm(b.p-b.anchor)),
                    "tension_N":b.rope_impulse/dt if b.rope else 0.,
                    "bend_damping_rate_per_s":r.get("bend_damping_rate_per_s",0.) if b.rope else 0.,
                    "bend_relative_angular_velocity_rad_s":b.bend_relative_angular_velocity.tolist(),
                    "bend_coefficient_Nms_per_rad":b.bend_coefficient,
                    "bend_impulse_Nms":b.bend_impulse.tolist(),
                    "bend_dissipated_last_step_J":b.bend_dissipation,
                    "slack_m":max(0.,r["length_m"]-dist) if b.rope else None,
                    "state":"removed" if not b.rope else ("taut" if dist>=r["length_m"]-1.e-6 else "slack")}}
        return {"time_sec":step*dt,"objects":objects,"total_energy_J":sum(o["energy_J"] for o in objects.values())}

    for step in range(nframes*sub+1):
        if step%sample_stride==0:samples.append(snapshot(step))
        if step%sub==0 and step//sub<nframes:
            frames.append({"frame_index":step//sub+1,**snapshot(step)})
        if step==nframes*sub:break
        events.extend(world.step())
        energy=sum(b.energy(world.g,refz) for b in bodies)
        maxenergy=max(maxenergy,energy);maxstep=max(maxstep,energy-lastenergy);lastenergy=energy
        for b in bodies:
            maxy=max(maxy,abs(float(b.p[1])));maxspeed=max(maxspeed,float(np.linalg.norm(b.v)))
            if b.rope and np.linalg.norm(b.endpoint()-b.anchor)<b.rope["length_m"]-1.e-6:slack_steps[b.name]+=1
        if progress and step%(sub*fps)==0:print(f"sim t={step*dt:.2f}s wall={time.perf_counter()-begin:.1f}s",flush=True)
    turns=summarize_turns(samples,events,cfg)
    ball_events=[e for e in events if e["kind"]=="ball_ball"]
    first={}
    for name in turns:
        if not ph["ropes"][name]["present"]:
            first[name]=None
            continue
        lo=ball_events[0]["time_sec"]+.02 if ball_events else .05
        hi=ball_events[1]["time_sec"]-.02 if len(ball_events)>1 else rd["duration_sec"]
        eligible=[s for s in samples if lo<s["time_sec"]<hi]
        if eligible:
            apex=max(eligible,key=lambda s:s["objects"][name]["location"][2]);b=apex["objects"][name]
            rope=ph["ropes"][name];zero=rope["anchor_m"][2]-rope["length_m"]-rope["attachment_local_m"][2]
            first[name]={"time_sec":apex["time_sec"],"location":b["location"],
                "height_above_initial_lowest_center_m":b["location"][2]-zero,
                "measurement_window_sec":[lo,hi],"first_horizontal_turn":turns[name][0] if turns[name] else None}
        else:first[name]=None
    free_apices={name:[{"time_sec":cur["time_sec"],"location":cur["objects"][name]["location"]}
        for prev,cur in zip(samples,samples[1:]) if prev["objects"][name]["linear_velocity"][2]>0>=cur["objects"][name]["linear_velocity"][2]]
        for name in turns if not ph["ropes"][name]["present"]}
    return {"schema_version":1,"scene":"opposing_pendulum_collision","configuration":cfg,
        "configuration_sha256":signature(cfg),"solver":SOLVER_VERSION,"python_version":platform.python_version(),
        "numpy_version":np.__version__,"time_step_sec":dt,"fps":fps,"frame_end":nframes,
        "length_ledger":length_ledger(cfg),"collision_boxes":construction(cfg),
        "initial_state_policy":{"simultaneous_release_sec":0.,"zero_initial_velocities":True,
            "gravity_only_start":True,"free_rigid_body_dofs":6,"planar_joints":0,"motors":0,
            "rope_model":"Unilateral massless inextensible endpoint constraint with nonnegative tensile impulse; slack permitted. Textile/eyelet bend damping acts only under tension, with zero stiffness and no angle target.",
            "bend_damping_model":"Rayleigh dissipation in relative transverse body/cord angular velocity. Full Jacobian transpose reaction; implicit joint/contact solve. Axial twist remains free; no damping when slack or deleted.",
            "solver":"Projected nonlinear endpoint and hard-contact impulses, semi-implicit translation, SO(3) orientation",
            "contact_policy":"Actual nonpositive signed gap; no anticipatory rebound, pose projection or velocity bias",
            "prescribed_trajectory":False,"spring_energy":False,"energy_clamp":False},
        "effective_contacts":{"combination_rule":"Explicit pair materials: effective restitution equals pair configuration directly; no per-body multiplication",
            "ball_ball_restitution":ph["contacts"]["ball_ball"]["restitution"],"pair_materials":ph["contacts"]},
        "frames":frames,"trajectory_samples":samples,"contact_events":events,
        "turning_points":turns,"first_rebound":first,"free_body_vertical_apices":free_apices,"initial_total_mechanical_energy_J":energy0,
        "quality":{"max_ball_or_box_penetration_m":world.max_penetration,
            "max_rope_extension_m":world.max_rope_extension,
            "max_out_of_plane_m":maxy,"max_positive_passive_constraint_work_in_contact_free_step_J":world.max_positive_rope_work,
            "total_passive_constraint_work_contact_free_steps_J":world.total_rope_work,
            "bend_damping_dissipated_J":world.bend_dissipated,
            "max_positive_bend_damping_work_J":world.max_positive_bend_work,
            "max_bend_damping_constitutive_residual_rad_s":world.max_bend_constitutive_error,
            "max_total_energy_above_initial_J":maxenergy-energy0,"max_positive_energy_step_J":maxstep,
            "final_total_energy_J":lastenergy,"max_speed_m_per_s":maxspeed,
            "max_solver_iterations_used":world.max_solver_iterations,"slack_substeps":slack_steps,
            "contact_substeps":world.contact_steps,"minimum_tension_N":min_tension},
        "simulation_wall_sec":time.perf_counter()-begin}

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--case",choices=list(__import__("scene_config").CASES),default="source")
    ap.add_argument("--scenario-overrides-json",type=Path);ap.add_argument("--progress",action="store_true")
    a=ap.parse_args();cfg=scenario(a.case,json.loads(a.scenario_overrides_json.read_text()) if a.scenario_overrides_json else None)
    r=simulate(cfg,a.progress);write_json(a.out,r);export_csv(a.out.with_name("trajectory.csv"),r)
    write_json(a.out.with_name("contacts.json"),{"events":r["contact_events"]})
    print(json.dumps({"case":a.case,"events":r["contact_events"],"turns":r["turning_points"],
        "quality":r["quality"],"wall_sec":r["simulation_wall_sec"]},indent=2),flush=True)

if __name__=="__main__":main()
