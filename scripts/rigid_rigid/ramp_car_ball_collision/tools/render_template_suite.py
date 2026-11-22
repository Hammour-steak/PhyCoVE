"""Render a suite prepared by tools/prepare_template_suite.py; any frame range, any backend.

Several processes may render the same suite at once (different cases or frame ranges).  Frames are
written atomically.  A frame is copied instead of rendered only when another case of the same suite
has the identical packed template, frame index and root matrices at shutter start, centre and end
(render_state_signatures.json); nothing approximate is reused.  Encoding and
checks are done afterwards by tools/review_template_suite.py.

blender -b --factory-startup -t 48 --python-exit-code 1 \
  --python scripts/rigid_rigid/ramp_car_ball_collision/tools/render_template_suite.py -- \
  --out-root renders/ramp_car_ball_collision/template_suite --cases source --backend CPU --threads 48
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import socket
import sys
import time
import bpy

sys.path.insert(0, str(Path(__file__).resolve().parent))
from render_diecast import setup, state_signature, dump, sha
from object_presence import apply_frame_presence


def exact_reuse(out, case_id, frame, key, template_hash):
    """Return an already rendered PNG of another case with the identical render state, if any."""
    for other in sorted((out / 'cases').iterdir()):
        if other.name == case_id:
            continue
        signatures = other / 'render_state_signatures.json'
        png = other / 'frames' / ('frame_%04d.png' % frame)
        if not (signatures.is_file() and png.is_file()):
            continue
        data = json.loads(signatures.read_text())
        if data['template_sha256'] == template_hash and data['frame_keys'].get(str(frame)) == key:
            return other.name, png
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--out-root', type=Path, required=True)
    parser.add_argument('--cases', nargs='+', required=True)
    parser.add_argument('--backend', choices=['CPU', 'OPTIX', 'CUDA', 'METAL'], default='CPU')
    parser.add_argument('--threads', type=int, default=48)
    parser.add_argument('--frame-start', type=int, default=1)
    parser.add_argument('--frame-end', type=int, default=96)
    parser.add_argument('--tag', default=None, help='Name of this process in render_execution_<tag>.json')
    parser.add_argument('--no-reuse', action='store_true', help='Render every frame; use when this case runs on a different device than the other cases')
    args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
    out = args.out_root.resolve()
    template = out / 'source_template.blend'
    manifest = json.loads((out / 'suite_manifest.json').read_text())
    template_hash = sha(template)
    assert template_hash == manifest['source_template_sha256'], 'Template differs from the prepared suite'
    tag = args.tag or '%s_%s_%d_%d' % (socket.gethostname(), args.backend.lower(), args.frame_start, args.frame_end)
    for case_id in args.cases:
        folder = out / 'cases' / case_id
        frames = folder / 'frames'
        frames.mkdir(exist_ok=True)
        scene, roots, backend = setup(folder, template, args.backend, args.threads)
        configuration = json.loads((folder / 'settings.json').read_text())
        prepared = json.loads((folder / 'render_state_signatures.json').read_text())
        keys = {str(f): state_signature(scene, roots, f, configuration) for f in range(1, 97)}
        assert prepared == {'template_sha256': template_hash, 'frame_keys': keys}, 'Scene state differs from preparation'
        record = {'case_id': case_id, 'tag': tag, 'host': socket.gethostname(), 'backend': backend, 'threads': args.threads,
                  'cuda_visible_devices': os.environ.get('CUDA_VISIBLE_DEVICES'), 'samples': scene.cycles.samples,
                  'persistent_data': scene.render.use_persistent_data, 'motion_blur_shutter': scene.render.motion_blur_shutter,
                  'requested_frames': [args.frame_start, args.frame_end], 'template_sha256': template_hash,
                  'status': 'rendering', 'frame_seconds': {}, 'reused_frames': [], 'skipped_existing': []}
        report = folder / ('render_execution_%s.json' % tag)
        dump(report, record)
        for frame in range(args.frame_start, args.frame_end + 1):
            path = frames / ('frame_%04d.png' % frame)
            key = keys[str(frame)]
            apply_frame_presence(roots, configuration, frame)
            scene.frame_set(frame)
            bpy.context.view_layer.update()
            if path.exists():
                record['skipped_existing'].append(frame)
                continue
            match = None if args.no_reuse else exact_reuse(out, case_id, frame, key, template_hash)
            if match:
                temporary = frames / ('.reuse_%s_frame_%04d.png' % (tag, frame))
                shutil.copy2(match[1], temporary)
                os.replace(temporary, path)
                record['reused_frames'].append({'frame': frame, 'from_case': match[0], 'state_sha256': key, 'png_sha256': sha(path)})
            else:
                temporary = frames / ('.partial_%s_frame_%04d.png' % (tag, frame))
                scene.render.filepath = str(temporary)
                start = time.monotonic()
                bpy.ops.render.render(write_still=True)
                os.replace(temporary, path)
                record['frame_seconds'][str(frame)] = round(time.monotonic() - start, 2)
            dump(report, record)
            print('FRAME', case_id, frame, record['frame_seconds'].get(str(frame), 'reused'), flush=True)
        record['status'] = 'requested_frames_complete'
        dump(report, record)
        print('CASE_DONE', case_id, flush=True)
    assert sha(template) == template_hash


if __name__ == '__main__':
    main()
