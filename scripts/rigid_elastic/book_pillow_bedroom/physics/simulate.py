"""Exact 24 Hz native samples of a four-second physical solve; no retiming."""
from pathlib import Path
import argparse, hashlib, json, os, socket, sys, time
import numpy as np
from collections import deque
from physics import ROOT, DATA, CASES, Simulation, config_for, write_cache, overrides_for
sys.path.insert(0, str(ROOT / 'scripts'))
from pcve_media_contract import CONTRACT, require_times

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--case', choices=CASES, required=True)
    p.add_argument('--tag', default='quilt');p.add_argument('--out',type=Path)
    p.add_argument('--stop', type=float, default=4.)
    p.add_argument('--rate', type=int, default=1200)
    p.add_argument('--material', choices=['cotton'], default='cotton')
    p.add_argument('--fail-fast-deletion', action='store_true')
    a = p.parse_args()
    if a.fail_fast_deletion and a.case != 'remove_pillow':
        p.error('--fail-fast-deletion is only for the deletion interaction')
    host = socket.gethostname().split('.')[0]
    assert sys.platform == 'linux'
    assert a.rate % CONTRACT['fps'] == 0 and a.tag.replace('_','').isalnum()
    out = a.out or DATA / 'outputs' / (a.tag + '_' + a.case)
    out.mkdir(parents=True, exist_ok=False)
    c = config_for(a.case, a.rate, a.material)
    start = time.monotonic()
    sim = Simulation(c, out); sim.park_books()
    stable = 0; check_stride = a.rate // 30
    geometry_history=deque(maxlen=9) if a.case=='add_bedside_book' else None
    geometry_quiet=True;quilt_window=0.;pillow_window=0.
    for step in range(1, a.rate*8+1):
        sim.advance()
        if step % check_stride: continue
        quilt_x,quilt_v=sim.duvet_state()
        ds = float(np.sqrt(np.mean(np.sum(quilt_v**2, axis=1))))
        pillow_x,pillow_v=sim.pillow_state() if c['pillow_present'] else (None,None)
        ps = float(np.sqrt(np.mean(np.sum(pillow_v**2, axis=1)))) if c['pillow_present'] else 0.
        bs = sim.accent_speed()
        if geometry_history is not None:
            geometry_history.append((quilt_x,pillow_x))
            quilt_window=max(float(np.linalg.norm(x-geometry_history[0][0],axis=1).max())
                             for x,p in geometry_history)
            pillow_window=max(float(np.linalg.norm(p-geometry_history[0][1],axis=1).max())
                              for x,p in geometry_history)
            geometry_quiet=len(geometry_history)==9 and max(quilt_window,pillow_window)<.00025
        stable = stable+1 if max(ds,ps,bs)<.00008 and geometry_quiet else 0
        if step % (a.rate//5)==0:
            print('PREROLL', a.case, step/a.rate, ds,ps,bs,flush=True)
            if hasattr(sim,'accent_motion'):
                print('PREROLL_BOOK_MOTION',json.dumps(sim.accent_motion),flush=True)
            if geometry_history is not None:
                print('PREROLL_SURFACE_WINDOW',quilt_window,pillow_window,flush=True)
        minimum_preroll=3. if geometry_history is not None else .5
        if stable >= 8 and step >= round(a.rate*minimum_preroll): break
    if stable < 8: raise RuntimeError('Resting bedding/added book did not equilibrate')
    preroll = {'steps':step, 'duration_s':step/a.rate, 'duvet_rms_m_s':ds, 'pillow_rms_m_s':ps, 'added_book_state_speed':bs}
    if hasattr(sim,'accent_motion'):
        preroll['added_book_surface_motion']=sim.accent_motion
    if geometry_history is not None:
        preroll.update(quilt_window_max_displacement_m=quilt_window,
                       pillow_window_max_displacement_m=pillow_window)
    sim.release_books()
    sim.record_visible_dynamics=True;sim.visible_origin_step=sim.steps
    states, times = [], []
    stride = a.rate // CONTRACT['fps']; count = round(a.stop*CONTRACT['fps'])
    last = (count-1)*stride
    for n in range(last+1):
        if n % stride == 0:
            s = sim.state(); sim.telemetry(s); states.append(s); times.append(n/a.rate)
            if len(states)%6==1:
                write_cache(out / 'partial_checkpoint.npz', states, times, sim)
                (out/'progress.json').write_text(json.dumps({'case':a.case,'samples':len(times),'time_s':times[-1],'complete':False,'elapsed_s':time.monotonic()-start}))
                print('SAMPLE',a.case,len(times),times[-1],flush=True)
        if n < last:
            sim.advance()
            if a.fail_fast_deletion:
                minimum_j = min(sim.orientation_records[-1][1:])
                upward_speed = sim.micro_book_records[-1][3]
                if minimum_j <= .05 or upward_speed >= .3:
                    rejection = {
                        'time_s': (n + 1) / a.rate,
                        'minimum_jacobian': minimum_j,
                        'upward_book_speed_m_s': upward_speed,
                    }
                    (out / 'candidate_rejection.json').write_text(json.dumps(rejection, indent=2))
                    raise RuntimeError(f'Deletion motion gate failed: {rejection}')
    arrays = write_cache(out / 'simulation.npz', states, times, sim)
    if a.stop == 4.: require_times(times)
    initial_book=arrays['phone_transforms'][0]
    initial_bottom=float((np.asarray(sim.phone.vertices)@initial_book[:3,:3].T+initial_book[:3,3])[:,2].min())
    m = {'case_id':a.case,'worker':host,
        'gpu_uuid':os.environ['CUDA_VISIBLE_DEVICES'],'frames':len(times),'fps':24,'sample_times_s':times,
        'duration_s':count/24,'physical_sample_span_s':[times[0],times[-1]],'simulation_rate_hz':a.rate,'physical_time_scale':1.,
        'mass_kg':c['phone_mass_kg'],'pillow_young_modulus_pa':c['pillow_young_modulus_pa'],
        'initial_book_bottom_world_z_m':initial_bottom,
        'preroll_converged':True,'preroll':preroll,'manual_motion':False,
        'physical_overrides':overrides_for(a.case, a.material),
        'final_speed_m_s':float(np.linalg.norm(arrays['phone_linear_velocity'][-1])),
        'minimum_jacobians_all_substeps':np.array(sim.orientation_records)[:,1:].min(0).tolist(),
        'maximum_upward_book_velocity_native_substeps_m_s':max(0.,max(row[3] for row in sim.micro_book_records)),
        'minimum_book_center_z_native_substeps_m':min(row[4] for row in sim.micro_book_records),
        'solver_elapsed_s':time.monotonic()-start,'native_cache_sha256':hashlib.sha256((out/'simulation.npz').read_bytes()).hexdigest(),
        'effective_material_not_experimental_calibration':True}
    (out/'metrics.json').write_text(json.dumps(m,indent=2))
    np.savez_compressed(out/'orientation_steps.npz',records=np.array(sim.orientation_records))
    np.savez_compressed(out/'visible_book_substeps.npz',columns=np.array(['time_s','vx_m_s','vy_m_s','vz_m_s','center_z_m']),records=np.array(sim.micro_book_records))
    print('SIM_COMPLETE', json.dumps(m),flush=True)

if __name__ == '__main__': main()
