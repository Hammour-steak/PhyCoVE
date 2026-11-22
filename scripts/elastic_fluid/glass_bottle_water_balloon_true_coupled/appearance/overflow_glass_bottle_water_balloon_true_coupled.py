"""Conservative spill ledger and a declared geometric overflow display proxy.

The membrane solver supplies cumulative discharged water. Exterior rivulets
and a shallow front-counter puddle visualize that discharge; they are NOT a
CFD simulation of the flow around the lip, film wetting or splashes. A flight
delay separates water on the jar from water collected on the counter. No
objects are added for a zero-spill case, preserving the existing source look.
"""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np

FPS=24
G=9.81
LIP_Z=.354
COUNTER_SIM_Z=.1002
INITIAL_SPILL_SPEED=.18
TRAVEL_SECONDS=(math.sqrt(INITIAL_SPILL_SPEED**2+2*G*(LIP_Z-COUNTER_SIM_Z))-INITIAL_SPILL_SPEED)/G

def overflow_ledger(rows):
    times=np.arange(len(rows),dtype=float)/FPS
    spilled=np.array([r["spilled_ml"] for r in rows],dtype=float)*1e-6
    if (spilled<0).any() or (np.diff(spilled)<-1e-12).any():
        raise ValueError("Overflow must be a nonnegative cumulative discharge")
    collected=np.interp(times-TRAVEL_SECONDS,times,spilled,left=0.,right=float(spilled[-1]))
    return [{"frame":i+1,"time_s":float(t),"spilled_m3":float(s),"on_jar_m3":float(s-p),"puddle_m3":float(p)}
        for i,(t,s,p) in enumerate(zip(times,spilled,collected))]

def puddle_mesh(volume):
    """A closed, shallow front half-annulus; its geometric volume is the ledger volume."""
    nr,na=12,72
    inner=.060
    outer=math.sqrt(inner**2+2*volume/(math.pi*.0011))
    verts=[]
    for layer in (0,1):
        for ir in range(nr+1):
            u=ir/nr
            for ia in range(na+1):
                v=ia/na
                phi=-math.pi+math.pi*v
                outline=math.sin(math.pi*v)**.65*(.96+.035*math.sin(5*phi+.3)+.015*math.sin(9*phi))
                radius=inner+(outer-inner)*u*outline
                height=.0014*math.sin(math.pi*u)**.7*math.sin(math.pi*v)**.25 if layer else 0.
                verts.append((radius*math.cos(phi),radius*math.sin(phi),height))
    n=(nr+1)*(na+1)
    faces=[]
    for ir in range(nr):
        for ia in range(na):
            a=ir*(na+1)+ia;b=a+1;c=a+na+1;d=c+1
            faces.extend(((a,d,b),(a,c,d),(a+n,b+n,d+n),(a+n,d+n,c+n)))
    boundary=[ia for ia in range(na+1)]
    boundary += [ir*(na+1)+na for ir in range(1,nr+1)]
    boundary += [nr*(na+1)+ia for ia in range(na-1,-1,-1)]
    boundary += [ir*(na+1) for ir in range(nr-1,0,-1)]
    for a,b in zip(boundary,boundary[1:]+boundary[:1]):
        faces.extend(((a,b,b+n),(a,b+n,a+n)))
    vertices=np.asarray(verts,dtype=float)
    triangles=np.asarray(faces,dtype=np.int32)
    def measure():
        a,b,c=vertices[triangles[:,0]],vertices[triangles[:,1]],vertices[triangles[:,2]]
        return float(np.einsum("ij,ij->i",a,np.cross(b,c)).sum()/6.)
    signed=measure()
    if signed<0:
        triangles=triangles[:,::-1].copy()
        signed=-signed
    vertices[n:,2]*=volume/max(signed,1e-30)
    return vertices,triangles,measure()

def add_overflow_visuals(args,sim,water,jar_profile,counter_z,frame_count,show_only_on):
    config_path=Path(args.surface_dir).parent/"sim/membrane.json"
    if not config_path.is_file():
        return
    config=json.loads(config_path.read_text())
    rows=config["rows"]
    ledger=overflow_ledger(rows)
    if config["args"].get("water_retention")=="retain_all":
        if any(row["spilled_ml"]!=0.0 for row in rows):
            raise RuntimeError("retain_all must have zero discharged water")
        report={"model":"overflow disabled: idealized retain-all boundary", "disabled":True,
            "object_count":0,"rows":ledger,
            "limits":["All injected water remains in the membrane; no exterior water film or puddle is generated."]}
        (args.out/"overflow_visualization.json").write_text(json.dumps(report,indent=2))
        return
    import bpy
    samples=np.array([r["spilled_m3"] for r in ledger])
    times=np.arange(frame_count)/FPS
    rates=np.r_[0.,np.diff(samples)*FPS]
    profile=np.asarray(jar_profile,dtype=float)
    center=np.array(sim.location,dtype=float)
    object_count=0
    for row in ledger:
        frame,t=row["frame"],row["time_s"]
        if row["spilled_m3"]<=1e-10:
            continue
        for index,phi0 in enumerate(np.linspace(-2.85,-.29,6)):
            zs=np.linspace(LIP_Z,COUNTER_SIM_Z,40)
            drops=LIP_Z-zs
            velocities=np.sqrt(INITIAL_SPILL_SPEED**2+2*G*drops)
            delays=(velocities-INITIAL_SPILL_SPEED)/G
            q=np.interp(t-delays,times,rates,left=0.,right=float(rates[-1]))/6.
            if q.max()<1e-10:
                continue
            # A thin, flattened wet film on the glass, rather than a round tube.
            # Width/thickness are qualitative display parameters; only the
            # transit ledger and collected mesh are volume annotations.
            across=8
            verts=[]
            for layer in (0,1):
              for k,z in enumerate(zs):
                wall=float(np.interp(z,profile[:,1],profile[:,0]))
                phi=phi0+.025*math.sin((z-.1)*36+index)
                strength=math.sqrt(max(q[k],0.)/1.25e-5)
                angle=min(.15,.055*strength)
                for j in range(across+1):
                    fraction=j/across
                    a=phi+angle*(2*fraction-1)
                    height=min(.00055,.00022*strength)*math.sin(math.pi*fraction)**.65 if layer else 0.
                    distance=wall+.00007+height
                    verts.append((distance*math.cos(a),distance*math.sin(a),float(z)))
            count=len(zs)*(across+1)
            faces=[]
            for k in range(len(zs)-1):
              for j in range(across):
                a=k*(across+1)+j;b=a+1;c=a+across+1;d=c+1
                faces.extend(((a,b,d),(a,d,c),(a+count,d+count,b+count),(a+count,c+count,d+count)))
            boundary=list(range(across+1))
            boundary += [k*(across+1)+across for k in range(1,len(zs))]
            boundary += [(len(zs)-1)*(across+1)+j for j in range(across-1,-1,-1)]
            boundary += [k*(across+1) for k in range(len(zs)-2,0,-1)]
            for a,b in zip(boundary,boundary[1:]+boundary[:1]):
                faces.extend(((a,b+count,b),(a,a+count,b+count)))
            mesh=bpy.data.meshes.new(f"Overflow wet film {frame:03d}_{index}")
            mesh.from_pydata(verts,[],faces)
            mesh.update()
            obj=bpy.data.objects.new(mesh.name,mesh)
            bpy.context.scene.collection.objects.link(obj)
            obj.location=tuple(center)
            mesh.materials.append(water)
            for face in mesh.polygons:face.use_smooth=True
            show_only_on(obj,frame,frame_count)
            object_count+=1
        if row["puddle_m3"]>1e-9:
            v,f,measured=puddle_mesh(row["puddle_m3"])
            mesh=bpy.data.meshes.new(f"Collected overflow {frame:03d}")
            mesh.from_pydata(v.tolist(),[],f.tolist())
            mesh.update()
            obj=bpy.data.objects.new(mesh.name,mesh)
            bpy.context.scene.collection.objects.link(obj)
            obj.location=(center[0],center[1],counter_z+.00015)
            mesh.materials.append(water)
            for face in mesh.polygons:face.use_smooth=True
            show_only_on(obj,frame,frame_count)
            object_count+=1
            stored=np.array([vertex.co[:] for vertex in mesh.vertices],dtype=float)
            a,b,c=stored[f[:,0]],stored[f[:,1]],stored[f[:,2]]
            row["measured_puddle_mesh_m3"]=float(abs(np.einsum("ij,ij->i",a,np.cross(b,c)).sum()/6.))
    report={"model":"geometric overflow proxy driven by conservative discharged-water records; not exterior CFD",
        "limits":["Rivulet paths, front-counter spreading and the visual lip transition are analytic display approximations, not resolved wetting/splash hydrodynamics.",
            "The puddle has the ledger's collected-water volume; thin wet-film geometry is a qualitative transit proxy."],
        "travel_seconds":TRAVEL_SECONDS,"object_count":object_count,"rows":ledger}
    (args.out/"overflow_visualization.json").write_text(json.dumps(report,indent=2))
