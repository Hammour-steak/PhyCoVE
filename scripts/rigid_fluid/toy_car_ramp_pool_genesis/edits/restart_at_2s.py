"""Continue from the recorded source state; only mass changes at t=2 seconds.

The source prefix is reused, not regenerated. Position and velocity are restored
through the solver's public state setters. A matched constant-mass restart uses
the same restoration, including stored float16 liquid velocity precision.
"""
import copy,json,os,sys,threading,time
from pathlib import Path
import numpy as np
H=Path(__file__).resolve().parent;sys.path.insert(0,str(H))
import simulate_timed_mass as sim

def restore_car(car,row):
    car.set_pos(row['car_pos'],zero_velocity=False)
    car.set_quat(row['car_quat_wxyz'],zero_velocity=False)
    # Determine the world-velocity map from the actual free-joint API rather
    # than assuming whether the rotational DOFs are local or world aligned.
    columns=[]
    for i in range(6):
        v=np.zeros(6,np.float32);v[i]=1;car.set_dofs_velocity(v)
        _,_,linear,angular=sim.rigid_state(car);columns.append(np.r_[linear,angular])
    jacobian=np.asarray(columns).T
    target=np.r_[row['car_vel'],row['car_ang']]
    qd=np.linalg.solve(jacobian,target);car.set_dofs_velocity(qd.astype(np.float32))
    pos,quat,vel,ang=sim.rigid_state(car)
    errors={k:float(np.max(np.abs(np.asarray(a)-b))) for k,a,b in [
        ('position',pos,row['car_pos']),('quaternion',quat,row['car_quat_wxyz']),
        ('velocity',vel,row['car_vel']),('angular_velocity',ang,row['car_ang'])]}
    assert max(errors.values())<2e-6,errors
    return {'velocity_jacobian':jacobian.tolist(),'restored_dofs_velocity':qd.tolist(),'errors':errors}

def main():
    args=sim.parse_args();sim.CAR_MASS=args.car_mass;sim.CAR_DENSITY=args.car_mass/float(np.prod(sim.CAR_SIZE))
    source=Path(os.environ['REBASE_SOURCE_RUN']);base=json.loads((source/'simulation_report.json').read_text())
    args.out.mkdir(parents=True,exist_ok=False);particles=args.out/'particles';particles.mkdir()
    gs,scene,car,water,build,center,wcenter,wsize=sim.build_scene(args,False)
    source_row=base['frames'][48]
    with np.load(source/'particles/frame_0049.npz') as data:
        water.set_particles_pos(data['water_pos']);water.set_particles_vel(data['water_vel'].astype(np.float32))
        source_water=data['water_pos'].copy();source_vel=data['water_vel'].astype(np.float32)
    restored=restore_car(car,source_row)
    wp,wv=sim.particle_state(water)
    assert np.array_equal(wp,source_water) and np.array_equal(wv,source_vel)
    restored.update({'frame':49,'time_s':2.,'source_run':str(source),
        'water_positions_exact':True,'stored_water_velocities_exact':True,
        'stored_water_velocity_dtype':'float16','solver_auxiliary_fields':'recomputed by native DFSPH solver',
        'external_pose_driving_after_restart':False,'gravity_and_native_coupling_retained':True})
    sim.save_json(args.out/'restart_acceptance.json',restored)
    rows=[]
    for f in range(1,49):
        src=source/'particles'/f'frame_{f:04d}.npz';os.link(src,particles/src.name)
        row=copy.deepcopy(base['frames'][f-1]);row.update(car_mass_kg=.42,mass_event_applied=False);rows.append(row)
    event=sim.apply_mass_event(car,args,384) if args.mass_change_time is not None else None
    start=time.monotonic();writer=None
    for f in range(49,97):
        tick=time.monotonic()
        if f>49:
            for _ in range(args.steps_per_frame):sim.step_with_boundary(scene,water,args)
        pos,vel=sim.particle_state(water);cpos,q,cvel,cang=sim.rigid_state(car)
        mass=float(car.get_mass().item())
        assert np.isfinite(pos).all() and np.isfinite(vel).all() and np.isfinite(cpos).all()
        if writer is not None:writer.join()
        writer=threading.Thread(target=np.savez_compressed,args=(particles/f'frame_{f:04d}.npz',),kwargs={
            'water_pos':pos,'water_vel':vel.astype(np.float16),'car_pos':cpos,'car_quat_wxyz':q,
            'car_vel':cvel,'car_ang':cang,'car_present':True,'car_mass_kg':mass,'mass_event_applied':event is not None})
        writer.start();speed=np.linalg.norm(vel,axis=1)
        row={'frame':f,'time_s':(f-1)/24,'car_pos':cpos.tolist(),'car_quat_wxyz':q.tolist(),
             'car_vel':cvel.tolist(),'car_ang':cang.tolist(),'car_mass_kg':mass,'mass_event_applied':event is not None,
             'water_z_max':float(pos[:,2].max()),'water_speed_max':float(speed.max()),
             'water_speed_p99':float(np.percentile(speed,99)),'compute_seconds':time.monotonic()-tick}
        row.update(sim.boundary_metrics(pos,args));rows.append(row)
        if f%8==0:print('RESTART_FRAME',f,cpos.tolist(),mass,flush=True)
    writer.join()
    report={'status':'complete','solver':'Genesis 1.4.3 rigid + DFSPH state continuation',
        'coupling':'Native two-way rigid/SPH pressure and momentum coupling after restart',
        'physics':{'car_mass_kg':.42,'car_size_m':sim.CAR_SIZE.tolist(),'car_present':True,
            'water_density_kg_m3':args.water_density,'water_kinematic_viscosity_m2_s':args.water_viscosity,'gravity_m_s2':9.81,
            'mass_event':sim.actual_configuration(args)['physics']['mass_event']},
        'numerics':{'fps':24,'frames':96,'dx_m':args.dx,'steps_per_frame':args.steps_per_frame,'substeps_per_step':args.substeps},
        'build_seconds':build,'simulation_seconds':time.monotonic()-start,'water_particles':len(pos),
        'water_initial_center_m':list(wcenter),'water_initial_size_m':list(wsize),'initial_car_center':base['initial_car_center'],
        'actual_configuration':sim.actual_configuration(args),'frames':rows,'mass_event':event,'restart':restored}
    sim.save_json(args.out/'simulation_report.json',report);print('RESTART_DONE',flush=True)
if __name__=='__main__':main()
