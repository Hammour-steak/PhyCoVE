"""Common cotton scarf: free ends, native ribbon fringe, SI geometry."""
from pathlib import Path
import hashlib,json,sys
sys.path.insert(0,str(Path(__file__).resolve().parents[3]))
from pcve_assets import asset
CASE='scarf_chair_slip'
HERE=Path(__file__).resolve().parent
REPO=HERE.parents[3]
# Data locations; physics below is byte-identical to the executed source of the accepted delivery.
ASSETS=asset('scenes/'+CASE)          # prepared chair, scarf fabric and room assets
NATIVE=ASSETS/'native'                # accepted native output per case: cache.npz, simulation_config.json
RUNTIME=REPO/'.runtime'/CASE          # pyuipc 0.0.29 install record and wheel (CPython runtime staged on the pool worker)
DELIVERY=REPO/'renders'/CASE/'accepted'    # accepted delivery (audits, portable scenes, reference videos)
WORK=REPO/'renders'/CASE/'rebuild'    # reproduction outputs, launch receipts and logs
PHYSICS=dict(scarf_young_modulus=4e6,scarf_density=420.,scarf_thickness=.00035,
 scarf_poisson_ratio=.3,scarf_friction=.32,scarf_self_friction=.55,scarf_floor_friction=.45,scarf_book_friction=.45,
 scarf_bending_reference_nm=4e-6,scarf_modulus_reference_pa=4e6,
 chair_mass=6.718874313889162,chair_active=[1],book_active=[0],book_location=[.025,.015,.496],book_dimensions=[.245,.19,.037],book_mass=.65,
 gravity=[0.,0.,-9.81],air_density=1.225,air_drag_coefficient=1.15)
LAYOUT=dict(width=.27,long_side=.60,short_side=.18,fringe_length=.035,fringe_segments=6,rail_y=.17856,rail_z=1.058,
 rail_radius_y=.035,rail_radius_z=.025,front_outward_tangent=.65,short_outward_tangent=.45,
 chair_geometry_dir='prepared_chair',chair_collision_file='chair_collision_closed.npz',chair_revision='household_chair',
 chair_ground_clearance=.0012,camera_location=[2.25,-.85,2.3],camera_target=[-.025,.055,.65],camera_lens=40.,
 fps=24,duration=4.,release_time=0.,construction_revision='free_hanging_native_fringe',initial_seat_contact_permitted=False)
def save(p,data):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(data,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def scarf(pitch=.006):
 import numpy as np
 fl=LAYOUT['fringe_length'];front=LAYOUT['long_side']+fl;back=LAYOUT['short_side']+fl
 theta=np.linspace(0,np.pi,2001);arc=np.c_[LAYOUT['rail_y']-LAYOUT['rail_radius_y']*np.cos(theta),LAYOUT['rail_z']+LAYOUT['rail_radius_z']*np.sin(theta)]
 aa=np.r_[0,np.cumsum(np.linalg.norm(np.diff(arc,axis=0),axis=1))];length=front+aa[-1]+back
 def arm(side,total):
  distance=np.linspace(0,total,2501);slope=LAYOUT['front_outward_tangent']if side=='front'else LAYOUT['short_outward_tangent'];beta=np.arcsin(slope)*(1-np.exp(-distance/(.045 if side=='front'else .006)))
  dy=np.r_[0,np.cumsum((np.sin(beta[1:])+np.sin(beta[:-1]))*.5*np.diff(distance))];dz=np.r_[0,np.cumsum((np.cos(beta[1:])+np.cos(beta[:-1]))*.5*np.diff(distance))]
  return distance,dy,dz
 fdist,fdy,fdz=arm('front',front);bdist,bdy,bdz=arm('back',back)
 def centre(s):
  t=np.asarray(s)-front;y=np.interp(np.clip(t,0,aa[-1]),aa,arc[:,0]);z=np.interp(np.clip(t,0,aa[-1]),aa,arc[:,1]);f=t<0;b=t>aa[-1]
  y=np.where(f,arc[0,0]-np.interp(-t,fdist,fdy),y);z=np.where(f,LAYOUT['rail_z']-np.interp(-t,fdist,fdz),z)
  y=np.where(b,arc[-1,0]+np.interp(t-aa[-1],bdist,bdy),y);z=np.where(b,LAYOUT['rail_z']-np.interp(t-aa[-1],bdist,bdz),z)
  return y,z
 nx=round(LAYOUT['width']/pitch)+1;ny=round((length-2*fl)/pitch)+1
 u,s=np.meshgrid(np.linspace(0,1,nx),np.linspace(fl,length-fl,ny),indexing='ij');coords=[list(x)for x in np.c_[u.ravel(),s.ravel()]];faces=[]
 def point(uu,ss):coords.append([uu,ss]);return len(coords)-1
 roots=[]
 for i in range(nx-1):
  ui=i/(nx-1);du=1/(nx-1)
  for j in range(ny-1):
   a=i*ny+j;b=a+ny;c=a+1;d=b+1
   if j==0:
    p=point(ui+.30*du,fl);q=point(ui+.70*du,fl);faces.extend([(c,a,p),(c,p,q),(c,q,b),(c,b,d)]);roots.append((0,i,p,q,ui+.30*du,ui+.70*du))
   elif j==ny-2:
    p=point(ui+.30*du,length-fl);q=point(ui+.70*du,length-fl);faces.extend([(a,b,d),(a,d,q),(a,q,p),(a,p,c)]);roots.append((1,i,p,q,ui+.30*du,ui+.70*du))
   else:faces.extend([(a,b,d),(a,d,c)]if(i+j)%2 else[(a,b,c),(c,b,d)])
 for end,i,a,b,ua,ub in roots:
  actual=fl*(.88+.12*np.cos(i*1.91+end*.73));start=fl if end==0 else length-fl
  for k in range(1,LAYOUT['fringe_segments']+1):
   ss=start+(-1 if end==0 else 1)*actual*k/LAYOUT['fringe_segments'];c=point(ua,ss);d=point(ub,ss)
   faces.extend([(a,d,b),(a,c,d)]if end==0 else[(a,b,d),(a,d,c)]);a,b=c,d
 coords=np.asarray(coords);u=coords[:,0];s=coords[:,1];y,z=centre(s)
 eps=1e-5;ya,za=centre(s-eps);yb,zb=centre(s+eps);dy=yb-ya;dz=zb-za;norm=np.maximum(np.hypot(dy,dz),1e-12);normal_y=-dz/norm;normal_z=dy/norm
 distance=np.maximum(np.maximum(front-s,s-front-aa[-1]),0.);fade=1-np.exp(-(distance/.09)**2)
 twist=.055*np.sin(2*np.pi*s/length+.8)*fade;lateral=LAYOUT['width']*(u-.5)
 crease=.0035*np.sin(4*np.pi*u+.65*np.sin(5*s/length))*fade
 offset=lateral*np.sin(twist)+crease
 x=0.+lateral*np.cos(twist);y+=offset*normal_y;z+=offset*normal_z+LAYOUT['chair_ground_clearance']
 placed=np.c_[x,y,z];rest=np.c_[lateral,np.full_like(s,-.7),1.4-s];uv=np.c_[u,s/length]
 return placed,np.asarray(faces,np.int32),uv,rest,(nx,ny),float(length)
