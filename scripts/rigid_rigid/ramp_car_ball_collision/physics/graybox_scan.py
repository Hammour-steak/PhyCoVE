"""Validate source before independent single-parameter mass and restitution scans."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
from pathlib import Path
from scene_config import configured_scenario,save_json
from simulate_ramp_car_ball_collision import simulate
from validate_ramp_car_ball_collision import validate

def compact(r):
    o=r['outcome'];f=o['first_collision'];samples=r['trajectory_samples']
    window=[s for s in samples if f and f['time_sec']<s['time_sec']<f['time_sec']+.12]
    return {'ball_mass_kg':r['configuration']['physics']['ball']['mass_kg'],'ball_restitution':r['configuration']['physics']['ball']['restitution'],
        'first_collision_sec':f['time_sec'] if f else None,'ramp_exit_sec':o['ramp_exit']['time_sec'],
        'car_preimpact_vx_m_s':f['preimpact']['car_body']['linear_velocity'][0] if f else None,
        'car_immediate_postimpact_vx_m_s':f['at_contact']['car_body']['linear_velocity'][0] if f else None,
        'car_postimpact_30ms_vx_m_s':f['postimpact_30ms']['objects']['car_body']['linear_velocity'][0] if f else None,
        'minimum_early_postimpact_car_vx_m_s':min([s['objects']['car_body']['linear_velocity'][0] for s in window] or [0.]),
        'ball_forward_displacement_m':o['ball_forward_displacement_m'],'car_final_x_m':o['car_final_position_m'][0],
        'secondary_contact_count':o['secondary_contact_count'],'maximum_penetration_m':r['diagnostics']['maximum_penetration_m'],
        'simulation_sec':r['simulation_wall_sec']}

def main():
    p=argparse.ArgumentParser();p.add_argument('--out-root',type=Path,required=True);p.add_argument('--configuration-json',type=Path);a=p.parse_args();out=a.out_root
    def scenario(override=None):return configured_scenario(configuration_path=a.configuration_json,override=override)
    src=simulate(scenario());report=validate(src);save_json(out/'source/physics_transforms.json',src);save_json(out/'source/validation.json',report)
    assert report['accepted'],report;rows=[compact(src)]
    for mass in [.06,.12,.25,.4,.5,.6,.8,1.2]:
        r=simulate(scenario(override={'physics':{'ball':{'mass_kg':mass}}}));save_json(out/('mass_%g'%mass)/'physics_transforms.json',r);rows.append(compact(r));print(json.dumps(rows[-1]),flush=True)
    save_json(out/'mass_scan.json',{'rows':rows,'only_changed':'physics.ball.mass_kg; inertia derived consistently as (2/3)*mass*radius^2'})
    for e in [.4,.1,0.]:
        r=simulate(scenario(override={'physics':{'ball':{'restitution':e}}}));save_json(out/('restitution_%g'%e)/'physics_transforms.json',r);rows.append(compact(r));print(json.dumps(rows[-1]),flush=True)
    save_json(out/'scan_summary.json',{'rows':rows,'source_gate':report,'contact_rule':'Bullet restitution product; edit affects all ball contacts, including ground'})
    # Numerical check changes only timestep; it is not one of the physical edits.
    fine=simulate(scenario(override={'simulation_quality':{'substeps_per_frame':512}}));save_json(out/'timestep_512/physics_transforms.json',fine)
    save_json(out/'timestep_convergence.json',{'before':src['configuration'],'after':fine['configuration'],
        'coarse':compact(src),'fine':compact(fine),'contact_time_difference_sec':fine['outcome']['first_collision']['time_sec']-src['outcome']['first_collision']['time_sec'],
        'ball_final_x_difference_m':fine['outcome']['ball_forward_displacement_m']-src['outcome']['ball_forward_displacement_m'],
        'car_final_x_difference_m':fine['outcome']['car_final_position_m'][0]-src['outcome']['car_final_position_m'][0]})
if __name__=='__main__':main()
