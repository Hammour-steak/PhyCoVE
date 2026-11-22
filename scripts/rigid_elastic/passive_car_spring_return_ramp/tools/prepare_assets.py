"""Prepare CC0 scanned assets and validate the retained original book artwork."""
import hashlib,json,shutil,urllib.request,zipfile
from pathlib import Path
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset

HERE=Path(__file__).resolve().parents[1]
ROOT=HERE.parents[2]
ASSETS=scene_asset(HERE, 'assets/realism')

def main():
    ASSETS.mkdir(parents=True,exist_ok=True)
    records=[]
    def acquire(asset,name,url,author,source,width=None,reuse=None,height=None,license_ref="https://polyhaven.com/license"):
        target=ASSETS/asset/name;target.parent.mkdir(parents=True,exist_ok=True)
        if not target.exists():
            if reuse and reuse.is_file():shutil.copy2(reuse,target)
            else:
                req=urllib.request.Request(url,headers={'User-Agent':'PhyCoVE research asset preparation'})
                with urllib.request.urlopen(req,timeout=90) as response,target.with_suffix(target.suffix+'.part').open('wb') as f:shutil.copyfileobj(response,f)
                target.with_suffix(target.suffix+'.part').replace(target)
        rec={'asset':asset,'path':str(Path('assets')/target.relative_to(ASSETS.parent)),'source_page':source,'url':url,'author':author,
             'license':'CC0','license_reference':license_ref,'bytes':target.stat().st_size,
             'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        if width:rec['real_world_width_m']=width
        if height:rec['real_world_height_m']=height
        records.append(rec);print(asset,name,rec['bytes'],flush=True)
    for channel in ['diff','rough','nor_gl']:
        asset='wood_floor';name=f'{asset}_{channel}_2k.jpg'
        acquire(asset,name,f'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/{asset}/{name}',
                'Dimitrios Savva','https://polyhaven.com/a/wood_floor',1.7)
        asset='white_oak_veneer';name=f'{asset}_{channel}_4k.jpg'
        acquire(asset,name,f'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/4k/{asset}/{name}',
                'Jenelle van Heerden','https://polyhaven.com/a/white_oak_veneer',.5,
                ROOT/'assets/rigid_fluid/tilted_cup_environment'/asset/name)
        asset='white_maple_veneer';name=f'{asset}_{channel}_2k.jpg'
        acquire(asset,name,f'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/{asset}/{name}',
                'Jenelle van Heerden','https://polyhaven.com/a/white_maple_veneer',1.0,
                scene_asset(ROOT/'scripts/rigid_elastic/toy_car_silicone_bridge','assets/pbr')/asset/name)
        asset='cotton_jersey';name=f'{asset}_{channel}_2k.jpg'
        acquire(asset,name,f'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/2k/{asset}/{name}',
                'Rico Cilliers (processing), colormass (photography)','https://polyhaven.com/a/cotton_jersey',height=.3)
    # Real scanned fleece for the rabbit, with authoritative file and info metadata.
    plush='curly_teddy_natural';author='Rico Cilliers (processing), colormass (photography)';source='https://polyhaven.com/a/'+plush
    acquire(plush,'official_files.json','https://api.polyhaven.com/files/'+plush,author,source,.3)
    acquire(plush,'official_info.json','https://api.polyhaven.com/info/'+plush,author,source,.3)
    official=json.loads((ASSETS/plush/'official_files.json').read_text())
    for key,channel in [('Diffuse','diff'),('Rough','rough'),('nor_gl','nor_gl')]:
        entry=official[key]['2k']['jpg'];name=f'{plush}_{channel}_2k.jpg'
        acquire(plush,name,entry['url'],author,source,.3)
        target=ASSETS/plush/name
        assert hashlib.md5(target.read_bytes()).hexdigest()==entry['md5'] and target.stat().st_size==entry['size']
        records[-1]['official_md5']=entry['md5']
    acquire('residential_garden','residential_garden_1k.hdr',
        'https://dl.polyhaven.org/file/ph-assets/HDRIs/hdr/1k/residential_garden_1k.hdr',
        'Greg Zaal','https://polyhaven.com/a/residential_garden',
        reuse=ROOT/'assets/polyhaven/residential_garden/residential_garden_1k.hdr')
    # CC0 source mesh and the exact four dependencies listed by the official API.
    acquire('rubber_duck_toy','rubber_duck_toy_2k.blend','https://dl.polyhaven.org/file/ph-assets/Models/blend/2k/rubber_duck_toy/rubber_duck_toy_2k.blend','Plat251','https://polyhaven.com/a/rubber_duck_toy',.3)
    acquire('rubber_duck_toy','textures/rubber_duck_toy_metal_2k.exr','https://dl.polyhaven.org/file/ph-assets/Models/exr/2k/rubber_duck_toy/rubber_duck_toy_metal_2k.exr','Plat251','https://polyhaven.com/a/rubber_duck_toy',.3)
    acquire('rubber_duck_toy','textures/rubber_duck_toy_rough_2k.exr','https://dl.polyhaven.org/file/ph-assets/Models/exr/2k/rubber_duck_toy/rubber_duck_toy_rough_2k.exr','Plat251','https://polyhaven.com/a/rubber_duck_toy',.3)
    acquire('rubber_duck_toy','textures/rubber_duck_toy_nor_gl_2k.exr','https://dl.polyhaven.org/file/ph-assets/Models/exr/2k/rubber_duck_toy/rubber_duck_toy_nor_gl_2k.exr','Plat251','https://polyhaven.com/a/rubber_duck_toy',.3)
    acquire('rubber_duck_toy','textures/rubber_duck_toy_diff_2k.jpg','https://dl.polyhaven.org/file/ph-assets/Models/jpg/2k/rubber_duck_toy/rubber_duck_toy_diff_2k.jpg','Plat251','https://polyhaven.com/a/rubber_duck_toy',.3)
    source='https://ambientcg.com/view?id=Fingerprints001';license_ref='https://docs.ambientcg.com/license/'
    url='https://ambientcg.com/get?file=Fingerprints001_1K-JPG.zip'
    acquire('fingerprints001','Fingerprints001_1K-JPG.zip',url,'ambientCG (individual author not specified on source page)',source,license_ref=license_ref)
    archive=ASSETS/'fingerprints001/Fingerprints001_1K-JPG.zip';member='Fingerprints001_1K-JPG_Roughness.jpg';target=archive.parent/member
    with zipfile.ZipFile(archive) as z:
        data=z.read(member)
    if not target.exists():target.write_bytes(data)
    assert target.read_bytes()==data
    records.append({'asset':'fingerprints001','path':str(Path('assets')/target.relative_to(ASSETS.parent)),'source_page':source,'url':url,
        'source_archive':str(Path('assets')/archive.relative_to(ASSETS.parent)),'archive_member':member,'author':'ambientCG (individual author not specified on source page)',
        'license':'CC0','license_reference':license_ref,'bytes':target.stat().st_size,'sha256':hashlib.sha256(data).hexdigest(),
        'mapping_width_m':.18,'scale_note':'Artistic 0.18m mapping of procedural source, not a calibrated physical scan; affects roughness only'})
    # Generation is stochastic. Exact reproduction restores these retained files;
    # the saved prompt documents creation, rather than promising identical regeneration.
    generated={
        'woodland_cover.png':'7eb74bda01d7d87b4088f662d9019239e45373773500a70f540270bdd8184006',
        'woodland_cover.prompt.txt':'c7cede0b14825f38dd229ecfe6864ff598ea9a8f88b856f089da91c1466c2d08'}
    for name,expected in generated.items():
        target=ASSETS/'generated'/name
        if not target.is_file():raise FileNotFoundError('Restore retained original asset from delivery code/assets/realism/generated/: '+name)
        actual=hashlib.sha256(target.read_bytes()).hexdigest()
        if actual!=expected:raise RuntimeError('Retained original asset differs from reviewed version: '+name)
        records.append({'asset':'original_woodland_book','path':str(Path('assets')/target.relative_to(ASSETS.parent)),
            'source':'Original artwork generated for this scene with built-in image_gen, 2026-10-29',
            'author':'Generated for PhyCoVE scene','license':'Original AI-generated project artwork; not a CC0 scanned asset',
            'bytes':target.stat().st_size,'sha256':actual,
            'mapping_width_m':.153,'mapping_height_m':.179,
            'reproduction':'Restore exact retained PNG and prompt from delivery assets; prompt regeneration is not bit deterministic',
            'prompt_file':'assets/realism/generated/woodland_cover.prompt.txt'})
    books=json.loads((HERE/'book_assets.json').read_text())
    for row in books['downloads']:
        acquire('decorative_books',row['path'],row['url'],books['model_author'],books['source'])
        assert records[-1]['sha256']==row['sha256'] and records[-1]['bytes']==row['size'],row['path']
        records[-1]['official_md5']=row['md5']
        if 'image_stem' in row:records[-1]['source_image_stem']=row['image_stem']
        if row.get('image_stem') in books['cover_credits']:records[-1]['cover_credit']=books['cover_credits'][row['image_stem']]
    (ASSETS/'manifest.json').write_text(json.dumps({'schema_version':1,'source':'Poly Haven and ambientCG CC0 assets, plus original generated watercolor book print/prompt and selected CC0 decorative book meshes/maps',
        'downloads':records,'mapping':'Physical dimensions from source pages: floor 1.7 m wide, oak veneer 0.5 m wide, maple veneer 1.0 m wide, cotton 0.3 m tall with image aspect correction. No displacement of physical contact planes.',
        'reproduction':'python3 scripts/rigid_elastic/passive_car_spring_return_ramp/tools/prepare_assets.py'},indent=2)+'\n')

if __name__=='__main__':main()
