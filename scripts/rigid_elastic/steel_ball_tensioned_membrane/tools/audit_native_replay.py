"""Remote-only saved-scene audit against all 96 native video states."""
from pathlib import Path
import argparse
import json
import socket
import sys

import bpy
import numpy as np


def audit_saved_scene(folder):
    folder=Path(folder).resolve()
    bpy.ops.wm.open_mainfile(filepath=str(folder/'scene.blend'))
    z=np.load(folder/'simulation.npz',allow_pickle=False)
    scene=bpy.context.scene
    membrane=next((o for o in scene.objects if o.name.startswith('Rubber membrane')),None)
    primary=bpy.data.objects['304 stainless drop sphere']
    secondary=bpy.data.objects.get('304 stainless pre-positioned sphere')
    expected_second=bool(z['second_ball_present'][0])
    object_presence_ok=(secondary is not None)==expected_second and (membrane is not None)==bool(z['membrane_positions'].shape[1])
    if membrane:
        # Inspect the exact native replay mesh before cosmetic thickness and subdivision.
        # No changes are saved to the .blend or any simulation file.
        for modifier in membrane.modifiers:
            modifier.show_viewport=False
    center_error=0.;membrane_error=0.;camera_error=0.
    camera=np.array(scene.camera.matrix_world)
    for i in range(96):
        scene.frame_set(i+1)
        bpy.context.view_layer.update()
        camera_error=max(camera_error,float(np.max(np.abs(np.array(scene.camera.matrix_world)-camera))))
        center_error=max(center_error,float(np.linalg.norm(np.array(primary.matrix_world.translation)-z['ball_transforms'][i,:3,3])))
        if secondary:
            center_error=max(center_error,float(np.linalg.norm(np.array(secondary.matrix_world.translation)-z['second_ball_transforms'][i,:3,3])))
        if membrane:
            evaluated=membrane.evaluated_get(bpy.context.evaluated_depsgraph_get())
            mesh=evaluated.to_mesh()
            values=np.empty(len(mesh.vertices)*3,dtype=np.float64)
            mesh.vertices.foreach_get('co',values)
            membrane_error=max(membrane_error,float(np.max(np.linalg.norm(values.reshape(-1,3)-z['membrane_positions'][i],axis=1))))
            evaluated.to_mesh_clear()
    witness=[o.name for o in scene.objects if 'witness' in o.name.lower()]
    result=dict(frames_checked=96,render_frame_range=[scene.frame_start,scene.frame_end],fps=scene.render.fps,
        maximum_ball_center_error_m=center_error,maximum_native_membrane_vertex_error_m=membrane_error,
        maximum_camera_matrix_drift=camera_error,witness_mark_objects=witness,
        second_ball_visible=secondary is not None,membrane_visible=membrane is not None,
        object_presence_matches_cache=bool(object_presence_ok),
        ball_center_tolerance_m=1e-6,membrane_vertex_tolerance_m=1e-5,
        tolerance_note='Blender stores mesh coordinates and evaluates absolute shape-key time in single precision; allow at most 0.01 mm of replay error.',
        native_replay_ok=bool(center_error<1e-6 and membrane_error<1e-5 and camera_error==0 and not witness and object_presence_ok),
        execution_host=socket.gethostname().split('.')[0],local_blender_used=False,saved_scene_modified=False)
    (folder/'native_replay_audit.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(result))
    if not result['native_replay_ok']:
        raise SystemExit(2)
    return result


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--case-dir',type=Path,required=True)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    audit_saved_scene(args.case_dir)


if __name__=='__main__':main()
