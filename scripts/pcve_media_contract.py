"""Shared delivery contract and actual MP4 sample-table validation; no Blender."""
from __future__ import annotations

from fractions import Fraction
import json
import math
from pathlib import Path
import struct

HERE = Path(__file__).resolve().parent
CONTRACT = json.loads((HERE / 'benchmark_media_contract.json').read_text(encoding='utf-8'))


class MediaContractError(ValueError):
    pass


def _boxes(data):
    offset = 0
    while offset + 8 <= len(data):
        size, kind = struct.unpack_from('>I4s', data, offset)
        header = 8
        if size == 1:
            if offset + 16 > len(data):
                raise MediaContractError('Truncated 64-bit MP4 box')
            size = struct.unpack_from('>Q', data, offset + 8)[0]
            header = 16
        elif size == 0:
            size = len(data) - offset
        if size < header or offset + size > len(data):
            raise MediaContractError('Invalid MP4 box bounds')
        yield kind, data[offset + header:offset + size]
        offset += size


def _child(data, kind):
    for name, value in _boxes(data):
        if name == kind:
            return value
    raise MediaContractError('Missing MP4 box: ' + kind.decode('ascii'))


def _clock(data):
    version = data[0]
    if version == 0:
        return struct.unpack_from('>II', data, 12)
    if version == 1:
        return struct.unpack_from('>IQ', data, 20)
    raise MediaContractError('Unknown MP4 clock version')


def probe_mp4(path):
    """Read coded dimensions, sample count, and exact timing without decoding.

    Handles the non-fragmented MP4s produced by the benchmark's ffmpeg encoder.
    The finalizer also decodes each delivered movie for codec-integrity checks.
    """
    path = Path(path)
    moov = None
    with path.open('rb') as stream:
        length = path.stat().st_size
        while stream.tell() + 8 <= length:
            offset = stream.tell()
            size, kind = struct.unpack('>I4s', stream.read(8))
            header = 8
            if size == 1:
                size = struct.unpack('>Q', stream.read(8))[0]
                header = 16
            elif size == 0:
                size = length - offset
            if size < header or offset + size > length:
                raise MediaContractError('Invalid top-level MP4 box')
            if kind == b'moov':
                moov = stream.read(size - header)
                break
            stream.seek(offset + size)
    if moov is None:
        raise MediaContractError('No MP4 movie metadata: ' + str(path))
    movie_scale, movie_ticks = _clock(_child(moov, b'mvhd'))
    for kind, track in _boxes(moov):
        if kind != b'trak':
            continue
        media = _child(track, b'mdia')
        if _child(media, b'hdlr')[8:12] != b'vide':
            continue
        scale, ticks = _clock(_child(media, b'mdhd'))
        table = _child(_child(media, b'minf'), b'stbl')
        stsd = _child(table, b'stsd')
        codec = stsd[12:16].decode('ascii')
        width, height = struct.unpack_from('>HH', stsd, 40)
        count = struct.unpack_from('>I', _child(table, b'stsz'), 8)[0]
        stts = _child(table, b'stts')
        entries = struct.unpack_from('>I', stts, 4)[0]
        timings = [struct.unpack_from('>II', stts, 8 + i * 8) for i in range(entries)]
        samples = sum(n for n, delta in timings)
        coded_ticks = sum(n * delta for n, delta in timings)
        if not scale or not coded_ticks or samples != count or ticks != coded_ticks:
            raise MediaContractError('Inconsistent MP4 video sample clock')
        fps = Fraction(count * scale, coded_ticks)
        return {'width': width, 'height': height, 'fps': float(fps),
                'fps_numerator': fps.numerator, 'fps_denominator': fps.denominator,
                'frames': count, 'duration_s': coded_ticks / scale,
                'container_duration_s': movie_ticks / movie_scale,
                'constant_frame_rate': len({delta for n, delta in timings if n}) == 1,
                'codec': codec}
    raise MediaContractError('No video track: ' + str(path))


def require_video(path, contract=None):
    path = Path(path)
    wanted = CONTRACT if contract is None else contract
    observed = probe_mp4(path)
    wrong = {key: {'expected': wanted[key], 'actual': observed[key]}
             for key in ('width', 'height', 'fps', 'frames', 'duration_s')
             if not math.isclose(float(observed[key]), float(wanted[key]), rel_tol=0, abs_tol=1e-8)}
    if not observed['constant_frame_rate']:
        wrong['constant_frame_rate'] = {'expected': True, 'actual': False}
    if not math.isclose(observed['container_duration_s'], float(wanted['duration_s']), rel_tol=0, abs_tol=1e-6):
        wrong['container_duration_s'] = {'expected': wanted['duration_s'], 'actual': observed['container_duration_s']}
    if wrong:
        raise MediaContractError(f'{path}: {json.dumps(wrong, ensure_ascii=False)}')
    return observed


def require_times(times, contract=None):
    wanted = CONTRACT if contract is None else contract
    if len(times) != wanted['frames']:
        raise MediaContractError('GT/native sample count does not match the delivery contract')
    for i, value in enumerate(times):
        if not math.isfinite(float(value)) or abs(float(value) - i / wanted['fps']) > 1e-8:
            raise MediaContractError(f'GT time at frame {i} does not match normal-speed sampling')


def audit_suites(suite_dirs, selected=None):
    reports = []
    for folder in suite_dirs:
        if selected and folder.name[len('pcve_'):-len('_suite')] not in selected:
            continue
        meta = folder / 'suite_manifest.json'
        if not meta.is_file():
            continue
        manifest = json.loads(meta.read_text(encoding='utf-8'))
        if manifest.get('schema_version') != 3:
            continue
        scene = manifest.get('scene_id', manifest.get('scene'))
        for case in [manifest['source'], *manifest.get('edits', [])]:
            case_id = case['case_id'];path = folder / 'cases' / case_id / 'video.mp4'
            row = {'scene': scene, 'case_id': case_id, 'passed': False, 'canonical': False}
            try:
                observed = probe_mp4(path);row['observed'] = observed
                require_video(path);row.update(passed=True, canonical=True)
            except (OSError, ValueError, KeyError, struct.error) as error:
                row['error'] = str(error)
            reports.append(row)
    return {'contract': CONTRACT,
            'passed': bool(reports) and all(r['passed'] for r in reports),
            'all_canonical': bool(reports) and all(r['canonical'] for r in reports), 'videos': reports}
