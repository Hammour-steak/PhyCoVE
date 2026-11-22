#!/usr/bin/env python3
"""Verify a PhyCoVE publication snapshot using Python's standard library."""
import argparse
import collections
import concurrent.futures
import hashlib
import json
from pathlib import Path
import subprocess
import sys


def sha(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parent)
    parser.add_argument('--skip-blends', action='store_true', help='Validate a download that excludes blender/**')
    parser.add_argument('--decode', action='store_true', help='Fully decode every video with ffmpeg (optional)')
    args = parser.parse_args()
    root = args.root.resolve()

    def path_for(value):
        p = root / value
        assert not Path(value).is_absolute() and p.resolve().is_relative_to(root), value
        assert p.is_file(), value
        return p

    verified = 0
    for line in (root / 'SHA256SUMS').read_text().splitlines():
        digest, rel = line.split('  ', 1)
        if args.skip_blends and (rel.endswith('.blend') or rel.startswith('blender/')):
            continue
        assert sha(path_for(rel)) == digest, f'Hash mismatch: {rel}'
        verified += 1
    reference_layout = (root / 'benchmark_manifest.json').is_file()
    if reference_layout:
        benchmark = json.loads((root / 'benchmark_manifest.json').read_text())
        scenes = benchmark['scenes']
        def fields(p):
            return {f'prompt_{f}_{l}': p[f][l] for f in ('vague', 'quantitative') for l in ('zh', 'en')}
        sources = [{**r, 'id': r['global_id'], 'file_name': r['video'], **fields(r['prompts'])}
                   for r in benchmark['sources']]
        source_map = {r['global_id']: r for r in benchmark['sources']}
        edits = [{**r, 'id': r['global_id'], 'file_name': r['edited_video'],
                  'source_file_name': r['source_video'],
                  'source_video_sha256': source_map[r['scene'] + '/' + r['source_case_id']]['video_sha256'],
                  **fields(r['prompts'])} for r in benchmark['edits']]
        counts = benchmark['counts']
        info = {'source_count': counts['sources'], 'edit_count': counts['edits'],
                'scene_count': counts['scenes'], 'video_count': counts['sources'] + counts['edits']}
        assert not (root / 'thumbnails').exists()
        assert all('thumbnail' not in r for r in benchmark['sources'] + benchmark['edits'])
    else:
        sources = [json.loads(x) for x in (root / 'sources.jsonl').read_text().splitlines() if x.strip()]
        edits = [json.loads(x) for x in (root / 'metadata.jsonl').read_text().splitlines() if x.strip()]
        scenes = [json.loads(x) for x in (root / 'scenes.jsonl').read_text().splitlines() if x.strip()]
        info = json.loads((root / 'dataset_info.json').read_text())
    ids = set()
    source_by_id = {r['id']: r for r in sources}
    video_paths = set()
    gt_count = 0
    for row in sources + edits:
        assert row['id'] not in ids, row['id']
        ids.add(row['id'])
        video_paths.add(row['file_name'])
        assert sha(path_for(row['file_name'])) == row['video_sha256'], row['id']
        for flavor in ('vague', 'quantitative'):
            for language in ('zh', 'en'):
                value = row[f'prompt_{flavor}_{language}']
                assert isinstance(value, str) and value.strip(), row['id']
        if row.get('blend_file') and not args.skip_blends:
            path_for(row['blend_file'])
        if reference_layout:
            case = path_for(row['file_name']).parent
            pd = json.loads((case / 'prompts.json').read_text())
            assert pd['prompts'] == row['prompts'], row['id']
            gt = json.loads(path_for(row['ground_truth']).read_text())
            assert gt['scene'] == row['scene'] and gt['case_id'] == row['case_id']
            assert len(gt['frames']) == 96
            gt_count += 1
    for row in edits:
        source = source_by_id[row['scene'] + '/' + row['source_case_id']]
        assert row['source_file_name'] == source['file_name'], row['id']
        assert row['source_video_sha256'] == source['video_sha256'], row['id']
        assert row['edit_dsl'].strip(), row['id']
        if row.get('source_blend_file') and not args.skip_blends:
            path_for(row['source_blend_file'])
    assert len(sources) == info['source_count'] == info['scene_count'] == len(scenes)
    assert len(edits) == info['edit_count']
    assert len(video_paths) == info['video_count']
    # real/ holds the PhyCoVE-Real subset, which has its own manifest and is checked at the end.
    subset = root / 'real'
    assert video_paths == {str(p.relative_to(root)) for p in root.rglob('*.mp4')
                           if not p.is_relative_to(subset)}
    if reference_layout:
        expected_ids = {r['id'] for r in edits}
        all_ids = (root / 'splits/all.txt').read_text().splitlines()
        assert len(all_ids) == len(expected_ids) and set(all_ids) == expected_ids
        for section in ('by_property', 'by_timing', 'by_kind', 'by_category'):
            selected = []
            for name, count in counts[section].items():
                ids_here = (root / 'splits' / section / (name + '.txt')).read_text().splitlines()
                assert len(ids_here) == count and len(ids_here) == len(set(ids_here))
                assert set(ids_here) <= expected_ids
                selected.extend(ids_here)
            assert len(selected) == len(expected_ids) and set(selected) == expected_ids
        hf_rows = [json.loads(x) for x in (root / 'metadata.jsonl').read_text().splitlines() if x.strip()]
        assert len(hf_rows) == len(edits)
        edit_map = {e['id']: e for e in edits}
        for row in hf_rows:
            e = edit_map[row['id']]
            assert row['file_name'] == e['file_name'] and row['source_file_name'] == e['source_file_name']
            for key in fields(e['prompts']):
                assert row[key] == e[key], row['id']
    forbidden = []
    for p in root.rglob('*'):
        assert not p.is_symlink(), f'Nonportable link: {p}'
        if p.is_file() and p.suffix.lower() in ('.abc', '.npz', '.npy', '.uni', '.exr', '.png', '.jpg', '.jpeg', '.blend1', '.blend2', '.log', '.bak', '.tmp'):
            forbidden.append(str(p.relative_to(root)))
    assert not forbidden, forbidden
    decoded = 0
    if args.decode:
        def decode(rel):
            p = path_for(rel)
            result = subprocess.run(['ffmpeg', '-v', 'error', '-xerror', '-threads', '1', '-i', str(p),
                '-map', '0:v:0', '-f', 'null', '-'], text=True, capture_output=True)
            assert result.returncode == 0, f'{rel}: {result.stderr[:500]}'
            return rel
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for _ in pool.map(decode, sorted(video_paths)):
                decoded += 1
                if decoded % 100 == 0:
                    print(f'decoded {decoded}/{len(video_paths)}', flush=True)
    summary = {'passed': True, 'scene_count': len(scenes), 'source_count': len(sources),
               'edit_count': len(edits), 'video_count': len(video_paths), 'checksums_verified': verified,
               'videos_fully_decoded': decoded, 'all_prompts_complete': True,
               'ground_truth_cases_verified': gt_count,
               'reference_manifest_layout': reference_layout,
               'cache_files_found': 0, 'all_paths_portable': True}
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    if (subset / 'benchmark_manifest.json').is_file():
        print('PhyCoVE-Real subset (real/):', flush=True)
        subprocess.run([sys.executable, __file__, '--root', str(subset)]
                       + (['--decode'] if args.decode else []), check=True)


if __name__ == '__main__':
    main()
