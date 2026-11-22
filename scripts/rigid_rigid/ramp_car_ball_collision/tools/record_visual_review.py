"""Record an explicit completed visual review, gated by existing technical audits."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from scene_config import save_json
def main():
    p=argparse.ArgumentParser();p.add_argument('--case-dir',type=Path,required=True);p.add_argument('--review-json',type=Path,required=True);a=p.parse_args();folder=a.case_dir
    load=lambda p:json.loads(p.read_text());sha=lambda p:hashlib.sha256(p.read_bytes()).hexdigest();review=load(a.review_json)
    render=load(folder/'scenario_metadata.json')['configuration']['render'];total=round(render['fps']*render['duration_sec'])
    assert review['all_frames_reviewed'] and review['event_frames_reviewed'] and review['visual_accepted']
    for name in ['physics_validation.json','frame_audit.json','saved_scene_audit.json']:assert load(folder/name)['accepted'],name
    video=load(folder/'video_validation.json');assert video['full_decode'] and all(video['checks'].values())
    assert video['sha256']==sha(folder/'video.mp4')
    evidence=['frame_audit.json','saved_scene_audit.json','video_validation.json']
    if not review.get('full_native_1x_playback_0_to_4s',False):
        # A CLI review is explicit: retain decode/timestamp proof and every reviewed sheet.
        assert review['review_mode']=='cli_decode_and_exhaustive_frames'
        cli=load(folder/'cli_video_review.json')
        assert cli['accepted'] and all(cli['checks'].values())
        assert cli['video_sha256']==sha(folder/'video.mp4')
        assert len(cli['frame_timestamps_sec'])==total
        assert review['reviewed_frame_indices']==list(range(1,total+1))
        sheets=[f'motion_frames_{start:03d}_{start+23:03d}.jpg' for start in range(1,total+1,24)]
        assert review['reviewed_motion_sheets']==sheets
        assert all((folder/'review'/name).is_file() for name in sheets)
        evidence.append('cli_video_review.json')
    record={'accepted':True,'case':folder.name,'reviewed_at_utc':datetime.now(timezone.utc).isoformat(),
        'physics_sha256':sha(folder/'physics_transforms.json'),'video_sha256':sha(folder/'video.mp4'),
        'scenario_metadata_sha256':sha(folder/'scenario_metadata.json'),'review':review,
        'evidence_sha256':{n:sha(folder/n) for n in evidence}}
    save_json(folder/'case_acceptance.json',record);print(folder.name,'VISUAL_ACCEPTED')
if __name__=='__main__':main()
