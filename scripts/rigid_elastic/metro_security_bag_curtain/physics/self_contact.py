"""Adjacent-shell vertex/face and edge/edge contact, with passive Coulomb slip."""
import numpy as np
from numba import njit

def topology(triangles,strip_ids):
    edges=np.unique(np.sort(np.vstack((triangles[:,[0,1]],triangles[:,[1,2]],triangles[:,[2,0]])),axis=1),axis=0)
    def offsets(groups):
        assert np.all(np.diff(groups)>=0)
        return np.r_[0,np.cumsum(np.bincount(groups,minlength=6))].astype(np.int64)
    return edges,offsets(strip_ids),offsets(strip_ids[triangles[:,0]]),offsets(strip_ids[edges[:,0]])

@njit(cache=True)
def dot(a,b):return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

@njit(cache=True)
def cross(a,b):return np.array((a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]))

@njit(cache=True)
def rebuild(x,tri,edges,vo,to,eo,padding,vpairs,epairs):
    lo=np.empty((len(tri),3));hi=np.empty_like(lo)
    for t in range(len(tri)):
        for d in range(3):
            lo[t,d]=min(x[tri[t,0],d],x[tri[t,1],d],x[tri[t,2],d])
            hi[t,d]=max(x[tri[t,0],d],x[tri[t,1],d],x[tri[t,2],d])
    el=np.empty((len(edges),3));eh=np.empty_like(el)
    for e in range(len(edges)):
        for d in range(3):el[e,d]=min(x[edges[e,0],d],x[edges[e,1],d]);eh[e,d]=max(x[edges[e,0],d],x[edges[e,1],d])
    nv=0;ne=0
    for k in range(5):
        for direction in range(2):
            va=k if direction==0 else k+1;tb=k+1 if direction==0 else k
            for i in range(vo[va],vo[va+1]):
                for t in range(to[tb],to[tb+1]):
                    if x[i,1]<lo[t,1]-padding or x[i,1]>hi[t,1]+padding:continue
                    if x[i,2]<lo[t,2]-padding or x[i,2]>hi[t,2]+padding:continue
                    if x[i,0]<lo[t,0]-padding or x[i,0]>hi[t,0]+padding:continue
                    vpairs[nv,0]=i;vpairs[nv,1]=t;nv+=1
        for a in range(eo[k],eo[k+1]):
            for b in range(eo[k+1],eo[k+2]):
                if eh[a,1]+padding<el[b,1] or eh[b,1]+padding<el[a,1]:continue
                if eh[a,2]+padding<el[b,2] or eh[b,2]+padding<el[a,2]:continue
                if eh[a,0]+padding<el[b,0] or eh[b,0]+padding<el[a,0]:continue
                epairs[ne,0]=a;epairs[ne,1]=b;ne+=1
    return nv,ne

@njit(cache=True)
def displacement(x,anchor):
    maximum=0.
    for i in range(len(x)):
        dx=x[i]-anchor[i];maximum=max(maximum,dot(dx,dx))
    return np.sqrt(maximum)

@njit(cache=True)
def face_data(x,old,vertex,face):
    a,b,c=face[0],face[1],face[2];e=x[b]-x[a];f=x[c]-x[a]
    n=cross(e,f);length=np.sqrt(dot(n,n))
    if length<1e-14:return False,np.zeros(3),np.zeros(3),0.
    n/=length;p=x[vertex]-x[a]
    ee=dot(e,e);ef=dot(e,f);ff=dot(f,f);den=ee*ff-ef*ef
    u=(ff*dot(e,p)-ef*dot(f,p))/den;v=(ee*dot(f,p)-ef*dot(e,p))/den
    bary=np.array((1-u-v,u,v))
    if bary.min()<-1e-7:return False,n,bary,0.
    distance=dot(n,p);previous=old[vertex]-(bary[0]*old[a]+bary[1]*old[b]+bary[2]*old[c])
    sign=1. if dot(n,previous)>=0 else -1.
    return True,n*sign,bary,distance*sign

@njit(cache=True)
def edge_data(x,old,ea,eb):
    a,b,c,d=ea[0],ea[1],eb[0],eb[1]
    u=x[b]-x[a];v=x[d]-x[c];w=x[a]-x[c]
    aa=dot(u,u);bb=dot(u,v);cc=dot(v,v);dd=dot(u,w);ee=dot(v,w);den=aa*cc-bb*bb
    s=min(1.,max(0.,(bb*ee-cc*dd)/den)) if den>1e-18 else 0.
    t=(bb*s+ee)/cc
    if t<0:t=0.;s=min(1.,max(0.,-dd/aa))
    elif t>1:t=1.;s=min(1.,max(0.,(bb-dd)/aa))
    delta=(1-s)*x[a]+s*x[b]-(1-t)*x[c]-t*x[d];distance=np.sqrt(dot(delta,delta))
    if distance>1e-12:n=delta/distance
    else:
        n=(1-s)*old[a]+s*old[b]-(1-t)*old[c]-t*old[d];length=np.sqrt(dot(n,n))
        if length<1e-12:
            n=cross(u,v);length=np.sqrt(dot(n,n))
            if length<1e-12:n=cross(u,np.array((1.,0.,0.)));length=np.sqrt(dot(n,n))
        n/=max(length,1e-12)
    return n,np.array((1-s,s)),np.array((1-t,t)),distance

@njit(cache=True,inline='always')
def swept_face_overlap(x,old,i,face,h):
    for d in range(3):
        lo=min(x[face[0],d],x[face[1],d],x[face[2],d],old[face[0],d],old[face[1],d],old[face[2],d])
        hi=max(x[face[0],d],x[face[1],d],x[face[2],d],old[face[0],d],old[face[1],d],old[face[2],d])
        if min(x[i,d],old[i,d])>hi+h or max(x[i,d],old[i,d])<lo-h:return False
    return True

@njit(cache=True,inline='always')
def swept_edge_overlap(x,old,a,b,h):
    for d in range(3):
        la=min(x[a[0],d],x[a[1],d],old[a[0],d],old[a[1],d]);ha=max(x[a[0],d],x[a[1],d],old[a[0],d],old[a[1],d])
        lb=min(x[b[0],d],x[b[1],d],old[b[0],d],old[b[1],d]);hb=max(x[b[0],d],x[b[1],d],old[b[0],d],old[b[1],d])
        if la>hb+h or lb>ha+h:return False
    return True

@njit(cache=True)
def project(x,old,inv,tri,edges,vpairs,nv,epairs,ne,lv,le,thickness):
    maximum=0.
    for k in range(nv):
        i,t=vpairs[k];face=tri[t]
        if lv[k]<=0 and not swept_face_overlap(x,old,i,face,thickness):continue
        valid,n,bary,d=face_data(x,old,i,face)
        if not valid:continue
        gap=d-thickness
        if gap>=0 and lv[k]<=0:continue
        den=inv[i]
        for j in range(3):den+=inv[face[j]]*bary[j]*bary[j]
        if den<1e-14:continue
        dl=max(-lv[k],-gap/den);lv[k]+=dl;x[i]+=inv[i]*dl*n
        for j in range(3):x[face[j]]-=inv[face[j]]*bary[j]*dl*n
        maximum=max(maximum,-gap)
    for k in range(ne):
        ia,ib=epairs[k];ea,eb=edges[ia],edges[ib]
        if le[k]<=0 and not swept_edge_overlap(x,old,ea,eb,thickness):continue
        n,wa,wb,d=edge_data(x,old,ea,eb);gap=d-thickness
        if gap>=0 and le[k]<=0:continue
        den=0.
        for j in range(2):den+=inv[ea[j]]*wa[j]*wa[j]+inv[eb[j]]*wb[j]*wb[j]
        if den<1e-14:continue
        dl=max(-le[k],-gap/den);le[k]+=dl
        for j in range(2):x[ea[j]]+=inv[ea[j]]*wa[j]*dl*n;x[eb[j]]-=inv[eb[j]]*wb[j]*dl*n
        maximum=max(maximum,-gap)
    return maximum

@njit(cache=True)
def friction(x,old,v,inv,tri,edges,vpairs,nv,epairs,ne,lv,le,dt,mu):
    diss=0.
    for k in range(nv):
        if lv[k]<=0:continue
        i,t=vpairs[k];face=tri[t];valid,n,w,d=face_data(x,old,i,face)
        if not valid:continue
        relative=v[i].copy();den=inv[i]
        for j in range(3):relative-=w[j]*v[face[j]];den+=inv[face[j]]*w[j]*w[j]
        tangent=relative-dot(relative,n)*n;speed=np.sqrt(dot(tangent,tangent))
        if speed<1e-10 or den<1e-14:continue
        direction=tangent/speed;J=min(speed/den,mu*lv[k]/dt)
        v[i]-=inv[i]*J*direction
        for j in range(3):v[face[j]]+=inv[face[j]]*w[j]*J*direction
        diss+=J*speed-.5*J*J*den
    for k in range(ne):
        if le[k]<=0:continue
        ia,ib=epairs[k];ea,eb=edges[ia],edges[ib];n,wa,wb,d=edge_data(x,old,ea,eb)
        relative=np.zeros(3);den=0.
        for j in range(2):relative+=wa[j]*v[ea[j]]-wb[j]*v[eb[j]];den+=inv[ea[j]]*wa[j]*wa[j]+inv[eb[j]]*wb[j]*wb[j]
        tangent=relative-dot(relative,n)*n;speed=np.sqrt(dot(tangent,tangent))
        if speed<1e-10 or den<1e-14:continue
        direction=tangent/speed;J=min(speed/den,mu*le[k]/dt)
        for j in range(2):v[ea[j]]-=inv[ea[j]]*wa[j]*J*direction;v[eb[j]]+=inv[eb[j]]*wb[j]*J*direction
        diss+=J*speed-.5*J*J*den
    return diss
