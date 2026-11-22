"""CPU float64 triangular strip shells with Kelvin-Voigt XPBD and belt contact.

Plane-stress StVK membrane and signed discrete dihedral bending. E is in Pa;
thickness enters membrane energy linearly and bending energy cubically.
The rigid parts have one chute-aligned DOF, with plane/guide reactions.
No Blender, trajectory prescription, cached-motion scaling, or render offsets.
"""
from pathlib import Path
import sys
from scene_paths import RUNTIME
sys.path.insert(0, str(RUNTIME / 'python'))
import numpy as np
from numba import njit,objmode
from self_contact import topology as self_topology,rebuild as self_rebuild,displacement as self_displacement,project as self_project,friction as self_friction

@njit(cache=True)
def dot(a, b):
    return a[0]*b[0] + a[1]*b[1] + a[2]*b[2]

@njit(cache=True)
def cross(a,b):
    return np.array((a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]))

@njit(cache=True)
def angle_gradient(p):
    e=p[3]-p[2]; le=np.sqrt(dot(e,e))
    a=cross(p[2]-p[0],p[3]-p[0]); b=cross(p[3]-p[1],p[2]-p[1])
    aa=dot(a,a); bb=dot(b,b)
    grad=np.zeros((4,3))
    if min(aa,bb)<1e-20 or le<1e-10: return 0.,grad
    n1=a/np.sqrt(aa); n2=b/np.sqrt(bb)
    angle=np.arctan2(dot(cross(n1,n2),e)/le,dot(n1,n2))
    a/=aa; b/=bb
    grad[0]=-le*a;grad[1]=-le*b
    grad[2]=-dot(p[0]-p[3],e)/le*a-dot(p[1]-p[3],e)/le*b
    grad[3]=-dot(p[2]-p[0],e)/le*a-dot(p[2]-p[1],e)/le*b
    return angle,grad

def mesh(p,nx=19,ny=25):
    u=np.linspace(-p['curtain_width_m']/2,p['curtain_width_m']/2,nx)
    v=np.linspace(0,p['curtain_length_m'],ny)
    x=np.array([[0.,a,p['curtain_top_height_m']-b] for b in v for a in u])
    uv=np.array([[a,b] for b in v for a in u])
    tris=[]
    for j in range(ny-1):
        for i in range(nx-1):
            a=j*nx+i; b=a+1; c=a+nx; d=c+1
            tris.extend(((a,b,d),(a,d,c)) if (i+j)%2==0 else ((a,b,c),(b,d,c)))
    tris=np.array(tris,dtype=np.int64)
    coeff=[]; areas=[]; hinges=[];weights=[];edges={}
    masses=np.zeros(len(x))
    for tid,t in enumerate(tris):
        dm=np.stack((uv[t[1]]-uv[t[0]],uv[t[2]]-uv[t[0]]),axis=1)
        inv=np.linalg.inv(dm);area=abs(np.linalg.det(dm))/2
        coeff.append(np.array([-(inv[0]+inv[1]),inv[0],inv[1]]));areas.append(area)
        masses[t]+=area*p['curtain_density_kg_m3']*p['curtain_thickness_m']/3
        for a,b,o in ((t[0],t[1],t[2]),(t[1],t[2],t[0]),(t[2],t[0],t[1])):
            key=tuple(sorted((a,b)))
            if key in edges:
                a0,b0,o0,t0=edges[key];hinges.append((o0,o,a0,b0))
                edge2=np.sum((x[b]-x[a])**2)
                # Discrete-shell dual-height integration: k = D * 3 l^2 / (A1+A2).
                weights.append(3*edge2/(areas[t0]+area))
            else:edges[key]=(a,b,o,tid)
    invmass=1/masses;invmass[:2*nx]=0
    sample_ids=np.vstack((np.repeat(np.arange(len(x))[:,None],3,axis=1),tris))
    sample_w=np.vstack((np.tile([1.,0.,0.],(len(x),1)),np.full((len(tris),3),1/3)))
    return dict(rest=x,uv=uv,tris=tris,coeff=np.array(coeff),areas=np.array(areas),
                hinges=np.array(hinges,dtype=np.int64),bend_weights=np.array(weights),
                mass=masses,invmass=invmass,sample_ids=sample_ids.astype(np.int64),sample_w=sample_w,
                nx=nx,ny=ny)

@njit(cache=True)
def membrane_reference(x,old,inv,tris,coef,stiff,lam,dt,tau,reverse=False):
    gamma=tau/dt
    for ii in range(len(tris)):
        i=len(tris)-1-ii if reverse else ii
        ids=tris[i]; co=coef[i]
        for mode in range(3):
            fu=np.zeros(3);fv=np.zeros(3)
            for j in range(3):
                fu+=co[j,0]*x[ids[j]];fv+=co[j,1]*x[ids[j]]
            if mode==0: C=.5*(dot(fu,fu)+dot(fv,fv)-2);gu=fu;gv=fv
            elif mode==1:C=.5*(dot(fu,fu)-dot(fv,fv));gu=fu;gv=-fv
            else:C=dot(fu,fv);gu=fv;gv=fu
            grads=np.empty((3,3));den=0.;velterm=0.
            for j in range(3):
                g=co[j,0]*gu+co[j,1]*gv;grads[j]=g
                den+=inv[ids[j]]*dot(g,g);velterm+=dot(g,x[ids[j]]-old[ids[j]])
            alpha=1/(stiff[i,mode]*dt*dt)
            dl=(-C-alpha*lam[i,mode]-gamma*velterm)/((1+gamma)*den+alpha)
            lam[i,mode]+=dl
            for j in range(3):x[ids[j]]+=inv[ids[j]]*dl*grads[j]

@njit(cache=True)
def membrane(x,old,inv,tris,coef,stiff,lam,dt,tau,reverse=False):
    gamma=tau/dt
    for ii in range(len(tris)):
        i=len(tris)-1-ii if reverse else ii
        a=tris[i,0];b=tris[i,1];c=tris[i,2]
        au=coef[i,0,0];av=coef[i,0,1];bu=coef[i,1,0];bv=coef[i,1,1];cu=coef[i,2,0];cv=coef[i,2,1]
        for mode in range(3):
            ux=au*x[a,0]+bu*x[b,0]+cu*x[c,0];uy=au*x[a,1]+bu*x[b,1]+cu*x[c,1];uz=au*x[a,2]+bu*x[b,2]+cu*x[c,2]
            vx=av*x[a,0]+bv*x[b,0]+cv*x[c,0];vy=av*x[a,1]+bv*x[b,1]+cv*x[c,1];vz=av*x[a,2]+bv*x[b,2]+cv*x[c,2]
            uu=ux*ux+uy*uy+uz*uz;vv=vx*vx+vy*vy+vz*vz
            if mode==0:C=.5*(uu+vv-2);gux=ux;guy=uy;guz=uz;gvx=vx;gvy=vy;gvz=vz
            elif mode==1:C=.5*(uu-vv);gux=ux;guy=uy;guz=uz;gvx=-vx;gvy=-vy;gvz=-vz
            else:C=ux*vx+uy*vy+uz*vz;gux=vx;guy=vy;guz=vz;gvx=ux;gvy=uy;gvz=uz
            ax=au*gux+av*gvx;ay=au*guy+av*gvy;az=au*guz+av*gvz
            bx=bu*gux+bv*gvx;by=bu*guy+bv*gvy;bz=bu*guz+bv*gvz
            cx=cu*gux+cv*gvx;cy=cu*guy+cv*gvy;cz=cu*guz+cv*gvz
            den=inv[a]*(ax*ax+ay*ay+az*az)+inv[b]*(bx*bx+by*by+bz*bz)+inv[c]*(cx*cx+cy*cy+cz*cz)
            velterm=ax*(x[a,0]-old[a,0])+ay*(x[a,1]-old[a,1])+az*(x[a,2]-old[a,2])+bx*(x[b,0]-old[b,0])+by*(x[b,1]-old[b,1])+bz*(x[b,2]-old[b,2])+cx*(x[c,0]-old[c,0])+cy*(x[c,1]-old[c,1])+cz*(x[c,2]-old[c,2])
            alpha=1/(stiff[i,mode]*dt*dt);dl=(-C-alpha*lam[i,mode]-gamma*velterm)/((1+gamma)*den+alpha);lam[i,mode]+=dl
            x[a,0]+=inv[a]*dl*ax;x[a,1]+=inv[a]*dl*ay;x[a,2]+=inv[a]*dl*az
            x[b,0]+=inv[b]*dl*bx;x[b,1]+=inv[b]*dl*by;x[b,2]+=inv[b]*dl*bz
            x[c,0]+=inv[c]*dl*cx;x[c,1]+=inv[c]*dl*cy;x[c,2]+=inv[c]*dl*cz

@njit(cache=True)
def bending(x,old,inv,hinges,stiff,lam,dt,tau,reverse=False):
    gamma=tau/dt
    for ii in range(len(hinges)):
        i=len(hinges)-1-ii if reverse else ii
        ids=hinges[i];C,grad=angle_gradient(x[ids])
        den=0.;velterm=0.
        for j in range(4):
            den+=inv[ids[j]]*dot(grad[j],grad[j]);velterm+=dot(grad[j],x[ids[j]]-old[ids[j]])
        alpha=1/(stiff[i]*dt*dt)
        dl=(-C-alpha*lam[i]-gamma*velterm)/((1+gamma)*den+alpha)
        lam[i]+=dl
        for j in range(4):x[ids[j]]+=inv[ids[j]]*dl*grad[j]

@njit(cache=True)
def sdf(point,q,cs,sn,z0,dims,thick):
    # Trilinear signed-distance grid of the convex envelope of the actual scan.
    loc=point-np.array((q,0.,z0))
    spacing=dims[6];nx=int(dims[7]);ny=int(dims[8]);nz=int(dims[9])
    u=(loc-dims[3:6])/spacing
    ix=int(np.floor(u[0]));iy=int(np.floor(u[1]));iz=int(np.floor(u[2]))
    if ix<0 or iy<0 or iz<0 or ix>=nx-1 or iy>=ny-1 or iz>=nz-1:
        return .01,np.array((1.,0.,0.))
    t=u-np.array((ix,iy,iz));value=0.;g=np.zeros(3)
    for a in range(2):
      for b in range(2):
       for c in range(2):
        phi=dims[10+((ix+a)*ny+iy+b)*nz+iz+c]
        wx=t[0] if a else 1-t[0];wy=t[1] if b else 1-t[1];wz=t[2] if c else 1-t[2]
        value+=wx*wy*wz*phi
        g[0]+=(1. if a else -1.)*wy*wz*phi/spacing
        g[1]+=(1. if b else -1.)*wx*wz*phi/spacing
        g[2]+=(1. if c else -1.)*wx*wy*phi/spacing
    length=np.sqrt(dot(g,g))
    return value-thick/2,g/max(length,1e-12)

@njit(cache=True)
def contacts(x,inv,ids,sw,q,imq,cs,sn,z0,dims,thick,contact_lam,dt):
    maxpen=0.;impulse=np.zeros(len(q))
    tangent=np.array((cs,0.,-sn))
    for b in range(len(q)):
        for i in range(len(ids)):
            point=sw[i,0]*x[ids[i,0]]+sw[i,1]*x[ids[i,1]]+sw[i,2]*x[ids[i,2]]
            if abs(point[1])>dims[1]/2+.01 or abs(point[0]-q[b])>dims[0]/2+.01 or point[2]<z0-.01 or point[2]>z0+dims[2]+.01:continue
            gap,n=sdf(point,q[b],cs,sn,z0,dims,thick)
            if gap>=0:continue
            maxpen=max(maxpen,-gap)
            gq=-dot(n,tangent);den=imq[b]*gq*gq
            for j in range(3):den+=inv[ids[i,j]]*sw[i,j]*sw[i,j]
            if den<1e-15:continue
            dl=-gap/den
            for j in range(3):x[ids[i,j]]+=inv[ids[i,j]]*sw[i,j]*dl*n
            q[b]+=imq[b]*dl*gq
            contact_lam[b,i]+=dl
            impulse[b]+=dl*gq/dt
    return maxpen,impulse

@njit(cache=True)
def friction_velocity(x,v,inv,ids,sw,q,qv,imq,cs,sn,z0,dims,thick,normal_lam,dt,mu):
    tangent=np.array((cs,0.,-sn));diss=0.
    for b in range(len(q)):
        for i in range(len(ids)):
            if normal_lam[b,i]<=0:continue
            point=np.zeros(3);vel=np.zeros(3)
            for j in range(3):point+=sw[i,j]*x[ids[i,j]];vel+=sw[i,j]*v[ids[i,j]]
            gap,n=sdf(point,q[b],cs,sn,z0,dims,thick)
            if gap>.0004:continue
            rel=vel-tangent*qv[b];tv=rel-dot(rel,n)*n
            speed=np.sqrt(dot(tv,tv))
            if speed<1e-10:continue
            direction=tv/speed;gq=-dot(direction,tangent);den=imq[b]*gq*gq
            for j in range(3):den+=inv[ids[i,j]]*sw[i,j]*sw[i,j]
            if den<1e-14:continue
            J=min(speed/den,mu*normal_lam[b,i]/dt)
            for j in range(3):v[ids[i,j]]-=inv[ids[i,j]]*sw[i,j]*J*direction
            qv[b]-=imq[b]*J*gq;diss+=J*speed-.5*J*J*den
    return diss

@njit(cache=True)
def energy(x,v,q,qv,mass,mq,tri,coef,stiff,hinges,bend_stiff,cs,sn,z0):
    kinetic=0.;gravity=0.;elastic=0.
    for i in range(len(x)):
        kinetic+=.5*mass[i]*dot(v[i],v[i]);gravity+=9.81*mass[i]*x[i,2]
    for b in range(len(q)):
        kinetic+=.5*mq[b]*qv[b]*qv[b];gravity+=9.81*mq[b]*(z0-q[b]*sn)
    for i in range(len(tri)):
        fu=np.zeros(3);fv=np.zeros(3)
        for j in range(3):fu+=coef[i,j,0]*x[tri[i,j]];fv+=coef[i,j,1]*x[tri[i,j]]
        c0=.5*(dot(fu,fu)+dot(fv,fv)-2);c1=.5*(dot(fu,fu)-dot(fv,fv));c2=dot(fu,fv)
        elastic+=.5*(stiff[i,0]*c0*c0+stiff[i,1]*c1*c1+stiff[i,2]*c2*c2)
    for i in range(len(hinges)):
        a,_=angle_gradient(x[hinges[i]]);elastic+=.5*bend_stiff[i]*a*a
    return kinetic,gravity,elastic

@njit(cache=True)
def aerodynamic_force(x,v,tri):
    forces=np.zeros_like(x)
    for t in tri:
        area_normal=.5*cross(x[t[1]]-x[t[0]],x[t[2]]-x[t[0]])
        area=np.sqrt(dot(area_normal,area_normal))
        if area<1e-14:continue
        n=area_normal/area;vel=(v[t[0]]+v[t[1]]+v[t[2]])/3
        vn=dot(vel,n);vt=vel-vn*n
        # Still room air: rho=1.20 kg/m3, normal Cd=1.8, skin Cd=0.015.
        force=-.5*1.2*area*(1.8*abs(vn)*vn*n+.015*np.sqrt(dot(vt,vt))*vt)
        for j in range(3):forces[t[j]]+=force/3
    return forces

single_sheet_mesh=mesh
def mesh(p,nx=5,ny=25):
    parts=[];pitch=p['curtain_width_m']/p['strip_count'];offset=0
    for k in range(p['strip_count']):
        pp=dict(p);pp['curtain_width_m']=pitch-p['strip_gap_m']
        m=single_sheet_mesh(pp,nx,ny)
        m['rest'][:,1]+=-p['curtain_width_m']/2+(k+.5)*pitch
        for name in ('tris','hinges','sample_ids'):m[name]+=offset
        m['strip_ids']=np.full(len(m['rest']),k,dtype=np.int64)
        parts.append(m);offset+=len(m['rest'])
    keys=('rest','uv','tris','coeff','areas','hinges','bend_weights','mass','invmass','sample_ids','sample_w','strip_ids')
    result={k:np.concatenate([m[k] for m in parts],axis=0) for k in keys}
    edges=np.unique(np.sort(np.vstack((result['tris'][:,[0,1]],result['tris'][:,[1,2]],result['tris'][:,[2,0]])),axis=1),axis=0)
    extra=np.column_stack((edges[:,0],edges[:,1],edges[:,1]))
    result['sample_ids']=np.vstack((result['sample_ids'],extra));result['sample_w']=np.vstack((result['sample_w'],np.tile([.5,.5,0.],(len(edges),1))))
    result.update(nx=nx,ny=ny);return result

