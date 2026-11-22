"""Independent free rigid bodies; single initial velocity; genuine compound-hull contacts."""
from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"simulate")
# PCVE_UNIFIED_ENTRY_END
import argparse
import csv
import importlib.metadata
import json
import math
import platform
import tempfile
import time
from pathlib import Path
import pybullet as p
from scene_config import scenario,signature,pin_radius,pin_positions,pin_mass_properties,environment_fixed_geometry

def dump(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,indent=2,ensure_ascii=False)+"\n")

def norm(v):return math.sqrt(sum(x*x for x in v))

def hull_files(cfg,folder,com):
    """16 full-height convex bands; never exceed Bullet's 16-array-element limit."""
    profile=cfg["physics"]["pins"]["profile_z_radius_m"];n=cfg["simulation_quality"]["pin_radial_segments"]
    boundaries=cfg["simulation_quality"]["pin_convex_boundaries_m"]
    assert len(boundaries)-1<=16 and boundaries[0]==0 and boundaries[-1]==profile[-1][0]
    paths=[]
    for k,(lo,hi) in enumerate(zip(boundaries,boundaries[1:])):
        intervals=max(8,math.ceil((hi-lo)/.002))
        rings=sorted(set([lo+(hi-lo)*j/intervals for j in range(intervals+1)]+[z for z,r in profile if lo<z<hi]))
        verts=[(pin_radius(z,profile)*math.cos(2*math.pi*j/n),pin_radius(z,profile)*math.sin(2*math.pi*j/n),z-com) for z in rings for j in range(n)]
        last=len(rings)-1
        faces=[tuple(reversed(range(n))),tuple(range(last*n,(last+1)*n))]
        faces += [(i*n+j,i*n+(j+1)%n,(i+1)*n+(j+1)%n,(i+1)*n+j) for i in range(last) for j in range(n)]
        path=folder/f"convex_band_{k:02}.obj"
        path.write_text("\n".join([f"v {x:.10f} {y:.10f} {z:.10f}" for x,y,z in verts]+["f "+" ".join(str(i+1) for i in f) for f in faces])+"\n")
        paths.append(str(path))
    return paths

def simulate(cfg,record=True):
    start=time.perf_counter();ph=cfg["physics"];sq=cfg["simulation_quality"];rd=cfg["render"]
    fps=rd["fps"];nf=round(fps*rd["duration_sec"]);sub=sq["substeps_per_frame"];dt=1/(fps*sub)
    stride=max(1,round(1/(dt*sq["trajectory_hz"])));pp=ph["pins"];bp=ph["ball"]
    props=pin_mass_properties(pp["profile_z_radius_m"]);com=props["com_height_m"]
    cid=p.connect(p.DIRECT)
    try:
        p.setGravity(*ph["gravity"],physicsClientId=cid);p.setTimeStep(dt,physicsClientId=cid)
        p.setPhysicsEngineParameter(fixedTimeStep=dt,numSolverIterations=sq["solver_iterations"],
            contactBreakingThreshold=sq["contact_breaking_threshold_m"],contactSlop=sq["contact_slop_m"],
            restitutionVelocityThreshold=sq["restitution_velocity_threshold_m_per_s"],
            useSplitImpulse=int(sq["use_split_impulse"]),splitImpulsePenetrationThreshold=sq["split_impulse_penetration_threshold_m"],
            deterministicOverlappingPairs=1,enableConeFriction=1,physicsClientId=cid)
        labels={};bodies={};dynamics={};geometry=environment_fixed_geometry(cfg)
        for c in geometry:
            if c["kind"]=="box":
                shape=p.createCollisionShape(p.GEOM_BOX,halfExtents=[v/2 for v in c["size"]],physicsClientId=cid)
                body=p.createMultiBody(0.,shape,basePosition=c["center"],useMaximalCoordinates=False,physicsClientId=cid)
            else:
                shape=p.createCollisionShape(p.GEOM_MESH,vertices=c["vertices"],physicsClientId=cid)
                body=p.createMultiBody(0.,shape,useMaximalCoordinates=False,physicsClientId=cid)
            p.changeDynamics(body,-1,lateralFriction=c["friction"],restitution=c["restitution"],
                collisionMargin=0.,contactProcessingThreshold=0.,physicsClientId=cid);labels[body]=c["id"]
        # The ball is built unless a DELETE edit switches it off (physics.ball.active, absent = present).
        if bp.get("active",1):
            sphere=p.createCollisionShape(p.GEOM_SPHERE,radius=bp["radius_m"],physicsClientId=cid)
            ball=p.createMultiBody(bp["mass_kg"],sphere,basePosition=bp["initial_position_m"],baseOrientation=bp["initial_quaternion_xyzw"],useMaximalCoordinates=False,physicsClientId=cid)
            bodies["B01"]=ball;labels[ball]="B01"
            inertia=bp["inertia_factor"]*bp["mass_kg"]*bp["radius_m"]**2
            p.changeDynamics(ball,-1,mass=bp["mass_kg"],lateralFriction=bp["lateral_friction"],restitution=bp["restitution"],
                rollingFriction=bp["rolling_friction"],spinningFriction=bp["spinning_friction"],
                linearDamping=bp["linear_damping"],angularDamping=bp["angular_damping"],localInertiaDiagonal=[inertia]*3,
                contactProcessingThreshold=0.,ccdSweptSphereRadius=sq["ccd_swept_radius_m"],collisionMargin=0.,
                activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING,physicsClientId=cid)
            # Only assignment of velocity in the complete simulation. +Y spin is correct for +X travel.
            p.resetBaseVelocity(ball,bp["initial_velocity_m_per_s"],bp["initial_angular_velocity_rad_per_s"],physicsClientId=cid)
        with tempfile.TemporaryDirectory(prefix="pcve_bowling_hulls_") as folder:
            paths=hull_files(cfg,Path(folder),com)
            shape=p.createCollisionShapeArray(shapeTypes=[p.GEOM_MESH]*len(paths),fileNames=paths,
                meshScales=[[1,1,1]]*len(paths),collisionFramePositions=[[0,0,0]]*len(paths),physicsClientId=cid)
            if shape<0:raise RuntimeError("Compound hull construction failed")
            for i,(name,xy) in enumerate(zip(pp["ids"],pin_positions(cfg))):
                if not pp["active"][i]:continue
                body=p.createMultiBody(pp["masses_kg"][i],shape,basePosition=[*xy,com],useMaximalCoordinates=False,physicsClientId=cid)
                inertia=[v*pp["masses_kg"][i] for v in props["inertia_per_kg_m2"]]
                p.changeDynamics(body,-1,mass=pp["masses_kg"][i],lateralFriction=pp["frictions"][i],restitution=pp["restitutions"][i],
                    rollingFriction=pp["rolling_friction"],spinningFriction=pp["spinning_friction"],
                    linearDamping=pp["linear_damping"],angularDamping=pp["angular_damping"],localInertiaDiagonal=inertia,
                    contactProcessingThreshold=0.,collisionMargin=sq["collision_margin_m"],
                    activationState=p.ACTIVATION_STATE_DISABLE_SLEEPING,physicsClientId=cid)
                bodies[name]=body;labels[body]=name
        for name,body in bodies.items():
            d=p.getDynamicsInfo(body,-1,physicsClientId=cid)
            dynamics[name]={"mass_kg":d[0],"friction":d[1],"local_inertia_diagonal_kg_m2":list(d[2]),"restitution":d[5],"constructed_convex_shape_count":1 if name=="B01" else len(paths),"actual_collision_shape_count":len(p.getCollisionShapeData(body,-1,physicsClientId=cid))}
        p.performCollisionDetection(physicsClientId=cid)
        initial_contacts=[{"objects":[labels[c[1]],labels[c[2]]],"gap_m":c[8]} for c in p.getContactPoints(physicsClientId=cid)]
        frames=[];samples=[];contacts={};episodes=[];active={};prev=None
        events={name:{} for name in pp["ids"]};max_tilt={name:0. for name in pp["ids"]}
        max_speed={name:0. for name in bodies};max_omega={name:0. for name in bodies}
        max_pen=0.;worst=None;max_energy_step=0.;max_energy=0.;max_unforced_accel=0.;tail={name:[] for name in bodies}
        def state(t):
            out={};energy=0.
            for name,body in bodies.items():
                loc,q=p.getBasePositionAndOrientation(body,physicsClientId=cid);v,w=p.getBaseVelocity(body,physicsClientId=cid)
                if not all(math.isfinite(x) for x in (*loc,*q,*v,*w)):raise RuntimeError("Nonfinite solver state")
                rot=p.getMatrixFromQuaternion(q);tilt=math.degrees(math.acos(max(-1.,min(1.,rot[8]))))
                out[name]={"location":list(loc),"quaternion_xyzw":list(q),"linear_velocity":list(v),"angular_velocity":list(w),"tilt_deg":tilt}
                local_w=[sum(rot[j*3+i]*w[j] for j in range(3)) for i in range(3)]
                dy=dynamics[name];energy+=.5*dy["mass_kg"]*norm(v)**2+.5*sum(ij*wj*wj for ij,wj in zip(dy["local_inertia_diagonal_kg_m2"],local_w))+dy["mass_kg"]*9.81*loc[2]
                max_speed[name]=max(max_speed[name],norm(v));max_omega[name]=max(max_omega[name],norm(w))
                if name.startswith("P"):
                    max_tilt[name]=max(max_tilt[name],tilt)
                    for th in [1,10,30,45,80]:
                        if tilt>=th and str(th) not in events[name]:events[name][str(th)]=t
                if t>=rd["duration_sec"]-.5:tail[name].append(out[name])
            return {"time_sec":t,"objects":out,"mechanical_energy_J":energy}
        # Include a terminal t=duration state for physical annotation; video frame i is t=(i-1)/fps.
        for step in range(nf*sub+1):
            t=step*dt
            if step:p.stepSimulation(physicsClientId=cid)
            current=state(t);max_energy=max(max_energy,current["mechanical_energy_J"])
            if prev:max_energy_step=max(max_energy_step,current["mechanical_energy_J"]-prev["mechanical_energy_J"])
            pairs={};contact_names=set()
            for cp in p.getContactPoints(physicsClientId=cid):
                if cp[9]<=sq["contact_force_threshold_N"]:continue
                a,b=sorted([labels[cp[1]],labels[cp[2]]]);key=a+"|"+b
                contact_names.update([a,b]);pen=max(0.,-cp[8])
                if pen>max_pen:max_pen=pen;worst={"time_sec":t,"objects":[a,b],"penetration_m":pen}
                if key not in pairs:pairs[key]={"objects":[a,b],"normal_force_N":0.,"normal_impulse_Ns":0.,"min_gap_m":cp[8],"point_on_b_m":list(cp[6]),"normal_on_b":list(cp[7])}
                c=pairs[key];c["normal_force_N"]+=cp[9];c["normal_impulse_Ns"]+=cp[9]*dt;c["min_gap_m"]=min(c["min_gap_m"],cp[8])
            for key,c in pairs.items():
                if key not in contacts:contacts[key]={"objects":c["objects"],"first_time_sec":t,"last_time_sec":t,"total_normal_impulse_Ns":0.,"max_normal_force_N":0.,"max_penetration_m":0.,"first_point_on_b_m":c["point_on_b_m"]}
                total=contacts[key];total["last_time_sec"]=t;total["total_normal_impulse_Ns"]+=c["normal_impulse_Ns"]
                total["max_normal_force_N"]=max(total["max_normal_force_N"],c["normal_force_N"]);total["max_penetration_m"]=max(total["max_penetration_m"],-c["min_gap_m"])
                if key not in active:
                    active[key]={"objects":c["objects"],"start_time_sec":t,"end_time_sec":t,"normal_impulse_Ns":0.,"max_force_N":0.,"min_gap_m":c["min_gap_m"],"first_point_on_b_m":c["point_on_b_m"],
                        "velocities_before":{name:prev["objects"][name]["linear_velocity"] for name in c["objects"] if prev and name in bodies}}
                e=active[key];e["end_time_sec"]=t;e["normal_impulse_Ns"]+=c["normal_impulse_Ns"];e["max_force_N"]=max(e["max_force_N"],c["normal_force_N"]);e["min_gap_m"]=min(e["min_gap_m"],c["min_gap_m"])
                e["velocities_after"]={name:current["objects"][name]["linear_velocity"] for name in c["objects"] if name in bodies}
            for key in list(active):
                if key not in pairs:episodes.append(active.pop(key))
            if prev:
                for name,st in current["objects"].items():
                    if name not in contact_names and name not in prev.get("contact_ids",[]):
                        residual=norm([st["linear_velocity"][i]-prev["objects"][name]["linear_velocity"][i]-ph["gravity"][i]*dt for i in range(3)])/dt
                        max_unforced_accel=max(max_unforced_accel,residual)
            current["contact_ids"]=sorted(contact_names)
            if record and step%stride==0:samples.append(current)
            if record and step%sub==0 and step<nf*sub:frames.append({"frame_index":step//sub+1,**current})
            prev=current
        episodes.extend(active.values())
        dynamic_contacts=sorted([c for c in contacts.values() if all(x in bodies for x in c["objects"])],key=lambda c:c["first_time_sec"])
        onset_without_contact=[]
        for name in pp["ids"]:
            if name not in bodies:continue
            contact_t=min([c["first_time_sec"] for c in dynamic_contacts if name in c["objects"]]+[math.inf])
            if events[name].get("1",math.inf)<contact_t-dt:onset_without_contact.append(name)
        q={"toppled_count":sum(v>=45 for v in max_tilt.values()),"max_tilt_deg":max_tilt,
          "final_tilt_deg":{n:s["tilt_deg"] for n,s in current["objects"].items() if n.startswith("P")},
          "max_penetration_m":max_pen,"worst_contact":worst,"max_linear_speed_m_per_s":max_speed,
          "max_angular_speed_rad_per_s":max_omega,"max_energy_step_gain_J":max_energy_step,
          "initial_mechanical_energy_J":samples[0]["mechanical_energy_J"] if samples else None,"max_mechanical_energy_J":max_energy,
          "max_free_flight_acceleration_residual_m_per_s2":max_unforced_accel,"premature_tipping_ids":onset_without_contact,
          "initial_max_penetration_m":max([0.]+[-c["gap_m"] for c in initial_contacts]),
          "tail_max_equivalent_speed_m_per_s":{n:max([norm(st["linear_velocity"])+.19*norm(st["angular_velocity"]) for st in vals]+[0.]) for n,vals in tail.items()}}
        return {"schema_version":3,"simulator":"pybullet","solver_version":importlib.metadata.version("pybullet"),"python_version":platform.python_version(),
            "configuration":cfg,"configuration_sha256":signature(cfg),"fps":fps,"frame_start":1,"frame_end":nf,"duration_sec":rd["duration_sec"],"physics_dt":dt,
            "pin_mass_properties":props,"actual_dynamics":dynamics,"fixed_colliders":geometry,
            "initial_contacts":initial_contacts,"constraints":[],"external_forces":[],"prescribed_motion":False,
            "initial_velocity_assignment_count":1 if "B01" in bodies else 0,"orientation_source":"actual solver quaternion; no reconstructed roll",
            "contact_events":dynamic_contacts,"all_contacts":contacts,"contact_episodes":episodes,
            "tilt_threshold_times_sec":events,"final_state":current,"quality":q,"frames":frames,"trajectory_samples":samples,
            "simulation_wall_sec":time.perf_counter()-start}
    finally:p.disconnect(cid)

def export_csv(path,result):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("w",newline="") as f:
        w=csv.writer(f);w.writerow(["time_sec","object_id","x_m","y_m","z_m","qx","qy","qz","qw","vx","vy","vz","wx","wy","wz","tilt_deg"])
        for sample in result["trajectory_samples"]:
            for name,o in sample["objects"].items():w.writerow([sample["time_sec"],name,*o["location"],*o["quaternion_xyzw"],*o["linear_velocity"],*o["angular_velocity"],o["tilt_deg"]])

def main():
    a=argparse.ArgumentParser(description=__doc__);a.add_argument("--out",type=Path,required=True);a.add_argument("--case",default="source")
    a.add_argument("--scenario-overrides-json",type=Path);a.add_argument("--substeps",type=int)
    args=a.parse_args();cfg=scenario(json.loads(args.scenario_overrides_json.read_text()) if args.scenario_overrides_json else None,case=args.case)
    if args.substeps:cfg["simulation_quality"]["substeps_per_frame"]=args.substeps
    r=simulate(cfg);dump(args.out,r);export_csv(args.out.with_name("trajectory.csv"),r);print(json.dumps(r["quality"],ensure_ascii=False))

if __name__=="__main__":main()
