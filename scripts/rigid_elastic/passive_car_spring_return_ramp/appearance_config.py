"""Appearance overlays never mutate accepted physical or numerical inputs."""
import copy,hashlib,json
from pathlib import Path
from scene_config import digest
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import scene_asset, asset

HERE=Path(__file__).resolve().parent
# Current look: the appearance overlay applied on top of scene_config.py.
CURRENT_OVERLAY=HERE/'appearance/appearance_overlay.json'
# Registered shared assets (assets.json) read by appearance/look_passive_car_spring_return_ramp.py.
LOOK_ASSET_FILES={'polyhaven/beige_wall_001':['beige_wall_001_diff_4k.jpg','beige_wall_001_nor_gl_4k.jpg','beige_wall_001_rough_4k.jpg'],
    'polyhaven/potted_plant_04':['potted_plant_04_2k.blend','textures/potted_plant_04_diff_2k.jpg','textures/potted_plant_04_nor_gl_2k.exr','textures/potted_plant_04_rough_2k.exr']}

def effective_configuration(config,path=None):
    path=Path(path) if path else CURRENT_OVERLAY
    overlay=json.loads(path.read_text())
    if set(overlay)-{'schema_version','revision','appearance'}:raise ValueError('Only an appearance overlay is permitted')
    if not isinstance(overlay.get('appearance'),dict):raise ValueError('Missing appearance object')
    result=copy.deepcopy(config);result['appearance'].update(copy.deepcopy(overlay['appearance']))
    result['appearance']['revision']=overlay['revision']
    for key in ['physics','simulation_quality','render']:
        assert result[key]==config[key],key
    return result

def asset_signature():
    path=scene_asset(HERE, 'assets/realism/manifest.json')
    if not path.is_file():raise FileNotFoundError('Run the canonical prepare_assets.py first')
    manifest=json.loads(path.read_text());actual={}
    for row in manifest['downloads']:
        file=scene_asset(HERE,row['path']);sha=hashlib.sha256(file.read_bytes()).hexdigest()
        if sha!=row['sha256']:raise RuntimeError('Texture differs from its provenance: '+str(file))
        actual[row['path']]=sha
    registry=json.loads((HERE.parents[2]/'assets.json').read_text())['assets']
    for name,files in LOOK_ASSET_FILES.items():
        for rel in files:
            file=asset(f'{name}/{rel}')
            if not file.is_file():raise FileNotFoundError(f'Run scripts/download_assets.py --scene rigid_elastic/passive_car_spring_return_ramp: {file}')
            sha=hashlib.sha256(file.read_bytes()).hexdigest()
            if sha!=registry[name]['files'][rel]['sha256']:raise RuntimeError('Asset differs from assets.json: '+str(file))
            actual[f'assets/{name}/{rel}']=sha
    return digest(actual)
