"""Blender-side comparison of every saved video-frame pose with the solver."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Quaternion,Vector
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from scene_config import save_json

def main():
    argv=sys.argv[sys.argv.index('--')+1:];p=argparse.ArgumentParser();p.add_argument('--case-dir',type=Path,required=True);a=p.parse_args(argv);folder=a.case_dir
    r=json.loads((folder/'physics_transforms.json').read_text());cfg=json.loads((folder/'scenario_metadata.json').read_text())['configuration'];bpy.ops.wm.open_mainfile(filepath=str(folder/'ramp_car_ball_collision.blend'));s=bpy.context.scene
    pos=0.;rot=0.;rows=[]
    for frame in r['frames']:
        s.frame_set(frame['frame_index']);bpy.context.view_layer.update()
        for name,st in frame['objects'].items():
            o=bpy.data.objects[name];expected=Vector(st['location']);pos=max(pos,(o.matrix_world.translation-expected).length)
            x,y,z,w=st['quaternion_xyzw'];q=Quaternion((w,x,y,z));dot=abs(o.matrix_world.to_quaternion().dot(q));rot=max(rot,2*math.acos(min(1.,max(-1.,dot))))
    camera=s.camera;initial=s.frame_set(1);bpy.context.view_layer.update()
    visual_measurements={}
    checks={'all_solved_frame_positions_match_within_2um':pos<2e-6,'all_solved_orientations_match_within_0_002rad':rot<.002,
        'camera_has_no_animation':camera.animation_data is None,'camera_location_matches':(camera.location-Vector(cfg['appearance']['camera']['location'])).length<1e-6,
        'resolution_matches_configuration':[s.render.resolution_x,s.render.resolution_y]==list(cfg['render']['resolution']) and s.render.resolution_percentage==100,
        'fps_and_frame_range_match_configuration':s.render.fps==cfg['render']['fps'] and s.frame_start==1 and s.frame_end==round(cfg['render']['fps']*cfg['render']['duration_sec']),'cycles_samples_match_configuration':s.render.engine=='CYCLES' and s.cycles.samples==cfg['render']['samples'],
        'depth_of_field_matches_configuration':camera.data.dof.use_dof==cfg['appearance']['camera'].get('use_depth_of_field',False) and (not camera.data.dof.use_dof or (abs(camera.data.dof.focus_distance-cfg['appearance']['camera']['focus_distance_m'])<1e-5 and abs(camera.data.dof.aperture_fstop-cfg['appearance']['camera']['f_stop'])<1e-5)),'SI_units':s.unit_settings.system=='METRIC' and s.unit_settings.scale_length==1.,
        'no_blender_rigid_body_resimulation':all(o.rigid_body is None for o in s.objects),
        'ball_presence_matches':('ball' in bpy.data.objects)==cfg['physics']['ball']['present'],
        'all_texture_images_packed':all(im.packed_file is not None for im in bpy.data.images if im.source=='FILE' and im.users>0),
        'no_missing_textures':all(im.size[0]>0 and im.size[1]>0 for im in bpy.data.images if im.source=='FILE' and im.users>0)}
    if visual_measurements:checks['new_wheel_and_bumper_visuals_match_collision_geometry']=all(v.get('radius_matches_solver_within_10um',v.get('matches_collision_box',False)) for v in visual_measurements.values())
    if cfg['appearance'].get('window_curtain',{}).get('revision')=='casement_linen_clearance':
        # The final look removes this helper lamp; if it is present it must stay invisible in the glass.
        window_light=bpy.data.objects.get('Soft daylight through side window')
        checks['window_light_emitter_hidden_in_glass']=window_light is None or (not window_light.visible_glossy and not window_light.visible_transmission)
        checks['two_fixed_curtain_panels_and_four_glass_sheets']=sum(o.name.startswith('Curtain hanging linen panel') for o in s.objects)==2 and sum(o.name.startswith('Window 4mm clear glass pane') for o in s.objects)==4
    def target_ball(obj):
        while obj:
            if obj.name=='ball':return True
            obj=obj.parent
        return False
    def object_record(obj):
        rec={'name':obj.name,'type':obj.type,'parent':obj.parent.name if obj.parent else None}
        if obj.name not in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3','ball']:rec['matrix_basis']=[list(row) for row in obj.matrix_basis]
        if obj.type=='MESH':
            # Blender's sphere face order/cyclic start can vary between processes.
            # Canonicalize cyclic face records while preserving winding, UV-to-vertex
            # association, smooth shading and material assignment. No mesh is edited.
            co=lambda v:tuple('%.9g'%x for x in v)
            faces=[]
            for poly in obj.data.polygons:
                seq=tuple((co(obj.data.vertices[obj.data.loops[k].vertex_index].co),tuple(co(uv.data[k].uv) for uv in obj.data.uv_layers)) for k in poly.loop_indices)
                seq=min(seq[k:]+seq[:k] for k in range(len(seq)))
                faces.append((seq,poly.material_index,poly.use_smooth))
            h=hashlib.sha256(json.dumps({'vertices':sorted(co(v.co) for v in obj.data.vertices),'faces':sorted(faces)},sort_keys=True).encode())
            rec.update({'mesh_sha256':h.hexdigest(),'materials':[m.name if m else None for m in obj.data.materials],
                'modifiers':[(m.name,m.type) for m in obj.modifiers]})
        elif obj.type=='CURVE':rec['curve']={'bevel_depth':obj.data.bevel_depth,'points':[[list(p.co) for p in sp.points] for sp in obj.data.splines]}
        elif obj.type=='LIGHT':rec['light']={'type':obj.data.type,'energy':obj.data.energy,'color':list(obj.data.color),'size':getattr(obj.data,'size',None),'ray_visibility':{key:getattr(obj,key) for key in ['visible_camera','visible_glossy','visible_transmission']}}
        elif obj.type=='CAMERA':rec['camera']={'lens':obj.data.lens,'sensor_width':obj.data.sensor_width,'use_depth_of_field':obj.data.dof.use_dof,'focus_distance':obj.data.dof.focus_distance,'f_stop':obj.data.dof.aperture_fstop}
        return rec
    def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()
    def node_tree_record(tree,seen=None):
        seen=set() if seen is None else seen
        if tree is None or tree.name in seen:return None
        seen.add(tree.name);nodes=[]
        for n in sorted(tree.nodes,key=lambda n:n.name):
            row={'name':n.name,'type':n.bl_idname,'inputs':[]}
            for sock in n.inputs:
                val=getattr(sock,'default_value',None)
                if hasattr(val,'name'):val=val.name
                elif val is not None and not isinstance(val,(str,bool,float,int)):
                    try:val=list(val)
                    except TypeError:val=str(val)
                row['inputs'].append((sock.identifier,val))
            for key in ['operation','blend_type','projection','projection_blend','interpolation','extension','space','distribution','subsurface_method','noise_dimensions','normalize','vector_type']:
                if hasattr(n,key):row[key]=getattr(n,key)
            if getattr(n,'image',None):
                im=n.image;row['image']={'name':im.name,'colorspace':im.colorspace_settings.name,'packed_sha256':hashlib.sha256(im.packed_file.data).hexdigest() if im.packed_file else None}
            if getattr(n,'object',None):row['object']=n.object.name
            if getattr(n,'node_tree',None):row['group']=node_tree_record(n.node_tree,seen)
            if hasattr(n,'color_ramp'):row['color_ramp']=[(e.position,list(e.color)) for e in n.color_ramp.elements]
            nodes.append(row)
        return {'nodes':nodes,'links':sorted((l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in tree.links)}
    def materials_record(objects):
        materials={m.name:m for o in objects if o.type=='MESH' for m in o.data.materials if m}
        return {name:node_tree_record(m.node_tree) for name,m in sorted(materials.items())}
    nonball=[object_record(o) for o in sorted(s.objects,key=lambda o:o.name) if not target_ball(o)]
    ball_objects=[object_record(o) for o in sorted(s.objects,key=lambda o:o.name) if target_ball(o)]
    common_shading={'materials':materials_record([o for o in s.objects if not target_ball(o)]),'world':node_tree_record(s.world.node_tree),
        'color_management':{'view':s.view_settings.view_transform,'look':s.view_settings.look,'exposure':s.view_settings.exposure,'gamma':s.view_settings.gamma}}
    result={'accepted':all(checks.values()),'checks':checks,'maximum_position_error_m':pos,'maximum_orientation_error_rad':rot,'frames_checked':len(r['frames']),
        'nonball_geometry_camera_lights_sha256':digest(nonball),'ball_geometry_sha256':digest(ball_objects) if ball_objects else None,'nonball_object_count':len(nonball),
        'nonball_materials_world_color_management_sha256':digest(common_shading),'ball_materials_sha256':digest(materials_record([o for o in s.objects if target_ball(o)])) if ball_objects else None,
        'geometry_signature_method':'Canonical cyclic face/UV/material records; insensitive to polygon storage order, preserves winding and all actual geometry/color assignments',
        'blender_version':bpy.app.version_string,'visual_geometry_measurements':visual_measurements,'scope':'Every frame, every solver body; camera, optics, units, texture packing and ball deletion'}
    save_json(folder/'saved_scene_audit.json',result);print(json.dumps(result));raise SystemExit(0 if result['accepted'] else 2)
if __name__=='__main__':main()
