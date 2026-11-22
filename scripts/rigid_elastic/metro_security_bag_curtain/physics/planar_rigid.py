"""Planar rigid contact: true x/z translation and pitch, Coulomb friction.

The packed scan's convex x/z silhouette supplies support geometry. The guide
constraint fixes y/roll/yaw; no position or angle is prescribed along the route.
Positive pitch is Blender's positive Y rotation (the leading edge moves down).
"""
import numpy as np
from numba import njit

@njit(cache=True)
def world(y,lx,lz):
    c=np.cos(y[2]);s=np.sin(y[2])
    return y[0]+c*lx+s*lz,y[1]-s*lx+c*lz

@njit(cache=True)
def apply(y,im,ii,lx,lz,nx,nz,dl):
    c=np.cos(y[2]);s=np.sin(y[2]);rx=c*lx+s*lz;rz=-s*lx+c*lz
    y[0]+=im*dl*nx;y[1]+=im*dl*nz;y[2]+=ii*dl*(rz*nx-rx*nz)

@njit(cache=True)
def project_one(y,im,ii,lx,lz,nx,nz,offset,lam,anchors,b,p,k):
    wx,wz=world(y[b],lx,lz);gap=nx*wx+nz*wz-offset
    if gap>=0:return 0.
    rx=wx-y[b,0];rz=wz-y[b,1];g=rz*nx-rx*nz
    den=im[b]+ii[b]*g*g
    dl=-gap/den
    apply(y[b],im[b],ii[b],lx,lz,nx,nz,dl)
    lam[b,p,k]+=dl;anchors[b,p,k,0]=lx;anchors[b,p,k,1]=lz;anchors[b,p,k,2]=nx;anchors[b,p,k,3]=nz
    return -gap

@njit(cache=True)
def project_vertex(y,im,ii,hull,lam,anchors,b,p,bid,gx,gz):
    nv=len(hull);maximum=-1e20;closest=-1;cnx=0.;cnz=1.;fraction=0.
    for edge in range(nv):
        j=(edge+1)%nv;ax,az=world(y[b],hull[edge,0],hull[edge,1]);bx,bz=world(y[b],hull[j,0],hull[j,1])
        ex=bx-ax;ez=bz-az;length=np.sqrt(ex*ex+ez*ez);signed=((gx-ax)*ez-(gz-az)*ex)/length
        if signed>0:return 0.
        if signed>maximum:maximum=signed;closest=edge;cnx=-ez/length;cnz=ex/length;fraction=min(1.,max(0.,((gx-ax)*ex+(gz-az)*ez)/(length*length)))
    if closest<0:return 0.
    j=(closest+1)%nv;lx=hull[closest,0]+fraction*(hull[j,0]-hull[closest,0]);lz=hull[closest,1]+fraction*(hull[j,1]-hull[closest,1])
    return project_one(y,im,ii,lx,lz,cnx,cnz,cnx*gx+cnz*gz,lam,anchors,b,p,nv+2*closest+bid)

@njit(cache=True)
def project_ground(y,im,ii,hull,profile,lam,anchors):
    # profile rows: x_min,x_max,z_at_x_min,slope; continuous upper faces.
    nv=len(hull);ns=len(profile);peak=0.
    for b in range(len(y)):
      for p in range(ns):
        lo,hi,z,m=profile[p];norm=np.sqrt(1+m*m);nx=-m/norm;nz=1/norm;off=(z-m*lo)/norm
        for k in range(nv):
            lx,lz=hull[k];wx,wz=world(y[b],lx,lz)
            if wx>=lo-1e-10 and wx<=hi+1e-10:
                peak=max(peak,project_one(y,im,ii,lx,lz,nx,nz,off,lam,anchors,b,p,k))
        # A ground VERTEX inside a bag contacts the BAG FACE. Its normal is
        # that face's normal, not the neighbouring ground plane normal. Taking
        # the latter produces a spurious pin at the belt/slope junction.
        for bound_id in range(2):
          gx=lo if bound_id==0 else hi;gz=z+m*(gx-lo)
          peak=max(peak,project_vertex(y,im,ii,hull,lam,anchors,b,p,bound_id,gx,gz))
      end=profile[-1,1];bottom=profile[-1,2]
      for k in range(nv):
        lx,lz=hull[k];wx,wz=world(y[b],lx,lz)
        if wz>=bottom-.005 and wz<=bottom+.095:
            peak=max(peak,project_one(y,im,ii,lx,lz,-1.,0.,-end,lam,anchors,b,ns,k))
      for bid in range(2):peak=max(peak,project_vertex(y,im,ii,hull,lam,anchors,b,ns,bid,end,bottom+bid*.09))
    return peak

@njit(cache=True)
def position_friction(y,old,im,ii,profile,lam,anchors,tlam,dt,mus,belt_speed):
    for b in range(len(y)):
      for p in range(len(profile)+1):
        for k in range(lam.shape[2]):
            if lam[b,p,k]<=0:continue
            lx=anchors[b,p,k,0];lz=anchors[b,p,k,1];tx=anchors[b,p,k,3];tz=-anchors[b,p,k,2];target=belt_speed*tx if p==0 else 0.
            wx,wz=world(y[b],lx,lz);ox,oz=world(old[b],lx,lz)
            g=(wz-y[b,1])*tx-(wx-y[b,0])*tz;den=im[b]+ii[b]*g*g
            C=(wx-ox)*tx+(wz-oz)*tz-target*dt;limit=mus[p]*lam[b,p,k]
            updated=min(limit,max(-limit,tlam[b,p,k]-C/den));dl=updated-tlam[b,p,k];tlam[b,p,k]=updated
            apply(y[b],im[b],ii[b],lx,lz,tx,tz,dl)

@njit(cache=True)
def friction_work(tlam,anchors,dt,belt_speed):
    return np.sum(tlam[:,0,:]*anchors[:,0,:,3])*belt_speed/dt

@njit(cache=True)
def ground_friction(y,u,im,ii,profile,lam,anchors,dt,mus,belt_speed,tlam):
    work=0.;diss=0.
    for b in range(len(y)):
      for p in range(len(profile)+1):
        for k in range(lam.shape[2]):
            if lam[b,p,k]<=0:continue
            lx=anchors[b,p,k,0];lz=anchors[b,p,k,1];tx=anchors[b,p,k,3];tz=-anchors[b,p,k,2];target=belt_speed*tx if p==0 else 0.
            wx,wz=world(y[b],lx,lz);rx=wx-y[b,0];rz=wz-y[b,1];g=rz*tx-rx*tz
            rel=(u[b,0]+u[b,2]*rz)*tx+(u[b,1]-u[b,2]*rx)*tz-target
            den=im[b]+ii[b]*g*g;limit=mus[p]*lam[b,p,k]/dt
            previous=tlam[b,p,k]/dt
            # J is the additional opposing impulse; previous already entered
            # velocity through the positional static-friction constraint.
            J=previous-min(limit,max(-limit,previous-rel/den))
            u[b,0]-=im[b]*J*tx;u[b,1]-=im[b]*J*tz;u[b,2]-=ii[b]*J*g
            work-=J*target;diss+=max(0.,J*rel-.5*J*J*den)
    return work,diss

@njit(cache=True)
def pair_geometry(y,hull):
    # Reference-face SAT and clipped incident edge. The contact wrench acts at
    # one common world point, preserving the free Y-axis angular momentum.
    nv=len(hull);w=np.zeros((2,nv,2))
    for b in range(2):
        for i in range(nv):w[b,i,0],w[b,i,1]=world(y[b],hull[i,0],hull[i,1])
    best=-1e9;owner=0;face=0;ox=1.;oz=0.
    for b in range(2):
      for i in range(nv):
        j=(i+1)%nv;dx=w[b,j,0]-w[b,i,0];dz=w[b,j,1]-w[b,i,1];length=np.sqrt(dx*dx+dz*dz)
        nx=dz/length;nz=-dx/length;plane=nx*w[b,i,0]+nz*w[b,i,1];nearest=1e9
        for k in range(nv):nearest=min(nearest,nx*w[1-b,k,0]+nz*w[1-b,k,1])
        gap=nearest-plane
        if gap>0:return gap,1.,0.,np.zeros((2,2))
        if gap>best:best=gap;owner=b;face=i;ox=nx;oz=nz
    j=(face+1)%nv;r0=w[owner,face];r1=w[owner,j];edge=r1-r0;length=np.sqrt(edge[0]*edge[0]+edge[1]*edge[1]);tangent=edge/length
    incident=1-owner;which=0;opposition=1e9
    for i in range(nv):
        j=(i+1)%nv;e=w[incident,j]-w[incident,i];le=np.sqrt(e[0]*e[0]+e[1]*e[1]);score=(e[1]*ox-e[0]*oz)/le
        if score<opposition:opposition=score;which=i
    a=w[incident,which];b=w[incident,(which+1)%nv];e=b-a
    s0=(a[0]-r0[0])*tangent[0]+(a[1]-r0[1])*tangent[1];ds=e[0]*tangent[0]+e[1]*tangent[1];lo=0.;hi=1.
    if abs(ds)<1e-14:
        if s0<-.0000001 or s0>length+.0000001:raise ValueError('Pair incident edge misses reference face')
    else:
        t0=-s0/ds;t1=(length-s0)/ds;lo=max(0.,min(t0,t1));hi=min(1.,max(t0,t1))
        if lo>hi+1e-10:raise ValueError('Pair contact clipping produced an empty manifold')
    p0=a+lo*e;p1=a+hi*e;g0=ox*(p0[0]-r0[0])+oz*(p0[1]-r0[1]);g1=ox*(p1[0]-r0[0])+oz*(p1[1]-r0[1])
    if abs(g0-g1)<1e-10:point=(p0+p1)/2;gap=(g0+g1)/2
    elif g0<g1:point=p0;gap=g0
    else:point=p1;gap=g1
    # Midway between the incident point and its projection to the reference
    # face; using the same lever-arm point for both bodies balances torque.
    contact=point-.5*gap*np.array((ox,oz));anchor=np.zeros((2,2))
    for body in range(2):
        dx=contact[0]-y[body,0];dz=contact[1]-y[body,1];c=np.cos(y[body,2]);s=np.sin(y[body,2])
        anchor[body,0]=c*dx-s*dz;anchor[body,1]=s*dx+c*dz
    nx=-ox if owner==0 else ox;nz=-oz if owner==0 else oz
    return gap,nx,nz,anchor

@njit(cache=True)
def project_pair(y,im,ii,hull,lam,anchor,normal):
    if len(y)!=2:return 0.
    if abs(y[0,0]-y[1,0])>.5 or abs(y[0,1]-y[1,1])>.3:return 0.
    gap,nx,nz,points=pair_geometry(y,hull)
    if gap>=0:return 0.
    den=im[0]+im[1]
    for b in range(2):
        wx,wz=world(y[b],points[b,0],points[b,1]);g=(wz-y[b,1])*nx-(wx-y[b,0])*nz;den+=ii[b]*g*g
    dl=-gap/den
    apply(y[0],im[0],ii[0],points[0,0],points[0,1],nx,nz,dl)
    apply(y[1],im[1],ii[1],points[1,0],points[1,1],-nx,-nz,dl)
    lam[0]+=dl;anchor[:]=points;normal[0]=nx;normal[1]=nz
    return -gap

@njit(cache=True)
def pair_friction(y,u,im,ii,lam,anchor,normal,dt,mu):
    if len(y)!=2 or lam[0]<=0:return 0.
    tx=normal[1];tz=-normal[0];rel=0.;den=im[0]+im[1];g=np.zeros(2)
    ax,az=world(y[0],anchor[0,0],anchor[0,1]);bx,bz=world(y[1],anchor[1,0],anchor[1,1]);cx=(ax+bx)/2;cz=(az+bz)/2
    for b in range(2):
        rx=cx-y[b,0];rz=cz-y[b,1];g[b]=rz*tx-rx*tz
        rel+=(1 if b==0 else -1)*((u[b,0]+u[b,2]*rz)*tx+(u[b,1]-u[b,2]*rx)*tz);den+=ii[b]*g[b]*g[b]
    limit=mu*lam[0]/dt;J=min(limit,max(-limit,rel/den))
    for b in range(2):
        s=1 if b==0 else -1;u[b,0]-=s*im[b]*J*tx;u[b,1]-=s*im[b]*J*tz;u[b,2]-=s*ii[b]*J*g[b]
    return max(0.,J*rel-.5*J*J*den)
