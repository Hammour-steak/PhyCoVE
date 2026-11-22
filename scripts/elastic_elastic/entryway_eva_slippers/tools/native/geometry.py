"""Fixed common poses, genuine volume masses and an optional fixed doorstop."""
import numpy as np

def rotation(euler_deg):
 x,y,z=np.deg2rad(euler_deg);cx,sx=np.cos(x),np.sin(x);cy,sy=np.cos(y),np.sin(y);cz,sz=np.cos(z),np.sin(z)
 return np.array([[cz,-sz,0],[sz,cz,0],[0,0,1.]])@np.array([[cy,0,sy],[0,1.,0],[-sy,0,cy]])@np.array([[1.,0,0],[0,cx,-sx],[0,sx,cx]])

def placed(z,p,name):
 v=z['vertices'].copy();t=z['tetrahedra'].copy();f=z['faces'].copy()
 if p[name+'_mirror_x']:
  v[:,0]*=-1;t[:,[1,2]]=t[:,[2,1]];f[:,[1,2]]=f[:,[2,1]]
 R=rotation(p[name+'_euler_deg']);v=v@R.T
 center=np.array(p[name+'_center_m'])
 if name=='resting':center[2]-=v[:,2].min()
 return v+center,t,f

def lumped_mass(v,t,rho):
 volume=np.linalg.det(np.stack([v[t[:,k]]-v[t[:,0]] for k in [1,2,3]],axis=-1))/6
 if np.min(volume)<=0:raise ValueError('Nonpositive rest element')
 mass=np.zeros(len(v));np.add.at(mass,t.ravel(),np.repeat(volume*rho/4,4));return mass,volume

def doorstop(p):
 n=48;r=p['doorstop_radius_m'];h=p['doorstop_height_m'];rings=[(-h/2,r*.88),(-h/2+.002,r),(h/2-.004,r),(h/2,r*.78)];v=[]
 for z,rad in rings:
  for i in range(n):v.append([rad*np.cos(2*np.pi*i/n),rad*np.sin(2*np.pi*i/n),z])
 v.extend([[0,0,-h/2],[0,0,h/2]]);f=[]
 for j in range(len(rings)-1):
  for i in range(n):a=j*n+i;b=j*n+(i+1)%n;c=(j+1)*n+(i+1)%n;d=(j+1)*n+i;f.extend([[a,b,c],[a,c,d]])
 for i in range(n):f.extend([[4*n,(i+1)%n,i],[4*n+1,3*n+i,3*n+(i+1)%n]])
 return np.asarray(v)+p['doorstop_center_m'],np.asarray(f,np.int32)
