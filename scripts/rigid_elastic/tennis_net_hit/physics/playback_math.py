"""State interpolation using native positions/velocities and native skin topology."""
import numpy as np

def hermite(p0,v0,p1,v1,alpha,dt):
    a=float(alpha);p0=np.asarray(p0,np.float64);p1=np.asarray(p1,np.float64)
    v0=np.asarray(v0,np.float64);v1=np.asarray(v1,np.float64)
    return (2*a**3-3*a*a+1)*p0+(a**3-2*a*a+a)*dt*v0+(-2*a**3+3*a*a)*p1+(a**3-a*a)*dt*v1

def thicken(mid,faces,thickness):
    # Same area-weighted normals and vertex order as the native exporter.
    mid=np.asarray(mid,np.float64);normal=np.zeros_like(mid)
    tri=mid[faces];area=np.cross(tri[:,1]-tri[:,0],tri[:,2]-tri[:,0])
    for j in range(3):np.add.at(normal,faces[:,j],area)
    length=np.linalg.norm(normal,axis=1)
    if np.any(length<1e-15):raise ValueError('Degenerate native webbing normal')
    normal/=length[:,None]
    return np.concatenate((mid+normal*thickness/2,mid-normal*thickness/2))
