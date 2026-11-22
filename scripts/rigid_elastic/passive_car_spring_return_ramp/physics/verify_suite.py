"""Audit actual edits, solved caches, mechanics, frame/video specifications."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import argparse
import hashlib
import json
import subprocess
from pathlib import Path
import numpy as np
from scene_config import CASES,config_for,differences,digest,save_json

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',required=True,type=Path);p.add_argument('--cases',nargs='+',choices=CASES,default=list(CASES));p.add_argument('--video',action='store_true')
    a=p.parse_args();rows=[];source=config_for('source')
    allowed={'source':[], 'soft_spring':['physics.spring.stiffness_N_m'],'stiff_spring':['physics.spring.stiffness_N_m'],
             'high_friction':['physics.car.travel_resistance_multiplier'],'heavy_car':['physics.car.mass_kg'],
             'delete_spring':['physics.spring.damping_Ns_m','physics.spring.present','physics.spring.stiffness_N_m']}
    for case in a.cases:
        folder=a.root/case;sim=folder/'simulation';cfg=json.loads((sim/'config.json').read_text());rep=json.loads((sim/'simulation_report.json').read_text())
        edit=json.loads((sim/'edit_manifest.json').read_text());cache=np.load(sim/'simulation.npz');diff=differences(source,cfg)
        checks={'actual_configuration_matches_requested':cfg==config_for(case),'only_declared_edits':[d['path'] for d in diff]==allowed[case],
                'before_after_match_actual':edit['before']==source and edit['after']==cfg and edit['differences']==diff,
                'physics_accepted':rep['status']=='accepted','all_solver_checks_pass':all(rep['checks'].values()),
                'four_independent_wheels':cache['wheel_angle'].shape==(96,4),'96_solved_frames':len(cache['time'])==96,
                'no_spring_preload_or_initial_velocity':bool(np.all(cache['initial_qvel']==0)),
                'appearance_render_quality_identical':all(cfg[k]==source[k] for k in ['appearance','render','simulation_quality']),
                'zero_solver_warnings':not any(rep['diagnostics']['warnings'])}
        coil_clearance=(cfg['physics']['spring']['rest_length_m']-rep['maximum_compression']['m']-2*cfg['physics']['spring']['wire_diameter_m'])/cfg['physics']['spring']['active_turns']-cfg['physics']['spring']['wire_diameter_m']
        checks['coil_clearance_positive']=coil_clearance>0
        row={'case':case,'checks':checks,'differences':diff,'metrics':rep,'minimum_active_coil_clearance_m':coil_clearance,
             'cache_sha256':hashlib.sha256((sim/'simulation.npz').read_bytes()).hexdigest()}
        if a.video:
            video=folder/'video.mp4';probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration','-of','json',str(video)],text=True));stream=probe['streams'][0]
            checks['video_specs']=stream['width']==1280 and stream['height']==720 and stream['r_frame_rate']=='24/1' and stream['avg_frame_rate']=='24/1' and int(stream['nb_read_frames'])==96 and abs(float(probe['format']['duration'])-4)<.001
            decode=subprocess.run(['ffmpeg','-v','error','-i',str(video),'-f','null','-'],capture_output=True,text=True)
            checks['full_video_decode']=decode.returncode==0 and not decode.stderr
            frames=sorted((folder/'render/frames').glob('*.png'));checks['complete_frame_sequence']=[f.name for f in frames]==[f'{i:04d}.png' for i in range(1,97)]
            renderinput=json.loads((folder/'render/render_input.json').read_text());checks['render_uses_actual_cache']=renderinput['cache_sha256']==row['cache_sha256'] and renderinput['config_sha256']==digest(cfg)
            if 'effective_config_sha256' in renderinput:
                effective=json.loads((folder/'render/render_config.json').read_text());adiff=json.loads((folder/'render/appearance_diff.json').read_text())
                checks['render_changes_only_appearance']=all(effective[k]==cfg[k] for k in ['physics','simulation_quality','render']) and all(d['path'].startswith('appearance.') for d in adiff['differences'])
                checks['effective_render_config_matches']=digest(effective)==renderinput['effective_config_sha256']
            row.update(video_probe=probe,video_sha256=hashlib.sha256(video.read_bytes()).hexdigest(),render_input=renderinput)
        row['status']='accepted' if all(checks.values()) else 'failed';rows.append(row)
    # Input-state invariance and the control establish causality independently
    # of a hand-picked frame or an assumed mass/height outcome.
    cross={}
    if len(rows)==len(CASES):
        reps={row['case']:row['metrics'] for row in rows};v0=reps['source']['first_baffle_contact']['car_vx_m_s']
        cross['spring_edits_same_precontact_speed']=all(abs(reps[c]['first_baffle_contact']['car_vx_m_s']-v0)<1e-12 for c in ['soft_spring','stiff_spring','delete_spring'])
        cross['high_friction_slower_first_contact']=reps['high_friction']['first_baffle_contact']['car_vx_m_s']<v0
        cross['high_friction_spring_damping_unchanged']=config_for('high_friction')['physics']['spring']==source['physics']['spring']
        cross['delete_spring_no_ramp_return']=reps['delete_spring']['return_to_ramp'] is None
        cross['source_returns_and_separates']=reps['source']['first_return_peak'] is not None and reps['source']['car_detachment'] is not None
        if a.video:
            cross['same_actual_appearance_all_cases']=len({digest(row['render_input']['appearance']) for row in rows})==1
            if 'asset_dependency_sha256' in rows[0]['render_input']:cross['same_texture_dependencies_all_cases']=len({row['render_input']['asset_dependency_sha256'] for row in rows})==1
    result={'status':'accepted' if all(row['status']=='accepted' for row in rows) and all(cross.values()) else 'failed',
            'scope':'Physics, isolated edit inputs and optional formal video technical checks; visual full-sequence review recorded separately',
            'cases':rows,'cross_case_checks':cross}
    target=a.root/('suite_verification.json' if len(rows)==len(CASES) else rows[0]['case']+'/verification.json');save_json(target,result)
    print(json.dumps({'status':result['status'],'cases':[{ 'case':r['case'],'status':r['status'],'failed':[k for k,v in r['checks'].items() if not v]} for r in rows],'cross':cross},indent=2))
    raise SystemExit(0 if result['status']=='accepted' else 2)

if __name__=='__main__':main()
