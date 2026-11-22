"""Copy independently solved cases for an appearance-only revision, auditing every byte."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import hashlib
import json
from pathlib import Path
import shutil
from bridge_physics import CASES, baseline, config_for, differences, digest, save_json


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


# Render keys that define the solved sampling (frame times). Samples, denoiser and motion blur only
# change the image, so an appearance revision may change them and still reuse the solved caches.
TIMING_KEYS = ('width', 'height', 'fps', 'frames', 'duration_s')


def timing(render):
    return {k: render[k] for k in TIMING_KEYS}


def prepare(reference, out):
    reference, out = Path(reference).resolve(), Path(out).resolve()
    if reference == out:
        raise RuntimeError('Appearance revision requires a new output root')
    old_source = json.loads((reference / 'source/simulation/config.json').read_text())
    source = baseline()
    for key in ['physics', 'simulation_quality']:
        if source[key] != old_source[key]:
            raise RuntimeError('Only appearance changes may reuse a solved suite: ' + key)
    if timing(source['render']) != timing(old_source['render']):
        raise RuntimeError('Only appearance changes may reuse a solved suite: render timing')
    records = {}
    for case in CASES:
        src, dst = reference / case / 'simulation', out / case / 'simulation'
        if dst.exists():
            raise FileExistsError(dst)
        old = json.loads((src / 'config.json').read_text())
        cfg = config_for(case, source)
        assert all(old[k] == cfg[k] for k in ['physics', 'simulation_quality'])
        assert timing(old['render']) == timing(cfg['render'])
        original_hashes = {p.name: sha(p) for p in src.iterdir() if p.is_file()}
        shutil.copytree(src, dst)
        save_json(dst / 'config.json', cfg)
        save_json(out / case / 'requested_config.json', cfg)
        edit = json.loads((dst / 'edit_manifest.json').read_text())
        edit.update(before=source, after=cfg, differences=differences(source, cfg),
                    unchanged_appearance_signature=digest(source['appearance']))
        save_json(dst / 'edit_manifest.json', edit)
        report = json.loads((dst / 'simulation_report.json').read_text())
        report.update(cache=str(dst / 'simulation.npz'), reused_physics_cache_from=str(src),
                      reused_physics_cache_sha256=original_hashes['simulation.npz'])
        save_json(dst / 'simulation_report.json', report)
        protected = {p.name: sha(p) for p in src.iterdir() if p.is_file()
                     and p.name not in ['config.json', 'edit_manifest.json', 'simulation_report.json']}
        assert protected == {name: sha(dst / name) for name in protected}
        assert original_hashes == {p.name: sha(p) for p in src.iterdir() if p.is_file()}
        assert dst.stat().st_ino != src.stat().st_ino
        assert (dst / 'simulation.npz').stat().st_ino != (src / 'simulation.npz').stat().st_ino
        records[case] = {'reference': str(src), 'copy': str(dst),
                         'sha256': sha(dst / 'simulation.npz'),
                         'protected_files_sha256': {k: v for k, v in protected.items() if not k.endswith('.json')},
                         'all_protected_files_identical': True, 'reference_files_unchanged': True}
    for name in ['half_dt', 'finer_grid']:
        src = reference / 'validation' / name / 'simulation'
        if src.exists():
            shutil.copytree(src, out / 'validation' / name / 'simulation')
    save_json(out / 'physics_cache_reuse.json', {'reference': str(reference), 'cases': records,
              'physics_unchanged': True, 'solver_settings_unchanged': True,
              'independent_copies': True, 'all_trajectories_bit_identical': True})
    save_json(out / 'common_appearance_revision.json', {'before': old_source, 'after': source,
              'differences': differences(old_source, source), 'reference': str(reference),
              'scope': 'Common camera, geometry, material and light revision; all five solved caches frozen',
              'protected': ['physics', 'simulation_quality', 'render timing ' + '/'.join(TIMING_KEYS),
                            'raw rigid and flex states']})

