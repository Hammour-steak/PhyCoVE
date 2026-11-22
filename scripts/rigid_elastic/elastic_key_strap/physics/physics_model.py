"""Finite-strain membrane forces coupled to native MuJoCo rigid/flex dynamics.

No Blender imports. Neo-Hookean plane-stress membrane; native discrete bending;
objective reference-strain viscosity with nonnegative continuous dissipation.
All visible dynamic geometry is exported from the numerical solution.
"""
import os
os.environ.setdefault('MUJOCO_GL','disable')
from pathlib import Path
import sys, json, time, socket, hashlib, argparse
import numpy as np
import mujoco
from numba import njit, cfunc, carray, types
from numba.extending import intrinsic
from scipy.optimize import brentq
from scipy.spatial.transform import Rotation

FORMAL=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(FORMAL),str(FORMAL.parents[1])]
import edit_vocab
from pcve_assets import asset

def dump(p,value):
    Path(p).parent.mkdir(parents=True,exist_ok=True)
    Path(p).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def vec(v): return ' '.join(f'{a:.12g}' for a in np.ravel(v))

@intrinsic
def float_pointer(typingctx, source):
    signature=types.CPointer(types.float64)(source)
    def codegen(context,builder,sig,args):
        return builder.inttoptr(args[0],context.get_value_type(sig.return_type))
    return signature,codegen

@njit(cache=False)
def membrane_forces(x,v,tri,inv_dm,areas,mu,h,eta):
    forces=np.zeros_like(x); energy=0.; diss=0.; peak=0.
    for t in range(len(tri)):
        ia,ib,ic=tri[t]
        F=np.empty((3,2)); V=np.empty((3,2))
        c11=0.;c12=0.;c22=0.;e11=0.;e12=0.;e22=0.
        for a in range(3):
            d1=x[ib,a]-x[ia,a];d2=x[ic,a]-x[ia,a]
            v1=v[ib,a]-v[ia,a];v2=v[ic,a]-v[ia,a]
            F[a,0]=d1*inv_dm[t,0,0]+d2*inv_dm[t,1,0]
            F[a,1]=d1*inv_dm[t,0,1]+d2*inv_dm[t,1,1]
            V[a,0]=v1*inv_dm[t,0,0]+v2*inv_dm[t,1,0]
            V[a,1]=v1*inv_dm[t,0,1]+v2*inv_dm[t,1,1]
            c11+=F[a,0]*F[a,0];c12+=F[a,0]*F[a,1];c22+=F[a,1]*F[a,1]
            e11+=F[a,0]*V[a,0];e22+=F[a,1]*V[a,1]
            e12+=.5*(F[a,0]*V[a,1]+F[a,1]*V[a,0])
        det=c11*c22-c12*c12
        if det <= 1e-10: return forces,1e100,1e100,1e100
        s11=eta*(3*e11+e22);s22=eta*(e11+3*e22);s12=2*eta*e12
        for a in range(3):
            p1=mu*(F[a,0]-(F[a,0]*c22-F[a,1]*c12)/(det*det))+F[a,0]*s11+F[a,1]*s12
            p2=mu*(F[a,1]-(F[a,1]*c11-F[a,0]*c12)/(det*det))+F[a,0]*s12+F[a,1]*s22
            h1=-(p1*inv_dm[t,0,0]+p2*inv_dm[t,0,1])*areas[t]*h
            h2=-(p1*inv_dm[t,1,0]+p2*inv_dm[t,1,1])*areas[t]*h
            forces[ib,a]+=h1;forces[ic,a]+=h2;forces[ia,a]-=h1+h2
        energy+=0.5*mu*h*areas[t]*(c11+c22+1./det-3.)
        diss+=h*areas[t]*(s11*e11+s22*e22+2*s12*e12)
        tr=c11+c22
        eigenmax=(tr+np.sqrt(max(0.,tr*tr-4.*det)))*0.5
        peak=max(peak,np.sqrt(eigenmax))
    return forces,energy,diss,peak

def ribbon_reference(c):
    n=c['mesh_rows']; w=c['strap_width_m']; L=c['strap_length_m']; a=np.array(c['anchor_m'])
    uv=np.array([(j*w-w/2,i*L/(n-1)) for i in range(n) for j in range(2)])
    rest=np.array([(u,a[1],a[2]-s) for u,s in uv])
    tri=[]
    for i in range(n-1):
        k=2*i; tri.extend([(k,k+2,k+1),(k+1,k+2,k+3)])
    tri=np.array(tri,dtype=np.int32)
    inv=[]; areas=[]
    for t in tri:
        dm=(uv[t[1:]]-uv[t[0]]).T
        inv.append(np.linalg.inv(dm));areas.append(abs(np.linalg.det(dm))/2)
    return rest,uv,tri,np.array(inv),np.array(areas)

def initial_ribbon(c,uv):
    L=c['strap_length_m']; H=L-c['initial_lift_m']; dx=c['initial_lateral_m']
    s=np.linspace(0,1,4097)
    def arclength(A):
        return np.trapz(np.sqrt(H*H+dx*dx+(A*np.pi*np.cos(np.pi*s))**2),s)
    A=brentq(lambda A:arclength(A)-L,0.,L)
    speed=np.sqrt(H*H+dx*dx+(A*np.pi*np.cos(np.pi*s))**2)
    cumulative=np.r_[0.,np.cumsum((speed[:-1]+speed[1:])*np.diff(s)*0.5)]
    ss=np.interp(uv[:,1],cumulative,s)
    a=np.array(c['anchor_m'])
    # Width follows the cross product of the director and centreline tangent.
    tang=np.column_stack((np.full_like(ss,dx),-A*np.pi*np.cos(np.pi*ss),np.full_like(ss,-H)))
    tang/=np.linalg.norm(tang,axis=1)[:,None]
    width=np.tile(np.array([1.,0.,0.]),(len(ss),1))
    width-=np.sum(width*tang,axis=1)[:,None]*tang
    width/=np.linalg.norm(width,axis=1)[:,None]
    pos=np.column_stack((a[0]+dx*ss,a[1]-A*np.sin(np.pi*ss),a[2]-H*ss))
    pos+=width*uv[:,0,None]
    # Ferrule boundaries stay horizontal: exactly the native rigid attachments.
    pos[:2]=np.array([[-c['strap_width_m']/2,a[1],a[2]], [c['strap_width_m']/2,a[1],a[2]]])
    pos[-2:]=np.array([[dx-c['strap_width_m']/2,a[1],a[2]-H], [dx+c['strap_width_m']/2,a[1],a[2]-H]])
    return pos

def build_model(c,geometry_root=None):
    rest,uv,tri,inv,areas=ribbon_reference(c)
    present=bool(c['strap_present'][0]); n=len(rest); r=c['ring_radius_m']
    # DELETE keyring: no keyring body (and so no keys or fob, which hang from it); the strap's lower edge is free.
    ring_present=bool(c.get('keyring_present',[1])[0])
    ring_rest=np.array([0,c['anchor_m'][1],c['anchor_m'][2]-c['strap_length_m']-r])
    mass=np.zeros(n)
    for t,area in zip(tri,areas):mass[t]+=area*c['strap_thickness_m']*c['strap_density_kg_m3']/3
    body=[]; fbody=[]; flocal=[]; constraints=[]
    for i,p in enumerate(rest):
        fbody.append(f'p{i}'); flocal.append(np.zeros(3))
        if present:
            body.append(f'<body name="p{i}" pos="{vec(p)}"><inertial pos="0 0 0" mass="{mass[i]}" diaginertia="1e-11 1e-11 1e-11"/>'
                        f'<joint type="slide" axis="1 0 0"/><joint type="slide" axis="0 1 0"/><joint type="slide" axis="0 0 1"/></body>')
            if i<2 or (i>=n-2 and ring_present):
                body2='' if i<2 else 'body2="keyring"'
                constraints.append(f'<connect body1="p{i}" {body2} anchor="0 0 0" solref="0.00005 1" solimp="0.9999 0.9999 0.000001"/>')
    assets=[]; keys=[]
    for k in range(2):
        mesh=np.load((Path(geometry_root) if geometry_root else asset('scenes/elastic_key_strap/prepared'))/f'key{k+1}.npz')
        vv=mesh['vertices'];tt=mesh['triangles']
        assets.append(f'<mesh name="keymesh{k+1}" vertex="{vec(vv)}" face="{vec(tt)}"/>')
        # A ball joint at the ring's lower attachment transmits force while allowing natural key sway.
        q=Rotation.from_euler('xyz',([0.025,-0.15,-0.04] if k==0 else [-0.025,0.22,0.04])).as_quat()
        quat=np.r_[q[3],q[:3]]
        xyz=[(-0.0065 if k==0 else 0.0065),(-.003 if k==0 else .003),-.009]
        keys.append(f'<body name="key{k+1}" pos="{vec(xyz)}" quat="{vec(quat)}">'
                    f'<joint type="ball" damping="0.000008" frictionloss="0.0000015"/>'
                    f'<geom name="key{k+1}_collision" type="mesh" mesh="keymesh{k+1}" mass="{c["keys_mass_kg"]*(.48 if k==0 else .52)}" friction="0.45 0.001 0.0001"/></body>')
    if c['fob_present'][0]:
        ring_initial=ring_rest+np.array([c['initial_lateral_m'],0,c['initial_lift_m']])
        fob_local=np.array(c['fob_initial_location_m'])-ring_initial
        keys.append(f'<body name="brass_fob" pos="{vec(fob_local)}"><joint type="ball" damping="0.00001" frictionloss="0.000002"/>'
                    f'<geom type="box" pos="0 0 -0.018" size="0.008 0.0015 0.014" mass="{c["fob_mass_kg"]}"/></body>')
    ringgeom=[]
    for i in range(32):
        angle=2*np.pi*np.array([i,i+1])/32
        p=np.column_stack((r*np.sin(angle),np.zeros(2),r*np.cos(angle)))
        ringgeom.append(f'<geom type="capsule" contype="4" conaffinity="1" fromto="{vec(p)}" size="0.00085" mass="{c["ring_mass_kg"]/32}"/>')
    if ring_present:
        body.append(f'<body name="keyring" pos="{vec(ring_rest)}"><freejoint/><site name="ring_origin" size="0.0001"/>'
                    +''.join(ringgeom)+''.join(keys)+'</body>')
    else:
        assets=[]
    flex=''
    if present:
        flex=f'<deformable><flex name="strap" dim="2" radius="{c["strap_thickness_m"]/2}" body="{" ".join(fbody)}" vertex="{vec(flocal)}" element="{vec(tri)}">'
        flex+='<contact selfcollide="none" internal="false" contype="2" conaffinity="1" friction="0.55 0.001 0.0001" solref="0.001 1"/>'
        flex+=f'<elasticity young="{c["strap_young_modulus_pa"]}" poisson="0.49" thickness="{c["strap_thickness_m"]}" elastic2d="bend" damping="0"/></flex></deformable>'
    xml=f'''<mujoco model="elastic_key_strap"><compiler angle="radian"/><option timestep="{c['dt_s']}" integrator="Euler" solver="Newton" iterations="60" tolerance="1e-10" gravity="0 0 -9.81"><flag energy="enable"/></option>
    <default><geom condim="3" solref="0.0003 1" solimp="0.98 0.999 0.0001" margin="0"/></default>
    <asset>{''.join(assets)}</asset><worldbody><geom name="cabinet_top" type="box" pos="0 0.02 {c['cabinet_top_m']-.015}" size="0.52 0.25 0.015" friction="0.4 0.002 0.0002"/>
    <geom name="wall" type="plane" pos="0 0.205 1" euler="1.57079632679 0 0" size="2 2 .05"/>
    {''.join(body)}</worldbody>{flex}<equality>{''.join(constraints)}</equality></mujoco>'''
    model=mujoco.MjModel.from_xml_string(xml);data=mujoco.MjData(model)
    node_dofs=[]
    if present:
        start=initial_ribbon(c,uv)
        for i in range(n):
            bid=model.body(f'p{i}').id;jid=model.body_jntadr[bid]
            qa=model.jnt_qposadr[jid];da=model.jnt_dofadr[jid]
            data.qpos[qa:qa+3]=start[i]-rest[i]
            node_dofs.append(np.arange(da,da+3))
    if ring_present:
        bid=model.body('keyring').id; jid=model.body_jntadr[bid]
        qa=model.jnt_qposadr[jid]
        data.qpos[qa:qa+3]+=np.array([c['initial_lateral_m'],0,c['initial_lift_m']])
    mujoco.mj_forward(model,data)
    return model,data,rest,uv,tri,inv,areas,np.array(node_dofs),xml

def make_passive_callback(m,d,tri,inv,areas,node_dofs,c,monitor):
    """Compiled native callback permits very small physical timesteps at CPU speed.

    Addresses point to this live MjData only. Keep the callback and monitor alive,
    clear the global callback before destroying this MjData, and never reuse it
    for another model. No position/velocity integration occurs in this kernel.
    """
    xaddr=np.int64(d.flexvert_xpos.ctypes.data);vaddr=np.int64(d.qvel.ctypes.data)
    faddr=np.int64(d.qfrc_passive.ctypes.data);monaddr=np.int64(monitor.ctypes.data)
    nv=m.nv;n=len(node_dofs);mu=c['strap_young_modulus_pa']/3
    h=c['strap_thickness_m'];eta=c['strap_viscosity_pa_s'];dt=c['dt_s']
    @cfunc(types.void(types.voidptr,types.voidptr))
    def callback(modelptr,dataptr):
        x=carray(float_pointer(xaddr),(n,3))
        qv=carray(float_pointer(vaddr),(nv,))
        qf=carray(float_pointer(faddr),(nv,))
        mon=carray(float_pointer(monaddr),(5,))
        vv=np.empty((n,3))
        for i in range(n):
            for j in range(3):vv[i,j]=qv[node_dofs[i,j]]
        f,e,p,stretch=membrane_forces(x,vv,tri,inv,areas,mu,h,eta)
        for i in range(n):
            for j in range(3):qf[node_dofs[i,j]]+=f[i,j]-0.000003*vv[i,j]
        mon[0]=e;mon[1]=p;mon[2]=stretch;mon[3]+=p*dt
        mon[4]=max(mon[4],stretch)
    return callback

CACHE_FIELDS=('times','strap_vertices','body_positions','body_quaternions','qpos','qvel')

def simulate(case_id,out,duration=None,dt_factor=1.0,rows=None,source_cache=None):
    """Solve one case. A timed case (edit_vocab.TIMED_DSL) restores the exact source state (qpos, qvel) of its
    edit frame k from source_cache, applies the edited parameters there and keeps solving; the saved
    simulation.npz holds the source samples 1..k-1 followed by the continuation."""
    if mujoco.__version__ != '3.3.7':raise RuntimeError('Requires mujoco==3.3.7')
    c=dict(edit_vocab.BASELINE);override=edit_vocab.override_for(case_id);c.update(override)
    c['dt_s']*=dt_factor
    if rows:c['mesh_rows']=rows
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    schedule=c.get('timed_edits');start_step=0;src=None
    run_c={k:v for k,v in c.items() if k!='timed_edits'}
    if schedule:
        if len(schedule)!=1 or dt_factor!=1.0 or rows:raise ValueError('A timed edit continues the accepted source solve unchanged')
        k=int(schedule[0]['frame']);run_c.update(schedule[0]['params'])
        source_cache=Path(source_cache)
        if json.loads((source_cache/'resolved_config.json').read_text())!=dict(edit_vocab.BASELINE):
            raise RuntimeError(f'{source_cache} is not the baseline source solve')
        with np.load(source_cache/'simulation.npz',allow_pickle=False) as z:src={key:z[key] for key in z.files}
    m,d,rest,uv,tri,inv,areas,node_dofs,xml=build_model(run_c)
    (out/'model.xml').write_text(xml,encoding='utf8');dump(out/'scenario_overrides.json',override)
    dump(out/'resolved_config.json',c)
    if schedule:
        stride0=round(1/(24*run_c['dt_s']));start_step=(k-1)*stride0
        if abs(src['times'][k-1]-start_step*run_c['dt_s'])>1e-12 or src['qpos'].shape[1]!=m.nq or src['qvel'].shape[1]!=m.nv:
            raise RuntimeError('The source cache does not match this model and clock')
        d.qpos[:]=src['qpos'][k-1];d.qvel[:]=src['qvel'][k-1];d.time=start_step*run_c['dt_s']
        mujoco.mj_forward(m,d)
    c=run_c
    ring_present=bool(c.get('keyring_present',[1])[0])
    ring=m.body('keyring').id if ring_present else None
    body_names=(['keyring','key1','key2']+(['brass_fob'] if c['fob_present'][0] else [])) if ring_present else []
    body_ids=np.array([m.body(x).id for x in body_names],dtype=int)
    duration=duration or edit_vocab.SPEC['duration_s']; steps=round(duration/c['dt_s'])
    stride=round(1/(24*c['dt_s']));hi_stride=round(1/(240*c['dt_s']))
    cache={'times':[],'strap_vertices':[],'body_positions':[],'body_quaternions':[],'qpos':[],'qvel':[]}
    trace=[];velocity=np.zeros_like(rest);force_tmp=np.zeros(m.nv);ring_velocity=np.zeros(6)
    energy=0.;diss=0.;stretch=1.;max_pen=0.;min_jac=1.; dissipated=0.
    t0=time.monotonic()
    # Warm the pure CPU force kernel before timing any reported physical steps.
    membrane_forces(rest,np.zeros_like(rest),tri,inv,areas,c['strap_young_modulus_pa']/3,c['strap_thickness_m'],c['strap_viscosity_pa_s'])
    monitor=np.zeros(5);monitor[2]=monitor[4]=1.
    callback=None
    if c['strap_present'][0]:
        callback=make_passive_callback(m,d,tri,inv,areas,node_dofs,c,monitor)
        mujoco.set_mjcb_passive(callback.ctypes)
    for step in range(start_step,steps+1,hi_stride):
        mujoco.mj_forward(m,d)
        if callback is not None:monitor[3]-=monitor[1]*c['dt_s']
        energy,diss,stretch,dissipated=monitor[:4]
        if step%stride==0:
            cache['times'].append(step*c['dt_s'])
            cache['strap_vertices'].append(d.flexvert_xpos.copy() if c['strap_present'][0] else np.empty((0,3)))
            cache['body_positions'].append(d.xpos[body_ids].copy());cache['body_quaternions'].append(d.xquat[body_ids].copy())
            cache['qpos'].append(d.qpos.copy());cache['qvel'].append(d.qvel.copy())
        if step%hi_stride==0:
            # without the keyring the traced point is the midpoint of the strap's free lower edge
            tracked=d.xpos[ring] if ring is not None else d.flexvert_xpos[-2:].mean(0)
            trace.append([step*c['dt_s'],*tracked,energy,stretch,diss,dissipated,float(d.energy[0]),float(d.energy[1])])
        if step==steps:break
        if not np.isfinite(energy) or energy>10 or monitor[4]>4:
            mujoco.set_mjcb_passive(None)
            raise RuntimeError(f'Unstable at t={d.time}: E={energy}, stretch={monitor[4]}')
        if d.ncon:
            max_pen=min(max_pen,min(float(con.dist) for con in d.contact))
        mujoco.mj_step(m,d,nstep=min(hi_stride,steps-step))
        if step%round(.25/c['dt_s'])==0: print(case_id,f't={d.time:.3f}',f'lambda={stretch:.3f}',flush=True)
    mujoco.set_mjcb_passive(None)
    cache={k:np.array(v) for k,v in cache.items()};trace=np.array(trace);handoff=None
    if schedule:
        i=k-1
        handoff={key:float(np.max(np.abs(cache[key][0]-src[key][i]))) for key in CACHE_FIELDS}
        if max(handoff.values())>=1e-8:raise RuntimeError(f'Source state was not restored exactly: {handoff}')
        cache={key:np.concatenate([src[key][:i],cache[key]]) for key in CACHE_FIELDS}
        if len(cache['times'])!=len(src['times']) or any(not np.array_equal(cache[key][:i],src[key][:i]) for key in CACHE_FIELDS):
            raise RuntimeError('Merged cache differs from the source before the edit frame')
        with np.load(source_cache/'trace_240hz.npz',allow_pickle=False) as z:source_trace=z['values']
        trace=np.concatenate([source_trace[source_trace[:,0]<cache['times'][i]-1e-12],trace])
    extra={'timed_edit_frame':np.array(k)} if schedule else {}
    np.savez_compressed(out/'simulation.npz',**cache,body_names=np.array(body_names),triangles=tri,uv=uv,reference=rest,**extra)
    np.savez_compressed(out/'trace_240hz.npz',values=trace,columns=np.array(['t','x','y','z','membrane_energy','max_stretch','viscous_power','dissipated','potential','kinetic']))
    z=np.array(cache['body_positions'])[:,0,2] if ring is not None else np.array(cache['strap_vertices'])[:,-2:,2].mean(1)
    report={'case_id':case_id,'solver':'MuJoCo 3.3.7 CPU + analytic plane-stress Neo-Hookean membrane',
        'simulation_hostname':socket.gethostname(),'simulation_platform':sys.platform,
        'cpu_only':True,'blender_used':False,'dt_s':c['dt_s'],'steps':steps,'frames_including_endpoint':len(z),
        'elapsed_s':time.monotonic()-t0,'minimum_ring_z_m':float(z.min()),'final_ring_z_m':float(z[-1]),
        **({} if ring is not None else {'keyring_present':False,'ring_z_note':'no keyring: minimum/final_ring_z_m are the strap lower-edge midpoint'}),
        'maximum_principal_stretch_all_steps':float(monitor[4]),
        'maximum_contact_penetration_240hz_m':float(-max_pen),'dissipated_j':float(dissipated),
        'warning_counts':{str(i):int(w.number) for i,w in enumerate(d.warning) if w.number},
        'material_scope':'Plausible uncalibrated silicone; no product-fit or certified benchmark-GT claim.',
        'collision_scope':'Rigid convex hulls of the original key meshes; holes and blade notches are conservative contact proxies.'}
    if schedule:
        report['continuation']={'edit_frame':k,'start_time_s':float(cache['times'][k-1]),'frames_from_source':[1,k-1],'frames_solved':[k,96],
            'source_cache':str(source_cache/'simulation.npz'),'source_cache_sha256':hashlib.sha256((source_cache/'simulation.npz').read_bytes()).hexdigest(),
            'restored_state':'MuJoCo qpos and qvel of the source sample (float64); mj_forward rebuilds positions, contacts and the strap membrane forces',
            'not_restored':'qacc_warmstart (Newton solver initial guess, tolerance 1e-10) and the 240 Hz dissipation accumulator, which restarts at the edit frame',
            'parameters_after_edit':schedule[0]['params'],'handoff_max_abs_error':handoff}
    dump(out/'physics_audit.json',report);print(json.dumps(report),flush=True)
    return report

def main():
    p=argparse.ArgumentParser();p.add_argument('--case',choices=[*edit_vocab.CASE_DSL,*edit_vocab.TIMED_DSL],default='source')
    p.add_argument('--out',type=Path,required=True);p.add_argument('--duration',type=float)
    p.add_argument('--dt-factor',type=float,default=1.0);p.add_argument('--rows',type=int)
    p.add_argument('--source-cache',type=Path,help='timed cases: folder of the source solve to continue from (default: accepted native_solves source)')
    a=p.parse_args()
    source=a.source_cache or asset('scenes/elastic_key_strap')/'native_solves'/'cases'/'source'
    simulate(a.case,a.out,a.duration,a.dt_factor,a.rows,source)

if __name__=='__main__':main()
