"""Equal-and-opposite rigid/shell impulses with rotated scan SDF normals."""
import numpy as np
from numba import njit
from constitutive import sdf,dot

@njit(cache=True)
def distance(point,y,dims,thick):
    c=np.cos(y[2]);s=np.sin(y[2]);dx=point[0]-y[0];dz=point[2]-y[1]
    local=np.array((c*dx-s*dz,point[1],s*dx+c*dz+dims[2]/2))
    gap,n=sdf(local,0.,1.,0.,0.,dims,thick)
    return gap,np.array((c*n[0]+s*n[2],n[1],-s*n[0]+c*n[2]))

@njit(cache=True)
def contacts(x,inv,ids,sw,y,im,ii,dims,thick,lam,dt):
    peak=0.;imp=np.zeros(len(y))
    for b in range(len(y)):
      for i in range(len(ids)):
        point=sw[i,0]*x[ids[i,0]]+sw[i,1]*x[ids[i,1]]+sw[i,2]*x[ids[i,2]]
        if abs(point[1])>dims[1]/2+.012 or abs(point[0]-y[b,0])>.255 or abs(point[2]-y[b,1])>.255:continue
        gap,n=distance(point,y[b],dims,thick)
        if gap>=0:continue
        peak=max(peak,-gap);rx=point[0]-y[b,0];rz=point[2]-y[b,1];g=-(rz*n[0]-rx*n[2])
        den=im[b]*(n[0]*n[0]+n[2]*n[2])+ii[b]*g*g
        for j in range(3):den+=inv[ids[i,j]]*sw[i,j]*sw[i,j]
        if den<1e-15:continue
        dl=-gap/den
        for j in range(3):x[ids[i,j]]+=inv[ids[i,j]]*sw[i,j]*dl*n
        y[b,0]-=im[b]*dl*n[0];y[b,1]-=im[b]*dl*n[2];y[b,2]+=ii[b]*dl*g
        lam[b,i]+=dl;imp[b]-=dl*n[0]/dt
    return peak,imp

@njit(cache=True)
def friction(x,v,inv,ids,sw,y,u,im,ii,dims,thick,lam,dt,mu):
    diss=0.
    for b in range(len(y)):
      for i in range(len(ids)):
        if lam[b,i]<=0:continue
        point=np.zeros(3);vel=np.zeros(3)
        for j in range(3):point+=sw[i,j]*x[ids[i,j]];vel+=sw[i,j]*v[ids[i,j]]
        gap,n=distance(point,y[b],dims,thick)
        if gap>.0004:continue
        rx=point[0]-y[b,0];rz=point[2]-y[b,1]
        rel=vel-np.array((u[b,0]+u[b,2]*rz,0.,u[b,1]-u[b,2]*rx))
        tv=rel-dot(rel,n)*n;speed=np.sqrt(dot(tv,tv))
        if speed<1e-10:continue
        t=tv/speed;g=rz*t[0]-rx*t[2]
        den=im[b]*(t[0]*t[0]+t[2]*t[2])+ii[b]*g*g
        for j in range(3):den+=inv[ids[i,j]]*sw[i,j]*sw[i,j]
        if den<1e-15:continue
        J=min(speed/den,mu*lam[b,i]/dt)
        for j in range(3):v[ids[i,j]]-=inv[ids[i,j]]*sw[i,j]*J*t
        u[b,0]+=im[b]*J*t[0];u[b,1]+=im[b]*J*t[2];u[b,2]+=ii[b]*J*g
        diss+=max(0.,J*speed-.5*J*J*den)
    return diss
