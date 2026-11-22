"""Closed finite-strain rubber ribbon + native MuJoCo frictional contact.

No Blender dependency. Triangle membrane: incompressible plane-stress
neo-Hookean equilibrium network and two objective material-strain Maxwell
branches in BOTH membrane stress and bending moment. Shell hinges use scalar
signed dihedral strains and strain rates,
not a world-space curvature-vector rate. All units are SI. Material numbers
are explicit reconstruction assumptions, not measurements of a real sample.
"""
import os
os.environ.setdefault('MUJOCO_GL','disable')
from pathlib import Path
import argparse,hashlib,json,platform,sys,time
import numpy as np
from numba import njit,cfunc,carray,types
from numba.extending import intrinsic
S=Path(__file__).resolve().parent
# MuJoCo 3.17.0 (the version of the accepted solve) unpacked from its wheel; see the scene README.
RUNTIME=Path(os.environ.get('PCVE_MUJOCO_RUNTIME',S.parents[3]/'.runtime/rubber_band_wood_slider/mujoco'))
sys.path.insert(0,str(RUNTIME))
import mujoco
def _warning(message):
    if 'has no equality constraints or passive forces' in message:
        return  # Finite-strain forces are supplied by our compiled callback.
    print('MUJOCO_REJECTED_WARNING',message,flush=True)
    raise RuntimeError('Reject MuJoCo warning: '+message)
mujoco.set_mju_user_warning(_warning)

BASE=dict(young_pa=1200000.,mass_kg=.036,friction=.20,wood_band_friction=.65,
    density_kg_m3=1000.,band_width_m=.0016,band_thickness_m=.0006,loop_rest_m=.200,
    equilibrium_fraction=.80,maxwell_fractions=[.15,.05],maxwell_times_s=[.030,.35],
    membrane_viscosity_pa_s=20.,bending_viscosity_pa_s=40.,poisson=.49,
    floor_z_m=.006,band_z_m=.0095,anchor_x_m=-.070,initial_x_m=.090,
    attachment_offset_m=-.0425,pin_radius_m=.003,slider_size_m=[.055,.042,.024],
    tongue_size_m=[.020,.020,.002],tongue_offset_m=-.035,
    guide_size_m=[.300,.066,.006],release_time_s=.50,hold_preparation_s=.40,
    band_present=[1],stopper_present=[0],stopper_position_m=[.015,0.,.016],
    stopper_size_m=[.006,.042,.020])
CASES={'source':{},'young_x0p5':{'young_pa':600000.},'mass_x3':{'mass_kg':.108},
       'friction_x2':{'friction':.40},'delete_band':{'band_present':[0]},'add_stop':{'stopper_present':[1]}}

def vec(a):return ' '.join(f'{x:.12g}' for x in np.ravel(a))
def dump(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

@njit(cache=True,inline='always')
def dot3(a,b):return a[0]*b[0]+a[1]*b[1]+a[2]*b[2]

@njit(cache=True,inline='always')
def cross3(a,b):return np.array([a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]])

@njit(cache=True)
def hinge_state(x,v,ids):
    a,b,c,d=ids
    edge=x[b]-x[a];e2=dot3(edge,edge);length=np.sqrt(e2)
    u=x[c]-x[a];w=x[d]-x[a]
    n1=cross3(edge,u);n2=cross3(w,edge)
    a1=dot3(n1,n1);a2=dot3(n2,n2)
    if min(a1,a2)<1e-24:return 0.,np.zeros((4,3)),0.
    q=np.zeros((4,3));q[2]=-length*n1/a1;q[3]=-length*n2/a2
    s2=dot3(u,edge)/e2;s3=dot3(w,edge)/e2
    q[0]=(s2-1)*q[2]+(s3-1)*q[3];q[1]=-s2*q[2]-s3*q[3]
    cosine=dot3(n1,n2)/np.sqrt(a1*a2)
    sine=dot3(cross3(n1,n2),edge)/(length*np.sqrt(a1*a2))
    angle=np.arctan2(sine,cosine);rate=0.
    for i in range(4):rate+=dot3(q[i],v[ids[i]])
    return angle,q,rate

def reference_mesh(n,rows,p):
    # A real thin band cut from a cylindrical tube: width has its own geometry
    # and may rotate freely. No world-space material director is prescribed.
    L=p['loop_rest_m'];width=p['band_width_m'];fractions=racetrack_fractions(n,p)
    lengths=np.diff(np.r_[fractions,1.])*L
    low=lengths.max()*.5000001;high=L
    for _ in range(70):
        r=(low+high)/2
        if (2*np.arcsin(lengths/(2*r))).sum()>2*np.pi:low=r
        else:high=r
    r=(low+high)/2
    theta=np.pi/2-np.r_[0.,np.cumsum(2*np.arcsin(lengths/(2*r)))[:-1]]
    rest=np.array([[r*np.cos(a),r*np.sin(a),p['band_z_m']+w]
        for a in theta for w in np.linspace(-width/2,width/2,rows)])
    uv=np.array([[fraction*L,w] for fraction in fractions for w in np.linspace(-width/2,width/2,rows)])
    tris=[]
    for i in range(n):
        k=(i+1)%n
        for j in range(rows-1):
            a=i*rows+j;b=k*rows+j;c=a+1;d=b+1
            tris.extend([(a,b,c),(c,b,d)])
    tris=np.asarray(tris,dtype=np.int32);inv=[];areas=[]
    edge_map={}
    for tri in tris:
        coords=uv[tri].copy()
        if np.ptp(coords[:,0])>L/2:coords[coords[:,0]<L/2,0]+=L
        mat=(coords[1:]-coords[0]).T
        inv.append(np.linalg.inv(mat));areas.append(abs(np.linalg.det(mat))/2)
        for j in range(3):
            a,b,c=map(int,(tri[j],tri[(j+1)%3],tri[(j+2)%3]))
            key=tuple(sorted((a,b)))
            edge_map.setdefault(key,[]).append((a,b,c))
    hinges=[];weights=[];angles=[]
    zero=np.zeros_like(rest)
    for adjacent in edge_map.values():
        if len(adjacent)!=2:continue
        a,b,c=adjacent[0];d=adjacent[1][2]
        ids=np.array([a,b,c,d],dtype=np.int32);hinges.append(ids)
        edge=rest[b]-rest[a];e2=np.dot(edge,edge)
        area_sum=(np.linalg.norm(np.cross(edge,rest[c]-rest[a]))+np.linalg.norm(np.cross(rest[d]-rest[a],edge)))/2
        # The dual width is (A1+A2)/edge_length. A cylindrical patch then
        # converges to 1/2 D kappa^2 per unit area without an empirical factor.
        weights.append(e2/area_sum)
        angles.append(hinge_state(rest,zero,ids)[0])
    return rest,uv,tris,np.asarray(inv),np.asarray(areas),np.asarray(hinges,dtype=np.int32),np.asarray(weights),np.asarray(angles)

def racetrack_fractions(n,p):
    if n<32 or n%2:raise ValueError('Use an even loop resolution >=32')
    span=p['initial_x_m']+p['attachment_offset_m']-p['anchor_x_m']
    rad=p['pin_radius_m']+p['band_thickness_m']/2+.000015
    perimeter=2*span+2*np.pi*rad;cap_edges=8;leg_edges=(n-2*cap_edges)//2
    lengths=[span,np.pi*rad,span,np.pi*rad];counts=[leg_edges,cap_edges,leg_edges,cap_edges]
    positions=[];offset=0.
    for length,count in zip(lengths,counts):
        positions.extend(offset+np.arange(count)*length/count);offset+=length
    return np.asarray(positions)/perimeter

def racetrack(n,rows,p):
    left=p['anchor_x_m'];right=p['initial_x_m']+p['attachment_offset_m']
    rad=p['pin_radius_m']+p['band_thickness_m']/2+.000015
    # Vertical strip: the band bends around the pegs about its weak axis.
    perimeter=2*(right-left)+2*np.pi*rad
    points=[]
    for fraction in racetrack_fractions(n,p):
        s=fraction*perimeter;span=right-left
        if s<span:x=left+s;y=rad
        elif s<span+np.pi*rad:
            a=np.pi/2-(s-span)/rad;x=right+rad*np.cos(a);y=rad*np.sin(a)
        elif s<2*span+np.pi*rad:x=right-(s-span-np.pi*rad);y=-rad
        else:
            a=-np.pi/2-(s-2*span-np.pi*rad)/rad;x=left+rad*np.cos(a);y=rad*np.sin(a)
        for w in np.linspace(-p['band_width_m']/2,p['band_width_m']/2,rows):points.append([x,y,p['band_z_m']+w])
    return np.asarray(points)

@njit(cache=True)
def shell_forces(x,v,tri,inv_dm,areas,hinges,weights,theta0,history,pvalues,dt,advance):
    # pvalues: E, h, eta_membrane, eta_bending, nu, equilibrium fraction,
    # g1,g2,tau1,tau2. Internal variables live in reference material coordinates.
    E,h,eta,eta_b,nu,g_inf,g1,g2,tau1,tau2=pvalues
    force=np.zeros_like(x);elastic=0.;vis_power=0.;max_stretch=1.;min_area=1.
    fractions=np.array([g1,g2]);times=np.array([tau1,tau2])
    for k in range(len(tri)):
        ia,ib,ic=tri[k];F=np.empty((3,2));V=np.empty((3,2))
        for a in range(3):
            F[a,0]=(x[ib,a]-x[ia,a])*inv_dm[k,0,0]+(x[ic,a]-x[ia,a])*inv_dm[k,1,0]
            F[a,1]=(x[ib,a]-x[ia,a])*inv_dm[k,0,1]+(x[ic,a]-x[ia,a])*inv_dm[k,1,1]
            V[a,0]=(v[ib,a]-v[ia,a])*inv_dm[k,0,0]+(v[ic,a]-v[ia,a])*inv_dm[k,1,0]
            V[a,1]=(v[ib,a]-v[ia,a])*inv_dm[k,0,1]+(v[ic,a]-v[ia,a])*inv_dm[k,1,1]
        C=np.zeros((2,2));G=np.zeros((2,2))
        for a in range(3):
            C[0,0]+=F[a,0]*F[a,0];C[0,1]+=F[a,0]*F[a,1];C[1,1]+=F[a,1]*F[a,1]
            G[0,0]+=F[a,0]*V[a,0];G[0,1]+=F[a,0]*V[a,1];G[1,0]+=F[a,1]*V[a,0];G[1,1]+=F[a,1]*V[a,1]
        C[1,0]=C[0,1];det=C[0,0]*C[1,1]-C[0,1]**2
        if det<1e-8:return force,1e100,1e100,1e100,0.
        strain=np.array([.5*(C[0,0]-1),.5*(C[1,1]-1),.5*C[0,1]])
        rate=np.array([G[0,0],G[1,1],.5*(G[0,1]+G[1,0])])
        stress=np.array([eta*(3*rate[0]+rate[1]),eta*(rate[0]+3*rate[1]),2*eta*rate[2]])
        vis_power+=h*areas[k]*(stress[0]*rate[0]+stress[1]*rate[1]+2*stress[2]*rate[2])
        for branch in range(2):
            diff=strain-history[branch,k]
            if advance:
                history[branch,k]+=(-np.expm1(-dt/times[branch]))*diff
                diff=strain-history[branch,k]
            modulus=fractions[branch]*E
            a=modulus/(1-nu*nu);mu=modulus/(2*(1+nu))
            ss=np.array([a*(diff[0]+nu*diff[1]),a*(diff[1]+nu*diff[0]),2*mu*diff[2]])
            stress+=ss
            density=.5*(ss[0]*diff[0]+ss[1]*diff[1]+2*ss[2]*diff[2])
            elastic+=density*h*areas[k];vis_power+=2*density*h*areas[k]/times[branch]
        mu=E*g_inf/3
        for a in range(3):
            p1=F[a,0]*stress[0]+F[a,1]*stress[2]+mu*(F[a,0]-(F[a,0]*C[1,1]-F[a,1]*C[0,1])/(det*det))
            p2=F[a,0]*stress[2]+F[a,1]*stress[1]+mu*(F[a,1]-(F[a,1]*C[0,0]-F[a,0]*C[0,1])/(det*det))
            f1=-(p1*inv_dm[k,0,0]+p2*inv_dm[k,0,1])*areas[k]*h
            f2=-(p1*inv_dm[k,1,0]+p2*inv_dm[k,1,1])*areas[k]*h
            force[ib,a]+=f1;force[ic,a]+=f2;force[ia,a]-=f1+f2
        elastic+=.5*mu*h*areas[k]*(C[0,0]+C[1,1]+1/det-3.)
        tr=C[0,0]+C[1,1];lam=np.sqrt(.5*(tr+np.sqrt(max(0.,tr*tr-4*det))))
        max_stretch=max(max_stretch,lam);min_area=min(min_area,np.sqrt(det))
    rigidity=E*h**3/(12*(1-nu*nu));bend_vis=eta_b*h**3/(12*(1-nu*nu))
    for k in range(len(hinges)):
        theta,q,rate=hinge_state(x,v,hinges[k]);delta=theta-theta0[k]
        delta=(delta+np.pi)%(2*np.pi)-np.pi
        stiffness=rigidity*weights[k];damper=bend_vis*weights[k]
        # The same material relaxation acts on stress through the thickness,
        # hence on the bending moment too. Its scalar material curvature history
        # is objective; it does not damp a rigid rotation of a curved ribbon.
        moment=g_inf*stiffness*delta+damper*rate
        elastic+=.5*g_inf*stiffness*delta*delta;vis_power+=damper*rate*rate
        for branch in range(2):
            offset=len(tri)+k;diff=delta-history[branch,offset,0]
            if advance:
                history[branch,offset,0]+=(-np.expm1(-dt/times[branch]))*diff
                diff=delta-history[branch,offset,0]
            branch_stiffness=fractions[branch]*stiffness
            moment+=branch_stiffness*diff
            elastic+=.5*branch_stiffness*diff*diff
            vis_power+=branch_stiffness*diff*diff/times[branch]
        for j in range(4):force[hinges[k,j]]-=moment*q[j]
    return force,elastic,vis_power,max_stretch,min_area

@intrinsic
def float_pointer(typingctx,source):
    signature=types.CPointer(types.float64)(source)
    def codegen(context,builder,sig,args):return builder.inttoptr(args[0],context.get_value_type(sig.return_type))
    return signature,codegen

def clamp_groups(n,rows,p):
    start=racetrack(n,rows,p)
    left=np.flatnonzero(start[:,0]<=p['anchor_x_m']+1e-12)
    right=np.flatnonzero(start[:,0]>=p['initial_x_m']+p['attachment_offset_m']-1e-12)
    return left,right

@njit(cache=True)
def vertex_velocities(qvel,dofs):
    result=np.zeros(dofs.shape)
    for i in range(len(dofs)):
        for j in range(3):
            if dofs[i,j]>=0:result[i,j]=qvel[dofs[i,j]]
    return result

def model_for(p,n=128,rows=2,dt=1/48000):
    rest,uv,tri,inv,areas,hinges,weights,theta0=reference_mesh(n,rows,p)
    mass=np.zeros(len(rest))
    for ids,area in zip(tri,areas):mass[ids]+=p['density_kg_m3']*p['band_thickness_m']*area/3
    nodes=[];right_nodes=[];names=[]
    start=racetrack(n,rows,p);left_ids,right_ids=clamp_groups(n,rows,p)
    if p['band_present'][0]:
        for i,point in enumerate(rest):
            name=f'rubber_{i}';names.append(name)
            inertia=f'<inertial mass="{mass[i]:.12g}" pos="0 0 0" diaginertia="1e-12 1e-12 1e-12"/>'
            if i in left_ids:
                nodes.append(f'<body name="{name}" pos="{vec(start[i])}">{inertia}</body>')
            elif i in right_ids:
                local=start[i]-np.array([p['initial_x_m'],0.,0.])
                right_nodes.append(f'<body name="{name}" pos="{vec(local)}">{inertia}</body>')
            else:
                nodes.append(f'<body name="{name}" pos="{vec(point)}">{inertia}'
                    '<joint type="slide" axis="1 0 0"/><joint type="slide" axis="0 1 0"/><joint type="slide" axis="0 0 1"/></body>')
    r=p['pin_radius_m'];floor=p['floor_z_m'];z=p['band_z_m']
    def peg(prefix,x):
        return (f'<geom name="{prefix}_shaft" type="cylinder" pos="{x} 0 {(floor+.013)/2}" size="{r} {(.013-floor)/2}" contype="8" conaffinity="6"/>'
            f'<geom name="{prefix}_lower_lip" type="cylinder" pos="{x} 0 .0080" size=".00365 .0002" contype="8" conaffinity="6"/>'
            f'<geom name="{prefix}_upper_lip" type="cylinder" pos="{x} 0 .0110" size=".00365 .0002" contype="8" conaffinity="6"/>')
    stop=''
    if p['stopper_present'][0]:
        for sign in [-1,1]:stop+=f'<geom name="added_stop_{sign}" type="box" pos="{p["stopper_position_m"][0]} {sign*.016} .016" size=".003 .005 .010" contype="8" conaffinity="6"/>'
    flex=''
    if names:
        flex=f'<deformable><flex name="rubber_loop" dim="2" radius="{p["band_thickness_m"]/2}" body="{" ".join(names)}" vertex="{vec(np.zeros_like(rest))}" element="{vec(tri)}">'
        flex+=f'<contact selfcollide="auto" contype="2" conaffinity="15" condim="3" friction="{p["wood_band_friction"]} .0001 .00001" solref=".0002 1" solimp=".995 .9999 .00005"/></flex></deformable>'
    # Wood floor friction is represented by the prismatic joint's exact dry
    # friction constraint. Band contact uses native finite-thickness friction.
    xml=f'''<mujoco model="closed_rubber_pullback"><compiler angle="radian"/>
    <option timestep="{dt}" integrator="Euler" solver="Newton" jacobian="sparse" iterations="50" tolerance="1e-10" gravity="0 0 -9.81"><flag energy="enable"/></option>
    <size memory="128M"/><default><geom condim="3" contype="1" conaffinity="2" friction="{p['wood_band_friction']} .0001 .00001" solref=".0002 1" solimp=".995 .9999 .00005"/>
    <default class="moving"><geom contype="4" conaffinity="10"/></default></default>
    <worldbody><geom name="guide_floor" type="plane" pos="0 0 {floor}" size=".15 .033 .003"/>
    <geom name="rail_front" type="box" pos="0 -.0275 .012" size=".15 .005 .006"/><geom name="rail_back" type="box" pos="0 .0275 .012" size=".15 .005 .006"/>
    {peg('anchor',p['anchor_x_m'])}{stop}
    <body name="wood_slider" childclass="moving" pos="{p['initial_x_m']} 0 0"><inertial pos="0 0 .018" mass="{p['mass_kg']}" diaginertia=".00001 .00001 .00001"/>
    <joint name="slide" type="slide" axis="1 0 0" frictionloss="{p['friction']*p['mass_kg']*9.81}" solreffriction=".0002 1" solimpfriction=".99999 .99999 .000001"/>
    <geom name="slider_main" type="box" pos="0 0 .018" size=".0275 .021 .012"/>
    <geom name="slider_tongue" type="box" pos="-.035 0 .007" size=".010 .010 .001"/>
    {peg('slider_pin',p['attachment_offset_m'])}{''.join(right_nodes)}</body>{''.join(nodes)}</worldbody>
    {flex}<equality><joint name="held_slider" joint1="slide" polycoef="0 0 0 0 0" solref=".00004 1" solimp=".9999 .9999 .000001"/></equality></mujoco>'''
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    dofs=[];qadr=[]
    if names:
        for i,name in enumerate(names):
            if i in left_ids:
                dofs.append(np.array([-1,-1,-1]));qadr.append(-1);continue
            if i in right_ids:
                da=model.jnt_dofadr[model.joint('slide').id]
                dofs.append(np.array([da,-1,-1]));qadr.append(-1);continue
            bid=model.body(name).id;jid=model.body_jntadr[bid]
            qa=model.jnt_qposadr[jid];da=model.jnt_dofadr[jid]
            data.qpos[qa:qa+3]=start[i]-rest[i];dofs.append(np.arange(da,da+3));qadr.append(qa)
    mujoco.mj_forward(model,data)
    return model,data,(rest,uv,tri,inv,areas,hinges,weights,theta0),np.asarray(dofs),np.asarray(qadr),xml

def make_callback(m,d,mesh,dofs,p,history,monitor):
    rest,uv,tri,inv,areas,hinges,weights,theta0=mesh
    n=len(dofs);nv=m.nv
    pv=np.array([p[k] for k in ['young_pa','band_thickness_m','membrane_viscosity_pa_s','bending_viscosity_pa_s','poisson','equilibrium_fraction']]+p['maxwell_fractions']+p['maxwell_times_s'])
    xa=np.int64(d.flexvert_xpos.ctypes.data);va=np.int64(d.qvel.ctypes.data);fa=np.int64(d.qfrc_passive.ctypes.data)
    ha=np.int64(history.ctypes.data);ma=np.int64(monitor.ctypes.data);ca=np.int64(d.qfrc_constraint.ctypes.data);dt=m.opt.timestep
    nt=len(tri);nh=len(hinges)
    previous_velocity=np.zeros(nv);ledger_steps=np.zeros(1)
    pa=np.int64(previous_velocity.ctypes.data);la=np.int64(ledger_steps.ctypes.data)
    @cfunc(types.void(types.voidptr,types.voidptr))
    def callback(mptr,dptr):
        x=carray(float_pointer(xa),(n,3));qv=carray(float_pointer(va),(nv,));qf=carray(float_pointer(fa),(nv,))
        hist=carray(float_pointer(ha),(2,nt+nh,3));mon=carray(float_pointer(ma),(10,));constraint=carray(float_pointer(ca),(nv,))
        vel=np.empty((n,3))
        for i in range(n):
            for j in range(3):vel[i,j]=qv[dofs[i,j]] if dofs[i,j]>=0 else 0.
        previous=carray(float_pointer(pa),(nv,));ledger=carray(float_pointer(la),(1,))
        # Flush completed-step constraint work at the velocity midpoint. This
        # diagnostic never enters forces or integration, including at impacts.
        if mon[7]>ledger[0]:
            for j in range(nv):
                mon[8]+=.5*constraint[j]*(qv[j]+previous[j])*dt
                previous[j]=qv[j]
            ledger[0]=mon[7]
        advance=mon[9]>.5
        force,energy,power,stretch,area=shell_forces(x,vel,tri,inv,areas,hinges,weights,theta0,hist,pv,dt,advance)
        # Physical normal drag on the actual finite-width surface, Cd=1.2.
        for k in range(nt):
            ia,ib,ic=tri[k];normal=cross3(x[ib]-x[ia],x[ic]-x[ia]);twice=np.sqrt(dot3(normal,normal))
            if twice>1e-15:
                normal/=twice;vv=(vel[ia]+vel[ib]+vel[ic])/3;speed=dot3(vv,normal)
                drag=-.5*1.2*1.2*(twice/2)*abs(speed)*speed*normal
                force[ia]+=drag/3;force[ib]+=drag/3;force[ic]+=drag/3;power-=dot3(drag,vv)
        for i in range(n):
            for j in range(3):
                if dofs[i,j]>=0:qf[dofs[i,j]]+=force[i,j]
        mon[0]=energy;mon[1]=power;mon[2]=stretch;mon[3]=area
        if advance:
            mon[4]+=power*dt;mon[5]=max(mon[5],stretch);mon[6]=min(mon[6],area);mon[7]+=1
    callback._ledger_keepalive=(previous_velocity,ledger_steps)
    return callback

def simulate(case='source',out=None,n=128,rows=2,dt=1/192000,seconds=4.,prepare=.40,initial=None,save_initial=None):
    if out is None:raise ValueError('Pass --out (outside scripts/)')
    p={**BASE,**CASES[case]};out=Path(out);out.mkdir(parents=True,exist_ok=True)
    m,d,mesh,dofs,qadr,xml=model_for(p,n,rows,dt);rest,uv,tri,inv,areas,hinges,weights,theta0=mesh
    history=np.zeros((2,len(tri)+len(hinges),3));monitor=np.zeros(10);monitor[6]=1;monitor[9]=1
    callback=None;started=time.perf_counter()
    if p['band_present'][0]:
        callback=make_callback(m,d,mesh,dofs,p,history,monitor)
        mujoco.set_mjcb_passive(callback.ctypes)
    try:
        if initial:
            frozen=np.load(initial)
            if p['band_present'][0]:
                if frozen['qpos'].shape!=d.qpos.shape:raise ValueError('shared initial mesh differs')
                d.qpos[:]=frozen['qpos'];history[:]=frozen['material_history']
            else:d.qpos[0]=frozen['qpos'][0]
            d.qvel[:]=0.
        elif prepare:
            mujoco.mj_step(m,d,nstep=round(prepare/dt))
            d.qvel[:]=0.
        # Freeze one mechanically prepared common starting geometry for all
        # edits. Constitutive internal strains are copied, never material poses.
        if callback is not None:mujoco.set_mjcb_passive(None)
        mujoco.mj_forward(m,d)
        if save_initial:
            Path(save_initial).parent.mkdir(parents=True,exist_ok=True)
            np.savez_compressed(save_initial,qpos=d.qpos.copy(),material_history=history.copy(),band_vertices=d.flexvert_xpos.copy())
        d.time=0.;mujoco.set_mjcb_passive(None);mujoco.mj_forward(m,d)
        sample_hz=480;stride=round(1/(sample_hz*dt));steps=round(seconds/dt)
        pos=[];trace=[];qpos=[];qvel=[]
        absent_vertices=frozen['band_vertices'] if initial and 'band_vertices' in frozen.files else racetrack(n,rows,p)
        slide=m.joint('slide').qposadr[0];sv=m.joint('slide').dofadr[0]
        for step in range(0,steps+1,stride):
            if step*dt>=p['release_time_s']-dt/2:d.eq_active[m.equality('held_slider').id]=0
            if callback is not None:
                monitor[9]=0.;mujoco.set_mjcb_passive(callback.ctypes)
            mujoco.mj_forward(m,d)
            if p['band_present'][0]:
                x=d.flexvert_xpos.copy();v=vertex_velocities(d.qvel,dofs)
                pv=np.array([p[k] for k in ['young_pa','band_thickness_m','membrane_viscosity_pa_s','bending_viscosity_pa_s','poisson','equilibrium_fraction']]+p['maxwell_fractions']+p['maxwell_times_s'])
                _,energy,power,stretch,area=shell_forces(x,v,tri,inv,areas,hinges,weights,theta0,history,pv,dt,False)
            else:
                x=absent_vertices;energy=0.;power=0.;stretch=1.;area=1.
            pos.append(x);qpos.append(d.qpos.copy());qvel.append(d.qvel.copy())
            penetration=max([0.]+[-float(c.dist) for c in d.contact])
            trace.append([step*dt,p['initial_x_m']+d.qpos[slide],d.qvel[sv],energy,power,stretch,area,d.energy[1],monitor[4],penetration,d.ncon,d.energy[0],monitor[8],float(d.solver_niter[0])])
            if step%round(.5/dt)==0:print('STATE',case,round(step*dt,3),'x',round(trace[-1][1],6),'band_E',energy,'contacts',d.ncon,flush=True)
            if not np.isfinite(d.qpos).all() or stretch>2 or area<.4:raise RuntimeError('invalid deformation; reject development run')
            if step==steps:break
            if callback is not None:monitor[9]=1.
            mujoco.mj_step(m,d,nstep=min(stride,steps-step))
    finally:mujoco.set_mjcb_passive(None)
    trace=np.asarray(trace);pos=np.asarray(pos)
    left_ids,right_ids=clamp_groups(n,rows,p)
    left_error=float(np.linalg.norm(pos[:,left_ids]-pos[0,left_ids],axis=2).max())
    displacement=trace[:,1]-trace[0,1]
    relative=pos[:,right_ids]-pos[0,right_ids]-displacement[:,None,None]*np.array([1.,0.,0.])
    right_error=float(np.linalg.norm(relative,axis=2).max())
    np.savez_compressed(out/'states.npz',times=trace[:,0],band_vertices=pos,trace=trace,qpos=np.asarray(qpos),qvel=np.asarray(qvel),triangles=tri,rest_vertices=rest,uv=uv,hinges=hinges,hinge_rest_angles=theta0,final_material_history=history,clamped_left_ids=left_ids,clamped_right_ids=right_ids)
    (out/'model.xml').write_text(xml,encoding='utf-8')
    info={'revision':out.parent.name,'case_id':case,'physics':p,'solver':'MuJoCo 3.17.0 CPU contacts + closed objective finite-strain shell with Maxwell membrane and bending response','mujoco':mujoco.__version__,
        'host':platform.node(),'python':platform.python_version(),'n_loop':n,'width_rows':rows,'dt_s':dt,'state_rate_hz':480,'duration_s':seconds,'preparation_s':prepare if not initial else 0.,
        'shared_initial_sha256':hashlib.sha256(Path(initial).read_bytes()).hexdigest() if initial else None,
        'numerical_constraints':{'joint_friction_solref':[.0002,1.],'joint_friction_solimp':[.99999,.99999,.000001],
            'band_contact_solref':[.0002,1.],'band_contact_solimp':[.995,.9999,.00005]},
        'constraint_work_method':'completed native-step force dot midpoint velocity dt; diagnostic only',
        'native_contact_arena_bytes':int(m.narena),'peak_native_arena_use_bytes':int(d.maxuse_arena),
        'wall_s':time.perf_counter()-started,'material_calibrated':False,'material_internal_variables':'two Maxwell branches for each membrane Green strain and each signed dihedral bending strain',
        'trace_columns':['time_s','slider_x_m','slider_vx_m_s','rubber_energy_j','rubber_dissipation_w','max_principal_stretch','min_area_ratio','kinetic_energy_j','rubber_dissipated_j','max_contact_penetration_m','contacts','gravity_energy_j','constraint_work_j','solver_iterations'],
        'metrics':{'displacement_m':float(trace[0,1]-trace[-1,1]),'peak_slider_speed_m_s':float(abs(trace[:,2]).max()),'max_contact_penetration_m':float(trace[:,9].max())}}
    info['boundary_conditions']={'left':'finite material arc fixed directly to world, no slip or equality compliance','right':'finite material arc rigidly attached to prismatic slider; membrane and bending forces mapped by the exact translational Jacobian',
        'left_material_point_count':len(left_ids),'right_material_point_count':len(right_ids),'applicable':bool(p['band_present'][0]),
        'max_left_drift_m':left_error if p['band_present'][0] else None,'max_right_attachment_slip_m':right_error if p['band_present'][0] else None}
    dump(out/'physics.json',info);print('DONE',json.dumps(info['metrics']), 'wall_s',info['wall_s'],flush=True)
    return pos,trace,info

if __name__=='__main__':
    a=argparse.ArgumentParser();a.add_argument('--case',choices=CASES,default='source');a.add_argument('--n',type=int,default=128);a.add_argument('--rows',type=int,default=2)
    a.add_argument('--dt',type=float,default=1/192000);a.add_argument('--seconds',type=float,default=4.);a.add_argument('--prepare',type=float,default=.4);a.add_argument('--out',type=Path)
    a.add_argument('--initial',type=Path);a.add_argument('--save-initial',type=Path)
    v=a.parse_args();simulate(v.case,v.out,v.n,v.rows,v.dt,v.seconds,v.prepare,v.initial,v.save_initial)
