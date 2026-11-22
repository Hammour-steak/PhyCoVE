"""Settle a separate decorative cloth on the actual basket mesh, then freeze it."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
_scene_sys.path.append(str(_ScenePath(__file__).resolve().parents[3]))  # scripts/, for pcve_assets
import bpy,numpy as np,sys,json,hashlib,time,argparse,datetime,io
from pathlib import Path
S=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(S));from scene_geometry import import_metric_prop,box,material
# The renderer reads the settled cloth from the scene's registered asset folder (scene_asset), in every
# frame. A new solve goes to a fresh run folder; it replaces a registered file only when asked with --out
# and when its sha256 equals the one in assets.json, unless --force is given.
from pcve_assets import scene_asset,REPO
ASSET=scene_asset(S,'assets/generated').resolve()
p=argparse.ArgumentParser(prog='generate_basket_linen.py',description='Settle the decorative cloth on the basket (run inside Blender, options after --).')
p.add_argument('--out',type=Path,default=REPO/'renders'/S.name/'rebuild'/datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ'),
 help=f'output folder (default: renders/{S.name}/rebuild/<UTC time>); the registered folder {ASSET} is checked against assets.json')
p.add_argument('--force',action='store_true',help='replace registered files even when their new sha256 differs from assets.json')
a=p.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])
R=a.out.expanduser().resolve();R.mkdir(parents=True,exist_ok=True)
bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
# Only the scene-local CC0 basket and a floor take part in this auxiliary cloth solve.
root=import_metric_prop('wicker_basket_01',[.015,.79,0],.3832,-.07)
for o in list(bpy.data.objects):
 if o.type=='MESH':
  mod=o.modifiers.new('Basket fabric collision','COLLISION');o.collision.thickness_outer=.0015;o.collision.thickness_inner=.001
# The woven basket has thread-sized gaps. A continuous front envelope prevents
# decorative cloth samples from passing between individual wicker strands.
front=box('Continuous wicker front collision envelope',(.015,.625,.0585),(.40,.016,.117),material('Envelope',(.4,.4,.4,1)),.007)
front.modifiers.new('Continuous weave collision','COLLISION');front.collision.thickness_outer=.0015
floor=box('Floor for decorative fabric settlement',(0,.7,-.008),(1.2,1.2,.016),material('Grey',(.4,.4,.4,1)),0)
floor.modifiers.new('Floor collision','COLLISION');floor.collision.thickness_outer=.0008
nx,ny=36,60;verts=[];faces=[]
for j in range(ny+1):
 v=j/ny
 for i in range(nx+1):
  u=i/nx
  x=-.016+.178*u;y=.49+.448*v
  z=.119+.022*(1-v)+.002*np.sin(u*9+v*3)*(1-v)
  verts.append((x,y,z))
for j in range(ny):
 for i in range(nx):
  k=j*(nx+1)+i;faces.append((k,k+1,k+nx+2,k+nx+1))
mesh=bpy.data.meshes.new('Natural linen quadrilateral grid');mesh.from_pydata(verts,[],faces);mesh.update()
cloth=bpy.data.objects.new('Decorative rim-tucked linen',mesh);bpy.context.collection.objects.link(cloth)
pins=cloth.vertex_groups.new(name='Fabric edge tucked at rear basket rim')
pins.add(list(range(ny*(nx+1),(ny+1)*(nx+1))),1.,'REPLACE')
mod=cloth.modifiers.new('Gravity settlement for decorative linen','CLOTH')
s=mod.settings;s.vertex_group_mass=pins.name;s.pin_stiffness=1.;s.quality=8;s.mass=.12;s.tension_stiffness=22;s.compression_stiffness=22;s.shear_stiffness=12;s.bending_stiffness=.035
s.tension_damping=6;s.compression_damping=6;s.shear_damping=6;s.bending_damping=.6;s.air_damping=4
mod.collision_settings.use_collision=True;mod.collision_settings.distance_min=.001
mod.collision_settings.use_self_collision=True;mod.collision_settings.self_distance_min=.001;mod.collision_settings.collision_quality=5
mod.point_cache.frame_start=1;mod.point_cache.frame_end=100
sc=bpy.context.scene;sc.render.fps=24;sc.frame_start=1;sc.frame_end=100
start=time.monotonic()
for f in range(1,101):
 sc.frame_set(f);deps=bpy.context.evaluated_depsgraph_get();ev=cloth.evaluated_get(deps);_ = ev.to_mesh();ev.to_mesh_clear()
 if f%20==0:print('settled',f,'seconds',round(time.monotonic()-start,1),flush=True)
deps=bpy.context.evaluated_depsgraph_get();evaluated=cloth.evaluated_get(deps);mesh=evaluated.to_mesh()
points=np.array([evaluated.matrix_world@v.co for v in mesh.vertices]);faces=np.array([list(p.vertices) for p in mesh.polygons]);evaluated.to_mesh_clear()
original=np.array(verts);uv=np.array([(i/nx*.178/.4,j/ny*.448/.4) for j in range(ny+1) for i in range(nx+1)])
buffer=io.BytesIO();np.savez_compressed(buffer,vertices=points,faces=faces,uv=uv);npz=buffer.getvalue()
report={'source':'Original Blender cloth gravity settlement on the existing CC0 basket mesh and planar floor; rear fabric edge is tucked at the basket rim','physics_scope':'Auxiliary decorative cloth only. Final mesh is static; benchmark MuJoCo vehicle/silicone inputs and trajectories are untouched.','blender':bpy.app.version_string,'frames':100,'fps':24,'seconds':time.monotonic()-start,'cloth_original_size_m':[.178,.448],'vertices':len(points),'min_m':points.min(axis=0).tolist(),'max_m':points.max(axis=0).tolist(),'minimum_y_vs_vehicle_corridor_m':float(points[:,1].min()-.14),'sha256':hashlib.sha256(npz).hexdigest(),'files':['settled_linen_envelope.npz'],'collision_envelope':'Continuous auxiliary front weave envelope prevents cloth samples slipping through strand gaps; envelope is absent from formal render and benchmark solver', 'boundary_condition':'Last cloth vertex row held at the rear basket rim, representing a tucked cloth edge'}
assert np.isfinite(points).all() and points[:,2].min()>-.002 and points[:,1].min()>.14
data={'settled_linen_envelope.npz':npz,'linen_settlement_envelope.json':(json.dumps(report,indent=2)+'\n').encode()}
if R==ASSET:
 files=json.loads((REPO/'assets.json').read_text())['assets'].get(f'scenes/{S.name}',{}).get('files',{})
 refused=[f"{name}: new sha256 {hashlib.sha256(blob).hexdigest()}, assets.json {files.get('generated/'+name,{}).get('sha256')}" for name,blob in data.items()
          if (R/name).exists() and hashlib.sha256(blob).hexdigest()!=files.get('generated/'+name,{}).get('sha256')]
 if refused and not a.force:
  raise SystemExit(f'Refusing to replace the registered cloth the renderer reads in every frame ({R}): '+'; '.join(refused)
   +'. Write to another --out, compare, and replace the files deliberately (and their assets.json entries), or pass --force.')
for name,blob in data.items():(R/name).write_bytes(blob)
print(json.dumps({**report,'written_to':str(R)}),flush=True)
