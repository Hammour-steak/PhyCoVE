"""Canonical locations of book_pillow_bedroom and verified inputs for the isolated worker kit.

Repository locations:
  assets/scenes/book_pillow_bedroom/        registered kit inputs (assets.json group scenes/book_pillow_bedroom)
  assets/scenes/book_pillow_bedroom/kit/    byte-frozen kit modules, files.json index, kit_layout.json
  assets/polyhaven/<id>/                    scanned room props and textures of the current look
  renders/book_pillow_bedroom/accepted/     accepted physics delivery: native caches and motion audits
                                            (scene_manifest.json native_delivery)
  renders/pcve_suites/pcve_book_pillow_bedroom_suite/
                                            current published videos, prompts and ground truth
                                            (scene_manifest.json canonical_suites)
  .runtime/book_pillow_bedroom/             restored worker kits and their job scratch

The worker kit is restored from the minimum-inputs tarball in the accepted delivery's inputs/.
It keeps its own internal repository layout; kit_layout.json names those directories, which are
places inside the restored kit, not in this repository.
"""
from pathlib import Path
import hashlib
import json
import os
import sys

from pcve_assets import asset

SCENE='book_pillow_bedroom'
CASE=Path(__file__).resolve().parent
REPO=CASE.parents[2]
ASSET_GROUP='scenes/'+SCENE
SUITE='pcve_'+SCENE+'_suite'
RUNTIME=REPO/'.runtime'/SCENE


def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda:stream.read(1<<20),b''):h.update(block)
    return h.hexdigest()


def manifest():
    return json.loads((CASE/'scene_manifest.json').read_text(encoding='utf-8'))


def in_checkout(target):
    """An absolute renders/... target of scene_manifest.json, resolved inside this checkout."""
    parts=Path(target).parts
    if 'renders' not in parts:
        return Path(target)
    return REPO.joinpath(*parts[len(parts)-parts[::-1].index('renders')-1:])


def canonical_suite():
    """The published-suite pointer of scene_manifest.json (suite and video hashes)."""
    return manifest()['canonical_suites'][SUITE]


def suite_dir():
    return in_checkout(canonical_suite()['target'])


def native_delivery():
    """Accepted physics delivery (native caches, motion audits, acceptance records)."""
    return in_checkout(manifest()['native_delivery']['target'])


def kit_files():
    return asset(ASSET_GROUP)/'kit'


def kit_dirs(kit):
    """Case-data and helper directories inside a restored worker kit."""
    layout=json.loads((kit_files()/'kit_layout.json').read_text(encoding='utf-8'))
    return kit/layout['case_data'],kit/layout['support']


def output_path(value):
    """A job output outside the code tree, the registered assets and the accepted deliveries."""
    path=value.expanduser().resolve()
    for protected in (REPO/'scripts',REPO/'assets',native_delivery(),suite_dir()):
        protected=protected.resolve()
        if path==protected or protected in path.parents:
            raise ValueError(f'Write job output outside {protected}')
    return path


def worker_only(role='simulate'):
    # The restored kit runtime is a Linux build (Python 3.10 + CUDA runtime); rendering needs Blender 4.3.2.
    if sys.platform!='linux':
        raise RuntimeError(f'{role} runs only on Linux')


def link_checked(source,dest,expected,root):
    if not dest.resolve().is_relative_to(root):
        raise ValueError('Input path escapes the restored kit')
    if not dest.exists():
        if sha(source)!=expected:
            raise RuntimeError(f'Input hash differs: {source}')
        dest.parent.mkdir(parents=True,exist_ok=True)
        try:
            os.link(source,dest)
        except FileExistsError:
            pass
    if sha(dest)!=expected:
        raise RuntimeError(f'Restored kit input hash differs: {dest}')


def prepare_worker(role='simulate'):
    worker_only(role)
    kit=Path(os.environ['BOOK_PILLOW_ROOT']).resolve(strict=True)
    if RUNTIME.resolve() not in kit.parents:
        raise ValueError(f'Restore the worker kit inside {RUNTIME}')
    data,_=kit_dirs(kit)
    kit_assets=data/'assets'
    index=json.loads((REPO/'assets.json').read_text(encoding='utf-8'))['assets']
    group=index[ASSET_GROUP]['files']
    for relative,record in group.items():
        if relative.startswith('kit/'):
            continue
        link_checked(asset(ASSET_GROUP)/relative,kit_assets/relative,record['sha256'],kit_assets.resolve())
    files=json.loads((kit_files()/'files.json').read_text(encoding='utf-8'))
    for relative,record in files.items():
        link_checked(kit_files()/record['name'],kit/relative,record['sha256'],kit)
    return kit
