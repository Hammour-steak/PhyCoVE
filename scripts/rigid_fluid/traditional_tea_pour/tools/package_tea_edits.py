"""Encode complete native sequences, verify streams, and record reference integrity."""
import argparse
import hashlib
import json
from pathlib import Path
import struct
import subprocess
import sys
import time
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from pcve_config_diff import audit_report
def file_hash(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('root',type=Path)
p.add_argument('--cases',nargs='+',default=['speed_2x','speed_0p5x','remove_tea','stop_flow_at_2s'])
p.add_argument('--skip-integrity',action='store_true')
a=p.parse_args();root=a.root.resolve()
for name in a.cases:
    case=root/name
    files=sorted((case/'frames').glob('frame_*.png'))
    assert [p.name for p in files]==[f'frame_{f:04d}.png' for f in range(1,97)]
    for path in files:
        with path.open('rb') as f:header=f.read(24)
        assert header[:8]==b'\x89PNG\r\n\x1a\n' and struct.unpack('>II',header[16:24])==(1280,720)
    validation=json.loads((case/'edit_validation.json').read_text());assert validation['accepted_numerical_and_semantic']
    report=json.loads((case/'edit_diff.json').read_text());diff=audit_report(report,report['declared_changed_paths'])
    assert diff['config_diff_status']=='matched_declared_changes'
    (case/'config_diff_audit.json').write_text(json.dumps(diff,indent=2)+'\n')
    target=case/'video.mp4';started=time.monotonic()
    subprocess.run(['ffmpeg','-y','-v','error','-threads','8','-framerate','24','-start_number','1','-i',str(case/'frames/frame_%04d.png'),'-frames:v','96','-c:v','libx264','-threads','8','-preset','slow','-crf','14','-pix_fmt','yuv420p','-movflags','+faststart',str(target)],check=True)
    encode_seconds=time.monotonic()-started
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-select_streams','v:0','-count_frames','-show_entries','stream=width,height,r_frame_rate,avg_frame_rate,nb_read_frames,codec_name,pix_fmt:format=duration','-of','json',str(target)],text=True))
    s=probe['streams'][0]
    checks={'width_height':(s['width'],s['height'])==(1280,720),'fps24':s['r_frame_rate']==s['avg_frame_rate']=='24/1',
            'frames96':int(s['nb_read_frames'])==96,'duration4':float(probe['format']['duration'])==4.,
            'h264_yuv420p':s['codec_name']=='h264' and s['pix_fmt']=='yuv420p'}
    subprocess.run(['ffmpeg','-v','error','-i',str(target),'-f','null','-'],check=True)
    checks['full_decode_no_errors']=True;assert all(checks.values())
    native=json.loads((case/'scene_revision.json').read_text());assert native['all_textures_packed']
    result={'video':str(target),'sha256':file_hash(target),'checks':checks,'probe':probe,'encoding_crf':14,
            'encode_seconds':encode_seconds,'visual_review':'pending full sequence review'}
    (case/'video_validation.json').write_text(json.dumps(result,indent=2)+'\n')
    print(name,json.dumps(checks),flush=True)
if not a.skip_integrity:
    before=json.loads((root/'reference_integrity_before.json').read_text())
    after={str(path):{'size':Path(path).stat().st_size,'mtime_ns':Path(path).stat().st_mtime_ns,'sha256':file_hash(Path(path))} for path in before}
    assert before==after
    (root/'reference_integrity_after.json').write_text(json.dumps(after,indent=2)+'\n')
    (root/'reference_integrity_validation.json').write_text(json.dumps({'all_reference_files_unchanged':True,'files_checked':len(before)},indent=2)+'\n')
