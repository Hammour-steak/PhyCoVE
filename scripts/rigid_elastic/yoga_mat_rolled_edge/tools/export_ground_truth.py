"""Ground truth (pcve_ground_truth/1) of one suite case from its native cache and render record.

Reads cases/<case>/native_metadata/{simulation.npz, simulation_config.json, render_report.json} of a suite (24 fps
native states at t=(i-1)/24, i=1..96, and the camera of the render) and returns the ground-truth document: the ball
as its native affine body transform, the mat as the centroid of its shell vertices per frame (identity rotation),
the render camera. A case without the mat (delete_mat) marks the mat absent in every frame.

    python3 tools/export_ground_truth.py --out DIR [--suite SUITE] [--cases CASE ...]   write DIR/<case>/ground_truth_transforms.json
    python3 tools/export_ground_truth.py --check [--suite SUITE]                       compare with the published files

--check compares everything except the "source" record (which names the files the export was made from).
Needs numpy.
"""
from pathlib import Path
import argparse
import hashlib
import json
import math
import sys

import numpy as np

CASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(CASE),str(CASE.parents[1])]
from scene_paths import REPO,SCENE,output_path,suite_dir  # noqa: E402

FPS,FRAMES=24,96
BALL='Medicine ball — exact collision surface'
MAT='Yoga mat — native shell replay'


def sha(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):
            h.update(block)
    return h.hexdigest()


def matrix(m):
    return [[float(m[i][j]) for j in range(4)] for i in range(4)]


def quaternion_xyzw(m):
    r=[[float(m[i][j]) for j in range(3)] for i in range(3)]
    trace=r[0][0]+r[1][1]+r[2][2]
    if trace>0:
        s=math.sqrt(trace+1.0)*2
        w,x,y,z=.25*s,(r[2][1]-r[1][2])/s,(r[0][2]-r[2][0])/s,(r[1][0]-r[0][1])/s
    elif r[0][0]>r[1][1] and r[0][0]>r[2][2]:
        s=math.sqrt(1.0+r[0][0]-r[1][1]-r[2][2])*2
        w,x,y,z=(r[2][1]-r[1][2])/s,.25*s,(r[0][1]+r[1][0])/s,(r[0][2]+r[2][0])/s
    elif r[1][1]>r[2][2]:
        s=math.sqrt(1.0+r[1][1]-r[0][0]-r[2][2])*2
        w,x,y,z=(r[0][2]-r[2][0])/s,(r[0][1]+r[1][0])/s,.25*s,(r[1][2]+r[2][1])/s
    else:
        s=math.sqrt(1.0+r[2][2]-r[0][0]-r[1][1])*2
        w,x,y,z=(r[1][0]-r[0][1])/s,(r[0][2]+r[2][0])/s,(r[1][2]+r[2][1])/s,.25*s
    n=math.sqrt(x*x+y*y+z*z+w*w)
    q=[x/n,y/n,z/n,w/n]
    return [-v for v in q] if q[3]<0 else q


def entry(m=None):
    if m is None:
        return {'present':False,'location':None,'quaternion_xyzw':None,'matrix_world':None}
    m=matrix(m)
    return {'present':True,'location':[m[0][3],m[1][3],m[2][3]],'quaternion_xyzw':quaternion_xyzw(m),'matrix_world':m}


def relative(path):
    path=Path(path).resolve()
    return path.relative_to(REPO.resolve()).as_posix() if REPO.resolve() in path.parents else str(path)


def export(case_dir):
    """The pcve_ground_truth/1 document of one suite case folder (cases/<case_id>)."""
    case_dir=Path(case_dir)
    meta=case_dir/'native_metadata'
    report=json.loads((meta/'render_report.json').read_text(encoding='utf-8'))
    config=json.loads((meta/'simulation_config.json').read_text(encoding='utf-8'))
    cam=report['camera']
    if report['resolution']!=[1280,720] or report['fps']!=FPS:
        raise ValueError(f'{case_dir.name}: render is not 1280x720 at {FPS} fps')
    with np.load(meta/'simulation.npz',allow_pickle=False) as z:
        times=z['times'];ball=z['ball_transforms'];present=bool(z['mat_present'][0])
        # DELETE ball: the cache carries ball_present = 0 (the published caches have no such key: present).
        ball_present=bool(z['ball_present'][0]) if 'ball_present' in z.files else True
        mat=z['mat_positions'];rest=z['mat_rest_positions'];radius=float(np.ptp(z['ball_vertices'][:,0])/2)
    if len(times)!=FRAMES or not np.allclose(times,np.arange(FRAMES)/FPS,atol=1e-12):
        raise ValueError(f'{case_dir.name}: native cache is not sampled at t=(i-1)/{FPS}, i=1..{FRAMES}')
    objects={'ball':{'object_name':BALL,'kind':'rigid','present':ball_present,'radius':radius,
                     'origin':'ball centre (native affine body transform; the mesh is replayed through shape keys)'},
             'mat':{'object_name':MAT,'kind':'deformable','present':present,
                    'location_definition':'centroid of the native shell vertices of the frame'}}
    if present:
        objects['mat']['dimensions']=[float(x) for x in np.ptp(rest,axis=0)]
    camera_matrix=matrix(cam['matrix_world'])
    frames=[]
    for i in range(FRAMES):
        frame={'frame_index':i+1,'time_sec':i/FPS,'camera_matrix_world':camera_matrix,'ball':entry(ball[i]) if ball_present else entry()}
        if present:
            c=mat[i].mean(axis=0)
            frame['mat']=entry([[1.,0.,0.,float(c[0])],[0.,1.,0.,float(c[1])],[0.,0.,1.,float(c[2])],[0.,0.,0.,1.]])
            frame['mat']['quaternion_xyzw']=[0.,0.,0.,1.]
        else:
            frame['mat']=entry()
        frames.append(frame)
    files=[meta/'simulation.npz',meta/'simulation_config.json',meta/'render_report.json']
    source={'how':'Native libuipc states at t=(i-1)/24; ball = native affine body transform; mat = centroid of the shell '
                  'vertices; camera = the contact-view camera recorded by the render.',
            'files':[relative(f) for f in files],'sha256':{relative(f):sha(f) for f in files if f.suffix!='.json'},
            'tool':relative(__file__)}
    if config.get('timed_edit'):
        source['timed_edit']=config['timed_edit']
    return {'schema_version':1,'format_version':'pcve_ground_truth/1','scene':SCENE,'case_id':case_dir.name,
            'fps':FPS,'frame_start':1,'frame_end':FRAMES,'units':'m',
            'camera':{'resolution':[1280,720],'projection':'perspective','lens_mm':float(cam['lens_mm']),
                      'sensor_width_mm':float(cam['sensor_width_mm']),'sensor_fit':cam.get('sensor_fit','AUTO'),
                      'shift_x':float(cam.get('shift_x',0.)),'shift_y':float(cam.get('shift_y',0.)),'matrix_world':camera_matrix},
            'objects':objects,'frames':frames,'source':source}


def differences(case_dir):
    """Keys of the published ground truth that differ from a fresh export (the source record is not compared)."""
    published=json.loads((Path(case_dir)/'ground_truth_transforms.json').read_text(encoding='utf-8'))
    fresh=json.loads(json.dumps(export(case_dir)))
    return sorted(k for k in set(published)|set(fresh) if k!='source' and published.get(k)!=fresh.get(k))


def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--suite',type=Path,help='video suite (default: the published suite of scene_manifest.json)')
    p.add_argument('--cases',nargs='+',help='suite case folders (default: all)')
    mode=p.add_mutually_exclusive_group(required=True)
    mode.add_argument('--out',type=Path,help='write <out>/<case>/ground_truth_transforms.json')
    mode.add_argument('--check',action='store_true',help='compare fresh exports with the suite files')
    a=p.parse_args()
    suite=(a.suite or suite_dir()).resolve()
    cases=a.cases or sorted(d.name for d in (suite/'cases').iterdir() if d.is_dir())
    if a.check:
        result={c:differences(suite/'cases'/c) for c in cases}
        print(json.dumps({'suite':str(suite),'differences_except_source':result},indent=1))
        raise SystemExit(1 if any(result.values()) else 0)
    out=output_path(a.out)
    for c in cases:
        target=out/c/'ground_truth_transforms.json'
        target.parent.mkdir(parents=True,exist_ok=True)
        target.write_text(json.dumps(export(suite/'cases'/c),indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
        print('wrote',target)


if __name__=='__main__':
    main()
