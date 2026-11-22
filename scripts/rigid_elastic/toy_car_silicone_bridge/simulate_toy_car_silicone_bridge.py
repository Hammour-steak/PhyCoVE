"""Simulate an unactuated rigid toy car and a clamped silicone bridge."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == '__main__':
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    if _PcvePath(__file__).with_name('entrypoints.json').is_file():
        _pcve_sys.path.insert(0,str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__,'simulate')
# PCVE_UNIFIED_ENTRY_END
import argparse
import platform
import time
from pathlib import Path
import numpy as np
import mujoco as mj
from bridge_physics import CASES,STAGED_CASES,baseline,config_for,differences,digest,save_json,model_xml,car_properties

def surface_height(x,y,v,faces,bridge,road):
    if abs(y)>road['width_m']/2: return 0.
    if abs(x)>=bridge['free_span_m']/2:
        if road['left_extent_m']<=x<=road['right_extent_m']: return road['height_m']
        return 0.
    if not len(v): return 0.
    tri=v[faces];ax=tri[:,0,0];ay=tri[:,0,1]
    u=tri[:,1,:2]-tri[:,0,:2];w=tri[:,2,:2]-tri[:,0,:2]
    det=u[:,0]*w[:,1]-u[:,1]*w[:,0]
    good=np.abs(det)>1e-12
    uu=np.zeros(len(det));ww=uu.copy()
    uu[good]=((x-ax[good])*w[good,1]-(y-ay[good])*w[good,0])/det[good]
    ww[good]=(u[good,0]*(y-ay[good])-u[good,1]*(x-ax[good]))/det[good]
    mask=good&(uu>=-1e-7)&(ww>=-1e-7)&(uu+ww<=1+1e-7)
    if not np.any(mask): return 0.
    z=tri[:,0,2]+uu*(tri[:,1,2]-tri[:,0,2])+ww*(tri[:,2,2]-tri[:,0,2])
    return float(np.max(z[mask])+bridge['thickness_m']/2)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--output-dir',type=Path,required=True)
    p.add_argument('--case',choices=(*CASES,*STAGED_CASES),default='source')
    p.add_argument('--base-config',type=Path)
    p.add_argument('--timestep',type=float,help='Diagnostic quality override; record in config')
    p.add_argument('--grid',nargs=2,type=int,help='Diagnostic quality override')
    p.add_argument('--no-car',action='store_true',help='Unloaded bridge capability probe')
    p.add_argument('--reuse-cache',action='store_true')
    a=p.parse_args();a.output_dir=a.output_dir.resolve();out=a.output_dir
    import json
    base=json.loads(a.base_config.read_text()) if a.base_config else baseline()
    if a.timestep: base['simulation_quality']['timestep_s']=a.timestep
    if a.grid: base['simulation_quality']['grid']=a.grid
    cfg=config_for(a.case,base)
    # DELETE car (car present false): the model has no car, as with the unloaded probe.
    car_absent=not cfg['physics']['car'].get('present',True)
    if car_absent:a.no_car=True
    if out.exists() and any(out.iterdir()):
        if a.reuse_cache and (out/'simulation_report.json').exists() and (out/'simulation.npz').exists() and json.loads((out/'config.json').read_text())==cfg and json.loads((out/'simulation_report.json').read_text())['status']=='accepted':
            print('Reusing verified configuration:',out);return
        p.error('Refusing to overwrite existing simulation: '+str(out))
    out.mkdir(parents=True,exist_ok=True);save_json(out/'config.json',cfg)
    save_json(out/'edit_manifest.json',{'case':a.case,'before':base,'after':cfg,
        'differences':differences(base,cfg),'car_properties_before':car_properties(base),
        'car_properties_after':car_properties(cfg),'effective_from':'before gravity preroll',
        'unchanged_appearance_signature':digest(cfg['appearance']),
        'unchanged_render_signature':digest(cfg['render']),
        'unchanged_quality_signature':digest(cfg['simulation_quality'])})
    start=time.monotonic();xml=model_xml(cfg,car=not a.no_car);(out/'model.xml').write_text(xml)
    m=mj.MjModel.from_xml_string(xml);d=mj.MjData(m);mj.mj_forward(m,d)
    assert mj.__version__=='3.17.0',mj.__version__
    assert m.nu==0 and m.nmocap==0
    dt=m.opt.timestep;fps=cfg['render']['fps'];steps=round(1/fps/dt)
    if abs(steps*dt-1/fps)>1e-12: raise ValueError('Timestep must exactly divide a video frame')
    b=cfg['physics']['bridge'];c=cfg['physics']['car'];road=cfg['physics']['road']
    rest=d.flexvert_xpos.copy();faces=m.flex_elem.reshape(-1,3).copy() if m.nflex else np.empty((0,3),int)
    fixed=m.flex_vertbodyid==0;pre=[];settle_tail=[]
    for i in range(round(cfg['simulation_quality']['preroll_s']/dt)):
        mj.mj_step(m,d)
        if i%round(.05/dt)==0:
            pre.append({'t_s':float(d.time),'min_bridge_z_m':float(d.flexvert_xpos[:,2].min()) if len(rest) else None})
            if d.time>=cfg['simulation_quality']['preroll_s']-.5: settle_tail.append(d.flexvert_xpos.copy())
    settled=d.flexvert_xpos.copy()
    drift=float(np.ptp(np.array(settle_tail),axis=0).max()) if len(rest) and settle_tail else 0.
    save_json(out/'preroll.json',{'duration_s':cfg['simulation_quality']['preroll_s'],
        'bridge_last_half_second_max_coordinate_range_m':drift,'samples':pre})
    np.savez_compressed(out/'preroll_state.npz',qpos=d.qpos,qvel=d.qvel,vertices=settled)
    if not a.no_car:
        car=m.body('chassis').id;body_ids=[car]+[m.body(f'wheel_{i}').id for i in range(4)]
        free=int(m.jnt_dofadr[m.joint('car_free').id]);axles=[int(m.jnt_dofadr[m.joint(f'axle_{i}').id]) for i in range(4)]
        tire_ids={m.geom(f'tire_{i}').id for i in range(4)}
        car_geoms=tire_ids|{m.geom('chassis_base').id,m.geom('chassis_roof').id};floor_id=m.geom('floor').id
    else:body_ids=[];tire_ids=set();car_geoms=set();floor_id=m.geom('floor').id
    d.time=0.;pushed=False;push=None;frame_data={k:[] for k in ['time','qpos','qvel','vertices','body_pose','velocity','pitch','wheel_angle','wheel_angular_speed']}
    history=[];contact_history=[];contact_force=np.zeros(6);maxdef=0.;maxload=0.;maxpen=0.;maxpin=0.;maxstrain=0.
    first_contact=None;pass_time=None;fall_time=None;peak_time=None;min_floor=float('inf');min_support=float('inf')
    support_clearances=[];floor_clearances=[]
    sample_every=round(1/240/dt)
    basepoints=np.array([[x,y,.003] for x in np.linspace(-.0525,.0525,9) for y in np.linspace(-.026,.026,3)])
    roofpoints=np.array([[x,y,z] for x in [-.034,.018] for y in [-.024,.024] for z in [.021,.041]])
    base_top=np.array([[x,y,.021] for x in [-.0525,.0525] for y in [-.026,.026]])
    basepoints=np.vstack([basepoints,base_top,roofpoints])
    total_steps=cfg['render']['frames']*steps
    print('SIMULATION_START',a.case,'dof',m.nv,'vertices',m.nflexvert,'dt',dt,flush=True)
    for tick in range(total_steps+1):
        t=tick*dt
        if not pushed and not a.no_car and t>=c['push_time_s']-dt/2:
            before=d.qvel.copy();d.qvel[free]=c['initial_speed_m_s']
            for adr in axles:d.qvel[adr]=c['initial_speed_m_s']/c['wheel_radius_m']
            pushed=True;push={'time_s':t,'type':'one initial rigid generalized velocity impulse',
                'qvel_before':before.tolist(),'qvel_after':d.qvel.tolist(),
                'force_or_motor_afterwards':False}
        # Forward makes exported poses exactly correspond to the current qpos.
        if tick%steps==0 or tick%sample_every==0: mj.mj_forward(m,d)
        if tick%sample_every==0:
            v=d.flexvert_xpos;df=float(np.max(rest[:,2]-v[:,2])) if len(rest) else 0.
            ld=float(np.max(settled[:,2]-v[:,2])) if len(rest) else 0.
            if df>maxdef: maxdef=df;peak_time=t
            maxload=max(maxload,ld)
            if len(rest):
                maxpin=max(maxpin,float(np.abs(v[fixed]-rest[fixed]).max()))
                # Principal in-plane stretch (linear triangles, rest XY basis).
                a0=rest[faces[:,1],:2]-rest[faces[:,0],:2];b0=rest[faces[:,2],:2]-rest[faces[:,0],:2]
                inv=np.linalg.inv(np.stack([a0,b0],axis=-1))
                edges=np.stack([v[faces[:,1]]-v[faces[:,0]],v[faces[:,2]]-v[faces[:,0]]],axis=-1)
                deformation=edges@inv
                maxstrain=max(maxstrain,float(np.abs(np.linalg.svd(deformation,compute_uv=False)-1).max()))
            bridge_force=np.zeros(3);wheel_contacts=0;car_floor_contact=False
            for ci,con in enumerate(d.contact):
                if con.efc_address<0:continue
                if (con.geom[0]==floor_id and con.geom[1] in car_geoms) or (con.geom[1]==floor_id and con.geom[0] in car_geoms):
                    car_floor_contact=True
                side=next((side for side in [0,1] if con.geom[side] in tire_ids),None)
                if side is not None and con.flex[1-side]>=0:
                    mj.mj_contactForce(m,d,ci,contact_force)
                    force=con.frame.reshape(3,3).T@contact_force[:3]
                    bridge_force+=force*(1 if side==0 else -1)
                    wheel_contacts+=1;maxpen=max(maxpen,-float(con.dist))
            if wheel_contacts and first_contact is None:first_contact=t
            contact_history.append({'time_s':t,'wheel_flex_contacts':wheel_contacts,
                'solved_force_on_bridge_N':bridge_force.tolist(),
                'opposite_force_on_car_N':(-bridge_force).tolist()})
            row={'time_s':t,'deflection_from_flat_m':df,'load_deflection_from_settled_m':ld}
            if not a.no_car:
                pos=d.xpos[car];rot=d.xmat[car].reshape(3,3);samples=basepoints@rot.T+pos
                ground=float(samples[:,2].min());support=min(float(point[2]-surface_height(point[0],point[1],v,faces,b,road)) for point in samples)
                min_floor=min(min_floor,ground);min_support=min(min_support,support)
                floor_clearances.append(ground);support_clearances.append(support)
                wheel_x=d.xpos[body_ids[1:],0];pitch=float(np.arctan2(-rot[2,0],rot[0,0]))
                if pass_time is None and wheel_x.min()-c['wheel_radius_m']>b['free_span_m']/2 and pos[2]>.06:pass_time=t
                # Tire or chassis contact with the gap floor catches upright
                # landings and overturned landings without a pose threshold.
                if fall_time is None and car_floor_contact and abs(pos[0])<b['free_span_m']/2:fall_time=t
                row.update(car_position_m=pos.tolist(),speed_m_s=float(np.linalg.norm(d.qvel[free:free+3])),vx_m_s=float(d.qvel[free]),pitch_rad=pitch,
                    underbody_floor_clearance_m=ground,underbody_support_clearance_m=support)
            history.append(row)
        if tick%steps==0:
            frame_data['time'].append(t);frame_data['qpos'].append(d.qpos.copy());frame_data['qvel'].append(d.qvel.copy());frame_data['vertices'].append(d.flexvert_xpos.copy())
            if not a.no_car:
                frame_data['body_pose'].append(np.concatenate([d.xpos[body_ids],d.xquat[body_ids]],axis=1))
                frame_data['velocity'].append(d.qvel[free:free+6].copy());frame_data['pitch'].append(float(np.arctan2(-d.xmat[car][6],d.xmat[car][0])))
                frame_data['wheel_angle'].append([d.qpos[m.jnt_qposadr[m.joint(f'axle_{i}').id]] for i in range(4)])
                frame_data['wheel_angular_speed'].append(d.qvel[axles].copy())
            if tick%(steps*24)==0:print('FRAME',tick//steps,'t',t,'max_deflection_m',maxdef,flush=True)
        if tick==total_steps:break
        mj.mj_step(m,d)
        if not np.isfinite(d.qpos).all() or not np.isfinite(d.qvel).all() or abs(d.time-(t+dt))>dt/2:
            raise RuntimeError('Nonfinite state or solver reset')
    frames={k:np.array(v) for k,v in frame_data.items()}
    np.savez_compressed(out/'simulation.npz',**frames,rest_vertices=rest,settled_vertices=settled,faces=faces,fixed_mask=fixed)
    save_json(out/'metrics_240hz.json',history);save_json(out/'contact_forces_240hz.json',contact_history);save_json(out/'initial_push.json',push)
    warnings={str(i):int(w.number) for i,w in enumerate(d.warning) if w.number}
    final_pos=d.xpos[car].copy() if not a.no_car else None
    outcome=('car_absent' if car_absent else 'unloaded_probe') if a.no_car else ('passed' if pass_time is not None else 'fell' if fall_time is not None else 'stayed')
    residual=float(np.max(np.abs(d.flexvert_xpos-settled))) if len(rest) else None
    checks={'finite':True,'zero_solver_warnings':not warnings,'gravity_equilibrium':drift<.0001,
        'clamps_fixed':maxpin<1e-10,'tire_flex_penetration_below_0_5mm':maxpen<.0005,
        'in_plane_strain_below_15pct':maxstrain<.15,
        'free_car_and_four_hinges':a.no_car or (m.nu==0 and len(axles)==4),
        'contact_and_deformation':not b['present'] or a.no_car or (first_contact is not None and maxload>.001)}
    if a.case=='source':checks.update(source_passes=outcome=='passed',source_recovers=residual is not None and residual<.0005)
    report={'case':a.case,'status':'accepted' if all(checks.values()) else 'failed','checks':checks,
        'solver':{'name':'MuJoCo','version':mj.__version__,'integrator':'discrete','ipc':False,
                  'model':'finite thickness 2D StVK shell, bending + stretching; 6DOF chassis + 4 revolute rigid wheels',
                  'coupling':'native shared frictional flex/rigid contact Jacobian and effective-inertia solve; no motors/mocap'},
        'max_bridge_deflection_from_flat_m':maxdef,'max_load_deflection_from_settled_m':maxload,
        'unloaded_center_sag_m':float(np.max(rest[:,2]-settled[:,2])) if len(rest) else None,
        'peak_deflection_time_s':peak_time,'first_wheel_bridge_contact_s':first_contact,
        'fully_on_right_road_time_s':pass_time,'first_floor_fall_time_s':fall_time,
        'min_underbody_floor_clearance_m':None if a.no_car else min_floor,
        'min_underbody_support_clearance_m':None if a.no_car else min_support,
        'max_tire_flex_penetration_m':maxpen,'max_clamp_displacement_m':maxpin,
        'max_principal_membrane_strain':maxstrain,'final_bridge_displacement_from_settled_m':residual,
        'max_abs_pitch_deg':float(np.rad2deg(np.abs(frames['pitch'])).max()) if not a.no_car else None,
        'max_speed_m_s':max((r.get('speed_m_s',0) for r in history),default=0),
        'final_speed_m_s':history[-1].get('speed_m_s'),'final_car_position_m':final_pos.tolist() if final_pos is not None else None,
        'outcome':outcome,'warning_counts':warnings,'elapsed_simulation_s':time.monotonic()-start,
        'platform':platform.platform(),'cache':str(out/'simulation.npz'),
        'measurement':'metrics at 240 Hz; poses at 24 Hz including t=4 endpoint; video uses t=0..95/24. Clearance samples chassis collision-box undersides against deformed triangle surface and floor.',
        'limitations':['Finite-thickness shell assumes constant thickness and small material strain; no 3D incompressible solid or calibrated silicone viscoelasticity.','Engineering verification, not a comparison with a measured physical experiment.']}
    save_json(out/'simulation_report.json',report)
    print('SIMULATION_FINISH',json.dumps(report),flush=True)
    if not all(checks.values()):raise SystemExit(2)

if __name__=='__main__':main()
