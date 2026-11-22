"""Reproduce the pinned CC0 wood, textile, daylight and glTF assets, checking every hash."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import urllib.request
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset

PINNED = (Path(__file__).parents[1] / 'asset_sources.json')
ASSETS = tuple(d['id'] for d in json.loads(PINNED.read_text())['assets'])

def get(url):
    request = urllib.request.Request(url, headers={'User-Agent': 'PCVE-scene-material-reproduction/1.0'})
    with urllib.request.urlopen(request, timeout=90) as response:
        return response.read()

def fetch(asset, root):
    folder = root / asset
    folder.mkdir(parents=True, exist_ok=True)
    pinned = next(d for d in json.loads(PINNED.read_text())['assets'] if d['id'] == asset)
    info = pinned['api_info']
    files = {d['channel']: {'2k': {d.get('format', 'jpg'): {'url': d['url'], 'md5': d['md5'], 'size': d['bytes']}}}
             for d in pinned['provenance']['files']}
    (folder / 'api_info.json').write_text(json.dumps(info, indent=2) + '\n')
    (folder / 'api_files.json').write_text(json.dumps(files, indent=2) + '\n')
    records = []
    for pinned_file in pinned['provenance']['files']:
        channel = pinned_file['channel']
        record = files[channel]['2k'][pinned_file.get('format', 'jpg')]
        target = folder / pinned_file.get('relative_path', record['url'].split('/')[-1])
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or hashlib.md5(target.read_bytes()).hexdigest() != record['md5']:
            target.write_bytes(get(record['url']))
        raw = target.read_bytes()
        assert hashlib.md5(raw).hexdigest() == record['md5'], target
        records.append({'channel': channel, 'name': target.name, 'url': record['url'],
                        'bytes': len(raw), 'md5': record['md5'],
                        'sha256': hashlib.sha256(raw).hexdigest(),
                        'relative_path': str(target.relative_to(folder)),
                        'format': pinned_file.get('format', 'jpg')})
    provenance = {'id': asset, 'provider': 'Poly Haven', 'authors': info['authors'],
                  'source': 'https://polyhaven.com/a/' + asset,
                  'license': 'CC0-1.0', 'license_url': 'https://polyhaven.com/license',
                  'files_hash': info['files_hash'], 'resolution': '2k',
                  'dimensions_mm': info.get('dimensions'),
                  'reproduce': 'python3 fetch_assets.py --assets-dir ./assets/pbr',
                  'files': records}
    (folder / 'provenance.json').write_text(json.dumps(provenance, indent=2) + '\n')
    return provenance

def fetch_external(root):
    records=[]
    for entry in json.loads(PINNED.read_text()).get('external_assets',[]):
        folder=root.parent/'external'/entry['id'];folder.mkdir(parents=True,exist_ok=True)
        for file in entry['files']:
            target=folder/file['relative_path'];target.parent.mkdir(parents=True,exist_ok=True)
            if not target.exists() or hashlib.sha256(target.read_bytes()).hexdigest()!=file['sha256']:
                target.write_bytes(get(file['url']))
            assert hashlib.sha256(target.read_bytes()).hexdigest()==file['sha256'],target
        provenance={k:v for k,v in entry.items() if k!='id'}
        (folder/'provenance.json').write_text(json.dumps(provenance,indent=2)+'\n')
        records.append({'id':entry['id'],'source_commit':entry['git_commit'],'files':len(entry['files'])})
    return records

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--assets-dir', type=Path, default=scene_asset(Path(__file__).parents[1], 'assets/pbr'))
    a = p.parse_args()
    a.assets_dir.mkdir(parents=True, exist_ok=True)
    with ThreadPoolExecutor(max_workers=2) as pool:
        result = list(pool.map(lambda asset: fetch(asset, a.assets_dir), ASSETS))
    (a.assets_dir / 'provenance.json').write_text(json.dumps(result, indent=2) + '\n')
    extra=fetch_external(a.assets_dir)
    print(json.dumps({'downloaded': ASSETS,'external':extra,'directory': str(a.assets_dir)}, indent=2))
