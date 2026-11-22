"""Unactuated four-wheel car contacting a native passive spring slider."""
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
import json
import math
import time
from pathlib import Path
import numpy as np
import mujoco as mj
from scene_config import CASES, baseline, config_for, car_properties, differences, digest, model_xml, profile, save_json, resistance_parameters

def main():
    pa=argparse.ArgumentParser(description=__doc__)
    pa.add_argument('--output-dir',type=Path,required=True);pa.add_argument('--case',choices=CASES,default='source')
    pa.add_argument('--base-config',type=Path);pa.add_argument('--reuse-cache',action='store_true')
    a=pa.parse_args();out=a.output_dir.resolve();base=json.loads(a.base_config.read_text()) if a.base_config else baseline();cfg=config_for(a.case,base)
    if out.exists() and any(out.iterdir()):
        if a.reuse_cache and (out/'simulation_report.json').is_file() and json.loads((out/'config.json').read_text())==cfg:
            print('REUSE',out);return
        pa.error('Refusing to overwrite existing cache: '+str(out))
    out.mkdir(parents=True,exist_ok=True);save_json(out/'config.json',cfg)
    save_json(out/'edit_manifest.json',{'case':a.case,'before':base,'after':cfg,'differences':differences(base,cfg),
        'mass_and_inertia_before':car_properties(base),'mass_and_inertia_after':car_properties(cfg),
        'appearance_sha256':digest(cfg['appearance']),'render_sha256':digest(cfg['render']),
        'simulation_quality_sha256':digest(cfg['simulation_quality']),'effective_from':'t=0, initially at rest'})
    start=time.monotonic();xml=model_xml(cfg);(out/'model.xml').write_text(xml)
    m=mj.MjModel.from_xml_string(xml);d=mj.MjData(m);mj.mj_forward(m,d)
    assert mj.__version__=='3.17.0';assert m.nu==0 and m.nmocap==0 and m.neq==0
    p=cfg['physics'];c=p['car'];sp=p['spring'];b=p['baffle'];resistance=resistance_parameters(cfg);dt=m.opt.timestep;fps=cfg['render']['fps'];steps=round(1/fps/dt)
    assert abs(steps*dt-1/fps)<1e-12
    # car=False (DELETE car): the model has no chassis or wheels; car quantities are recorded as NaN/None.
    car=bool(c.get('present',True))
    guide=m.joint('guide');gq=int(guide.qposadr[0]);gv=int(guide.dofadr[0]);free=int(m.joint('car_free').dofadr[0]) if car else None
    axes=[int(m.joint(f'axle_{i}').dofadr[0]) for i in range(4)] if car else []
    body_ids=[m.body(name).id for name in [*(['chassis',*[f'wheel_{i}' for i in range(4)]] if car else []),'baffle']]
    tire_ids={m.geom(f'tire_{i}').id:i for i in range(4)} if car else {};baffle_id=m.geom('baffle_face').id
    car_ids={m.geom(n).id for n in ['chassis_base','cabin','front_bumper','rear_bumper',*[f'tire_{i}' for i in range(4)]]} if car else set()
    road_ids={i for i in range(m.ngeom) if m.geom(i).name.startswith('road_')}
    samples={key:[] for key in ['time','body_pose','qpos','qvel','spring_compression','wheel_angle']};history=[]
    first=None;reverse=None;detach=None;separation_start=None;return_ramp=None;peak=None;last_vx=0.;maxq=0.;maxqtime=0.;contact_seen=False;had_return=False
    dissip={'spring_damping_J':0.,'guide_viscous_J':0.,'guide_dry_friction_J':0.,'axle_viscous_J':0.,'axle_dry_friction_J':0.}
    maxpen=0.;maxtiregap=0.;maxflight=0.;flight=0.;maxay=0.;maxroll=0.;maxacc=0.;initial_energy=None;lastenergy=None;maxrise=0.
    hist_every=round(1/cfg['simulation_quality']['history_hz']/dt);g=abs(p['gravity_m_s2'][2]);flat_axle=p['road']['flat_top_z_m']+c['wheel_radius_m']
    final_t=cfg['render']['duration_s'];total=round(final_t/dt);initial_qvel=d.qvel.copy();initial_qpos=d.qpos.copy();last_record=None
    for tick in range(total+1):
        t=tick*dt
        if tick: mj.mj_forward(m,d)
        vx=float(d.qvel[free]) if car else float('nan');q=float(d.qpos[gq]);vb=float(d.qvel[gv]);carcontact=False;load=[0.]*4
        for con in d.contact:
            pair={int(con.geom1),int(con.geom2)};maxpen=max(maxpen,-float(con.dist))
            if baffle_id in pair and pair & car_ids: carcontact=True
            if pair & road_ids:
                for geom,i in tire_ids.items():
                    if geom in pair:load[i]=1.
        if not first and carcontact:
            first={'t_s':t,'car_vx_m_s':vx,'speed_m_s':float(np.linalg.norm(d.qvel[free:free+3]))};contact_seen=True
        if q>maxq:maxq=q;maxqtime=t
        if contact_seen and reverse is None and vx<-.002:reverse={'t_s':t,'car_vx_m_s':vx,'compression_m':q}
        if car:
            bumper=m.geom('front_bumper').id
            front=float(d.geom_xpos[bumper,0]+np.abs(d.geom_xmat[bumper].reshape(3,3)[0])@m.geom_size[bumper])
            separation=b['rest_x_m']+q-b['thickness_m']/2-front
        else:separation=float('nan')
        if reverse and detach is None and not carcontact and vx<-.02 and separation>.0001:
            if separation_start is None:separation_start={'t_s':t,'car_vx_m_s':vx,'baffle_vx_m_s':vb,'compression_m':q,'gap_m':separation}
            if t-separation_start['t_s']>=.005:detach=separation_start
        else:separation_start=None
        if car:x=float(d.xpos[body_ids[0],0]);z=float(d.xpos[body_ids[0],2]);height=z-flat_axle
        else:x=z=height=float('nan')
        if reverse and return_ramp is None and x<=0 and vx<-.02:
            return_ramp={'t_s':t,'car_vx_m_s':vx,'axle_z_m':z};had_return=True
        if had_return and peak is None and last_vx<0<=vx:
            peak={'t_s':t,'car_x_m':x,'axle_height_above_flat_m':height,'car_axle_z_m':z,'car_vx_m_s':vx}
        if tick%hist_every==0 or tick==total:
            # Native kinetic energy contains all body translation, rotation and wheel spin.
            mj.mj_energyVel(m,d)
            grav=sum(float(m.body_mass[bid])*g*(float(d.xipos[bid,2])-(flat_axle+(c['chassis_com_z_m'] if j==0 else 0))) for j,bid in enumerate(body_ids[:5] if car else []))
            spring=.5*sp['stiffness_N_m']*q*q;kin=float(d.energy[1]);energy=grav+spring+kin
            if initial_energy is None:initial_energy=energy
            if lastenergy is not None:maxrise=max(maxrise,energy-lastenergy)
            lastenergy=energy
            history.append([t,x,z,vx,q,vb,grav,kin,spring,energy,*dissip.values(),int(carcontact),*load])
        if tick%steps==0 and tick//steps<cfg['render']['frames']:
            samples['time'].append(t);samples['body_pose'].append(np.c_[d.xpos[body_ids],d.xquat[body_ids]].copy())
            samples['qpos'].append(d.qpos.copy());samples['qvel'].append(d.qvel.copy());samples['spring_compression'].append(q)
            samples['wheel_angle'].append(d.qpos[[int(m.joint(f'axle_{i}').qposadr[0]) for i in range(4)] if car else []].copy())
        # Track geometric wheel-to-surface distance (tangent support envelope).
        for bid in body_ids[1:5]:
            wx,wy,wz=d.xpos[bid];rz,ang=profile(cfg,float(wx))
            gap=(wz-rz)*math.cos(ang)-c['wheel_radius_m'];maxtiregap=max(maxtiregap,float(gap))
        if car and sum(load)==0:flight+=dt;maxflight=max(maxflight,flight)
        else:flight=0.
        if car:maxay=max(maxay,abs(float(d.xpos[body_ids[0],1])));maxacc=max(maxacc,float(np.linalg.norm(d.qacc[free:free+3])))
        last_vx=vx
        if tick==total:break
        dissip['spring_damping_J']+=sp['damping_Ns_m']*vb*vb*dt
        dissip['guide_viscous_J']+=b['guide_damping_Ns_m']*vb*vb*dt
        dissip['guide_dry_friction_J']+=b['guide_frictionloss_N']*abs(vb)*dt
        omega=d.qvel[axes];dissip['axle_viscous_J']+=resistance['axle_damping_Nms']*float(omega@omega)*dt
        dissip['axle_dry_friction_J']+=resistance['axle_frictionloss_Nm']*float(abs(omega).sum())*dt
        mj.mj_step(m,d)
    history=np.asarray(history);np.savez_compressed(out/'simulation.npz',**{k:np.asarray(v) for k,v in samples.items()},initial_qpos=initial_qpos,initial_qvel=initial_qvel,final_qpos=d.qpos,final_qvel=d.qvel)
    columns=['t_s','car_x_m','car_axle_z_m','car_vx_m_s','compression_m','baffle_vx_m_s','car_gravity_J','kinetic_J','spring_J','mechanical_J',*dissip.keys(),'car_baffle_contact','wheel_0_support','wheel_1_support','wheel_2_support','wheel_3_support']
    np.savetxt(out/'history.csv',history,delimiter=',',header=','.join(columns),comments='')
    final_energy=float(history[-1,9]);loss=initial_energy-final_energy
    checks={'zero_initial_velocity':bool(np.all(initial_qvel==0)), 'zero_initial_spring_compression':float(initial_qpos[gq])==0.,
        'no_actuators_mocap_or_equalities':m.nu==m.nmocap==m.neq==0,
        'finite_history':bool(np.isfinite(history if car else np.delete(history,[1,2,3],axis=1)).all()),'first_contact_observed':first is not None if car else first is None,
        'penetration_under_0_5mm':maxpen<.0005,'compression_under_stop_plus_0_5mm':maxq<sp['effective_stroke_m']+.0005,
        'no_total_energy_gain':float(history[:,9].max())<=initial_energy+.001,
        'no_all_wheel_flight_over_20ms':maxflight<.020 if car else True,'lateral_drift_under_1mm':maxay<.001,
        'source_complete_event':bool(peak and detach) if a.case=='source' else True,
        'deleted_spring_has_no_significant_return':return_ramp is None if a.case=='delete_spring' else True}
    report={'status':'accepted' if all(checks.values()) else 'failed','case':a.case,'solver':mj.__version__,
        'first_baffle_contact':first,'maximum_compression':{'m':maxq,'t_s':maxqtime,'spring_energy_J':.5*sp['stiffness_N_m']*maxq**2},
        'car_reversal':reverse,'car_detachment':detach,'return_to_ramp':return_ramp,'first_return_peak':peak,
        'final_state':{'t_s':final_t,'car_x_m':float(d.xpos[body_ids[0],0]) if car else None,'car_z_m':float(d.xpos[body_ids[0],2]) if car else None,'car_vx_m_s':float(d.qvel[free]) if car else None,'compression_m':float(d.qpos[gq])},
        'energy':{'initial_mechanical_J':initial_energy,'final_mechanical_J':final_energy,'total_loss_J':loss,
                  **dissip,'contact_rolling_and_numerical_residual_J':loss-sum(dissip.values()),'largest_history_energy_increase_J':maxrise,
                  'maximum_mechanical_J':float(history[:,9].max())},
        'diagnostics':{'maximum_contact_penetration_m':maxpen,'maximum_wheel_surface_gap_m':maxtiregap,'longest_all_wheel_flight_s':maxflight,
                       'maximum_lateral_drift_m':maxay,'maximum_car_linear_acceleration_m_s2':maxacc,'warnings':d.warning.number.tolist()},
        'checks':checks,'simulation_elapsed_s':time.monotonic()-start,'history_columns':columns,
        'model_scope':'Free six-DOF chassis, four independent hinge wheels, unilateral rigid contacts; exact slider guide, native linear spring/damper. Spring helix is a geometric reconstruction of solved slider displacement; no continuum wire FEM.',
        'sampling':'frames t=0..95/24; final metrics t=4; event detection every integration step',
        'config_sha256':digest(cfg),'derived_vehicle_resistance':resistance}
    save_json(out/'simulation_report.json',report)
    print(json.dumps(report,indent=2))
    if report['status']!='accepted':raise SystemExit(2)

if __name__=='__main__':main()
