"""Encode the existing accepted water-removal frame sequence without retiming."""
import argparse
from pathlib import Path
import subprocess

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--run',type=Path,required=True)
p.add_argument('--video',type=Path,required=True)
a=p.parse_args()
assert all((a.run/'render'/f'{frame:04d}.png').is_file() for frame in range(1,97))
subprocess.run(['ffmpeg','-nostdin','-v','error','-y','-framerate','24','-i',str(a.run/'render/%04d.png'),
                '-frames:v','96','-c:v','libx264','-crf','16','-pix_fmt','yuv420p','-movflags','+faststart',str(a.video)],check=True)
