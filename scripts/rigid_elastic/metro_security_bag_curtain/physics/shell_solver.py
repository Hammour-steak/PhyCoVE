"""3D clamped strip shells coupled to free planar rigid bodies and outfeed."""
from pathlib import Path
import sys,hashlib,json
from scene_paths import ASSETS, RUNTIME
sys.path.insert(0,str(RUNTIME/'python'))
import numpy as np
from numba import njit,objmode
from constitutive import mesh,membrane,bending,energy as sheet_energy,aerodynamic_force,dot
from self_contact import topology as self_topology,rebuild as self_rebuild,displacement as self_displacement,project as self_project,friction as self_friction
from planar_rigid import project_ground,ground_friction,project_pair,pair_friction,position_friction,friction_work
from curtain_coupling import contacts,friction

@njit(cache=True)
def energy(x,v,y,u,mass,mq,inertia,tri,coef,stiff,hinges,kb):
    k,g,e=sheet_energy(x,v,np.empty(0),np.empty(0),mass,np.empty(0),tri,coef,stiff,hinges,kb,1.,0.,0.)
    for b in range(len(y)):k+=.5*mq[b]*(u[b,0]**2+u[b,1]**2)+.5*inertia[b]*u[b,2]**2;g+=9.81*mq[b]*y[b,1]
    return k,g,e

@njit(cache=True)
def run(rest,inv,mass,tri,coef,stiff,hinges,kb,ids,sw,y_init,mq,inertia,hull,profile,mus,dt,iterations,steps,save_every,dims,thick,mu_contact,tau_mem,tau_bend,mass_damping,present,u_init,belt_speed,cpfile,self_edges,self_vo,self_to,self_eo,self_mu,self_skin,pair_mu,x_init,v_init):
    # Initial state: the rest/launch state of a fresh solve, or an exact saved state to continue from.
    x=x_init.copy();v=v_init.copy();y=y_init.copy();u=u_init.copy();im=1/mq;ii=1/inertia
    nsave=steps//save_every+1;xx=np.empty((nsave,len(x),3));vv=np.empty_like(xx);yy=np.empty((nsave,len(y),3));uu=np.empty_like(yy)
    te=max(1,int(round(1/(240*dt))));tele=np.zeros((steps//te+1,17));xx[0]=x;vv[0]=v;yy[0]=y;uu[0]=u;saveid=1;work=0.;diss=0.
    maxvp=0;maxep=0
    for si in range(5):
        maxvp+=(self_vo[si+1]-self_vo[si])*(self_to[si+2]-self_to[si+1])+(self_vo[si+2]-self_vo[si+1])*(self_to[si+1]-self_to[si])
        maxep+=(self_eo[si+1]-self_eo[si])*(self_eo[si+2]-self_eo[si+1])
    vpairs=np.empty((maxvp,2),np.int64);epairs=np.empty((maxep,2),np.int64);slv=np.zeros(maxvp);sle=np.zeros(maxep);nv=0;ne=0;sanchor=x.copy();rebuilds=0
    if present:nv,ne=self_rebuild(x,tri,self_edges,self_vo,self_to,self_eo,thick+self_skin,vpairs,epairs);rebuilds+=1
    peakvp=nv;peakep=ne;k,g,e=energy(x,v,y,u,mass,mq,inertia,tri,coef,stiff,hinges,kb)
    tele[0,5]=k;tele[0,6]=g;tele[0,7]=e
    if len(y)>0:tele[0,1]=y[0,0];tele[0,2]=u[0,0];tele[0,13]=y[0,1];tele[0,14]=y[0,2]
    for step in range(steps):
        old=x.copy();oldy=y.copy()
        if present:
            air=aerodynamic_force(x,v,tri)
            for i in range(len(x)):
                if inv[i]>0:
                    v[i]+=dt*inv[i]*air[i];v[i,2]-=9.81*dt
                    decay=np.exp(-mass_damping*dt);diss+=.5*mass[i]*dot(v[i],v[i])*(1-decay*decay);v[i]*=decay;x[i]+=dt*v[i]
        for b in range(len(y)):u[b,1]-=9.81*dt;y[b]+=dt*u[b]
        if present and self_displacement(x,sanchor)>self_skin*.25:
            nv,ne=self_rebuild(x,tri,self_edges,self_vo,self_to,self_eo,self_skin+thick,vpairs,epairs);sanchor[:]=x;rebuilds+=1;peakvp=max(peakvp,nv);peakep=max(peakep,ne)
        slv[:nv]=0.;sle[:ne]=0.
        lm=np.zeros((len(tri),3));lb=np.zeros(len(hinges));lc=np.zeros((len(y),len(ids)))
        lg=np.zeros((len(y),len(profile)+1,3*len(hull)));lt=np.zeros_like(lg);ag=np.zeros((len(y),len(profile)+1,3*len(hull),4));lp=np.zeros(1);ap=np.zeros((2,2));npair=np.zeros(2)
        penmax=0.;imp=np.zeros(len(y));groundpen=0.;pairpen=0.
        for it in range(iterations+4):
            if present:
                if it<iterations:
                    membrane(x,old,inv,tri,coef,stiff,lm,dt,tau_mem,it%2==1);bending(x,old,inv,hinges,kb,lb,dt,tau_bend,it%2==1)
                pen,J=contacts(x,inv,ids,sw,y,im,ii,dims,thick,lc,dt);penmax=max(penmax,pen);imp+=J
                if self_displacement(x,sanchor)>self_skin*.4:
                    nv,ne=self_rebuild(x,tri,self_edges,self_vo,self_to,self_eo,thick+self_skin,vpairs,epairs);sanchor[:]=x;rebuilds+=1;peakvp=max(peakvp,nv);peakep=max(peakep,ne);slv[:nv]=0.;sle[:ne]=0.
                self_project(x,old,inv,tri,self_edges,vpairs,nv,epairs,ne,slv,sle,thick)
                for i in range(len(x)):
                    if inv[i]<=0:continue
                    h=profile[0,2] if x[i,0]<=profile[1,1] else max(profile[-1,2],profile[2,2]+profile[2,3]*(x[i,0]-profile[2,0]))
                    if x[i,2]<h+thick/2:x[i,2]=h+thick/2
            pairpen=max(pairpen,project_pair(y,im,ii,hull,lp,ap,npair))
            groundpen=max(groundpen,project_ground(y,im,ii,hull,profile,lg,ag))
            position_friction(y,oldy,im,ii,profile,lg,ag,lt,dt,mus,belt_speed)
        if present:v=(x-old)/dt
        u=(y-oldy)/dt
        if present:
            diss+=friction(x,v,inv,ids,sw,y,u,im,ii,dims,thick,lc,dt,mu_contact)
            diss+=self_friction(x,old,v,inv,tri,self_edges,vpairs,nv,epairs,ne,slv,sle,dt,self_mu)
        diss+=pair_friction(y,u,im,ii,lp,ap,npair,dt,pair_mu)
        dw,dd=ground_friction(y,u,im,ii,profile,lg,ag,dt,mus,belt_speed,lt);dw+=friction_work(lt,ag,dt,belt_speed);work+=dw;diss+=dd
        if (step+1)%save_every==0:xx[saveid]=x;vv[saveid]=v;yy[saveid]=y;uu[saveid]=u;saveid+=1
        if (step+1)%te==0:
            k,g,e=energy(x,v,y,u,mass,mq,inertia,tri,coef,stiff,hinges,kb);ti=(step+1)//te
            tele[ti,0]=(step+1)*dt;tele[ti,3]=np.sum(imp)/dt;tele[ti,4]=penmax
            if len(y)>0:tele[ti,1]=y[0,0];tele[ti,2]=u[0,0];tele[ti,13]=y[0,1];tele[ti,14]=y[0,2]
            tele[ti,5]=k;tele[ti,6]=g;tele[ti,7]=e;tele[ti,8]=work;tele[ti,9]=np.max(np.abs(x[:,0]));tele[ti,10]=np.max(np.abs(v));tele[ti,11]=dw/dt;tele[ti,12]=diss;tele[ti,15]=groundpen;tele[ti,16]=pairpen
        if (step+1)%(12*save_every)==0:
            with objmode():checkpoint(cpfile,xx[:saveid],vv[:saveid],yy[:saveid],uu[:saveid],tele[:(step+1)//te+1],step+1,work,diss)
    return xx,vv,yy,uu,tele,rebuilds,peakvp,peakep

def checkpoint(filename,x,v,y,u,t,step,work,diss):
    target=Path(filename);temp=target.with_suffix('.part')
    with temp.open('wb') as f:np.savez_compressed(f,positions=x,velocities=v,bag_rigid=y,bag_rigid_velocity=u,telemetry=t,step=step,belt_work=work,diss=diss)
    temp.replace(target);print('CHECKPOINT '+str(step)+' '+target.name,flush=True)

def geometry(p):
    hull=np.load(ASSETS/'backpack/support_hull.npz')['hull_base_xz'].copy();hull[:,1]-=p['bag_dimensions_m'][2]/2
    end=p['belt_end_x_m'];rend=p['ramp_end_x_m'];top=p['belt_height_m'];bottom=p['pickup_height_m']
    nose=end-p['belt_nose_radius_m']
    profile=np.array([[-3.,nose,top,0.],[nose,end,top,0.],[end,rend,top,(bottom-top)/(rend-end)],[rend,p['pickup_end_x_m'],bottom,0.]])
    return hull,profile

def simulate(p,dt=1/9600,iterations=12,nx=5,ny=25,duration=4,initial_state=None):
    """Solve from the launch state, or continue from initial_state (a saved native state: positions,
    velocities, bag_rigid, bag_rigid_velocity of one 24 Hz sample) for `duration` seconds."""
    m=mesh(p,nx,ny);E=p['curtain_young_modulus_pa'];nu=p['curtain_poisson_ratio'];h=p['curtain_thickness_m'];mu=E/(2*(1+nu));la=E*nu/(1-nu*nu)
    stiff=m['areas'][:,None]*h*np.array([[la+mu,mu,mu]]);D=E*h**3/(12*(1-nu*nu));kb=D*m['bend_weights']
    y0=np.array([[p['bag_initial_center_m'][0],p['bag_initial_center_m'][2]+p['bag_dimensions_m'][2]/2,0.]])
    mq=np.array([p['bag_mass_kg']])
    if not p.get('bag_present',[1])[0]:
        # DELETE bag: no backpack body; the curtain hangs on its own (second-bag inputs stay off).
        assert not p['second_bag_present'][0],'Deleting the first backpack keeps the second one off'
        y0=np.zeros((0,3));mq=np.zeros(0)
    if p['second_bag_present'][0]:y0=np.vstack((y0,[p['second_bag_initial_center_m'][0],p['second_bag_initial_center_m'][2]+p['bag_dimensions_m'][2]/2,0.]));mq=np.append(mq,p['second_bag_mass_kg'])
    inertia=mq*(p['bag_dimensions_m'][0]**2+p['bag_dimensions_m'][2]**2)/12;hull,profile=geometry(p)
    collider=np.load(ASSETS/'backpack/collision_field.npz');packed=np.concatenate((collider['dimensions'],collider['origin'],[float(collider['spacing'])],np.array(collider['field'].shape),collider['field'].ravel())).astype(np.float64)
    every=round(1/(24*dt));steps=round(duration*24)*every
    assert abs(every*dt-1/24)<1e-12
    x_init=m['rest'].copy();v_init=np.zeros_like(x_init);u_init=np.zeros_like(y0);u_init[:,0]=p['bag_initial_speed_m_s'];start=''
    if initial_state is not None:
        x_init,v_init,y0,u_init=(np.array(initial_state[k],dtype=np.float64) for k in ('positions','velocities','bag_rigid','bag_rigid_velocity'))
        assert x_init.shape==m['rest'].shape and v_init.shape==x_init.shape and y0.shape==(len(mq),3) and u_init.shape==y0.shape,'Saved state does not match this model'
        start=hashlib.sha256(b''.join(a.tobytes() for a in (x_init,v_init,y0,u_init))).hexdigest()
    identity=hashlib.sha256(json.dumps([p,dt,iterations,nx,ny,duration]+([start] if start else []),sort_keys=True).encode()).hexdigest()[:20]
    folder=RUNTIME/'solver_checkpoints';folder.mkdir(parents=True,exist_ok=True)
    sedges,svo,sto,seo=self_topology(m['tris'],m['strip_ids'])
    mus=np.array([p['belt_bag_friction'],p['nose_plate_friction'],p['ramp_friction'],p['pickup_friction'],p['endstop_friction']])
    r=run(m['rest'],m['invmass'],m['mass'],m['tris'],m['coeff'],stiff,m['hinges'],kb,m['sample_ids'],m['sample_w'],y0,mq,inertia,hull,profile,mus,dt,iterations,steps,every,packed,h,p['curtain_contact_friction'],p['membrane_viscosity_pa_s']/E,p['bending_viscosity_pa_s']/E,p['curtain_mass_damping_s_inv'],bool(p['curtain_present'][0]),u_init,p['belt_speed_m_s'],str(folder/(identity+'.npz')),sedges,svo,sto,seo,p['self_contact_friction'],p['self_contact_skin_m'],p['bag_bag_friction'],x_init,v_init)
    meta=dict(dt_s=dt,iterations=iterations,nx=nx,ny=ny,membrane_stiffness=stiff,bending_stiffness=kb,flexural_rigidity_N_m=D,collider=packed,support_hull=hull,support_profile=profile,bag_mass=mq,bag_pitch_inertia=inertia,
      rigid_dofs='COM x, COM z, Y-axis pitch; fixed y/roll/yaw guide reactions',rigid_mass_model='uniform packed bounding volume; declared mass and box pitch inertia',contact_model='Scan convex SDF shell coupling; scan-derived convex x/z hull and clipped finite support faces; Coulomb friction; inelastic normal projection',
      self_contact_rebuilds=int(r[5]),self_contact_peak_vertex_pairs=int(r[6]),self_contact_peak_edge_pairs=int(r[7]),extra_contact_sweeps=4,distributed_mass_damping_s_inv=p['curtain_mass_damping_s_inv'],damping_model='Kelvin-Voigt membrane/bending and passive mass-proportional force, no freezing or motion filtering',membrane_relaxation_s=p['membrane_viscosity_pa_s']/E,bending_relaxation_s=p['bending_viscosity_pa_s']/E)
    return m,r[:5],meta
