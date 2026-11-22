"""Paths and small shared utilities of the entryway scene's native solver, renderers and launcher."""
from pathlib import Path
import hashlib,json,os

CASE='entryway_eva_slippers'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
# Accepted native delivery and case data (not in assets.json); PCVE_ENTRYWAY_DATA moves it.
DATA=Path(os.environ.get('PCVE_ENTRYWAY_DATA',str(ROOT/'renders'/CASE)))
FORMAL=HERE.parents[1]

import sys
sys.path.insert(0,str(ROOT/'scripts'))
from pcve_assets import asset
INPUTS=asset('scenes/'+CASE)

def save(path,value):
 path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
 path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False),encoding='utf-8')

def read(path):return json.loads(Path(path).read_text(encoding='utf-8'))

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1048576),b''):h.update(b)
 return h.hexdigest()
