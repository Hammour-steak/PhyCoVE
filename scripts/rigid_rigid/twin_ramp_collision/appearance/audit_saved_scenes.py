"""Blender-side validation of all cached poses, visible dimensions and frozen optics."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Quaternion
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_config import CASES,ramp_mesh

def main(root):
    root=Path(root);reports=[]
    for case in CASES:
        folder=root/"cases"/case;r=json.loads((folder/"physics_transforms.json").read_text());cfg=json.loads((folder/"settings.json").read_text())
        bpy.ops.wm.open_mainfile(filepath=str(folder/"twin_ramp_collision.blend"));s=bpy.context.scene;maxpos=0.;maxangle=0.
        for f in r['trajectory_samples']:
            frame=f['time_sec']*cfg['render']['fps']+1
            s.frame_set(math.floor(frame),subframe=frame-math.floor(frame))
            for name,b in f["objects"].items():
                obj=bpy.data.objects[name];maxpos=max(maxpos,max(abs(obj.location[i]-b["location"][i]) for i in range(3)))
                x,y,z,w=b["quaternion_xyzw"];actual=obj.rotation_quaternion.normalized();expected=Quaternion((w,x,y,z)).normalized()
                dot=min(1.,abs(actual.dot(expected)));maxangle=max(maxangle,2*math.acos(dot))
        camera=s.camera;c=cfg["appearance"]["camera"];rd=cfg["render"]
        imaging=cfg['appearance'].get('imaging',{})
        verts,_=ramp_mesh(cfg);visible=bpy.data.objects["Continuous 14 mm oak-veneered ramp running surface"]
        geomerr=max(abs(vertex.co[i]-verts[j][i]) for j,vertex in enumerate(visible.data.vertices) for i in range(3))
        checks={"all_solved_positions":maxpos<.000001,"all_solved_orientations":maxangle<.002,
            "unanimated_camera":camera.animation_data is None,"camera_location":max(abs(camera.location[i]-c["location"][i]) for i in range(3))<1e-6,
            "camera_lens":abs(camera.data.lens-c["lens_mm"])<1e-6,
            "declared_dof":camera.data.dof.use_dof==c.get("dof_enabled",False) and (not c.get("dof_enabled",False) or abs(camera.data.dof.aperture_fstop-c["fstop"])<1e-6),
            'declared_imaging':s.view_settings.look==imaging.get('look','AgX - Medium High Contrast') and abs(s.view_settings.exposure-imaging.get('exposure_stops',0.))<1e-6 and abs(s.view_settings.gamma-imaging.get('gamma',1.))<1e-6,
            'declared_shutter':s.render.use_motion_blur==(rd['motion_blur_shutter_frames']>0) and abs(s.render.motion_blur_shutter-rd['motion_blur_shutter_frames'])<1e-6,
            'declared_persistent_data':s.render.use_persistent_data==rd.get('persistent_data',True),
            "formal_render_settings":s.cycles.samples==rd['samples'] and [s.render.resolution_x,s.render.resolution_y]==list(rd['resolution']) and s.render.fps==rd['fps'] and s.frame_end==round(rd['fps']*rd['duration_sec']),
            "visible_profile_matches_physics":geomerr<1e-6,"all_texture_images_packed":all(img.packed_file for img in bpy.data.images if img.source=="FILE"),
            "correct_ball_presence":all((name in bpy.data.objects)==b["present"] for name,b in cfg["physics"]["balls"].items()),
            "correct_ball_diameters":all(max(abs(v-.05) for v in bpy.data.objects[name].dimensions)<1e-6 for name,b in cfg["physics"]["balls"].items() if b["present"])}
        report={"case_id":case,"passed":all(checks.values()),"checks":checks,"maximum_pose_position_error_m":maxpos,
            "maximum_pose_orientation_error_rad":maxangle,"visible_surface_vertex_error_m":geomerr,'checked_240hz_solver_samples':len(r['trajectory_samples'])}
        (folder/"saved_scene_audit.json").write_text(json.dumps(report,indent=2)+"\n");reports.append(report);print(json.dumps(report),flush=True)
    result={"passed":all(r["passed"] for r in reports),"cases":reports};(root/"saved_scene_audit.json").write_text(json.dumps(result,indent=2)+"\n")
    if not result["passed"]:raise RuntimeError("Saved scene audit failed")

if __name__=="__main__":main(sys.argv[sys.argv.index("--")+1])
