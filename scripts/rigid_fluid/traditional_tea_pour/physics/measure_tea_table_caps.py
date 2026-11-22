"""Measure cached droplet components, table clipping and projected pixel size."""
import argparse
import json
import sys
from pathlib import Path

import numpy as np
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree,ConvexHull

p=argparse.ArgumentParser()
p.add_argument('case',type=Path); p.add_argument('environment',type=Path); p.add_argument('output',type=Path)
p.add_argument('--all-frames',action='store_true')
a=p.parse_args()
case=a.case.resolve(); out=a.output.resolve(); out.mkdir(parents=True,exist_ok=True)
from audit_raw_liquid_cache import volume_below
metadata_path=a.environment if a.environment.is_file() else a.environment/'environment_edit.json'
metadata=json.loads(metadata_path.read_text())
camera=metadata['camera'] if 'camera' in metadata else metadata['protected_after']['camera']
view=np.linalg.inv(np.array(camera['matrix_world']))
focal=1280*camera['lens']/camera['sensor_width']
def project(v):
    c=np.c_[v,np.ones(len(v))]@view.T
    return np.c_[640-focal*c[:,0]/c[:,2],360+focal*c[:,1]/c[:,2]]
result={'camera':camera,'table_z_m':0,'frames':{}}
for frame in (range(21,97) if a.all_frames else [20,21,22,23,24,26,28,32,48,72,96]):
    with np.load(case/'surfaces'/f'frame_{frame:04d}.npz') as z: v=z['vertices'].astype(float); t=z['triangles']
    with np.load(case/'particles'/f'frame_{frame:04d}.npz') as z: pos=z['pos'].astype(float); ids=z['particle_ids']
    edges=np.r_[t[:,[0,1]],t[:,[1,2]],t[:,[2,0]]]
    graph=coo_matrix((np.ones(len(edges)),(edges[:,0],edges[:,1])),shape=(len(v),len(v))).tocsr()
    count,labels=connected_components(graph,directed=False)
    face_labels=labels[t[:,0]]
    rows=[]
    tree=cKDTree(pos)
    for label in range(count):
        vi=np.flatnonzero(labels==label)
        vv=v[vi]
        if vv[:,2].max()>.006 or np.linalg.norm(vv[:,:2],axis=1).min()<.06: continue
        tt=t[face_labels==label]
        full=volume_below(v,tt,1.)
        below=volume_below(v,tt,0.)
        pixels=project(vv)
        above_pixels=project(vv[vv[:,2]>0])
        bounds=[pixels.min(0).tolist(),pixels.max(0).tolist()]
        try: area=float(ConvexHull(above_pixels).volume) if len(above_pixels)>2 else 0.
        except Exception: area=0.
        _,near=tree.query(vv.mean(0))
        rows.append({'component':int(label),'nearest_particle_id':int(ids[near]),'particle_xyz_mm':(pos[near]*1000).tolist(),
                     'vertices':len(vv),'faces':len(tt),'mesh_volume_ul':full*1000,'mesh_above_table_volume_fraction':1-below/max(full,1e-30),
                     'bounds_z_mm':(vv[:,2][[np.argmin(vv[:,2]),np.argmax(vv[:,2])]]*1000).tolist(),
                     'screen_bbox_pixels':bounds,'bbox_width_height_px':np.ptp(pixels,axis=0).tolist(),
                     'unoccluded_above_table_convex_hull_area_px2':area})
    result['frames'][str(frame)]=rows
    print('CAP_COMPONENTS',frame,'n=',len(rows),'median_bbox_wh=',np.median([r['bbox_width_height_px'] for r in rows],axis=0).tolist() if rows else [],
          'median_area=',float(np.median([r['unoccluded_above_table_convex_hull_area_px2'] for r in rows])) if rows else 0,
          'median_above_fraction=',float(np.median([r['mesh_above_table_volume_fraction'] for r in rows])) if rows else 0,flush=True)
(out/('table_cap_geometry_all.json' if a.all_frames else 'table_cap_geometry.json')).write_text(json.dumps(result,indent=2)+'\n')
