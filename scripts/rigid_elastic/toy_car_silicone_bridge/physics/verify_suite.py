"""Audit actual cases, cache separation, full video specifications and QA sheets."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path
import shutil
import numpy as np
import mujoco as mj
from PIL import Image,ImageDraw
from bridge_physics import CASES,config_for,differences,save_json,car_properties,digest,model_xml
import edit_vocab

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--root',type=Path,required=True);a=p.parse_args();root=a.root.resolve()
    expected={'source':[], 'soft_bridge':['physics.bridge.young_pa'], 'stiff_bridge':['physics.bridge.young_pa'],
              'heavy_car':['physics.car.mass_kg'],'delete_bridge':['physics.bridge.present']}
    source=json.loads((root/'source/simulation/config.json').read_text())
    reuse=root/'physics_cache_reuse.json'
    source_hash=json.loads(reuse.read_text())['cases']['source']['sha256'] if reuse.exists() else json.loads((root/'source/render/render_input.json').read_text())['cache_sha256']
    assert sha(root/'source/simulation/simulation.npz')==source_hash
    results={};metrics=[];paths=[];inodes=set();qa=root/'qa';qa.mkdir(exist_ok=True)
    for case in CASES:
        folder=root/case;sim=folder/'simulation';cfg=json.loads((sim/'config.json').read_text());report=json.loads((sim/'simulation_report.json').read_text());data=np.load(sim/'simulation.npz')
        assert cfg==config_for(case,source),case
        delta=differences(source,cfg);assert [d['path'] for d in delta]==expected[case],(case,delta)
        edit=json.loads((sim/'edit_manifest.json').read_text());assert edit['before']==source and edit['after']==cfg
        assert report['status']=='accepted',report
        assert data['body_pose'].shape==(97,5,7);assert data['time'].shape==(97,);assert np.allclose(data['time'],np.arange(97)/24)
        assert data['vertices'].shape[1]==(0 if case=='delete_bridge' else 429)
        assert (sim/'model.xml').read_text()==model_xml(cfg)
        model=mj.MjModel.from_xml_path(str(sim/'model.xml'));bodies=[model.body('chassis').id]+[model.body(f'wheel_{i}').id for i in range(4)]
        mass=model.body_mass[bodies];inertia=model.body_inertia[bodies];car=car_properties(cfg)
        assert abs(mass.sum()-cfg['physics']['car']['mass_kg'])<1e-12
        assert np.allclose(mass,[car['chassis_mass_kg']]+[car['wheel_mass_kg']]*4,rtol=1e-11)
        assert np.allclose(inertia[0],car['chassis_inertia_kg_m2'])
        # MuJoCo sorts principal inertia axes; compare eigenvalues, not axis labels.
        assert np.allclose(np.sort(inertia[1:],axis=1),np.sort(car['wheel_inertia_kg_m2'])[None,:])
        assert model.nu==0 and model.nmocap==0
        assert model.nflex==(0 if case=='delete_bridge' else 1)
        compiled={'total_car_mass_kg':float(mass.sum()),'body_masses_kg':mass.tolist(),
            'principal_inertia_kg_m2':inertia.tolist(),'actuators':model.nu,'mocap_bodies':model.nmocap,
            'dof':model.nv,'flex_vertices':model.nflexvert,'flex_elements':model.nflexelem,
            'timestep_s':model.opt.timestep,'iterations':model.opt.iterations,'tolerance':model.opt.tolerance,
            'integrator':int(model.opt.integrator),'gravity':model.opt.gravity.tolist()}
        save_json(sim/'compiled_model_audit.json',compiled)
        cache=(sim/'simulation.npz').resolve();assert cache not in paths;paths.append(cache)
        inode=(cache.stat().st_dev,cache.stat().st_ino);assert inode not in inodes;inodes.add(inode)
        video=folder/'video.mp4';verification=json.loads((folder/'video_verification.json').read_text())
        assert json.loads((folder/'render/render_input.json').read_text())['cache_sha256']==sha(cache)
        assert all(verification['checks'].values()) and verification['full_decode'];assert verification['sha256']==sha(video)
        reuse_proof=root/'delete_bridge_render_reuse.json'
        if case=='delete_bridge' and reuse_proof.exists() and json.loads(reuse_proof.read_text())['status']=='accepted':
            rp=json.loads(reuse_proof.read_text())
            assert rp['physics_cache_sha256']==sha(cache) and rp['video_sha256']==sha(video)
            assert all(item['pixels_identical'] for item in rp['actual_full_quality_pixel_comparisons'])
            assert rp['absent_bridge_branch_elided_ast_identical'] and rp['render_program_unchanged']
            assert len(rp['frames'])==96
            for record in rp['frames']:
                assert sha(folder/'render/frames'/f"{record['frame']:04d}.png")==record['sha256']
        # Inspect every stored PNG, in addition to the full-video decoder check.
        frames=sorted((folder/'render/frames').glob('*.png'));assert len(frames)==96
        hist=[]
        for f in frames:
            with Image.open(f) as im:
                assert im.size==(1280,720);im.verify()
            hist.append({'file':str(f.relative_to(root)),'sha256':sha(f)})
        save_json(folder/'frame_integrity.json',hist)
        sheet=Image.new('RGB',(1280,6*204),(25,27,30));draw=ImageDraw.Draw(sheet)
        for i,f in enumerate(frames):
            with Image.open(f) as im:thumbnail=im.resize((160,90))
            # 8 columns x 12 rows: every frame, no time ranges skipped.
            x=(i%8)*160;y=(i//8)*102;sheet.paste(thumbnail,(x,y));draw.text((x+3,y+91),f'{i+1:02d}  {i/24:.3f}s',fill='white')
        sheet.save(qa/f'{case}_all_96_frames.jpg',quality=94)
        contact=Image.new('RGB',(1920,6*172),(25,27,30));contact_draw=ImageDraw.Draw(contact)
        for i,f in enumerate(frames[:36]):
            with Image.open(f) as im:detail=im.crop((170,275,745,552)).resize((320,154))
            x=(i%6)*320;y=(i//6)*172;contact.paste(detail,(x,y))
            contact_draw.text((x+3,y+155),f'{i+1:02d}  {i/24:.3f}s',fill='white')
        contact.save(qa/f'{case}_contact_sequence.jpg',quality=95)
        keydir=folder/'keyframes';keydir.mkdir(exist_ok=True)
        peakframe=max(1,min(96,round((report['peak_deflection_time_s'] or .5)*24)+1))
        important=set([1,10,peakframe,18,24,36,60,96])
        event_frames={}
        for key in ['first_wheel_bridge_contact_s','fully_on_right_road_time_s','first_floor_fall_time_s']:
            if report[key] is not None:
                nearest=max(1,min(96,round(report[key]*24)+1))
                after=max(1,min(96,math.ceil(report[key]*24-1e-10)+1))
                important.update([nearest,after])
                event_frames[key]={'time_s':report[key],'nearest_frame':nearest,'first_frame_at_or_after':after}
        important=sorted(important)
        for f in important:shutil.copy2(folder/'render/frames'/f'{f:04d}.png',keydir/f'{f:04d}.png')
        save_json(keydir/'manifest.json',{'frames':important,'events':event_frames,'peak_deflection_nearest_frame':peakframe})
        prompt={'case':case,'case_id':edit_vocab.public_case_id(case),'edit_dsl':edit_vocab.edit_dsl(case),'prompts':edit_vocab.prompts(case),
            'actual_delta':delta,'observed_outcome':report['outcome'],'actual_metrics':report}
        save_json(folder/'prompts.json',prompt)
        metrics.append({'case':case,'E_Pa':cfg['physics']['bridge']['young_pa'] if case!='delete_bridge' else None,
            'car_mass_kg':cfg['physics']['car']['mass_kg'],'max_deflection_mm':1000*report['max_bridge_deflection_from_flat_m'] if case!='delete_bridge' else None,
            'max_load_deflection_mm':1000*report['max_load_deflection_from_settled_m'] if case!='delete_bridge' else None,
            'max_speed_m_s':report['max_speed_m_s'],'pass_time_s':report['fully_on_right_road_time_s'],
            'min_underbody_floor_mm':1000*report['min_underbody_floor_clearance_m'],
            'min_underbody_support_mm':1000*report['min_underbody_support_clearance_m'],
            'final_speed_m_s':report['final_speed_m_s'],'outcome':report['outcome']})
        results[case]={'physics':report,'video':verification,'parameter_differences':delta,
            'cache':str(cache),'cache_sha256':sha(cache),'cache_device_inode':list(inode),'video_sha256':sha(video),
            'appearance_sha256':digest(cfg['appearance']),'render_sha256':digest(cfg['render']),
            'quality_sha256':digest(cfg['simulation_quality'])}
    for field in ['appearance_sha256','render_sha256','quality_sha256']:
        assert len({r[field] for r in results.values()})==1,field
    assert sha(root/'source/simulation/simulation.npz')==source_hash,'Source cache was modified'
    with (root/'metrics.csv').open('w') as f:
        writer=csv.DictWriter(f,fieldnames=list(metrics[0]));writer.writeheader();writer.writerows(metrics)
    # Same event time, plus end state, in a compact comparison sheet.
    comparison=Image.new('RGB',(1280,5*384),(24,27,30));draw=ImageDraw.Draw(comparison)
    for row,case in enumerate(CASES):
        draw.text((8,row*384+5),case+' | t=0.708s / t=3.958s',fill='white')
        for col,frame in enumerate([18,96]):
            with Image.open(root/case/'render/frames'/f'{frame:04d}.png') as im:comparison.paste(im.resize((640,360)),(col*640,row*384+24))
    comparison.save(qa/'comparison.jpg',quality=95)
    validation={}
    base_report=results['source']['physics']
    for name in ['half_dt','finer_grid']:
        f=root/'validation'/name/'simulation/simulation_report.json'
        if f.exists():
            r=json.loads(f.read_text());validation[name]={'status':r['status'],
                'peak_deflection_relative_difference':r['max_bridge_deflection_from_flat_m']/base_report['max_bridge_deflection_from_flat_m']-1,
                'pass_time_difference_s':r['fully_on_right_road_time_s']-base_report['fully_on_right_road_time_s'],
                'final_position_difference_m':(np.array(r['final_car_position_m'])-base_report['final_car_position_m']).tolist()}
    summary={'status':'technical_checks_passed_pending_visual_review','cases':results,'metrics':metrics,
        'cache_isolation':True,'source_cache_unchanged':True,'single_target_edit_audit':True,
        'validation':validation,'visual_qa_sheets':str(qa),
        'limitations':['Aligned 49x19 refinement changes the eventual stopping point by about 9.2 cm; qualitative crossing and peak deflection are more robust than final position.','Shell/contact engineering approximation, not experimental material calibration.']}
    save_json(root/'suite_acceptance.json',summary)
    print(json.dumps({'status':summary['status'],'metrics':metrics,'validation':validation},indent=2))

if __name__=='__main__':main()
