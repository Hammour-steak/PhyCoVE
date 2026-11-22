"""Normalize a pinned CC0 egg and build a signed-distance contact asset."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
from pathlib import Path
import bpy,numpy as np,json,hashlib,time
from mathutils import Vector,Matrix
from mathutils.bvhtree import BVHTree
S=Path(__file__).resolve().parents[1]
import argparse,sys
sys.path.insert(0,str(S))
ap=argparse.ArgumentParser();ap.add_argument('--out-dir',type=Path,default=S/'assets/rigid_egg');args=ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
A=args.out_dir;start=time.monotonic()
from download_rigid_egg import prepare
prepare(A)
if (A/'asset_manifest.json').is_file():
 old=json.loads((A/'asset_manifest.json').read_text())
 for item in old['assets']:
  if hashlib.sha256((A/item['path']).read_bytes()).hexdigest()!=item['sha256']:raise RuntimeError('Existing derived egg asset differs: '+item['path'])
 print('Verified existing pinned egg geometry and textures');raise SystemExit(0)

bpy.ops.object.select_all(action="SELECT");bpy.ops.object.delete(use_global=False)
with bpy.data.libraries.load(str(A/"egg_01_4k.blend"),link=False) as (src,dst):dst.objects=["Egg"]
o=dst.objects[0];bpy.context.collection.objects.link(o);bpy.context.view_layer.update()
dg=bpy.context.evaluated_depsgraph_get();evaluated=o.evaluated_get(dg)
mesh=bpy.data.meshes.new_from_object(evaluated,preserve_all_data_layers=True,depsgraph=dg)
points=np.array([list(evaluated.matrix_world@v.co) for v in mesh.vertices],dtype=float)
scale=.060/np.ptp(points[:,2]);points*=scale
mesh.calc_loop_triangles();faces=np.array([t.vertices[:] for t in mesh.loop_triangles],dtype=np.int32)
a,b,c=points[faces].transpose(1,0,2);vol=np.einsum("ij,ij->i",a,np.cross(b,c))/6
if vol.sum()<0:faces=faces[:,::-1];a,b,c=points[faces].transpose(1,0,2);vol=-vol
volume=vol.sum();summed=a+b+c;com=(vol[:,None]*summed/4).sum(0)/volume
second=(vol[:,None,None]*(np.einsum("ni,nj->nij",summed,summed)+np.einsum("ni,nj->nij",a,a)+np.einsum("ni,nj->nij",b,b)+np.einsum("ni,nj->nij",c,c))/20).sum(0)
Ip=(np.trace(second)*np.eye(3)-second)/volume-(np.dot(com,com)*np.eye(3)-np.outer(com,com))
assert np.linalg.eigvalsh(Ip).min()>0
points-=com
edges=np.sort(np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]]),axis=1);unique,counts=np.unique(edges,axis=0,return_counts=True);assert (counts==2).all()
o.data=mesh;o.parent=None;o.matrix_world=Matrix.Identity(4);o.modifiers.clear();o.constraints.clear();o.animation_data_clear()
o.data.vertices.foreach_set("co",points.astype(np.float32).ravel());o.data.update()
o.name="Whole brown egg • six degree-of-freedom rigid pose";o["rigid_interaction"]=True
for p in o.data.polygons:p.use_smooth=True
for im in bpy.data.images:
 if im.source=="FILE" and not im.packed_file:im.pack()
bpy.ops.wm.save_as_mainfile(filepath=str(A/"normalized_egg.blend"))
bvh=BVHTree.FromPolygons([Vector(p) for p in points],faces.tolist(),all_triangles=True)
lo=points.min(0)-.005;hi=points.max(0)+.005;N=129;spacing=(hi-lo)/(N-1);grid=np.empty((N,N,N),dtype=np.float32);zs=np.linspace(lo[2],hi[2],N)
for i,x in enumerate(np.linspace(lo[0],hi[0],N)):
 for j,y in enumerate(np.linspace(lo[1],hi[1],N)):
  # Float64 projected-triangle intersections avoid repeated near-identical
  # BVH hits at shared edges. Distances still use BVH nearest triangles.
  tri=points[faces];ab=tri[:,1]-tri[:,0];ac=tri[:,2]-tri[:,0]
  det=ab[:,0]*ac[:,1]-ab[:,1]*ac[:,0];valid=np.abs(det)>1e-16
  dx=x-tri[:,0,0];dy=y-tri[:,0,1];safe=np.where(valid,det,1)
  u=(dx*ac[:,1]-dy*ac[:,0])/safe;v=(ab[:,0]*dy-ab[:,1]*dx)/safe
  inside_tri=valid&(u>=-1e-10)&(v>=-1e-10)&(u+v<=1+1e-10)
  hits=np.sort((tri[:,0,2]+u*ab[:,2]+v*ac[:,2])[inside_tri])
  intersections=hits[np.r_[True,np.diff(hits)>1e-8]].tolist() if len(hits) else []
  if len(intersections)%2:raise RuntimeError(f"Odd vertical ray crossings at {i},{j}: {intersections}")
  for k,z in enumerate(zs):
   hit,normal,index,distance=bvh.find_nearest(Vector((x,y,z)))
   inside=sum(z>h for h in intersections)%2==1
   grid[i,j,k]=-distance if inside else distance
 if i%16==0:print(json.dumps({"phase":"sdf","x_slice":i,"wall_s":time.monotonic()-start}),flush=True)
def interp(p):
 q=(p-lo)/spacing;base=np.floor(q).astype(int);base=np.clip(base,0,N-2);f=q-base;out=np.zeros(len(p))
 for i in (0,1):
  for j in (0,1):
   for k in (0,1):
    weight=(f[:,0] if i else 1-f[:,0])*(f[:,1] if j else 1-f[:,1])*(f[:,2] if k else 1-f[:,2])
    out+=weight*grid[base[:,0]+i,base[:,1]+j,base[:,2]+k]
 return out
rng=np.random.default_rng(1101);fi=rng.integers(len(faces),size=20000);bary=rng.dirichlet([1,1,1],size=20000);samples=(points[faces[fi]]*bary[:,:,None]).sum(1)
error=np.abs(interp(samples));assert error.max()<.0001,error.max()
np.savez_compressed(A/"rigid_geometry.npz",vertices=points,faces=faces,sdf=grid,sdf_min=lo,sdf_spacing=spacing,inertia_per_mass_m2=Ip,volume_m3=volume)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
source=json.loads((A/"source_asset.json").read_text())
manifest={"kind":"rigid whole intact brown egg; no shell fracture or internal contents simulated","source":source,"source_dimensions_after_uniform_scale_m":np.ptp(points,axis=0).tolist(),"uniform_scale":scale,"source_center_of_mass_before_translation_m":com.tolist(),"homogeneous_effective_volume_m3":volume,"inertia_per_mass_m2":Ip.tolist(),"bounding_radius_m":float(np.linalg.norm(points,axis=1).max()),"vertices":len(points),"triangles":len(faces),"closed_manifold":True,"sdf":{"shape":[N]*3,"min_m":lo.tolist(),"spacing_m":spacing.tolist(),"sign_method":"Closed-mesh vertical ray parity; exact BVH nearest-triangle distances at grid samples","surface_interpolation_max_error_m":float(error.max()),"surface_interpolation_p95_error_m":float(np.percentile(error,95)),"surface_samples":len(samples)},"assets":[{"path":name,"sha256":sha(A/name),"bytes":(A/name).stat().st_size} for name in ("egg_01_4k.blend","normalized_egg.blend","rigid_geometry.npz","source_asset.json","source_metadata.json")],"wall_seconds":time.monotonic()-start}
(A/"asset_manifest.json").write_text(json.dumps(manifest,indent=2)+"\n")
print(json.dumps(manifest),flush=True)

