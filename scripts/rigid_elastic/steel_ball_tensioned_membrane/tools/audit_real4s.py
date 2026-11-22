"""Read-only native-time, geometry, policy and delivery audit. Never imports bpy."""
from __future__ import annotations

import argparse
import datetime
import hashlib
import json
from pathlib import Path
import sys

import cv2
import numpy as np
from trimesh.triangles import closest_point

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent)]
from audit import membrane_metrics
from edit_vocab import CASE_DSL, override_for

ORDER = ('source', 'ball_mass_heavy', 'membrane_soft', 'membrane_stiff', 'remove_membrane', 'add_second_ball')
LABELS = ('基准落球', '钢球质量 ×2', '膜杨氏模量 ×0.5', '膜杨氏模量 ×3', '删除橡胶膜', '增加同规格钢球')


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def video_metrics(path):
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise RuntimeError(f'Cannot decode {path}')
    data = dict(width=round(cap.get(cv2.CAP_PROP_FRAME_WIDTH)),
                height=round(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)),
                fps=float(cap.get(cv2.CAP_PROP_FPS)),
                frames=round(cap.get(cv2.CAP_PROP_FRAME_COUNT)))
    changes = []
    previous = None
    decoded = 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        if previous is not None:
            changes.append(float(cv2.absdiff(gray, previous).mean()))
        previous = gray
        decoded += 1
    cap.release()
    data.update(decoded_frames=decoded, duration_s=data['frames']/data['fps'],
                image_difference_per_transition=changes,
                sha256=sha(path))
    data['contract_ok'] = (data['width'], data['height'], data['fps'], data['frames'], decoded) == (1280,720,24.0,96,96)
    return data


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--previous-root', type=Path)
    parser.add_argument('--revision', default='native_real_time_4s')
    args = parser.parse_args()
    root = args.root.resolve()
    rows = []
    configs = {}
    cameras = []
    for case, label in zip(ORDER, LABELS):
        folder = root / 'cases' / case
        cache = np.load(folder / 'simulation.npz', allow_pickle=False)
        cfg = json.loads((folder / 'simulation_config.json').read_text(encoding='utf-8'))
        report = json.loads((folder / 'simulation_report.json').read_text(encoding='utf-8'))
        render = json.loads((folder / 'render_report.json').read_text(encoding='utf-8'))
        replay = json.loads((folder / 'native_replay_audit.json').read_text(encoding='utf-8'))
        configs[case] = cfg
        p = cfg['physics']
        times = cache['times']
        pos = cache['membrane_positions']
        faces = cache['membrane_faces']
        primary = cache['ball_transforms'][:,:3,3]
        secondary = cache['second_ball_transforms'][:,:3,3]
        present = bool(cache['second_ball_present'][0])
        depression = np.maximum(0, p['membrane_height_m']-pos[:,:,2].min(axis=1)) if pos.shape[1] else np.zeros(len(times))
        peak = int(depression.argmax())
        finite = all(np.isfinite(cache[key]).all() for key in (
            'times','membrane_positions','membrane_velocities','ball_transforms','ball_velocities',
            'second_ball_transforms','second_ball_velocities'))
        time_ok = len(times) == 97 and np.allclose(times,np.arange(97)/24,rtol=0,atol=1e-12)
        clamp_error = float(np.linalg.norm(pos[:,cache['membrane_fixed_mask']]-pos[0,cache['membrane_fixed_mask']],axis=-1).max()) if pos.shape[1] else 0.
        gaps = []
        second_gaps = []
        if pos.shape[1]:
            for i in range(len(times)):
                triangles = pos[i,faces]
                for center, radius, target in [(primary[i],p['ball_radius_m'],gaps)] + (
                    [(secondary[i],p['second_ball_radius_m'],second_gaps)] if present else []):
                    near = closest_point(triangles,np.broadcast_to(center,(len(faces),3)))
                    target.append(float(np.linalg.norm(near-center,axis=1).min()-radius))
        pair_gap = float((np.linalg.norm(primary-secondary,axis=1)-p['ball_radius_m']-p['second_ball_radius_m']).min()) if present else None
        gate_gaps=[]
        for centers,radius in [(primary,p['ball_radius_m'])]+([(secondary,p['second_ball_radius_m'])] if present else []):
            for height in (0.955,1.035):
                for x in (-0.122,0.122):
                    delta=np.maximum(np.abs(centers-np.array([x,0.025,height]))-np.array([0.028,0.034,0.029]),0)
                    gate_gaps.append(float((np.linalg.norm(delta,axis=1)-radius).min()))
        release_head_gap=float((1.140-primary[:,2]-p['ball_radius_m']).min())
        # Only the pre-impact interval is compared with gravity's analytic path.
        flight = times <= 0.125 + 1e-12
        analytic = primary[0,2]-0.5*p['gravity_m_s2']*times[flight]**2
        freefall_error = float(np.abs(primary[flight,2]-analytic).max())
        primary_world = np.einsum('fij,vj->fvi',cache['ball_transforms'][:,:3,:3],cache['ball_vertices'])+primary[:,None,:]
        floor_gap = float(primary_world[:,:,2].min())
        log = (root/f'{case}.simulate.log').read_text(encoding='utf-8',errors='replace')
        media = video_metrics(folder/'video.mp4')
        cameras.append(render['camera_matrix_world'])
        expected_override = override_for(case)
        policy_values_ok = all(p[key] == value for key,value in expected_override.items())
        singular_values = np.linalg.svd(cache['ball_transforms'][:,:3,:3],compute_uv=False)
        rigid_strain = float(np.abs(singular_values-1).max())
        segment_motion = []
        for second in range(4):
            a,b=second*24,(second+1)*24+1
            segment_motion.append(dict(start_s=second,end_s=second+1,
                ball_travel_mm=float(np.linalg.norm(np.diff(primary[a:b],axis=0),axis=1).sum()*1000),
                max_membrane_step_mm=float(np.linalg.norm(np.diff(pos[a:b],axis=0),axis=2).max()*1000) if pos.shape[1] else 0.))
        manifest = json.loads((folder/'artifact_manifest.json').read_text(encoding='utf-8'))
        gt=json.loads((folder/'ground_truth_transforms.json').read_text(encoding='utf-8'))
        identity_ok=(list(cache['rigid_body_ids'])==['ball','second_ball'] and present==(case=='add_second_ball') and present==bool(p['second_ball_present']) and render['visible_rigid_objects']==(['ball','second_ball'] if present else ['ball']) and bool(pos.shape[1])==bool(p['membrane_present']) and replay.get('object_presence_matches_cache',False))
        gt_ok=(len(gt['frames'])==96 and gt.get('simulation_endpoint_s')==4.0 and all(
            abs(f['time_s']-i/24)<1e-12 and np.allclose(f['ball_transform_4x4'],cache['ball_transforms'][i],rtol=0,atol=1e-12)
            and f['objects']['second_ball']['present']==present
            and (not present or np.allclose(f['objects']['second_ball']['transform_4x4'],cache['second_ball_transforms'][i],rtol=0,atol=1e-12))
            for i,f in enumerate(gt['frames'])))
        artifact_ok = all((folder/item['path']).is_file() and (folder/item['path']).stat().st_size==item['bytes'] and sha(folder/item['path'])==item['sha256'] for item in manifest['artifacts'] if 'sha256' in item)
        row = dict(case=case,label=label,dsl=CASE_DSL[case],finite=bool(finite),
            native_time_contract_ok=bool(time_ok),integration_steps=cfg.get('integration_steps'),
            dt_s=cfg['simulation']['dt_s'],simulation_end_s=float(times[-1]),
            peak_depression_mm=float(depression[peak]*1000),peak_time_s=float(times[peak]),
            ball_travel_mm=float((primary[:,2].max()-primary[:,2].min())*1000),
            clamp_drift_mm=clamp_error*1000,freefall_error_mm=freefall_error*1000,
            minimum_ball_membrane_gap_mm=min(gaps)*1000 if gaps else None,
            minimum_second_membrane_gap_mm=min(second_gaps)*1000 if second_gaps else None,
            minimum_ball_pair_gap_mm=pair_gap*1000 if present else None,
            minimum_photogate_box_gap_mm=min(gate_gaps)*1000,
            minimum_release_head_vertical_gap_mm=release_head_gap*1000,
            minimum_floor_gap_mm=floor_gap*1000,
            maximum_primary_affine_strain=rigid_strain,
            newton_warnings=log.count('Newton Iteration Exits with Max Iteration'),
            line_search_warnings=log.count('Line Search Exits with Max Iteration'),
            policy_values_ok=policy_values_ok,artifact_hashes_ok=artifact_ok,
            video_ground_truth_contract_ok=bool(gt_ok),
            object_identity_contract_ok=bool(identity_ok),
            simulation_status=report['status'],simulation_wall_s=report['wall_seconds'],
            render_wall_s=render['wall_seconds'],media=media,
            render_native_time_ok=bool(render.get('source_frame_count')==97 and render.get('frames')==96 and render.get('playback_rate')==1.0 and render.get('simulation_duration_s')==4.0 and render['cache_sha256']==sha(folder/'simulation.npz')),
            render_execution_host=render['execution_host'],render_samples=render['samples'],
            native_replay=replay,
            local_blender_used=render['local_blender_used'],
            trajectory=dict(time_s=times.tolist(),ball_z_mm=(primary[:,2]*1000).tolist(),
                second_ball_z_mm=(secondary[:,2]*1000).tolist() if present else None,
                depression_mm=(depression*1000).tolist()),
            motion_by_second=segment_motion,**membrane_metrics(pos,faces))
        if args.previous_root:
            old_path=args.previous_root/'cases'/case/'simulation.npz'
            if old_path.is_file():
                old=np.load(old_path,allow_pickle=False)
                pairs=[(i,int(matches[0])) for i,t in enumerate(old['times'])
                       if len(matches:=np.where(np.abs(times-t)<1e-10)[0])]
                row['historical_prefix_comparison']=dict(common_states=len(pairs),
                    end_s=max(float(old['times'][i]) for i,j in pairs),
                    maximum_ball_center_difference_mm=max(float(np.linalg.norm(old['ball_transforms'][i,:3,3]-cache['ball_transforms'][j,:3,3]))*1000 for i,j in pairs),
                    maximum_membrane_vertex_difference_mm=max(float(np.linalg.norm(old['membrane_positions'][i]-pos[j],axis=1).max())*1000 for i,j in pairs) if pos.shape[1] else 0.,
                    initial_ball_transform_identical=bool(np.array_equal(old['ball_transforms'][0],cache['ball_transforms'][0])))
        rows.append(row)

    baseline = configs['source']['physics']
    pose_keys=('ball_initial_location_m','membrane_height_m','membrane_clear_diameter_m')
    pose_ok=all(all(c['physics'][key]==baseline[key] for key in pose_keys) for c in configs.values())
    for row in rows:
        p=configs[row['case']]['physics']
        expected=override_for(row['case'])
        row['policy_values_ok'] = row['policy_values_ok'] and all(
            p[key] == expected.get(key, baseline[key]) for key in baseline)
    gates = dict(
        real_four_second_simulation=all(r['native_time_contract_ok'] and r['integration_steps']==7680 for r in rows),
        normal_speed_delivery=all(r['media']['contract_ok'] and r['render_native_time_ok'] for r in rows),
        matching_video_ground_truth=all(r['video_ground_truth_contract_ok'] for r in rows),
        correct_added_and_deleted_objects=all(r['object_identity_contract_ok'] for r in rows),
        native_scene_replay=all(r['native_replay']['native_replay_ok'] and r['native_replay']['frames_checked']==96 for r in rows),
        finite_states=all(r['finite'] for r in rows),
        rigid_sphere_shape=all(r['maximum_primary_affine_strain']<0.001 for r in rows),
        fixed_boundary=all(r['clamp_drift_mm']<0.001 for r in rows),
        no_projected_face_reversal=all(r['max_inverted_faces']==0 for r in rows),
        primary_freefall=all(r['freefall_error_mm']<1.0 for r in rows),
        floor_contact=all(r['minimum_floor_gap_mm']>=-0.1 for r in rows),
        no_ball_pair_overlap=all(r['minimum_ball_pair_gap_mm'] is None or r['minimum_ball_pair_gap_mm']>=-1.0 for r in rows),
        apparatus_clearance=all(r['minimum_photogate_box_gap_mm']>0 and r['minimum_release_head_vertical_gap_mm']>=-0.001 for r in rows),
        same_camera=all(np.allclose(cameras[0],c,rtol=0,atol=1e-12) for c in cameras),
        same_existing_initial_placement=pose_ok,
        physical_edit_policy=all(r['policy_values_ok'] for r in rows),
        artifact_hashes=all(r['artifact_hashes_ok'] for r in rows),
        remote_only_blender=all(not r['local_blender_used'] for r in rows),
        no_newton_warning=all(r['newton_warnings']==0 for r in rows),
        no_line_search_warning=all(r['line_search_warnings']==0 for r in rows))
    hard=('real_four_second_simulation','normal_speed_delivery','matching_video_ground_truth','correct_added_and_deleted_objects','native_scene_replay','finite_states','rigid_sphere_shape','fixed_boundary',
          'primary_freefall','floor_contact','no_ball_pair_overlap','apparatus_clearance','same_camera',
          'same_existing_initial_placement','physical_edit_policy','artifact_hashes','remote_only_blender')
    appearance_path=root/'appearance_audit.json'
    appearance=json.loads(appearance_path.read_text(encoding='utf-8')) if appearance_path.is_file() else None
    if appearance:
        gates['appearance_only_invariants']=bool(appearance['all_pass'])
        hard+=('appearance_only_invariants',)
    hard_ok=all(gates[g] for g in hard)
    result=dict(schema_version=1,case_id='steel_ball_tensioned_membrane',
        revision=args.revision,review_date=datetime.date.today().isoformat(),
        status='delivery_pass_with_numerical_cautions' if hard_ok and not all(gates.values()) else ('delivery_pass' if hard_ok else 'needs_revision'),
        hard_gates_pass=hard_ok,accepted_benchmark_gt=False,
        contract=dict(width=1280,height=720,fps=24,frames=96,duration_s=4.0,
            simulation_states=97,integration_steps=7680,dt_s=1/1920,playback_rate=1.0,
            retiming=False,final_frame_padding=False),gates=gates,rows=rows,
        limitations=['材料常数尚未用具体膜片实验标定。',
            '非线性薄壳、离散壳弯曲与 IPC 接触；尚未完成网格/时间步收敛研究。',
            'Newton 与线搜索上限告警逐案原样统计；它们影响数值置信度，不能因画面通过而忽略。',
            '球膜距离按理想球半径测量，物理解算钢球为细分 3 级二十面球，存在亚毫米离散几何差异。',
            '97 个样本包含 t=4.0 s 端点，96 帧视频显示 t=0 至 95/24 s，每帧显示 1/24 s。'])
    manual_path=root/'manual_review.json'
    if appearance:result['appearance_audit']=appearance
    if manual_path.is_file():
        result['manual_review']=json.loads(manual_path.read_text(encoding='utf-8'))
        if result['manual_review'].get('delete_case_camera_occlusion'):
            result['limitations'].append(result['manual_review']['camera_finding_zh'])
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    print(json.dumps(dict(status=result['status'],gates=gates),ensure_ascii=False,indent=2))
    if not hard_ok:
        raise SystemExit(2)


if __name__=='__main__':
    main()
