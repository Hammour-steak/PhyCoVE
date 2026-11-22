"""Metric planar rigid-cylinder / finite-rotation elastic cantilever dynamics.

The beam is an inextensible Kirchhoff strip: theta(s)=B(s)q and its centreline
is the integral of (cos(theta), sin(theta)). This retains finite rotations,
distributed translational inertia and the configuration-dependent mass matrix.
Eight Galerkin coordinates use reference Euler--Bernoulli FEM mode derivatives.
The rigid coins have independent translation and pitch, including impact torque.
No trajectories, launch events, or deformations are prescribed.
"""
from __future__ import annotations
import argparse, hashlib, json, math, platform, socket, sys, time, os
from pathlib import Path
import numpy as np
from scipy.linalg import eigh
from scipy.optimize import root
HERE=Path(__file__).resolve().parent
# Compiled numba kernels are a runtime cache (<repo>/.runtime/plastic_ruler_coin/numba_cache by default).
_repo=next((p for p in HERE.parents if (p/'scripts').is_dir() and (p/'assets.json').is_file()),HERE)
os.environ.setdefault('NUMBA_CACHE_DIR',str(_repo/'.runtime'/'plastic_ruler_coin'/'numba_cache'))
from numba import njit
sys.path.insert(0,str(HERE))
import vocabulary as vocab

def basis(cfg, modes=8, stations=121, elements=80):
    L=cfg['ruler_free_length_m']; A=cfg['ruler_width_m']*cfg['ruler_thickness_m']
    EI=cfg['ruler_young_modulus_pa']*cfg['ruler_width_m']*cfg['ruler_thickness_m']**3/12
    rho=cfg['ruler_density_kg_m3']; h=L/elements
    K=np.zeros((2*elements+2,2*elements+2)); M=K.copy()
    ke=EI/h**3*np.array([[12,6*h,-12,6*h],[6*h,4*h*h,-6*h,2*h*h],[-12,-6*h,12,-6*h],[6*h,2*h*h,-6*h,4*h*h]])
    me=rho*A*h/420*np.array([[156,22*h,54,-13*h],[22*h,4*h*h,13*h,-3*h*h],[54,13*h,156,-22*h],[-13*h,-3*h*h,-22*h,4*h*h]])
    for i in range(elements):
        idx=np.arange(2*i,2*i+4); K[np.ix_(idx,idx)]+=ke; M[np.ix_(idx,idx)]+=me
    ev,U=eigh(K[2:,2:],M[2:,2:],subset_by_index=[0,modes-1])
    U=np.vstack((np.zeros((2,modes)),U))
    s=np.linspace(0,L,stations); B=np.zeros((stations,modes))
    for i,ss in enumerate(s):
        j=min(elements-1,int(ss/h)); t=(ss-j*h)/h
        dN=np.array([(-6*t+6*t*t)/h,1-4*t+3*t*t,(6*t-6*t*t)/h,-2*t+3*t*t])
        B[i]=dN@U[2*j:2*j+4]
    weights=np.full(stations,L/(stations-1)*rho*A); weights[[0,-1]]*=.5
    # Re-orthogonalize reference inertia under the actual quadrature.
    q=np.zeros(modes); qd=q.copy()
    x,z,Jx,Jz,bx,bz,th=geometry(q,qd,s,B)
    mass=Jz.T@(weights[:,None]*Jz)
    vals,V=eigh(np.diag(ev),mass)
    B=np.ascontiguousarray(B@V)
    return s,B,vals,weights,EI

@njit(cache=True)
def geometry(q,qd,s,B):
    n=len(s); m=len(q); theta=B@q; td=B@qd
    x=np.zeros(n); z=np.zeros(n); Jx=np.zeros((n,m)); Jz=Jx.copy()
    bx=np.zeros(n); bz=bx.copy()
    for i in range(1,n):
        ds=(s[i]-s[i-1])*.5
        c0=math.cos(theta[i-1]); c1=math.cos(theta[i]); u0=math.sin(theta[i-1]); u1=math.sin(theta[i])
        x[i]=x[i-1]+ds*(c0+c1); z[i]=z[i-1]+ds*(u0+u1)
        bx[i]=bx[i-1]-ds*(c0*td[i-1]**2+c1*td[i]**2)
        bz[i]=bz[i-1]-ds*(u0*td[i-1]**2+u1*td[i]**2)
        for j in range(m):
            Jx[i,j]=Jx[i-1,j]-ds*(u0*B[i-1,j]+u1*B[i,j])
            Jz[i,j]=Jz[i-1,j]+ds*(c0*B[i-1,j]+c1*B[i,j])
    return x,z,Jx,Jz,bx,bz,theta

@njit(cache=True)
def acceleration(q,qd,c,cv,s,B,omega2,dm,damp,par,present):
    # par: mass[2], radius, thickness, beam thickness, midplane z, contact k,
    # contact zeta, mu, g, contact samples per face.
    m=len(q); x,z,Jx,Jz,bx,bz,theta=geometry(q,qd,s,B)
    MM=np.zeros((m,m)); force=-omega2*q-damp*qd
    for i in range(len(s)):
        for j in range(m):
            force[j]-=dm[i]*(Jx[i,j]*bx[i]+Jz[i,j]*(bz[i]+par[10]))
            for k in range(m):MM[j,k]+=dm[i]*(Jx[i,j]*Jx[i,k]+Jz[i,j]*Jz[i,k])
    ca=np.zeros((2,3)); normal_total=np.zeros(2); min_gap=1.0
    contact_energy=0.0; ns=int(par[11]); radius=par[2]; thick=par[3]
    for b in range(2):
        if not present[b]:continue
        mass=par[b]; inertia=mass*(3*radius**2+thick**2)/12
        ca[b,1]=-par[10]
        ct=math.cos(c[b,2]); st=math.sin(c[b,2])
        for side in range(2):
            lz=(-.5 if side==0 else .5)*thick
            for sample in range(ns):
                lx=radius*(2*sample/(ns-1)-1)
                rx=ct*lx-st*lz; rz=st*lx+ct*lz
                px=c[b,0]+rx; pz=c[b,1]+rz
                vx=cv[b,0]-cv[b,2]*rz; vz=cv[b,1]+cv[b,2]*rx
                nx=0.0; nz=1.0; tx=1.0; tz=0.0
                i=-1; a=0.0; vbx=0.0; vbz=0.0; gap=1.0
                if par[12]>.5 and px>=x[0] and px<=x[-1] and pz>par[5]-.12:
                    i=min(len(s)-2,max(0,np.searchsorted(x,px)-1))
                    a=(px-x[i])/(x[i+1]-x[i]); th=(1-a)*theta[i]+a*theta[i+1]
                    nx=-math.sin(th); nz=math.cos(th); tx=nz; tz=-nx
                    zz=(1-a)*z[i]+a*z[i+1]+par[5]
                    gap=(pz-zz)*nz-par[4]*.5
                    for j in range(m):
                        vbx+=((1-a)*Jx[i,j]+a*Jx[i+1,j])*qd[j]
                        vbz+=((1-a)*Jz[i,j]+a*Jz[i+1,j])*qd[j]
                elif px<-.001 and pz>par[5]-.12:
                    gap=pz-(par[5]-par[4]*.5) # desk top
                else:gap=pz # room floor, z=0
                if gap<min_gap:min_gap=gap
                if gap>=0:continue
                kk=par[6]/(2*ns)
                cc=2*par[7]*math.sqrt(kk*mass/(2*ns))
                vn=(vx-vbx)*nx+(vz-vbz)*nz
                fn=max(0.0,-kk*gap-cc*vn)
                vt=(vx-vbx)*tx+(vz-vbz)*tz
                ft=-par[8]*fn*math.tanh(vt/.0005)
                fx=nx*fn+tx*ft; fz=nz*fn+tz*ft
                ca[b,0]+=fx/mass; ca[b,1]+=fz/mass; ca[b,2]+=(rx*fz-rz*fx)/inertia
                normal_total[b]+=fn; contact_energy+=.5*kk*gap*gap
                if i>=0:
                    for j in range(m):
                        force[j]-=((1-a)*Jx[i,j]+a*Jx[i+1,j])*fx+((1-a)*Jz[i,j]+a*Jz[i+1,j])*fz
    # Planar cylinder/cylinder contact in the symmetry plane: convex SAT,
    # with contact torque and equal/opposite forces. Dormant if separated.
    if present[0] and present[1] and abs(c[0,0]-c[1,0])<2*radius+thick and abs(c[0,1]-c[1,1])<2*radius+thick:
        verts=np.zeros((2,4,2))
        for b in range(2):
            ct=math.cos(c[b,2]); st=math.sin(c[b,2])
            for j in range(4):
                lx=(-1 if j<2 else 1)*radius; lz=(-1 if j%2==0 else 1)*thick*.5
                verts[b,j,0]=c[b,0]+ct*lx-st*lz; verts[b,j,1]=c[b,1]+st*lx+ct*lz
        overlap=1e6; ax=0.0; az=0.0; touching=True
        for b in range(2):
            for j in range(2):
                angle=c[b,2]+j*math.pi*.5; nnx=math.cos(angle); nnz=math.sin(angle)
                lo=np.zeros(2); hi=lo.copy()
                for bb in range(2):
                    vv=verts[bb,:,0]*nnx+verts[bb,:,1]*nnz; lo[bb]=np.min(vv); hi[bb]=np.max(vv)
                ov=min(hi[0],hi[1])-max(lo[0],lo[1])
                if ov<=0:touching=False
                if ov<overlap:overlap=ov;ax=nnx;az=nnz
        if touching:
            if (c[1,0]-c[0,0])*ax+(c[1,1]-c[0,1])*az<0:ax=-ax;az=-az
            # Midpoint between closest support-feature centroids.
            cp=np.zeros(2)
            for b in range(2):
                vals=verts[b,:,0]*ax+verts[b,:,1]*az
                target=np.max(vals) if b==0 else np.min(vals); nn=0
                for j in range(4):
                    if abs(vals[j]-target)<1e-6:cp+=verts[b,j];nn+=1
                # Non-parallel faces usually contribute one vertex each.
            # Use line-of-centres midpoint to avoid an unbounded lever arm.
            cp=(c[0,:2]+c[1,:2])*.5
            vr=(cv[1,0]-cv[0,0])*ax+(cv[1,1]-cv[0,1])*az
            f=max(0.0,par[6]*overlap-2*par[7]*math.sqrt(par[6]/(1/par[0]+1/par[1]))*vr)
            for b in range(2):
                sign=-1 if b==0 else 1; fx=sign*f*ax; fz=sign*f*az
                inertia=par[b]*(3*radius**2+thick**2)/12
                ca[b,0]+=fx/par[b];ca[b,1]+=fz/par[b]
                ca[b,2]+=((cp[0]-c[b,0])*fz-(cp[1]-c[b,1])*fx)/inertia
            contact_energy+=.5*par[6]*overlap**2
    qa=np.linalg.solve(MM,force)
    energy=.5*np.dot(q,omega2*q)+contact_energy
    for i in range(len(s)):
        velx=0.0;velz=0.0
        for j in range(m):velx+=Jx[i,j]*qd[j];velz+=Jz[i,j]*qd[j]
        energy+=dm[i]*(.5*(velx**2+velz**2)+par[10]*z[i])
    for b in range(2):
        if present[b]:energy+=.5*par[b]*(cv[b,0]**2+cv[b,1]**2)+.5*par[b]*(3*radius**2+thick**2)/12*cv[b,2]**2+par[b]*par[10]*c[b,1]
    return qa,ca,normal_total,min_gap,energy,theta[-1]

@njit(cache=True)
def integrate(q,c,s,B,omega2,dm,damp,par,present,dt,steps,frame_stride,diagnostic_stride):
    qd=np.zeros(len(q));cv=np.zeros((2,3))
    frames=steps//frame_stride+1; diagnostics=steps//diagnostic_stride+1
    outq=np.zeros((frames,len(q)));outc=np.zeros((frames,2,3));outv=outc.copy()
    curves=np.zeros((frames,len(s),3)); high=np.zeros((diagnostics,16))
    qa,ca,fn,gap,energy,tipang=acceleration(q,qd,c,cv,s,B,omega2,dm,damp,par,present)
    max_pen=0.0; max_theta=0.0;min_tip=1.0; max_fn=np.zeros(2);max_energy=energy
    for step in range(steps+1):
        if step%frame_stride==0:
            f=step//frame_stride;outq[f]=q;outc[f]=c;outv[f]=cv
            x,z,Jx,Jz,bx,bz,theta=geometry(q,qd,s,B)
            curves[f,:,0]=x;curves[f,:,1]=z+par[5];curves[f,:,2]=theta
        if step%diagnostic_stride==0:
            i=step//diagnostic_stride
            x,z,Jx,Jz,bx,bz,theta=geometry(q,qd,s,B)
            high[i,0]=step*dt;high[i,1]=z[-1];high[i,2]=energy;high[i,3]=gap;high[i,4]=fn[0];high[i,5]=fn[1]
            high[i,6:9]=c[0];high[i,9:12]=cv[0];high[i,12:15]=c[1];high[i,15]=tipang
        if gap<0:max_pen=max(max_pen,-gap)
        max_theta=max(max_theta,abs(tipang));max_energy=max(max_energy,energy)
        max_fn=np.maximum(max_fn,fn)
        if step==steps:break
        qdhalf=qd+.5*dt*qa;cvhalf=cv+.5*dt*ca
        q=q+dt*qdhalf;c=c+dt*cvhalf
        qa,ca,fn,gap,energy,tipang=acceleration(q,qdhalf,c,cvhalf,s,B,omega2,dm,damp,par,present)
        qd=qdhalf+.5*dt*qa;cv=cvhalf+.5*dt*ca
    return outq,outc,outv,curves,high,max_pen,max_theta,max_fn,max_energy

def run(case, out, dt=None, modes=None, duration=None, stiffness_scale=1, cfg=None):
    # cfg: resolved physics of a case outside SPEC['cases'] (e.g. a DELETE ruler run); default vocab.resolve(case).
    spec=vocab.SPEC;cfg=vocab.resolve(case) if cfg is None else cfg;solver=dict(spec['solver'])
    if dt is not None:solver['time_step_s']=dt
    if modes is not None:solver['modes']=modes
    if duration is None:duration=spec['duration_s']
    start=time.perf_counter()
    s,B,omega2,dm,EI=basis(cfg,solver['modes'],solver['quadrature_stations'],solver['reference_fem_elements'])
    zeta=cfg['ruler_modal_damping_ratio'];damp=2*zeta*np.sqrt(omega2)
    def residual(q):
        g=geometry(q,np.zeros(len(q)),s,B)
        return omega2*q+cfg['gravity_m_s2']*(dm@g[3])
    equilibrium=root(residual,np.zeros(len(omega2)),tol=1e-11)
    if np.linalg.norm(residual(equilibrium.x))>1e-8:raise RuntimeError('Gravity equilibrium failed')
    q=equilibrium.x
    c=np.array([[cfg['coin_initial_location_m'][0],cfg['coin_initial_location_m'][2],0.0],
                [cfg['second_coin_initial_location_m'][0],cfg['second_coin_initial_location_m'][2],0.0]])
    present=np.array([bool(cfg['coin_present'][0]),bool(cfg['second_coin_present'][0])])
    par=np.array([cfg['coin_mass_kg'],cfg['second_coin_mass_kg'],cfg['coin_radius_m'],cfg['coin_thickness_m'],
        cfg['ruler_thickness_m'],cfg['ruler_midplane_z_m'],cfg['contact_stiffness_n_m']*stiffness_scale,
        cfg['contact_damping_ratio'],cfg['friction_coefficient'],0.,cfg['gravity_m_s2'],solver['contact_samples_per_face'],
        float(cfg.get('ruler_present',[1])[0])],float)   # par[12]: ruler present (DELETE ruler: 0, the coin meets only the desk top and the floor)
    dt=solver['time_step_s'];fps=spec['fps'];steps=round(duration/dt);fs=round(1/fps/dt);ds=round(1/solver['high_rate_hz']/dt)
    if not math.isclose(fs*dt,1/fps,abs_tol=1e-13) or not math.isclose(steps*dt,duration,abs_tol=1e-13):
        raise ValueError('Integration step must divide both the native frame period and duration exactly')
    result=integrate(q,c,s,B,omega2,dm,damp,par,present,dt,steps,fs,ds)
    outq,outc,outv,curves,high,maxpen,maxangle,maxfn,maxE=result
    times=np.arange(len(outq),dtype=float)/fps
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    np.savez_compressed(out/'simulation.npz',times=times,arc_length=s,beam_curves=curves,beam_q=outq,
        beam_angle_basis=B,coin_states=outc,coin_velocities=outv,present=present,diagnostics=high,
        mode_frequencies_hz=np.sqrt(omega2)/(2*np.pi),integration_dt_s=np.array(dt))
    # First contact, separation and subsequent apex are measured, never imposed.
    contacting=np.flatnonzero(high[:,4]>.002)
    impact=float(high[contacting[0],0]) if len(contacting) else None
    separation=None;apex=None;apex_time=None
    if len(contacting):
        begin=contacting[0]
        # First sustained force-free interval with positive vertical velocity.
        for k in range(begin+1,len(high)-10):
            if high[k,10]>.01 and np.all(high[k:k+8,4]<.002):
                separation=float(high[k,0]);end=min(len(high),k+round(.35*solver['high_rate_hz']))
                j=k+int(np.argmax(high[k:end,7]));apex=float(high[j,7]);apex_time=float(high[j,0]);break
    f1_exact=1.875104068711961**2/(2*np.pi)*np.sqrt(EI/(cfg['ruler_density_kg_m3']*cfg['ruler_width_m']*cfg['ruler_thickness_m']*cfg['ruler_free_length_m']**4))
    max_bending_moment=EI*float(np.max(np.abs(np.gradient(B@outq.T,s,axis=0))))
    hold_moment=cfg['book_mass_kg']*cfg['gravity_m_s2']*spec['diagnostics']['book_footprint_length_m']*.5
    report=dict(case=case,simulation_duration_s=float(times[-1]),fps=fps,video_frames=len(times)-1,
        dt_s=dt,solver='finite-rotation inextensible Kirchhoff beam, distributed inertia, rigid-cylinder contact',
        first_impact_s=impact,first_separation_s=separation,first_rebound_apex_z_m=apex,first_apex_time_s=apex_time,
        release_centre_z_m=float(c[0,1]),rebound_below_release=bool(apex<c[0,1]) if apex else None,
        maximum_downward_tip_deflection_mm=-1000*float(high[:,1].min()),
        maximum_contact_penetration_mm=1000*float(maxpen),maximum_tip_angle_rad=float(maxangle),
        peak_normal_force_n=maxfn.tolist(),max_mechanical_energy_j=float(maxE),initial_mechanical_energy_j=float(high[0,2]),
        final_mechanical_energy_j=float(high[-1,2]),maximum_bending_moment_n_m=max_bending_moment,
        book_available_hold_down_moment_n_m=hold_moment,clamp_moment_safety_factor=hold_moment/max(max_bending_moment,1e-12),
        f1_hz=float(np.sqrt(omega2[0])/(2*np.pi)),analytic_f1_hz=float(f1_exact),
        f1_relative_error=float(abs(np.sqrt(omega2[0])/(2*np.pi)/f1_exact-1)),
        maximum_segment_length_relative_error=float(np.max(np.abs(np.linalg.norm(np.diff(curves[:,:,:2],axis=1),axis=2)/np.diff(s)-1))),
        cpu_execution_host=socket.gethostname(),execution_os=platform.platform(),elapsed_s=time.perf_counter()-start,
        material_calibrated=False,accepted_benchmark_gt=False,no_authored_motion=True)
    (out/'simulation_config.json').write_text(json.dumps({'scene_id':'plastic_ruler_coin','case':case,'physics':cfg,'solver':solver,'duration_s':duration,'fps':fps,'video_frames':len(times)-1,'diagnostics':spec['diagnostics']},indent=2),encoding='utf-8')
    (out/'simulation_report.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    print(json.dumps(report,indent=2),flush=True)
    if not np.isfinite(outq).all() or maxpen>.001 or maxangle>1.0:raise RuntimeError('Non-finite or unresolved beam/contact')
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=list(vocab.SPEC['cases']),default='source')
    p.add_argument('--out',type=Path);p.add_argument('--dt',type=float);p.add_argument('--modes',type=int)
    p.add_argument('--duration',type=float);p.add_argument('--stiffness-scale',type=float,default=1)
    a=p.parse_args()
    if a.out is None:p.error('--out is required (simulate_plastic_ruler_coin.py chooses a fresh folder)')
    run(a.case,a.out,a.dt,a.modes,a.duration,a.stiffness_scale)
if __name__=='__main__':main()
