"""Quantitative per-case audit (membrane, contacts, media). Pure NumPy/JSON: this script never invokes Blender."""

from pathlib import Path
import argparse, hashlib, json, subprocess, sys
import numpy as np

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
sys.path.insert(0, str(CASE_DIR))
from edit_vocab import SPEC, CASE_DSL, override_for

def sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()

def media_metrics(d, case, cfg, expected_frames):
    video=d/'video.mp4';render_path=d/'render_report.json';artifact_path=d/'artifact_manifest.json'
    if not video.is_file():return {'media_present':False,'media_contract_ok':False}
    render=json.loads(render_path.read_text()) if render_path.is_file() else {}
    probe=json.loads(subprocess.run(['ffprobe','-v','error','-select_streams','v:0','-show_entries','stream=codec_name,width,height,avg_frame_rate,nb_frames','-of','json',str(video)],check=True,capture_output=True,text=True).stdout)['streams'][0]
    hashes_ok=False
    if artifact_path.is_file():
        manifest=json.loads(artifact_path.read_text());hashes_ok=all((d/a['path']).is_file() and (d/a['path']).stat().st_size==a['bytes'] and sha256(d/a['path'])==a['sha256'] for a in manifest.get('artifacts',[]) if 'sha256' in a)
    ok=(render.get('status')=='complete' and render.get('scene_id')==cfg['scene_id'] and render.get('case')==case and render.get('camera_id')=='B' and render.get('resolution')==[1280,720] and render.get('fps')==SPEC['fps'] and render.get('cache_schema_version')==2 and render.get('source_frame_count')==expected_frames and render.get('cache_sha256')==sha256(d/'simulation.npz') and int(probe.get('nb_frames') or 0)==expected_frames-1 and probe.get('codec_name')=='h264' and int(probe['width'])==1280 and int(probe['height'])==720 and probe.get('avg_frame_rate')==f"{SPEC['fps']}/1" and hashes_ok and render.get('playback_rate')==1.0)
    return {'media_present':True,'media_contract_ok':bool(ok),'video_codec':probe.get('codec_name'),'video_resolution':[int(probe['width']),int(probe['height'])],'video_frames':int(probe.get('nb_frames') or 0),'camera_id':render.get('camera_id'),'artifact_hashes_ok':hashes_ok}


def unique_edges(faces):
    if not len(faces):
        return np.empty((0, 2), np.int32)
    edges = np.concatenate((faces[:, [0, 1]], faces[:, [1, 2]], faces[:, [2, 0]]))
    edges.sort(axis=1)
    return np.unique(edges, axis=0)


def membrane_metrics(pos, faces):
    if not pos.shape[1]:
        return dict(max_edge_stretch_ratio=0.0, p995_edge_stretch_ratio=0.0,
                    inverted_face_frames=0, max_inverted_faces=0)
    edges = unique_edges(faces)
    initial = pos[0]
    edge0 = np.linalg.norm(initial[edges[:, 1]] - initial[edges[:, 0]], axis=1)
    tri0 = initial[faces]
    n0 = np.cross(tri0[:, 1] - tri0[:, 0], tri0[:, 2] - tri0[:, 0])
    stretch_max, stretch_p995, inverted = 1.0, 1.0, []
    for frame in pos:
        lengths = np.linalg.norm(frame[edges[:, 1]] - frame[edges[:, 0]], axis=1)
        ratios = lengths / np.maximum(edge0, 1e-12)
        stretch_max = max(stretch_max, float(ratios.max()))
        stretch_p995 = max(stretch_p995, float(np.quantile(ratios, .995)))
        tri = frame[faces]
        normals = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        inverted.append(int(np.count_nonzero(np.einsum('ij,ij->i', normals, n0) <= 0)))
    return dict(max_edge_stretch_ratio=stretch_max,
                p995_edge_stretch_ratio=stretch_p995,
                inverted_face_frames=int(np.count_nonzero(inverted)),
                max_inverted_faces=max(inverted, default=0))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--sim-root', type=Path, required=True)
    ap.add_argument('--out', type=Path)
    args = ap.parse_args()
    root = args.sim_root.resolve()
    rows = []
    for case in SPEC['cases']:
        d = root / case
        z = np.load(d / 'simulation.npz', allow_pickle=False)
        report = json.loads((d / 'simulation_report.json').read_text())
        cfg = json.loads((d / 'simulation_config.json').read_text())
        pos = z['membrane_positions']
        faces = z['membrane_faces']
        cache_schema_ok=bool(int(z['cache_schema_version'][0])==2 and list(z['rigid_body_ids'])==['ball','second_ball'])
        expected_second=case=='add_second_ball';second_present=bool(z['second_ball_present'][0])
        finite = bool(np.isfinite(pos).all() and np.isfinite(z['ball_transforms']).all() and (not second_present or np.isfinite(z['second_ball_transforms']).all()))
        ball_z = z['ball_transforms'][:, 2, 3]
        membrane_height = cfg['physics']['membrane_height_m']
        depression = (membrane_height - pos[:, :, 2].min(axis=1)) if pos.shape[1] else np.zeros(len(ball_z))
        peak_i = int(np.argmax(depression))
        log_path = d / 'simulate_remote.log'
        if not log_path.is_file():log_path=root.parent/f'{case}.simulate.log'
        log = log_path.read_text(encoding='utf-8', errors='replace')
        expected_frames=round(SPEC['duration_s']*SPEC['fps'])+1
        gt_path=d/'ground_truth_transforms.json';gt_ok=False
        if gt_path.is_file():
            gt=json.loads(gt_path.read_text())
            gt_ok=bool(gt.get('schema_version')==2 and gt.get('object_presence',{}).get('second_ball')==second_present and len(gt.get('frames',[]))==expected_frames-1 and all(frame.get('objects',{}).get('second_ball',{}).get('present')==second_present for frame in gt.get('frames',[])))
        row = {
            'case': case,
            'dsl': CASE_DSL[case],
            'policy_override': override_for(case),
            'finite': finite,
            'frames': int(len(ball_z)),
            'frame_contract_ok':bool(len(ball_z)==expected_frames and report.get('status')=='complete' and cfg.get('scene_id')==SPEC['scene_id'] and cfg.get('case')==case),
            'cache_schema_ok':cache_schema_ok,
            'second_ball_presence_ok':bool(second_present==expected_second),
            'ground_truth_contract_ok':gt_ok,
            'peak_depression_m': float(depression[peak_i]),
            'peak_depression_frame': peak_i + 1,
            'peak_depression_time_s': float(z['times'][peak_i]),
            'ball_vertical_travel_m': float(ball_z.max() - ball_z.min()),
            'minimum_ball_center_z_m': float(ball_z.min()),
            'second_ball_vertical_travel_m':float(z['second_ball_transforms'][:,2,3].max()-z['second_ball_transforms'][:,2,3].min()) if second_present else None,
            'minimum_second_ball_center_z_m':float(z['second_ball_transforms'][:,2,3].min()) if second_present else None,
            'minimum_ball_pair_center_distance_m':float(np.linalg.norm(z['ball_transforms'][:,:3,3]-z['second_ball_transforms'][:,:3,3],axis=1).min()) if second_present else None,
            'minimum_ball_pair_surface_gap_m':float(np.linalg.norm(z['ball_transforms'][:,:3,3]-z['second_ball_transforms'][:,:3,3],axis=1).min()-cfg['physics']['ball_radius_m']-cfg['physics']['second_ball_radius_m']) if second_present else None,
            'minimum_membrane_z_m': float(pos[:, :, 2].min()) if pos.shape[1] else None,
            'solver_max_iteration_warnings': log.count('Newton Iteration Exits with Max Iteration'),
            'line_search_max_iteration_warnings':log.count('Line Search Exits with Max Iteration'),
            **membrane_metrics(pos, faces),
            **media_metrics(d,case,cfg,expected_frames),
        }
        rows.append(row)
    source_peak = next(r['peak_depression_m'] for r in rows if r['case'] == 'source')
    for row in rows:
        row['peak_depression_change_vs_source_pct'] = (
            100.0 * (row['peak_depression_m'] - source_peak) / source_peak
            if source_peak and row['case'] not in ('remove_membrane',) else None
        )
    all_finite = all(r['finite'] for r in rows)
    frames_ok=all(r['frame_contract_ok'] and r['cache_schema_ok'] and r['second_ball_presence_ok'] and (r['ground_truth_contract_ok'] if r['media_present'] else True) for r in rows)
    require_media=any(r['media_present'] for r in rows)
    media_ok=all(r['media_present'] and r['media_contract_ok'] for r in rows) if require_media else None
    cameras={r.get('camera_id') for r in rows if r['media_present']}
    pair_contact_ok=all(r['minimum_ball_pair_surface_gap_m'] is None or r['minimum_ball_pair_surface_gap_m']>=-0.002 for r in rows)
    stiffness_direction_ok=next(r['peak_depression_m'] for r in rows if r['case']=='membrane_stiff')<source_peak
    numerical_clean = frames_ok and pair_contact_ok and stiffness_direction_ok and all(r['max_inverted_faces'] == 0 and r['solver_max_iteration_warnings'] == 0 and r['line_search_max_iteration_warnings']==0 for r in rows) and (media_ok is not False)
    result = {
        'status': 'passed_visualization_audit_only' if all_finite and numerical_clean else ('passed_visualization_audit_with_research_warnings' if all_finite else 'failed_nonfinite_state'),
        'scene_id': SPEC['scene_id'],
        'policy': 'pcve-physical-add-delete',
        'local_blender_used': False,
        'accepted_benchmark_gt': False,
        'gates': {
            'all_finite': all_finite,
            'frame_and_identity_contract':frames_ok,
            'no_face_inversion': all(r['max_inverted_faces'] == 0 for r in rows),
            'no_solver_max_iteration_warning': all(r['solver_max_iteration_warnings'] == 0 for r in rows),
            'no_line_search_max_iteration_warning':all(r['line_search_max_iteration_warnings']==0 for r in rows),
            'ball_pair_no_deep_interpenetration':pair_contact_ok,
            'stiffer_membrane_reduces_peak_depression':stiffness_direction_ok,
            'media_contract':media_ok,
            'shared_camera':len(cameras)==1 if require_media else None,
        },
        'rows': rows,
        'limitations': [
            'Material constants are plausible effective values, not fit to a named membrane coupon.',
            'This suite uses a halved time step but does not itself constitute a mesh/time convergence study.',
            'Results are visualization-grade and are not accepted benchmark ground truth.',
        ],
    }
    out = args.out.resolve() if args.out else root / 'audit.json'
    out.write_text(json.dumps(result, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps(result, indent=2, ensure_ascii=False))
    # Research warnings remain visible and keep accepted_benchmark_gt false, but
    # do not discard a complete visualization delivery. Non-finite state is the
    # hard failure for this development-candidate suite.
    if not all_finite:
        raise SystemExit(2)


if __name__ == '__main__':
    main()
