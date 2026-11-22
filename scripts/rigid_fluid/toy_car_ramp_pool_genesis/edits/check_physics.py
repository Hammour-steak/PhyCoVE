"""Verify actual edit parameters, outcomes, source-prefix identity and restart."""
import copy,hashlib,itertools,json,math
from pathlib import Path
import numpy as np
W=Path(__file__).resolve().parent.parent;P=json.loads((W/'edit_plan.json').read_text());R=Path(P['root']);B=Path(P['baseline'])
def read(p):return json.loads(p.read_text())
def write(p,d):p.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
corners=np.array(list(itertools.product((-.08,.08),(-.0355,.0355),(-.0275,.0275))))
def bounds(row):
    w,x,y,z=row['car_quat_wxyz'];s=2/(w*w+x*x+y*y+z*z)
    m=np.array([[1-s*(y*y+z*z),s*(x*y-z*w),s*(x*z+y*w)],[s*(x*y+z*w),1-s*(x*x+z*z),s*(y*z-x*w)],[s*(x*z-y*w),s*(y*z+x*w),1-s*(x*x+y*y)]])
    p=corners@m.T+row['car_pos'];return float(p[:,2].min()),float(p[:,2].max())
def yaw(row):
    w,x,y,z=row['car_quat_wxyz'];return math.degrees(math.atan2(2*(w*z+x*y),1-2*(y*y+z*z)))
base=read(B/'simulation/run/simulation_report.json');cfgbase=read(B/'actual_configuration.json')
basephysics=copy.deepcopy(cfgbase['physics']);basephysics.update(car_present=True,mass_event=None)
with np.load(B/'simulation/run/particles/frame_0001.npz') as d:initial=d['water_pos'];initial_vel=d['water_vel'];level=float(np.percentile(initial[:,2],99.5))+.005
controls={name:read(R/'controls'/name/'simulation/run/simulation_report.json') for name in ['viscosity_control_32','restart_control']}
control=controls['viscosity_control_32'];control_travel=max(r['car_pos'][0] for r in control['frames'][23:])-control['frames'][23]['car_pos'][0]
outcomes=[]
for c in P['cases']:
    root=Path(c['root']);run=root/'simulation/run';sim=read(run/'simulation_report.json');cfg=read(run/'actual_configuration.json');phys=cfg['physics'];name=c['id']
    assert all(phys[k]==v for k,v in c['physics'].items()),name
    assert cfg['boundary']==cfgbase['boundary']
    assert len(sim['frames'])==96 and sim['water_particles']==95277
    with np.load(run/'particles/frame_0001.npz') as d:assert np.array_equal(d['water_pos'],initial) and np.array_equal(d['water_vel'],initial_vel)
    rows=[]
    for f,row in enumerate(sim['frames'],1):
        assert row['frame']==f and row['time_s']==(f-1)/24
        assert row['below_rim_outside_10mm_count']==0,(name,f,'water escape')
        with np.load(run/'particles'/f'frame_{f:04d}.npz') as d:
            assert d['water_pos'].shape==(95277,3) and np.isfinite(d['water_pos']).all() and np.isfinite(d['water_vel']).all()
            if 'car_present' in d.files:assert bool(d['car_present'])==c['physics']['car_present']
        if phys['car_present']:
            bottom,top=bounds(row);rows.append({'frame':f,'bottom_z_m':bottom,'top_z_m':top,
                'fully_submerged':top<level-.002,'floor_contact':abs(bottom-.03)<.002,
                'yaw_degrees':yaw(row),'car_pos':row['car_pos'],'speed_m_s':float(np.linalg.norm(row['car_vel']))})
    result={'id':name,'physics':phys,'runtime_materials':cfg['runtime_materials'],'all_96_states_finite':True,
            'same_initial_water_state':True,'water_particles':95277,'all_96_below_rim_escape_counts_zero':True,
            'reference_surface_level_m':level,'frames':rows}
    if name=='no_car':
        assert cfg['runtime_materials']['car_present'] is False and cfg['runtime_materials']['car_mass_kg'] is None
        result['outcome']='No physical or visual car; no car-induced splash'
    elif name in ['heavy_car_x3','low_density_div4']:
        late=rows[63:];assert all(r['fully_submerged'] and r['floor_contact'] for r in late),(name,late)
        result.update(outcome='Car remains fully submerged on the bottom',late_floor_contact_frames=33,late_submerged_frames=33)
    elif name=='high_viscosity_x20000':
        travel=max(r['car_pos'][0] for r in rows[23:])-rows[23]['car_pos'][0];ratio=travel/control_travel
        assert travel<.10 and ratio<.25,(travel,ratio)
        result.update(outcome='Car nearly stops at entry in highly viscous liquid',post_contact_travel_m=travel,
            matched_water_control_travel_m=control_travel,travel_fraction_of_matched_control=ratio,
            additional_numerical_change='32 substeps instead of 4 for explicit viscosity stability',
            matched_control=str(R/'controls/viscosity_control_32'))
    else:
        event=sim['mass_event'];assert event['time_s']==2. and event['integration_step']==384 and event['multiplier']==3
        assert event['mass_inertia_and_inverse_weights_verified'] and event['pose_and_velocity_continuous']
        assert np.array_equal(event['before']['dofs_velocity'],event['after']['dofs_velocity'])
        for f in range(1,50):
            a=sim['frames'][f-1];b=base['frames'][f-1]
            for k in ['car_pos','car_quat_wxyz','car_vel','car_ang']:assert np.allclose(a[k],b[k],atol=2e-6,rtol=0),(f,k)
            assert math.isclose(a['car_mass_kg'],.42 if f<49 else 1.26,rel_tol=1e-5)
            with np.load(run/'particles'/f'frame_{f:04d}.npz') as d,np.load(B/'simulation/run/particles'/f'frame_{f:04d}.npz') as z:
                assert np.array_equal(d['water_pos'],z['water_pos']) and np.array_equal(d['water_vel'],z['water_vel']),(f,'source water prefix')
        for f in range(1,49):assert sha(run/'particles'/f'frame_{f:04d}.npz')==sha(B/'simulation/run/particles'/f'frame_{f:04d}.npz')
        late=rows[72:];assert all(r['fully_submerged'] for r in late),late
        depression=float(np.mean([r['car_pos'][2] for r in base['frames'][72:]])-np.mean([r['car_pos'][2] for r in sim['frames'][72:]]))
        assert depression>.025,depression
        matched=controls['restart_control'];assert bounds(matched['frames'][-1])[1]>level
        restart_depression=float(np.mean([r['car_pos'][2] for r in matched['frames'][72:]])-np.mean([r['car_pos'][2] for r in sim['frames'][72:]]))
        assert restart_depression>.025,restart_depression
        result.update(outcome='Source prefix retained; car fully submerges after 2-second mass event',event_frame=49,
            source_prefix_physical_frames_verified=[1,49],event=event,
            late_fully_submerged_frames=24,late_mean_depth_increase_vs_source_m=depression,
            late_mean_depth_increase_vs_restart_control_m=restart_depression,
            restart_control=str(R/'controls/restart_control'),restart=sim['restart'])
    if rows:result.update(maximum_absolute_yaw_degrees=max(abs(r['yaw_degrees']) for r in rows),final_yaw_degrees=rows[-1]['yaw_degrees'])
    change={'before':{'physics':basephysics,'simulation_quality':cfgbase['simulation_quality']},
            'after':{'physics':phys,'simulation_quality':cfg['simulation_quality']}}
    write(root/'configuration_change.json',change);write(root/'physics_acceptance.json',result)
    outcomes.append({k:v for k,v in result.items() if k not in ['frames','event','runtime_materials']})
write(R/'physics_acceptance.json',{'status':'all_five_rebased_edits_passed','baseline':str(B),'cases':outcomes,
    'timed_prefix_matches_selected_source':True,'restored_state_limitation':P['timed_edit_restart']['limitations']})
print('ALL_FIVE_REBASED_PHYSICAL_OUTCOMES_PASSED',flush=True)
