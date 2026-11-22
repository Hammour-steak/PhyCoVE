"""Remote-only appearance upgrade of an approved, fully animated .blend.

Run on a selected idle GPU worker, never locally or on the storage host.
The lossless FFV1 master is encoded locally to the standard H.264 deliverable.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys
import time

import bpy
import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE))
from realism import apply


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1024*1024), b''):
            digest.update(block)
    return digest.hexdigest()


def setup_gpu():
    host = socket.gethostname().split('.')[0]
    requested = os.environ.get('CUDA_VISIBLE_DEVICES', '')
    if not requested.startswith('GPU-') or ',' in requested:
        raise RuntimeError('Bind exactly one preflighted idle GPU by UUID')
    preferences = bpy.context.preferences.addons['cycles'].preferences
    preferences.compute_device_type = 'OPTIX'
    preferences.get_devices()
    available = []
    for device in preferences.devices:
        device.use = device.type == 'OPTIX'
        if device.use:
            available.append(dict(name=device.name,id=device.id,type=device.type))
    if len(available) != 1:
        raise RuntimeError(f'Expected exactly one isolated OptiX GPU, got {available}')
    bpy.context.scene.cycles.device = 'GPU'
    gpu = subprocess.check_output(['nvidia-smi','-i',requested,
        '--query-gpu=uuid,name,driver_version','--format=csv,noheader'],text=True).strip()
    return dict(hostname=host,
                cuda_visible_devices=requested,gpu=gpu,cycles_devices=available,
                blender_version=bpy.app.version_string,python_version=sys.version)


def immutable_signature(scene):
    """Byte-sensitive geometry/animation signature, excluding appearance."""
    record={}
    for obj in sorted(scene.objects,key=lambda item:item.name):
        if obj.type=='LIGHT':continue
        item=dict(type=obj.type,matrix=np.array(obj.matrix_world).tolist(),
                  parent=obj.parent.name if obj.parent else None)
        if obj.type=='MESH':
            digest=hashlib.sha256()
            coords=np.empty(len(obj.data.vertices)*3,dtype=np.float32)
            obj.data.vertices.foreach_get('co',coords);digest.update(coords.tobytes())
            loops=np.empty(len(obj.data.loops),dtype=np.int32)
            obj.data.loops.foreach_get('vertex_index',loops);digest.update(loops.tobytes())
            if obj.data.shape_keys:
                for key in obj.data.shape_keys.key_blocks:
                    key.data.foreach_get('co',coords);digest.update(coords.tobytes())
            item['mesh_and_shape_keys']=digest.hexdigest()
            item['modifiers']=[dict(type=m.type,**{key:getattr(m,key) for key in
                ('levels','render_levels','thickness','offset','width','segments','show_render') if hasattr(m,key)})
                for m in obj.modifiers]
        animations=[]
        owners=[obj]+([obj.data.shape_keys] if obj.type=='MESH' and obj.data.shape_keys else [])
        for owner in owners:
            if owner.animation_data and owner.animation_data.action:
                for curve in owner.animation_data.action.fcurves:
                    animations.append(dict(path=curve.data_path,index=curve.array_index,
                        keys=[(list(k.co),k.interpolation) for k in curve.keyframe_points]))
        item['animations']=animations
        if obj.type=='CAMERA':
            item['camera']=dict(lens=obj.data.lens,sensor_width=obj.data.sensor_width,
                clip_start=obj.data.clip_start,clip_end=obj.data.clip_end,
                dof=obj.data.dof.use_dof,fstop=obj.data.dof.aperture_fstop,
                focus_object=obj.data.dof.focus_object.name if obj.data.dof.focus_object else None)
        record[obj.name]=item
    return hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--input',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--hdri',type=Path,required=True)
    parser.add_argument('--samples',type=int,default=256)
    parser.add_argument('--preview-frames',type=int,nargs='+')
    parser.add_argument('--width',type=int,default=1280)
    args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
    original=args.input.resolve();out=args.out.resolve();out.mkdir(parents=True,exist_ok=True)
    bpy.ops.wm.open_mainfile(filepath=str(original/'scene.blend'))
    scene=bpy.context.scene
    scene.frame_set(1);bpy.context.view_layer.update()
    camera=np.array(scene.camera.matrix_world)
    transforms={o.name:np.array(o.matrix_world) for o in scene.objects}
    immutable_before=immutable_signature(scene)
    # A missing absolute storage-host path must not silently turn the world pink.
    for node in scene.world.node_tree.nodes:
        if node.type=='TEX_ENVIRONMENT':
            node.image=bpy.data.images.load(str(args.hdri.resolve()),check_existing=True)
    appearance=apply(scene,args.samples)
    provenance=setup_gpu()
    bpy.context.view_layer.update()
    if not np.array_equal(camera,np.array(scene.camera.matrix_world)):
        raise RuntimeError('Appearance pass changed the camera')
    if any(not np.array_equal(transforms[o.name],np.array(o.matrix_world)) for o in scene.objects):
        raise RuntimeError('Appearance pass changed an object transform')
    immutable_after=immutable_signature(scene)
    if immutable_before!=immutable_after:
        raise RuntimeError('Appearance pass changed geometry, animation, camera or object layout')
    scene.render.engine='CYCLES';scene.render.use_persistent_data=True
    scene.render.resolution_x=args.width;scene.render.resolution_y=round(args.width*9/16)
    scene.render.resolution_percentage=100;scene.render.fps=24
    scene.frame_start=1;scene.frame_end=96
    scene.render.image_settings.color_mode='RGB'
    started=time.monotonic()
    if args.preview_frames:
        for frame in args.preview_frames:
            scene.frame_set(frame)
            scene.render.image_settings.file_format='PNG'
            scene.render.filepath=str(out/f'preview_{frame:04d}.png')
            bpy.ops.render.render(write_still=True)
    else:
        # Preserve all 96 native-time states and let Blender's bundled codec
        # produce a lossless master without installing a worker-wide ffmpeg.
        scene.render.image_settings.file_format='FFMPEG'
        scene.render.ffmpeg.format='MKV'
        scene.render.ffmpeg.codec='FFV1'
        scene.render.ffmpeg.audio_codec='NONE'
        scene.render.filepath=str(out/'lossless_master.mkv')
        # Pack the active HDRI only. Approved files may retain an unused old
        # storage-host Image datablock whose original path is not on the worker.
        for node in scene.world.node_tree.nodes:
            if node.type=='TEX_ENVIRONMENT' and node.image:
                node.image.pack()
        bpy.ops.wm.save_as_mainfile(filepath=str(out/'scene.blend'),compress=True)
        bpy.ops.render.render(animation=True)
    report=json.loads((original/'render_report.json').read_text())
    report.update(status='preview' if args.preview_frames else 'complete',
        frames=len(args.preview_frames) if args.preview_frames else 96,
        resolution=[scene.render.resolution_x,scene.render.resolution_y],samples=args.samples,
        source_approved_scene_sha256=sha(original/'scene.blend'),
        immutable_scene_signature_before=immutable_before,
        immutable_scene_signature_after=immutable_after,
        appearance=appearance,execution_host=provenance['hostname'],worker=provenance,
        camera_matrix_world=camera.tolist(),local_blender_used=False,
        appearance_only_revision=True,physical_cache_unchanged=True,
        hdri_sha256=sha(args.hdri),wall_seconds=time.monotonic()-started)
    (out/'render_report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    if not args.preview_frames:
        shutil.copy2(original/'simulation.npz',out/'simulation.npz')
        shutil.copy2(original/'simulation_config.json',out/'simulation_config.json')
        from audit_native_replay import audit_saved_scene
        audit_saved_scene(out)
    print('REALISM_RENDER_COMPLETE',json.dumps(dict(case=report['case'],host=provenance['hostname'],seconds=report['wall_seconds'])),flush=True)


if __name__=='__main__':main()
