"""Two independent unforced 6-DOF spheres, released together under gravity."""
from __future__ import annotations
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
import importlib.metadata
import json
import math
from pathlib import Path
import time
import pybullet as p
from scene_config import scenario,initial_position,ramp_mesh,profile,signature,surface

def write_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")

def export_csv(path,result):
    fields=["time_sec","object_id","x","y","z","qx","qy","qz","qw","vx","vy","vz","wx","wy","wz","energy_J"]
    with Path(path).open("w") as f:
        writer=csv.writer(f);writer.writerow(fields)
        for s in result["trajectory_samples"]:
            for name,b in s["objects"].items():
                writer.writerow([s["time_sec"],name,*b["location"],*b["quaternion_xyzw"],*b["linear_velocity"],*b["angular_velocity"],b["energy_J"]])

def simulate(cfg):
    begin=time.perf_counter();client=p.connect(p.DIRECT)
    try:
        ph=cfg["physics"];q=cfg["simulation_quality"];rd=cfg["render"];fps=rd["fps"];sub=q["substeps_per_frame"];dt=1/(fps*sub)
        p.resetSimulation();p.setGravity(*ph["gravity"]);p.setTimeStep(dt)
        p.setPhysicsEngineParameter(numSolverIterations=q["solver_iterations"],numSubSteps=0,deterministicOverlappingPairs=1,
            contactBreakingThreshold=q["contact_breaking_threshold_m"],contactSlop=q["contact_slop_m"],contactERP=q["contact_erp"],
            restitutionVelocityThreshold=q["restitution_velocity_threshold_m_per_s"],useSplitImpulse=int(q["split_impulse"]),
            splitImpulsePenetrationThreshold=0.,enableConeFriction=1)
        verts,faces=ramp_mesh(cfg);indices=[]
        for f in faces:
            for j in range(1,len(f)-1):indices += [f[0],f[j],f[j+1]]
        # A compound of planar full-width plates avoids triangle-diagonal contact normals.
        # Adjacent top endpoints are identical. The toe is a C1 fillet discretization.
        halves=[];centers=[];rotations=[];points=profile(cfg);thick=ph["ramp"]["board_thickness_m"]
        for (x0,z0),(x1,z1) in zip(points,points[1:]):
            angle=math.atan2(z1-z0,x1-x0)
            halves.append([math.hypot(x1-x0,z1-z0)/2,ph["ramp"]["width_m"]/2,thick/2])
            centers.append([(x0+x1)/2+math.sin(angle)*thick/2,0.,(z0+z1)/2-math.cos(angle)*thick/2])
            rotations.append(p.getQuaternionFromEuler([0.,-angle,0.]))
        r=ph["ramp"]
        ramps=[]
        for i in range(0,len(halves),12):
            shape=p.createCollisionShapeArray(shapeTypes=[p.GEOM_BOX]*len(halves[i:i+12]),halfExtents=halves[i:i+12],
                collisionFramePositions=centers[i:i+12],collisionFrameOrientations=rotations[i:i+12])
            ramp=p.createMultiBody(baseMass=0,baseCollisionShapeIndex=shape);ramps.append(ramp)
            p.changeDynamics(ramp,-1,restitution=r["restitution"],lateralFriction=r["lateral_friction"],
                rollingFriction=r["rolling_friction"],spinningFriction=r["spinning_friction"],collisionMargin=q["collision_margin_m"])
        bodies={};actual={}
        for name,b in ph["balls"].items():
            if not b["present"]: continue
            sphere=p.createCollisionShape(p.GEOM_SPHERE,radius=b["radius_m"])
            body=p.createMultiBody(baseMass=b["mass_kg"],baseCollisionShapeIndex=sphere,basePosition=initial_position(cfg,name),
                baseOrientation=b["initial_quaternion_xyzw"])
            inertia=b["inertia_factor"]*b["mass_kg"]*b["radius_m"]**2
            p.changeDynamics(body,-1,restitution=b["restitution"],lateralFriction=b["lateral_friction"],rollingFriction=b["rolling_friction"],
                spinningFriction=b["spinning_friction"],linearDamping=b["linear_damping"],angularDamping=b["angular_damping"],
                localInertiaDiagonal=[inertia]*3,collisionMargin=q["collision_margin_m"],
                ccdSweptSphereRadius=b["radius_m"]*.8,contactProcessingThreshold=0.,activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING)
            # Initial state is set once, before the first solver step. No later resets or applied forces.
            p.resetBaseVelocity(body,b["initial_velocity_m_per_s"],b["initial_angular_velocity_rad_per_s"])
            bodies[name]=body
            d=p.getDynamicsInfo(body,-1)
            actual[name]={"body_id":body,"mass_kg":d[0],"lateral_friction":d[1],"inertia_diagonal_kg_m2":list(d[2]),
                "restitution":d[5],"rolling_friction":d[6],"spinning_friction":d[7],"initial_position_m":initial_position(cfg,name)}
        g=-ph["gravity"][2];zref=r["central_surface_z_m"]+.025
        def state():
            objs={}
            for name,body in bodies.items():
                xyz,quat=p.getBasePositionAndOrientation(body);v,w=p.getBaseVelocity(body);b=ph["balls"][name]
                I=b["inertia_factor"]*b["mass_kg"]*b["radius_m"]**2
                objs[name]={"location":list(xyz),"quaternion_xyzw":list(quat),"linear_velocity":list(v),"angular_velocity":list(w),
                    "energy_J":b["mass_kg"]*g*(xyz[2]-zref)+.5*b["mass_kg"]*sum(a*a for a in v)+.5*I*sum(a*a for a in w)}
            return objs
        frames=[];samples=[];events=[];contact_rows=[];was_pair=False
        quality={"max_ball_penetration_m":0.,"max_ramp_penetration_m":0.,"max_abs_y_m":0.,"max_abs_vy_m_per_s":0.,
            "max_surface_clearance_m":0.,"max_total_energy_increase_J":0.,"max_step_energy_increase_J":0.,"max_frame_displacement_m":0.}
        nframes=round(fps*rd["duration_sec"]);total_steps=(nframes-1)*sub
        stride=round(1/(q["trajectory_hz"]*dt));assert abs(stride*dt-1/q["trajectory_hz"])<1e-12
        s0=state();energy0=sum(v["energy_J"] for v in s0.values());previous=s0;previous_frame=s0
        for step in range(total_steps+1):
            t=step*dt
            if step:
                previous=current
                p.stepSimulation()
            current=state();en=sum(b["energy_J"] for b in current.values())
            quality["max_total_energy_increase_J"]=max(quality["max_total_energy_increase_J"],en-energy0)
            quality["max_step_energy_increase_J"]=max(quality["max_step_energy_increase_J"],en-sum(b["energy_J"] for b in previous.values()))
            for name,b in current.items():
                x,y,z=b["location"];quality["max_abs_y_m"]=max(quality["max_abs_y_m"],abs(y))
                quality["max_abs_vy_m_per_s"]=max(quality["max_abs_vy_m_per_s"],abs(b["linear_velocity"][1]))
                sz,slope=surface(cfg,x);radius=ph["balls"][name]["radius_m"]
                clearance=(z-sz)/math.sqrt(1+slope*slope)-radius
                quality["max_surface_clearance_m"]=max(quality["max_surface_clearance_m"],clearance)
            active=[];pair=False
            for c in p.getContactPoints():
                if c[9]<q["contact_force_threshold_N"]: continue
                names={v:k for k,v in bodies.items()};a=names.get(c[1],"ramp");b=names.get(c[2],"ramp")
                is_pair=a!="ramp" and b!="ramp"
                pair=pair or is_pair
                key="max_ball_penetration_m" if is_pair else "max_ramp_penetration_m"
                quality[key]=max(quality[key],max(0.,-c[8]))
                if is_pair or step%stride==0:
                    row={"time_sec":t,"objects":[a,b],"position_a_m":list(c[5]),"position_b_m":list(c[6]),
                        "normal_on_b":list(c[7]),"signed_gap_m":c[8],"normal_force_N":c[9],"normal_impulse_Ns":c[9]*dt,
                        "lateral_force_1_N":c[10],"lateral_direction_1":list(c[11]),"lateral_force_2_N":c[12],"lateral_direction_2":list(c[13])}
                    contact_rows.append(row)
                if is_pair:active.append(c)
            if pair and not was_pair:
                c=active[0];before=previous;after=current
                relbefore=before["B_left"]["linear_velocity"][0]-before["B_right"]["linear_velocity"][0]
                relafter=after["B_left"]["linear_velocity"][0]-after["B_right"]["linear_velocity"][0]
                events.append({"index":len(events)+1,"time_sec":t,"position_m":[(c[5][i]+c[6][i])/2 for i in range(3)],
                    "both_in_horizontal":all(abs(s["location"][0])<r["central_length_m"]/2 for s in before.values()),
                    "before":before,"after":after,"measured_normal_restitution":-relafter/relbefore if relbefore>1e-8 else None,
                    "energy_before_J":sum(v["energy_J"] for v in before.values()),"energy_after_J":en})
            was_pair=pair
            if step%stride==0:samples.append({"time_sec":t,"objects":current})
            if step%sub==0:
                frames.append({"frame_index":step//sub+1,"time_sec":t,"objects":current})
                for name,b in current.items():
                    dist=math.dist(b["location"],previous_frame[name]["location"])
                    quality["max_frame_displacement_m"]=max(quality["max_frame_displacement_m"],dist)
                previous_frame=current
        rebound={};turns={}
        for name in bodies:
            turns[name]=[];side=-1 if name=="B_left" else 1
            for i in range(1,len(samples)):
                old=samples[i-1]["objects"][name];now=samples[i]["objects"][name]
                if old["linear_velocity"][0]*now["linear_velocity"][0]<0:
                    x=now["location"][0]
                    if abs(x)>.105:
                        turns[name].append({"time_sec":samples[i]["time_sec"],"location_m":now["location"],
                            "height_above_horizontal_center_m":now["location"][2]-zref,"linear_velocity":now["linear_velocity"],
                            "angular_velocity":now["angular_velocity"],"on_original_side":x*side>0})
            if events:
                candidates=[x for x in turns[name] if x["time_sec"]>events[0]["time_sec"]]
                rebound[name]=candidates[0] if candidates else None
        return {"schema_version":1,"scene":"twin_ramp_collision","configuration":cfg,"configuration_sha256":signature(cfg),
            "solver":{"name":"PyBullet","version":importlib.metadata.version("pybullet"),"api_version":p.getAPIVersion(),
                "timestep_sec":dt,"actual_bodies":actual,"fixed_colliders":[f"ramp_plate_group_{i}" for i in range(len(ramps))],
                "collision_representation":"C1 toe profile, full-width box plates in static compounds; exactly shared surface endpoints",
                "constraints":p.getNumConstraints(),"body_count":p.getNumBodies(),"engine_parameters":p.getPhysicsEngineParameters(),"external_forces":0,
                "gravity_only_release":True,"pose_resets_after_release":0,"velocity_resets_after_release":0},
            "effective_contacts":{"ball_ball_restitution":ph["balls"]["B_left"]["restitution"]*ph["balls"]["B_right"]["restitution"],
                "ball_ramp_restitution":{k:b["restitution"]*r["restitution"] for k,b in ph["balls"].items()},
                "ball_ramp_lateral_friction":{k:b["lateral_friction"]*r["lateral_friction"] for k,b in ph["balls"].items()},
                "ball_ramp_rolling_friction":{k:b["rolling_friction"]*r["lateral_friction"]+r["rolling_friction"]*b["lateral_friction"] for k,b in ph["balls"].items()},
                "combination_source":"https://github.com/bulletphysics/bullet3/blob/3.25/src/BulletCollision/CollisionDispatch/btManifoldResult.cpp"},
            "fps":fps,"frame_end":nframes,"frames":frames,"trajectory_samples":samples,"contact_events":events,
            "contact_samples":contact_rows,"first_rebound":rebound,"ramp_turning_points":turns,"quality":quality,
            "initial_total_mechanical_energy_J":energy0,"simulation_wall_sec":time.perf_counter()-begin}
    finally:p.disconnect(client)

def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument("--out",type=Path,required=True)
    ap.add_argument("--case",choices=["source","edit_heavy_left","edit_low_restitution","edit_remove_right"],default="source")
    ap.add_argument("--scenario-overrides-json",type=Path)
    args=ap.parse_args();cfg=scenario(args.case,json.loads(args.scenario_overrides_json.read_text()) if args.scenario_overrides_json else None)
    r=simulate(cfg);write_json(args.out,r);export_csv(args.out.with_name("trajectory.csv"),r)
    write_json(args.out.with_name("contacts.json"),{"events":r["contact_events"],"samples":r["contact_samples"]})
    print(json.dumps({"case":args.case,"collisions":[[e["time_sec"],e["measured_normal_restitution"]] for e in r["contact_events"]],
        "first_rebound":r["first_rebound"],"quality":r["quality"],"wall_sec":r["simulation_wall_sec"]},indent=2))

if __name__=="__main__":main()
