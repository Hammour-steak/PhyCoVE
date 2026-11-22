"""Continuous material-frame reconstruction at actual integration steps."""
import numpy as np
from numba import njit

@njit(cache=False)
def unit(v):return v/max(np.linalg.norm(v),1e-14)

@njit(cache=False)
def transport(w,a,b):
    axis=np.cross(a,b);c=max(-1.,min(1.,np.dot(a,b)));s2=np.dot(axis,axis)
    if s2>1e-16:w=w+np.cross(axis,w)+np.cross(axis,np.cross(axis,w))*(1-c)/s2
    return unit(w-np.dot(w,b)*b)

@njit(cache=False)
def frame(x,desired,old_t,old_w,old_roll,valid):
    n=len(x);t=np.zeros_like(x);edge=np.zeros((n-1,3));length=np.zeros(n-1)
    for i in range(n-1):
        e=x[i+1]-x[i];length[i]=np.linalg.norm(e);edge[i]=e/max(length[i],1e-14)
    t[0]=edge[0];t[-1]=edge[-1]
    for i in range(1,n-1):t[i]=unit(edge[i-1]+edge[i])
    up=np.array([0.,0.,1.])-t[0,2]*t[0];up_norm=np.linalg.norm(up)
    if not valid:root=unit(up)if up_norm>.1 else unit(np.cross(t[0],np.array([1.,0.,0.])))
    else:
        continued=transport(old_w,old_t,t[0])
        if up_norm>.1:
            up=unit(up)
            if np.dot(up,continued)<0:up=-up
            alpha=max(0.,min(1.,(up_norm-.1)/.25));root=unit((1-alpha)*continued+alpha*up)
        else:root=continued
    bishop=np.zeros_like(x);bishop[0]=root
    for i in range(1,n):bishop[i]=transport(bishop[i-1],t[i-1],t[i])
    end=desired-np.dot(desired,t[-1])*t[-1]
    if np.linalg.norm(end)>.05:
        end=unit(end);roll=np.arctan2(np.dot(t[-1],np.cross(bishop[-1],end)),np.dot(bishop[-1],end))
        if valid:roll+=2*np.pi*round((old_roll-roll)/(2*np.pi))
    else:roll=old_roll if valid else 0.
    wide=np.zeros_like(x);total=max(length.sum(),1e-14);arc=0.
    for i in range(n):
        if i>0:arc+=length[i-1]
        angle=roll*arc/total;wide[i]=np.cos(angle)*bishop[i]+np.sin(angle)*np.cross(t[i],bishop[i])
    return wide,t,roll,root

@njit(cache=False)
def table_contact(x,v,directors,tangents,width,thickness,l0):
    normals=np.cross(tangents,directors)
    for i in range(1,len(x)-1):
        stretch=max(np.linalg.norm(x[i+1]-x[i-1])/(2*l0),1.)
        support=(abs(directors[i,2])*width+abs(normals[i,2])*thickness)/(2*np.sqrt(stretch))+.000015
        if x[i,2]<support:
            x[i,2]=support;vn=v[i,2]
            if vn<0:
                impulse=-1.02*vn;v[i,2]+=impulse;speed=np.linalg.norm(v[i,:2])
                if speed>1e-12:v[i,:2]*=max(0.,1-.6*impulse/speed)

@njit(cache=False)
def boxes_contact(x,v,directors,l0,width,thickness,centers,half):
    maximum=0.
    top=-1e30
    for b in range(len(centers)):top=max(top,centers[b,2]+half[b,2])
    if np.min(x[:,2])>top+width/2+.0002:return maximum
    for i in range(1,len(x)-1):
        if i*l0<.014:continue
        for b in range(len(centers)):
            local=x[i]-centers[b]
            if np.any(np.abs(local)>half[b]+width/2+.0002):continue
            stretch=max(np.linalg.norm(x[i+1]-x[i-1])/(2*l0),1.)
            w=width/np.sqrt(stretch);h=thickness/np.sqrt(stretch)
            for repeat in range(2):
                for k in range(5):
                    point=x[i]+((k-2)/4)*w*directors[i];d=point-centers[b];q=np.abs(d)-half[b]
                    outside=np.maximum(q,0.);distance=np.linalg.norm(outside);normal=np.zeros(3)
                    if distance>1e-14:
                        for axis in range(3):normal[axis]=outside[axis]/distance*(1. if d[axis]>=0 else-1.)
                    else:
                        axis=np.argmax(q);distance=q[axis];normal[axis]=1. if d[axis]>=0 else-1.
                    gap=h/2+.000015-distance
                    if gap<=0:continue
                    x[i]+=gap*normal;vn=np.dot(v[i],normal)
                    if vn<0:
                        impulse=-1.02*vn;v[i]+=impulse*normal;tangent=v[i]-np.dot(v[i],normal)*normal;speed=np.linalg.norm(tangent)
                        if speed>1e-12:v[i]-=min(1.,.6*impulse/speed)*tangent
                    maximum=max(maximum,gap)
    return maximum
