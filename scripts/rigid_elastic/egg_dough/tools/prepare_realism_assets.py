"""Reproduce pinned CC0 wood maps for the baking-bench wood (appearance/realism_look.py)."""
from pathlib import Path
import argparse,hashlib,json,urllib.request
MANIFEST = {'provider': 'Poly Haven', 'asset': 'wood_table_worn', 'source_page': 'https://polyhaven.com/a/wood_table_worn', 'license': 'CC0', 'license_url': 'https://polyhaven.com/license', 'authors': {'Dimitrios Savva': 'Photography', 'Rico Cilliers': 'Processing'}, 'physical_dimensions_mm': [549.9999523162842, 550.0000715255737], 'provider_files_hash': '92fde8d58df92dd57a0a2854a6a6aeb79317b750', 'assets': [{'channel': 'Diffuse', 'path': 'wood_table_worn/wood_table_worn_diff_4k.jpg', 'source_url': 'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/4k/wood_table_worn/wood_table_worn_diff_4k.jpg', 'sha256': '1261fb3ab3fad39259528ea3db8b401fbfa2e09fc833e0913ca489938985cb9d', 'provider_md5': '1296890ff5cfaea5ad0104e53293dc1e', 'bytes': 12097188}, {'channel': 'Rough', 'path': 'wood_table_worn/wood_table_worn_rough_4k.jpg', 'source_url': 'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/4k/wood_table_worn/wood_table_worn_rough_4k.jpg', 'sha256': '4ce6c1d30e67baf2dbace9a613b7f04ed9bce2ab5621134fbc5c001cd60b4bca', 'provider_md5': '25bc0ddd7e7e12202b00fde9e1c5635b', 'bytes': 11785007}, {'channel': 'Displacement', 'path': 'wood_table_worn/wood_table_worn_disp_4k.jpg', 'source_url': 'https://dl.polyhaven.org/file/ph-assets/Textures/jpg/4k/wood_table_worn/wood_table_worn_disp_4k.jpg', 'sha256': '5d2c3cb6da0914cf444f269e9c92083a87a2f3cb8e39cd1e28f9093c3182ac45', 'provider_md5': 'b939e2824b313c8d9e05b4207675290b', 'bytes': 5980418}]}
def main():
    p=argparse.ArgumentParser();p.add_argument('--out-dir',type=Path,default=Path(__file__).parents[1]/'assets/worktop_textures');a=p.parse_args()
    a.out_dir.mkdir(parents=True,exist_ok=True)
    for item in MANIFEST['assets']:
        dest=a.out_dir/item['path'];dest.parent.mkdir(parents=True,exist_ok=True)
        if dest.is_file():
            payload=dest.read_bytes()
        else:
            req=urllib.request.Request(item['source_url'],headers={'User-Agent':'Mozilla/5.0 PhyCoVE reproducible asset download'})
            with urllib.request.urlopen(req,timeout=90) as response:payload=response.read()
        if hashlib.sha256(payload).hexdigest()!=item['sha256']:raise RuntimeError('Pinned checksum differs: '+item['path'])
        if not dest.exists():dest.write_bytes(payload)
    (a.out_dir/'asset_manifest.json').write_text(json.dumps(MANIFEST,indent=2)+'\n')
    print('Verified',len(MANIFEST['assets']),'CC0 wood maps')
if __name__=='__main__':main()
