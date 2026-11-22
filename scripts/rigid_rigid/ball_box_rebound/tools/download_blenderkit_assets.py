"""Download selected free assets through the provider's public asset API."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import urllib.parse
import urllib.request
import uuid

parser = argparse.ArgumentParser()
parser.add_argument('--base-id', required=True)
parser.add_argument('--name', required=True)
parser.add_argument('--asset-dir', type=Path, required=True)
parser.add_argument('--file-type', default='blend')
args = parser.parse_args()
headers = {'User-Agent': 'PhyCoVE selected asset preview/1.0'}
url = 'https://www.blenderkit.com/api/v1/search/?' + urllib.parse.urlencode({'query': 'asset_base_id:' + args.base_id, 'dict_parameters': 1})
with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=45) as response:
    metadata = next(a for a in json.load(response)['results'] if a['assetBaseId'] == args.base_id)
if not metadata['isFree'] or metadata['license'] not in ('royalty_free', 'cc_zero'):
    raise ValueError('Selected asset must be free and eligible for project use')
selected = next(f for f in metadata['files'] if f['fileType'] == args.file_type)
args.asset_dir.mkdir(parents=True, exist_ok=True)
destination = args.asset_dir / (args.name + ('.glb' if args.file_type == 'gltf' else '.blend'))
if not destination.exists() or destination.stat().st_size != selected['fileUploadSize']:
    request = urllib.request.Request(selected['downloadUrl'] + '?scene_uuid=' + str(uuid.uuid4()), headers=headers)
    with urllib.request.urlopen(request, timeout=45) as response:
        signed = json.load(response)
    errors = []
    for link in signed.get('filePaths', [{'url': signed['filePath']}]):
        try:
            request = urllib.request.Request(link['url'], headers=headers)
            with urllib.request.urlopen(request, timeout=120) as response, destination.with_suffix('.part').open('wb') as stream:
                shutil.copyfileobj(response, stream)
            if destination.with_suffix('.part').stat().st_size != selected['fileUploadSize']:
                raise ValueError('Downloaded size mismatch')
            destination.with_suffix('.part').replace(destination)
            break
        except Exception as error:
            errors.append(type(error).__name__)
    else:
        raise RuntimeError(errors)
manifest = {'name': metadata['displayName'], 'author': metadata['author']['fullName'].strip(),
    'source': 'https://www.blenderkit.com/asset-gallery-detail/' + args.base_id + '/',
    'asset_base_id': args.base_id, 'asset_version_id': metadata['id'], 'license': metadata['license'],
    'is_free': True, 'source_blender_version': metadata['sourceAppVersion'],
    'source_file': destination.name, 'bytes': destination.stat().st_size,
    'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
    'license_reference': 'https://www.blenderkit.com/docs/licenses/licensing-faq/',
    'redistribution': 'CC0 asset may be redistributed.' if metadata['license'] == 'cc_zero' else 'Project renders and embedded project only; no standalone asset redistribution.'}
(args.asset_dir / 'asset_manifest.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest))
