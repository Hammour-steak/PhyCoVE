"""CPU-only encoding of verified remote render frames for a compact transfer."""

import argparse,hashlib,json,shutil,subprocess,urllib.request,zipfile,io,os
from pathlib import Path
a=argparse.ArgumentParser();a.add_argument('--render',type=Path,required=True);a.add_argument('--simulation',type=Path,required=True);args=a.parse_args()
root=args.render;frames=sorted((root/'frames').glob('frame_*.png'))
assert [p.name for p in frames]==[f'frame_{i:04d}.png'for i in range(1,97)]
ffmpeg=shutil.which('ffmpeg')
if not ffmpeg:
    repo=Path(__file__).resolve().parents[4]
    found=list(repo.glob('tools/**/ffmpeg-linux*'))+list(repo.glob('.runtime/**/ffmpeg-linux*'))
    found=[p for p in found if p.is_file()and os.access(p,os.X_OK)]
    if found:ffmpeg=str(found[0])
    else:
        runtime=root.parents[1]/'encoder_runtime';runtime.mkdir(exist_ok=True)
        binary=runtime/'ffmpeg'
        if not binary.exists():
            with urllib.request.urlopen('https://pypi.org/pypi/imageio-ffmpeg/0.6.0/json',timeout=20)as stream:meta=json.load(stream)
            wheel=next(f for f in meta['urls']if f['filename'].endswith('manylinux2014_x86_64.whl'))
            with urllib.request.urlopen(wheel['url'],timeout=90)as stream:data=stream.read()
            assert hashlib.sha256(data).hexdigest()==wheel['digests']['sha256']
            archive=zipfile.ZipFile(io.BytesIO(data));name=next(n for n in archive.namelist()if '/binaries/ffmpeg-linux' in n)
            binary.write_bytes(archive.read(name));binary.chmod(0o755)
            (runtime/'source.json').write_text(json.dumps({'url':wheel['url'],'wheel_sha256':wheel['digests']['sha256'],'binary_sha256':hashlib.sha256(binary.read_bytes()).hexdigest()},indent=2))
        ffmpeg=str(binary)
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
receipt=root/'render_receipt_1_96.json';j=json.loads(receipt.read_text());assert j['physics_cache_sha256']==sha(next(p for p in (args.simulation/'trajectory.npz',args.simulation/'physics_cache.npz') if p.is_file()))
video=root/'video.mp4'
subprocess.run([ffmpeg,'-nostdin','-y','-v','error','-framerate','24','-i',str(root/'frames/frame_%04d.png'),'-frames:v','96',
 '-c:v','libx264','-threads','4','-crf','16','-preset','slow','-pix_fmt','yuv420p','-movflags','+faststart',str(video)],check=True)
record=dict(video_sha256=sha(video),source_frame_names=[p.name for p in frames],
 encoder_binary=ffmpeg,encoder_binary_sha256=sha(Path(ffmpeg)),
 physics_cache_sha256=j['physics_cache_sha256'],encoder='CPU libx264 CRF16 slow yuv420p',
 playback_role=j['playback_role'],physical_sample_times_s=j['physical_sample_times_s'],
 metadata='Actual 96 remote rendered frames at 24 fps. '+j['physical_time_mapping'])
(root/'encoding_receipt.json').write_text(json.dumps(record,indent=2));print(json.dumps(record))
