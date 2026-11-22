"""Independent exact-triangle cup audit against the actual cup triangles (no circular proxy).

Closed cavity cap is audit-only. It never appears in simulation or rendering.
An exterior droplet is not automatically labelled a through-wall leak: its
particle ID and over-rim history are retained for separate trajectory review.
"""
import argparse
import json
from pathlib import Path
import time

import igl
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components

p=argparse.ArgumentParser()
p.add_argument("case",type=Path)
p.add_argument("--frames",type=int,nargs="+")
a=p.parse_args()
case=a.case.resolve()
experiment=json.loads((case/"experiment.json").read_text())
settings=experiment["after"]
cavity=trimesh.load(case/"audit_cavity_closed.obj",force="mesh",process=False)
solid=trimesh.load(case/("visible_solid_closed.obj" if (case/"visible_solid_closed.obj").exists() else "cup_collider.obj"),force="mesh",process=False)
inner=np.load(case/"actual_inner_open.npz")
floor=float(inner["vertices"][:,2].min())
lowest_rim=float(inner["vertices"][inner["rim_indices"],2].min())
highest_rim=float(inner["vertices"][inner["rim_indices"],2].max())
rim_vertices=inner["vertices"][inner["rim_indices"]]
rim_center=rim_vertices[:,:2].mean(0)
rim_angles=np.mod(np.arctan2(rim_vertices[:,1]-rim_center[1],rim_vertices[:,0]-rim_center[0]),2*np.pi)
order=np.argsort(rim_angles)
rim_angles,rim_heights=rim_angles[order],rim_vertices[order,2]
def local_rim_height(points):
    angle=np.mod(np.arctan2(points[:,1]-rim_center[1],points[:,0]-rim_center[0]),2*np.pi)
    return np.interp(angle,np.r_[rim_angles[-1]-2*np.pi,rim_angles,rim_angles[0]+2*np.pi],
                     np.r_[rim_heights[-1],rim_heights,rim_heights[0]])
capacity=settings["capacity_particles"]
entered=np.zeros(capacity,dtype=bool)
over_rim=np.zeros(capacity,dtype=bool)
escaped=np.zeros(capacity,dtype=bool)
first_escape=np.zeros(capacity,dtype=int)
rows,surface_rows={},{}
start=time.monotonic()
def sdf(mesh,points):
    if not len(points):
        return np.empty(0)
    return igl.signed_distance(np.asarray(points,dtype=np.float64),mesh.vertices,mesh.faces.astype(np.int64),
                               igl.SIGNED_DISTANCE_TYPE_PSEUDONORMAL)[0]

for frame in a.frames or range(1,97):
    path=case/f"particles/frame_{frame:04d}.npz"
    if not path.exists():
        continue
    data=np.load(path)
    pos,ids=data["pos"],data["particle_ids"]
    ds,dc=sdf(solid,pos),sdf(cavity,pos)
    inside=dc<=0
    # A nonplanar audit cap includes some air above the lowest scallop. Do not
    # call incoming source particles "already splashed over the rim" merely
    # because they entered that cap. Require prior entry BELOW EVERY lip.
    entered[ids[inside&(pos[:,2]<lowest_rim-.001)]]=True
    over_rim[ids[entered[ids]&(pos[:,2]>local_rim_height(pos)+.0002)]]=True
    # Well away from both the rim and floor, an outside point can be tested
    # against actual outer triangles rather than an inner-radius heuristic.
    outside=(dc>.0002)&(ds>.0002)&(pos[:,2]<local_rim_height(pos)-.001)&(pos[:,2]>floor-.003)
    escaped[ids[outside&entered[ids]]]=True
    new=outside&entered[ids]&(first_escape[ids]==0)
    first_escape[ids[new]]=frame
    penetration=ds<-.0001
    rows[str(frame)]={
        "cup_particle_rest_volume_ml":int(inside.sum())*settings["particle_volume_ml"],
        "active_particle_count":len(pos),
        "total_mass_kg":len(pos)*settings["particle_mass_kg"],
        "outside_mass_ml":int(outside.sum())*settings["particle_volume_ml"],
        "exterior_below_rim_particles":int(outside.sum()),
        "ceramic_penetration_over_0_1mm_particles":int(penetration.sum()),
        "max_ceramic_penetration_mm":float(max(0,-ds.min())*1000) if len(ds) else 0.}
    surface_path=case/f"surfaces/frame_{frame:04d}.npz"
    if surface_path.exists():
        vertices=np.load(surface_path)["vertices"]
        triangles=np.load(surface_path)["triangles"]
        ss,sc=sdf(solid,vertices),sdf(cavity,vertices)
        low=vertices[:,2]<local_rim_height(vertices)-.001
        exterior=(sc>.0002)&(ss>.0002)&low&(vertices[:,2]>floor-.003)
        surface_rows[str(frame)]={"actual_exterior_vertices_below_rim":int(exterior.sum()),
            "actual_ceramic_penetration_over0_1mm_vertices":int((ss<-.0001).sum()),
            "max_material_penetration_mm":float(max(0,-ss.min())*1000) if len(ss) else 0.}
        # Remove every above-rim vertex before testing connectivity. A detached
        # outside splash must not be mistaken for a cup-interior surface that
        # directly crosses through solid below the lowest real lip.
        edges=np.vstack((triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]]))
        edges=edges[low[edges].all(1)]
        graph=coo_matrix((np.ones(len(edges),dtype=np.uint8),(edges[:,0],edges[:,1])),shape=(len(vertices),len(vertices))).tocsr()
        if len(vertices):
            _,labels=connected_components(graph,directed=False)
            inside_labels=np.unique(labels[(sc<-.0002)&low])
            outside_labels=np.unique(labels[exterior])
            crossing_labels=np.intersect1d(inside_labels,outside_labels)
        else:
            crossing_labels=np.empty(0,dtype=int)
        surface_rows[str(frame)]["below_rim_inside_to_exterior_connected_components"]=len(crossing_labels)
    if frame in (16,17,18,24,48,72,84,96):
        print("ACTUAL_CUP_FRAME="+json.dumps({"frame":frame,**rows[str(frame)],"surface":surface_rows.get(str(frame))}),flush=True)

all_audit=json.loads((case/"particle_audit.json").read_text())["frames"]
delete_frame=settings.get("deletion_frame")
stop_frame=settings.get('stop_flow_frame')
emission_end=min(84,delete_frame-1 if delete_frame is not None else 84,stop_frame-1 if stop_frame is not None else 84)
checks={"all96frames":all(str(f) in rows for f in range(1,97)),
    "native_emission_matches_intervention":all(r["new_particles"]==(settings["particles_per_frame"] if 13<=int(f)<=emission_end else 0) for f,r in all_audit.items()),
    "particle_count_matches_intervention":all(r["active_particles"]==(0 if delete_frame is not None and int(f)>=delete_frame else settings["particles_per_frame"]*max(0,min(int(f),emission_end)-12)) for f,r in all_audit.items())}

unexplained=np.flatnonzero(escaped&~over_rim)
result={"case":str(case),"method":"Exact actual-cup world triangle signed distances; fixed native mass; cavity cap only for audit",
    "checks":checks,"frames":rows,"surface_frames":surface_rows,
    "floor_m":floor,"lowest_actual_rim_m":lowest_rim,"highest_actual_rim_m":highest_rim,
    "rim_history_rule":"Enter actual cavity below lowest rim-1mm first; only a later position above the actual azimuth-local scalloped rim+0.2mm counts as over-rim. Incoming jet above an audit cap is not splash evidence.",
    "entered_then_exterior_ids":np.flatnonzero(escaped).tolist(),
    "exterior_ids_without_observed_over_rim":unexplained.tolist(),
    "first_exterior_frame":{str(i):int(first_escape[i]) for i in np.flatnonzero(escaped)},
    "max_ceramic_penetration_mm":max(r["max_ceramic_penetration_mm"] for r in rows.values()),
    "max_particles_inside_ceramic_over0_1mm":max(r["ceramic_penetration_over_0_1mm_particles"] for r in rows.values()),
    "elapsed_seconds":time.monotonic()-start,
    "note":"24fps outside IDs require trajectory review; accumulation success is not impermeability success."}
(case/("actual_cup_audit_selected.json" if a.frames else "actual_cup_audit.json")).write_text(json.dumps(result,indent=2)+"\n")
if not a.frames:
    (case/"genesis_audit.json").write_text(json.dumps(result,indent=2)+"\n")
print("ACTUAL_CUP_AUDIT="+json.dumps({k:v for k,v in result.items() if k not in ("frames","surface_frames","entered_then_exterior_ids","first_exterior_frame","exterior_ids_without_observed_over_rim")}),flush=True)
print("UNEXPLAINED_EXTERIOR_ID_COUNT="+str(len(unexplained)),flush=True)
