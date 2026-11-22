"""Canonical tennis delivery paths and physical edit contract."""
from pathlib import Path
import hashlib
import json
import os,sys

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[3]
# Accepted native delivery: original videos, physics/pose reports and the
# SHA-indexed worker archives that hold every render cache and native GT array.
DATA = Path(os.environ.get('PCVE_TENNIS_DELIVERY', str(REPO / 'renders/tennis_net_hit/accepted')))
sys.path.insert(0,str(HERE.parents[2]))
from pcve_assets import asset
# Frozen solver inputs (packed court scene, contact libraries, common initial
# packet, per-edit restart checkpoints), registered in assets.json.
INPUTS=asset('scenes/tennis_net_hit')
SOURCE_SHA = '49753ed161a83b5cb6d1d88093999dcce74f931cec2ad5d59337678a9461d9a4'
PACKET_SHA = 'bcfbf9e039e4594e0a48ce6648c27b4643dc8ac70947a3d9e733d11e464cfb70'
LIB_SHA = '0b0517a8881d79162a203cb5856a62fa2d834a7a65a7d5ce9658f121c7b6ad23'
CASES = {
 'source': ('新基准', None, 8., 1.),
 'ball_speed_div5': ('初速度 ×0.2', 'SET tennis_ball.initial_velocity TIMES 0.2', 1.6, 1.),
 'ball_speed_x2': ('初速度 ×2', 'SET tennis_ball.initial_velocity TIMES 2', 16., 1.),
 'net_young_div10': ('球网杨氏模量 ×0.1', 'SET tennis_net.young_modulus TIMES 0.1', 8., .1),
 'net_young_x10': ('球网杨氏模量 ×10', 'SET tennis_net.young_modulus TIMES 10', 8., 10.),
 'remove_entire_net': ('删除整套球网', 'DELETE tennis_net', 8., 1.),
}
KINEMATICS = ('net_positions', 'net_velocities', 'strap_positions', 'strap_velocities',
              'strap_surface_positions', 'ball_positions', 'ball_velocities',
              'ball_angular_velocities', 'ball_quaternions')


def worker_tars(data=None):
 """The delivery's worker_tars/<worker>/ folder: <case>_artifacts.tar with its <case>_files.json index."""
 folders = [p for p in (Path(data or DATA) / 'worker_tars').iterdir() if p.is_dir()]
 if len(folders) != 1: raise RuntimeError('Expected one worker folder in worker_tars/: ' + str(folders))
 return folders[0]


def sha(path):
 h = hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda: f.read(8*1024*1024), b''): h.update(b)
 return h.hexdigest()


def write(path, value):
 path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
 temp = path.with_suffix(path.suffix + '.writing')
 temp.write_text(json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf8')
 temp.replace(path)
