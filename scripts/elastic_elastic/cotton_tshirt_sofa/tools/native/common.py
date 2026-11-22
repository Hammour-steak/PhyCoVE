"""Paths and small shared utilities of the native solver, renderer and GPU launcher."""

from pathlib import Path
import json,hashlib,sys
CASE='cotton_tshirt_sofa'
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[4]
# Accepted render records (not in assets.json): render.py resolves a relative --cache here and room.py writes its
# support audit below it.
DATA=ROOT/'renders'/CASE/'accepted_renders'
sys.path.insert(0,str(ROOT/'scripts'))
from pcve_assets import asset as registered_asset
ASSETS=registered_asset('scenes/cotton_tshirt_sofa')
GEOMETRY=ASSETS/'geometry'
def save(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8',newline='\n')
def sha(path):
    h=hashlib.sha256()
    with Path(path).open('rb')as f:
        for block in iter(lambda:f.read(1024*1024),b''):h.update(block)
    return h.hexdigest()
def asset(name):
    for root in [ASSETS/'room_textures',ASSETS/'fabric_textures',ASSETS/'raw']:
        if(root/name).is_file():return root/name
    raise FileNotFoundError(name)
