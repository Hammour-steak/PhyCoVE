"""Reproduce the original, closed volumetric modeling-dough mesh in meters."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse,math
from pathlib import Path
import numpy as np
from scipy.spatial import Delaunay
from dough_config import ASSETS,write_json,digest

def prepare(out,spacing=.0048,layers=7,xy_scale=1.,profile='domed_pad'):
 out=Path(out);out.mkdir(parents=True,exist_ok=True)
 if (out/'geometry.npz').exists():raise FileExistsError(out/'geometry.npz')
 # Hexagonal disk sampling avoids skinny center wedges. A single indexed disk
 # is extruded with a globally consistent prism diagonal, so internal faces pair.
 disk=[[0.,0.]]
 for iy in range(-math.ceil(.050/(spacing*math.sqrt(3)/2))-1,math.ceil(.050/(spacing*math.sqrt(3)/2))+2):
  for ix in range(-math.ceil(.060/spacing)-1,math.ceil(.060/spacing)+2):
   xx=(ix+.5*(iy%2))*spacing;yy=iy*spacing*math.sqrt(3)/2
   r=math.sqrt((xx/.060)**2+(yy/.050)**2)
   if .001<r<.94:disk.append([xx,yy])
 for i in range(96):
  a=2*math.pi*i/96;disk.append([.060*math.cos(a),.050*math.sin(a)])
 disk=np.array(disk);tri=Delaunay(disk).simplices;n=len(disk);verts=[];original=[]
 scale=np.array([.94,.99,1.008,1.004,.995,.983,.968])
 for k in range(layers):
  t=k/(layers-1);s=float(np.interp(t,np.linspace(0,1,7),scale))
  for xx,yy in disk:
   r=math.sqrt((xx/.06)**2+(yy/.05)**2);a=math.atan2(yy,xx)
   # Rounded kneaded perimeter and a domed, slightly irregular top.
   handmade=1+.012*math.sin(3*a+.3)*r*r+.006*math.cos(5*a)*r*r
   h=.038-.018*r**6+.00005*math.cos(xx*45)*math.cos(yy*38)
   original.append([xx*s*handmade,yy*s*handmade,t*h])
   if profile=='tall_kneaded':h=.062-.047*r*r
   elif profile!='domed_pad':raise ValueError(profile)
   verts.append([xx*s*handmade,yy*s*handmade,t*h])
 v=np.array(verts,dtype=np.float64);v[:,:2]*=xy_scale;tet=[]
 for k in range(layers-1):
  for tr in tri:
   a,b,c=sorted(tr);a+=k*n;b+=k*n;c+=k*n;A,B,C=a+n,b+n,c+n
   tet.extend([[a,b,c,C],[a,b,B,C],[a,A,B,C]])
 tet=np.array(tet,dtype=np.int32)
 def dm():return np.stack([v[tet[:,j]]-v[tet[:,0]] for j in (1,2,3)],axis=-1)
 neg=np.linalg.det(dm())<0;tet[neg,1:3]=tet[neg,2:0:-1]
 if profile=='tall_kneaded':
  old=np.asarray(original);old_dm=np.stack([old[tet[:,j]]-old[tet[:,0]] for j in (1,2,3)],axis=-1)
  target_volume=float(np.abs(np.linalg.det(old_dm)).sum()/6)
  current_volume=float(np.abs(np.linalg.det(dm())).sum()/6)
  v[:,2]*=target_volume/current_volume
 else:target_volume=None
 mat=dm();vol=np.linalg.det(mat)/6;inv=np.linalg.inv(mat);faces={}
 for tt in tet:
  for ids,other in [((1,2,3),0),((0,3,2),1),((0,1,3),2),((0,2,1),3)]:
   f=list(tt[list(ids)]);key=tuple(sorted(f))
   if key in faces:del faces[key]
   else:
    a,b,c=v[f]
    if np.dot(np.cross(b-a,c-a),v[tt[other]]-a)>0:f=f[::-1]
    faces[key]=f
 surf=np.array(list(faces.values()),dtype=np.int32)
 area=np.linalg.norm(np.cross(v[surf[:,1]]-v[surf[:,0]],v[surf[:,2]]-v[surf[:,0]]),axis=1)/2
 # Each integration point carries area/3, linear barycentric nodal loads.
 bary=np.array([[2/3,1/6,1/6],[1/6,2/3,1/6],[1/6,1/6,2/3]])
 qids=np.repeat(surf,3,axis=0);qw=np.tile(bary,(len(surf),1));qa=np.repeat(area/3,3)
 alt=3*vol[:,None]/np.stack([np.linalg.norm(np.cross(v[tet[:,ids[1]]]-v[tet[:,ids[0]]],v[tet[:,ids[2]]]-v[tet[:,ids[0]]]),axis=1)/2 for ids in ((1,2,3),(0,3,2),(0,1,3),(0,2,1))],axis=1)
 assert vol.min()>0 and alt.min()>.0001,(float(vol.min()),float(alt.min()),int(alt.argmin()//4))
 np.savez_compressed(out/'geometry.npz',rest_vertices=v,tetrahedra=tet,inverse_dm=inv,volumes=vol,
  surface_triangles=surf,quadrature_nodes=qids,quadrature_weights=qw,quadrature_area=qa)
 write_json(out/'asset_manifest.json',{'license':'CC0-1.0','source':'Original deterministic scene-owned procedural geometry and shaders; no downloaded assets',
  'reproduce':f'python prepare_assets.py --out-dir {out} --profile {profile} --xy-scale {xy_scale} --spacing {spacing} --layers {layers}','mesh_sha256':digest(out/'geometry.npz'),
  'spacing_m':spacing*xy_scale,'reference_disk_spacing_m':spacing,'xy_scale':xy_scale,'profile':profile,'mass_preserving_target_volume_m3':target_volume,'layers':layers,'nodes':len(v),'tetrahedra':len(tet),'surface_triangles':len(surf),
  'volume_m3':float(vol.sum()),'minimum_altitude_m':float(alt.min()),'bounds_m':[v.min(0).tolist(),v.max(0).tolist()],
  'material_reference':'https://academic.oup.com/ijfst/article/42/6/699/7864305',
  'notes':'Solid kneaded unproofed dough mound, closed top, sides and bottom. No cavity, bowl, liquid or fixed nodes.'})
 print((out/'asset_manifest.json').read_text())
if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--out-dir',type=Path,default=ASSETS);p.add_argument('--xy-scale',type=float,default=1.);p.add_argument('--profile',choices=['domed_pad','tall_kneaded'],default='domed_pad');p.add_argument('--spacing',type=float,default=.0048);p.add_argument('--layers',type=int,default=7);a=p.parse_args();prepare(a.out_dir,a.spacing,a.layers,a.xy_scale,a.profile)
