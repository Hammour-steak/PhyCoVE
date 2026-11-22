"""Technical checks for the rope + puddle honey video.

These checks do not validate constitutive accuracy or replace watching the
whole video. They check bookkeeping, mesh sanity and the encoded file.
"""
import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import subprocess

import numpy as np


def main():
    p = argparse.ArgumentParser()
    p.add_argument('--run', type=Path, required=True)
    p.add_argument('--video', type=Path, required=True)
    p.add_argument('--source', type=Path, required=True)
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args()
    report = json.loads((a.run/'simulation_report.json').read_text())
    source = json.loads((a.source/'simulation_report.json').read_text())
    meshing = json.loads((a.run/'meshing_report_filament_meshes.json').read_text())
    rows = report['frames']
    assert len(rows) == 96 and [r['frame'] for r in rows] == list(range(1, 97))
    pv = report['hybrid_model']['particle_volume_m3']*1e6
    total = source['particles']*pv
    max_mass_error = 0.
    mesh_errors = []
    for row in rows:
        f = row['frame']
        particle = np.load(a.run/'particles'/f'frame_{f:04d}.npz')
        assert len(particle['honey_pos']) == row['reservoir_particles']
        assert np.isfinite(particle['honey_pos']).all() and np.isfinite(particle['honey_vel']).all()
        fluid = row['thread_volume_ml']+row['meniscus_buffer_volume_ml']+row['deposited_volume_ml']
        volume = row['reservoir_particles']*pv+fluid
        max_mass_error = max(max_mass_error, abs(volume-total)/total)
        assert abs(volume-total) < total*1e-9
        assert abs(fluid-row['transferred_volume_ml']) < total*1e-9
        mesh = np.load(a.run/'filament_meshes'/f'honey_{f:04d}.npz')
        v, t = mesh['vertices'], mesh['triangles']
        assert np.isfinite(v).all() and v.shape[1:] == (3,) and t.shape[1:] == (3,)
        if len(t):
            assert t.min() >= 0 and t.max() < len(v)
            edges = Counter(tuple(sorted((int(i), int(j)))) for tri in t
                            for i, j in ((tri[0], tri[1]), (tri[1], tri[2]), (tri[2], tri[0])))
            assert all(n == 2 for n in edges.values()), f'nonclosed honey surface {f}'
            q = v.astype(float)-v.mean(0)
            signed = np.einsum('ij,ij->i', q[t[:, 0]], np.cross(q[t[:, 1]], q[t[:, 2]])).sum()/6*1e6
            assert signed > 0, f'inward honey surface {f}'
            if fluid > 0:
                mesh_errors.append((f, signed-fluid, (signed-fluid)/fluid))
        else:
            assert fluid == 0
    # smooth-min blending, area smoothing, the lip meniscus overlapping the
    # strand root and the hidden slab below the toast top make the rendered
    # surface only approximately volume-exact
    bad = [e for e in mesh_errors if abs(e[1]) > .05 and abs(e[2]) > .10]
    assert not bad, bad
    assert rows[0]['transferred_volume_ml'] == 0 and rows[0]['nodes'] == 0
    assert source['frames'][0]['in_spoon_particles'] == source['particles']
    quats = np.array([r['spoon_quaternion_wxyz'] for r in report['source_frames']])
    assert np.array_equal(quats, np.repeat(quats[:1], 96, axis=0))
    assert all(r['spoon_tilt_deg'] == 15 for r in rows)
    contact = report['first_contact_frame']
    assert contact is not None
    # one continuous strand from the lip to the puddle once it has landed
    assert all(r['pieces'] == 1 for r in rows if r['frame'] >= contact)
    assert rows[-1]['deposited_volume_ml'] > 0
    probe = json.loads(subprocess.check_output(['ffprobe', '-v', 'error', '-select_streams', 'v:0',
        '-count_frames', '-show_entries',
        'stream=codec_name,width,height,r_frame_rate,avg_frame_rate,nb_read_frames:format=duration',
        '-of', 'json', str(a.video)], text=True))
    stream = probe['streams'][0]
    assert (stream['width'], stream['height']) == (1280, 720)
    assert stream['r_frame_rate'] == stream['avg_frame_rate'] == '24/1'
    assert int(stream['nb_read_frames']) == 96
    assert abs(float(probe['format']['duration'])-4) < 1e-6
    subprocess.run(['ffmpeg', '-v', 'error', '-i', str(a.video), '-f', 'null', '-'], check=True)
    after = [r for r in rows if r['frame'] >= contact]
    result = dict(
        status='technical_checks_passed_visual_review_separate',
        solver=report['solver'], scientific_validation='not experimentally calibrated',
        video=probe, video_sha256=hashlib.sha256(a.video.read_bytes()).hexdigest(),
        checks=dict(
            initial_honey_entirely_in_spoon=True, initial_extra_surface_empty=True,
            spoon_fixed_15_degrees_all_96_frames=True, finite_states=True,
            extra_surfaces_closed_and_outward=True, full_video_decode=True,
            total_volume_ml=total, maximum_relative_mass_error=max_mass_error,
            rendered_surface_volume_tolerance='within 10% or 0.05 mL',
            rendered_surface_volume_error_ml_range=[min(e[1] for e in mesh_errors), max(e[1] for e in mesh_errors)],
            rendered_surface_relative_volume_error_range=[min(e[2] for e in mesh_errors), max(e[2] for e in mesh_errors)],
            surface_voxel_m=meshing['voxel_m'],
            continuous_strand_after_contact=True, breakup_events=len(report['breakup_events']),
            first_contact_frame=contact, first_contact_playback_time_s=(contact-1)/24,
            thread_radius_range_after_contact_m=[min(r['min_thread_radius_m'] for r in after),
                                                 max(r['max_thread_radius_m'] for r in after)],
            max_strand_speed_m_s=max(r['max_speed_m_s'] for r in rows),
            max_lateral_offset_m=max(r['max_lateral_offset_m'] for r in rows),
            final_deposited_volume_ml=rows[-1]['deposited_volume_ml'],
            final_puddle_max_height_m=rows[-1]['puddle_max_height_m'],
            final_puddle_wet_radius_m=rows[-1]['puddle_wet_radius_m']),
        limitations=report['hybrid_model']['assumptions']+[
            'not a full-resolution 3-D Genesis free-surface simulation of the strand',
            'landed strand joins the puddle at once: no rope coiling on the pile',
            'no momentum or capillary feedback from the strand into the reservoir',
            'no validated physical-property counterfactuals included'])
    a.out.write_text(json.dumps(result, indent=2)+'\n')
    print(json.dumps(result['checks'], indent=2))


if __name__ == '__main__':
    main()
