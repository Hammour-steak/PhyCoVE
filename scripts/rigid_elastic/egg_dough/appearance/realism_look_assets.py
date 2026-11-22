"""Scanned CC0 maps read by realism_look.py. No bpy import, so render_*.py can hash them."""
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).resolve().parents[3]))
from pcve_assets import asset, scene_asset

SHARED=('polyhaven/macro_flour/macro_flour_diff_2k.jpg','polyhaven/macro_flour/macro_flour_disp_2k.jpg',
    'polyhaven/macro_flour/macro_flour_rough_2k.jpg','polyhaven/beige_wall_001/beige_wall_001_diff_4k.jpg',
    'polyhaven/beige_wall_001/beige_wall_001_rough_4k.jpg','polyhaven/rough_linen/rough_linen_diff_2k.jpg',
    'polyhaven/rough_linen/rough_linen_disp_2k.exr','polyhaven/rough_linen/rough_linen_rough_2k.jpg',
    'polyhaven/residential_garden/residential_garden_4k.hdr',
    'ambientcg/SurfaceImperfections018/SurfaceImperfections018_SQ_Roughness.jpg')
# Already registered under assets/scenes/<scene>/ for both dough scenes.
SCENE_OWN=('look_assets/white_maple_veneer/white_maple_veneer_diff_4k.jpg',
    'look_assets/white_maple_veneer/white_maple_veneer_rough_4k.jpg')

def files(scene_dir):
    """Registry name -> absolute path of every map the look reads."""
    out={name:asset(name) for name in SHARED}
    out.update({f'scenes/{Path(scene_dir).name}/{name}':scene_asset(scene_dir,'assets/'+name) for name in SCENE_OWN})
    return out
