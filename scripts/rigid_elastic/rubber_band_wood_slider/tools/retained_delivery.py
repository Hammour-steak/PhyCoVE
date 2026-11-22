"""Verify the accepted increment: edit policy, native states and the videos it was delivered with.

The increment (assets/scenes/rubber_band_wood_slider/native/accepted_increment.zip, registered in assets.json)
carries the native states the current suite replays, and the six videos it was delivered with
(cases/<case>/video.mp4).
"""
import ast
import hashlib
import io
import json
import struct
import sys
import tempfile
import zipfile
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(CASE_DIR), str(CASE_DIR.parents[1])]
from scene_paths import INCREMENT, INCREMENT_NAME, PREFIX  # noqa: E402
from pcve_media_contract import require_times, require_video  # noqa: E402
from pcve_edit_policy import audit_suite_manifest  # noqa: E402
from edit_vocab import VOCAB  # noqa: E402


def load_times(payload, member='times'):
    with zipfile.ZipFile(io.BytesIO(payload)) as z:
        raw = z.read(member + '.npy')
    if raw[:8] != b'\x93NUMPY\x01\x00':
        raise ValueError('Unsupported native sample clock')
    size, = struct.unpack_from('<H', raw, 8)
    header = ast.literal_eval(raw[10:10 + size].decode('latin1').strip())
    if header['descr'] not in {'<f8', '<f4'} or len(header['shape']) != 1:
        raise ValueError('Expected a 1D floating-point clock')
    code = 'd' if header['descr'] == '<f8' else 'f'
    return struct.unpack(f"<{header['shape'][0]}{code}", raw[10 + size:])


def verify(cases):
    result = []
    with zipfile.ZipFile(INCREMENT) as z, tempfile.TemporaryDirectory() as tmp:
        manifest = json.loads(z.read(PREFIX + 'suite_manifest.json'))
        if not audit_suite_manifest(manifest, VOCAB)['all_edits_compliant']:
            raise ValueError('Strict edit policy failed')
        for case in cases:
            prefix = PREFIX + f'cases/{case}/'
            encoded = json.loads(z.read(prefix + 'encoding_receipt.json'))
            provenance = json.loads(z.read(prefix + 'render_provenance.json'))
            state = z.read(prefix + 'simulation.npz')
            state_hash = hashlib.sha256(state).hexdigest()
            if state_hash != provenance['simulation_cache_sha256']:
                raise ValueError(f'Native render input changed: {case}')
            if not encoded['native_capture_times_checked'] or encoded['frames_checked'] != 96 or encoded['physical_time_scale'] != 1:
                raise ValueError(f'Invalid original capture timing: {case}')
            data = z.read(prefix + 'video.mp4')
            if hashlib.sha256(data).hexdigest() != encoded['video_sha256']:
                raise ValueError(f'Video checksum mismatch: {case}')
            video = Path(tmp) / f'{case}.mp4'
            video.write_bytes(data)
            times = load_times(state)
            require_times(times[:1920:20])
            if len(times) != 1921 or abs(times[-1] - 4.) > 1e-8:
                raise ValueError(f'Expected native 480 Hz over four seconds: {case}')
            result.append({'case_id': case, 'video': f'{INCREMENT_NAME}#{prefix}video.mp4',
                           'video_sha256': encoded['video_sha256'],
                           'native_cache': f'{INCREMENT_NAME}#{prefix}simulation.npz',
                           'native_cache_sha256': state_hash, 'native_samples': len(times), 'media': require_video(video)})
    return result
