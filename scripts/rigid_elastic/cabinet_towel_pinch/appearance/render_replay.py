"""Cycles renderer of the accepted delivery: builds the shared kitchen, replays the exact native cloth and door states.

This renderer produced the accepted delivery and its saved per-case scene.blend files
(assets scenes/cabinet_towel_pinch/native/<case>/scene.blend). The published look
(appearance/realism.py) restyles those saved scenes; this file reproduces the base renders.
"""
from pathlib import Path
import sys,argparse,json,math,time,os,socket
sys.path[:0]=[str(Path(__file__).resolve().parent),str(Path(__file__).resolve().parents[1]/'physics')]
assert sys.platform.startswith('linux'), 'Blender runs on a Linux GPU worker'
import bpy,bmesh,numpy as np
from itertools import combinations
from mathutils import Vector,Matrix
from common import save,sha,ASSETS
from geometry import LAYOUT,boxes,towel,door_transform,NEIGHBOR_CENTERS,neighbor_handle_x,neighbor_has_handle,COUNTER_DIMENSIONS,COUNTER_CENTER,COUNTER_TOP_Z
from geometry import COUNTER_FRAME_PANEL_DIMENSIONS,COUNTER_FRAME_PANEL_CENTER,COUNTER_STONE_DIMENSIONS,COUNTER_STONE_CENTER,structural_boxes
import surface_detail
from render_view import camera_for

def material(name,color,rough=.5,metal=0.):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    b=m.node_tree.nodes.get('Principled BSDF');b.inputs['Base Color'].default_value=(*color,1);b.inputs['Roughness'].default_value=rough;b.inputs['Metallic'].default_value=metal
    return m

def cube(name,dim,loc,mat,bevel=.001,parent=None):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc);o=bpy.context.object;o.name=name;o.dimensions=dim
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    if mat:o.data.materials.append(mat)
    if bevel:
        m=o.modifiers.new('Manufactured edge radius','BEVEL');m.width=bevel;m.segments=3
        m=o.modifiers.new('Weighted corner normals','WEIGHTED_NORMAL')
    if parent:o.parent=parent
    return o

def cylinder(name,rad,depth,loc,mat,rotation=(0,0,0),parent=None):
    bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=rad,depth=depth,location=loc,rotation=rotation)
    o=bpy.context.object;o.name=name;o.data.materials.append(mat)
    m=o.modifiers.new('Turned edges','BEVEL');m.width=.0006;m.segments=3
    for p in o.data.polygons:p.use_smooth=True
    if parent:o.parent=parent
    return o

def append_mat(key):
    with bpy.data.libraries.load(str(ASSETS/key/'asset.blend'),link=False)as(src,dst):dst.materials=list(src.materials)
    m=next(m for m in dst.materials if m)
    # Surface displacement is disabled: optical microstructure must not change
    # the simulated silhouette or create a visible artificial contact gap.
    for n in m.node_tree.nodes:
        if n.type=='OUTPUT_MATERIAL':
            for link in list(n.inputs['Displacement'].links):m.node_tree.links.remove(link)
    return m

def cotton_material(source):
    images=[n.image for n in source.node_tree.nodes if n.type=='TEX_IMAGE'and n.image]
    base=next(i for i in images if 'Base_color'in i.name)
    rough=next(i for i in images if 'Roughness'in i.name)
    normal=next(i for i in images if 'Normal'in i.name)
    m=material('Cotton hand towel · photographic weave',(.82,.77,.65),.85)
    n=m.node_tree.nodes;l=m.node_tree.links;b=n.get('Principled BSDF');b.inputs['Sheen Weight'].default_value=.32
    tex=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(3.,5.,1.)
    l.new(tex.outputs['UV'],mapping.inputs[0])
    im=n.new('ShaderNodeTexImage');im.image=base;l.new(mapping.outputs[0],im.inputs['Vector'])
    tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=.42;tint.inputs[2].default_value=(.88,.82,.69,1);l.new(im.outputs['Color'],tint.inputs[1])
    sep=n.new('ShaderNodeSeparateXYZ');l.new(tex.outputs['UV'],sep.inputs[0])
    masks=[]
    for lo,hi in [(.075,.092),(.111,.124),(.878,.891),(.907,.924)]:
        low=n.new('ShaderNodeMath');low.operation='GREATER_THAN';low.inputs[1].default_value=lo;l.new(sep.outputs['X'],low.inputs[0])
        high=n.new('ShaderNodeMath');high.operation='LESS_THAN';high.inputs[1].default_value=hi;l.new(sep.outputs['X'],high.inputs[0])
        mul=n.new('ShaderNodeMath');mul.operation='MULTIPLY';l.new(low.outputs[0],mul.inputs[0]);l.new(high.outputs[0],mul.inputs[1]);masks.append(mul.outputs[0])
    mask=masks[0]
    for a in masks[1:]:
        add=n.new('ShaderNodeMath');add.operation='MAXIMUM';l.new(mask,add.inputs[0]);l.new(a,add.inputs[1]);mask=add.outputs[0]
    stripe=n.new('ShaderNodeMixRGB');l.new(mask,stripe.inputs[0]);l.new(tint.outputs[0],stripe.inputs[1]);stripe.inputs[2].default_value=(.12,.19,.20,1);l.new(stripe.outputs[0],b.inputs['Base Color'])
    ri=n.new('ShaderNodeTexImage');ri.image=rough;l.new(mapping.outputs[0],ri.inputs['Vector']);l.new(ri.outputs['Color'],b.inputs['Roughness'])
    ni=n.new('ShaderNodeTexImage');ni.image=normal;l.new(mapping.outputs[0],ni.inputs['Vector'])
    # Official cotton normal uses DirectX Y; invert green for Cycles/OpenGL.
    sp=n.new('ShaderNodeSeparateColor');co=n.new('ShaderNodeCombineColor');inv=n.new('ShaderNodeMath');inv.operation='SUBTRACT';inv.inputs[0].default_value=1
    l.new(ni.outputs['Color'],sp.inputs[0]);l.new(sp.outputs['Red'],co.inputs['Red']);l.new(sp.outputs['Blue'],co.inputs['Blue']);l.new(sp.outputs['Green'],inv.inputs[1]);l.new(inv.outputs[0],co.inputs['Green'])
    nm=n.new('ShaderNodeNormalMap');nm.inputs['Strength'].default_value=.38;l.new(co.outputs[0],nm.inputs['Color']);l.new(nm.outputs[0],b.inputs['Normal'])
    return m

def uv_cabinet(o):
    uv=o.data.uv_layers.active or o.data.uv_layers.new(name='Wood grain metres')
    for p in o.data.polygons:
        normal=p.normal
        for loop in p.loop_indices:
            v=o.data.vertices[o.data.loops[loop].vertex_index].co
            import hashlib
            seed=int(hashlib.sha256(o.name.encode()).hexdigest()[:6],16)
            off=(seed%811)/811
            if abs(normal.y)>.5:uv.data[loop].uv=(v.x*2.+off,v.z*1.7+off*.53)
            elif abs(normal.z)>.5:uv.data[loop].uv=(v.x*2.+off,v.y*1.7+off*.53)
            else:uv.data[loop].uv=(v.y*2.+off,v.z*1.7+off*.53)

def prop(key,target,max_size,rotation=(0,0,0)):
    with bpy.data.libraries.load(str(ASSETS/key/'asset.blend'),link=False)as(src,dst):dst.objects=list(src.objects)
    objs=[o for o in dst.objects if o]
    for o in objs:bpy.context.collection.objects.link(o)
    # Preserve material slots/modifiers and artist relative object transforms.
    bpy.context.view_layer.update();meshes=[o for o in objs if o.type=='MESH']
    coords=[o.matrix_world@Vector(c)for o in meshes for c in o.bound_box]
    low=Vector([min(v[i]for v in coords)for i in range(3)]);high=Vector([max(v[i]for v in coords)for i in range(3)])
    center=(low+high)/2;factor=max_size/max(high-low)
    root=bpy.data.objects.new('Downloaded '+key,None);bpy.context.collection.objects.link(root)
    for o in objs:
        if o.parent is None:o.parent=root
    root.scale=(factor,)*3;root.rotation_euler=rotation
    bpy.context.view_layer.update()
    coords=[o.matrix_world@Vector(c)for o in meshes for c in o.bound_box]
    minimum=Vector([min(v[i]for v in coords)for i in range(3)]);maximum=Vector([max(v[i]for v in coords)for i in range(3)])
    root.location=Vector(target)-Vector([(minimum.x+maximum.x)/2,(minimum.y+maximum.y)/2,minimum.z])
    return [o.name for o in meshes]

def area(name,loc,target,power,size,color=(1,1,1),size_y=None):
    light=bpy.data.lights.new(name,'AREA');light.energy=power;light.color=color;light.shape='RECTANGLE';light.size=size;light.size_y=size_y or size
    o=bpy.data.objects.new(name,light);bpy.context.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def build(a,cache):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene;scene.render.engine='CYCLES';scene.cycles.device='GPU';scene.cycles.samples=a.samples;scene.cycles.use_denoising=True
    if a.backend=='CPU':
        if a.cache is not None:
            assert a.frames and len(a.frames.split(',')) <= 5 and a.samples <= 64 and not a.save_blend, 'CPU references are limited to sampled preview stills'
        scene.cycles.device='CPU'
    else:
        preferences=bpy.context.preferences.addons['cycles'].preferences;preferences.compute_device_type=a.backend;preferences.get_devices()
        for device in preferences.devices:device.use=device.type==a.backend
        if not any(d.use for d in preferences.devices):raise RuntimeError('No bound '+a.backend+' GPU')
    scene.render.resolution_x=a.width;scene.render.resolution_y=round(a.width*9/16);scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=len(cache['positions']);scene.render.image_settings.file_format='PNG'
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast'
    scene.world.use_nodes=True;scene.world.node_tree.nodes.get('Background').inputs[0].default_value=(.72,.81,.95,1);scene.world.node_tree.nodes.get('Background').inputs[1].default_value=.18
    oak=surface_detail.wood(append_mat('oak'));cotton=surface_detail.cotton(append_mat('cotton'))
    inner=material('Warm white cabinet interior',(.62,.60,.55),.64)
    dark=material('Toe kick shadow',(.06,.052,.041),.7);metal=surface_detail.brushed_metal()
    quartz=surface_detail.stone()
    oak_front_parts=[]
    # Manufactured cabinet components with separated faces and honest supports.
    for name,(dim,loc)in boxes().items():
        if 'stile'in name:
            oak_front_parts.append(cube(name,dim,loc,oak,bevel=0))
        else:
            o=cube(name,dim,loc,inner,bevel=.0006);uv_cabinet(o)
    cube('Cabinet bottom shelf',[.42,.45,.018],[.21,.265,.125],inner)
    cube('Continuous cabinet base',[2.42,.44,.024],[.36,.275,.108],inner,.0007)
    for x in [-.46,.03,.42,.83,1.08,1.40]:
        for y in [.15,.43]:cylinder('Cabinet leveling foot',.016,.116,[x,y,.058],dark)
    cube('Recessed toe kick',[2.42,.055,.10],[.36,.075,.05],dark)
    upper_panel=cube('Wooden upper cabinet frame panel',COUNTER_FRAME_PANEL_DIMENSIONS,COUNTER_FRAME_PANEL_CENTER,oak,.0003);uv_cabinet(upper_panel)
    stone_slab=cube('Stone countertop slab',COUNTER_STONE_DIMENSIONS,COUNTER_STONE_CENTER,quartz,.001)
    for name,(dimensions,center)in structural_boxes().items():
        if name=='Front cabinet stretcher':oak_front_parts.append(cube(name,dimensions,center,oak,0))
        else:
            o=cube(name,dimensions,center,oak,.0007);uv_cabinet(o)
    # An open-top carcass with stretchers lets the small inner cloth corner
    # hang freely; the mounting blocks and rear rail support the stone slab.
    for x in NEIGHBOR_CENTERS:
        oak_front_parts.append(cube('Neighbor oak door',[.465,.018,.65],[x,-.010,.445],oak,0))
        if not neighbor_has_handle(x):continue
        hx=neighbor_handle_x(x)
        for dx in [-.045,.045]:cylinder('Neighbor handle foot',.005,.027,[hx+dx,-.032,.714],metal,(math.pi/2,0,0))
        cylinder('Neighbor handle',.005,.115,[hx,-.048,.714],metal,(0,math.pi/2,0))
    # Render the same material union that the native fixed collider uses.
    # Coplanar manufacturing overlaps must not leave duplicate visible faces.
    # This changes the surface representation, not its physical envelope.
    front=oak_front_parts[0]
    bounds=[(np.array(o.location)-np.array(o.dimensions)/2,np.array(o.location)+np.array(o.dimensions)/2)for o in oak_front_parts]
    expected_front_volume=0.
    for count in range(1,len(bounds)+1):
        for selected in combinations(bounds,count):
            low=np.max([b[0]for b in selected],axis=0);high=np.min([b[1]for b in selected],axis=0)
            expected_front_volume+=(-1)**(count+1)*float(np.prod(np.maximum(0,high-low)))
    for other in oak_front_parts[1:]:
        bpy.context.view_layer.objects.active=front
        mod=front.modifiers.new('Native-equivalent oak union','BOOLEAN');mod.operation='UNION';mod.solver='EXACT';mod.object=other
        bpy.ops.object.modifier_apply(modifier=mod.name)
        bpy.data.objects.remove(other,do_unlink=True)
    front.name='Oak face frame and neighboring fronts · physical union';uv_cabinet(front)
    bm=bmesh.new();bm.from_mesh(front.data);actual_front_volume=bm.calc_volume(signed=False);bm.free()
    assert np.isclose(actual_front_volume,expected_front_volume,rtol=3e-5,atol=1e-8),'Rendered oak union does not preserve the common physical box envelope'
    edge=front.modifiers.new('Manufactured oak edge radius','BEVEL');edge.width=.0006;edge.segments=3
    front.modifiers.new('Weighted oak normals','WEIGHTED_NORMAL')
    # Complete the far end of the cabinet run; this fixed background panel is
    # over half a metre from the towel's measured motion envelope.
    o=cube('Far left cabinet door',[.395,.018,.65],[-.6725,-.010,.445],oak,.0012);uv_cabinet(o)
    for dx in [-.045,.045]:cylinder('Far left handle foot',.005,.027,[-.6725+dx,-.032,.714],metal,(math.pi/2,0,0))
    cylinder('Far left handle',.005,.115,[-.6725,-.048,.714],metal,(0,math.pi/2,0))
    cube('Kitchen wall',[3.2,.025,1.3],[.36,.555,.95],material('Grout',(.43,.42,.38),.9))
    tile=surface_detail.ceramic('Satin ivory glaze with orange peel',(.69,.70,.65),.32)
    for i in range(-9,14):
        for j in range(5):cube('Backsplash ceramic tile',[.148,.009,.073],[i*.15,.534,.86+j*.075],tile,.001)
    floor=surface_detail.ceramic('Warm porcelain with mineral speckling',(.34,.32,.28),.66)
    for i in range(-3,4):
        for j in range(-3,3):cube('Porcelain floor tile',[.598,.598,.015],[i*.6,j*.6,-.0075],floor,.0006)
    imported={}
    imported['board']=prop('board',[-.18,.12,COUNTER_TOP_Z+.001],.33,rotation=(0,0,.11))
    utensils_x,utensils_y=.72,.30
    imported['utensils']=prop('utensils',[utensils_x,utensils_y,COUNTER_TOP_Z+.001],.18)
    # Add a few tools to the actual downloaded pot rather than replacing it.
    wood=material('Beech kitchen tools',(.39,.23,.105),.53)
    imported['procedural_wooden_tools']=[]
    for idx in range(3):
        handle=cylinder('Wooden spoon handle',.004,.31,[utensils_x-.03+.025*idx,utensils_y,COUNTER_TOP_Z+.169],wood,(.08*idx,.05*(idx-1),0))
        bpy.ops.mesh.primitive_uv_sphere_add(segments=24,ring_count=12,location=(utensils_x-.03+.025*idx,utensils_y,COUNTER_TOP_Z+.309))
        spoon=bpy.context.object;spoon.name='Wooden spoon bowl';spoon.scale=(.015,.006,.026);spoon.data.materials.append(wood)
        imported['procedural_wooden_tools'].extend([handle.name,spoon.name])
    # Supported shelf contents and assembly details remain safely outside the
    # measured towel sweep. They give the open cabinet a real manufactured interior.
    shelf=cube('Inset lower shelf edge',[.414,.018,.020],[.21,.048,.137],inner,.0005)
    for x in [.014,.406]:
        for z in [.26,.34,.42,.50,.58]:
            cylinder('Shelf-pin recess',.0015,.001,[x,.09,z],dark,(0,math.pi/2,0))
    for x in [.12,.28]:
        for j in range(3):
            cylinder('Stacked stoneware coaster',.041,.012,[x,.29,.140+j*.012],surface_detail.ceramic('Stoneware glaze',(.32,.38,.34),.27))
    # Hanging door geometry follows the native ABD transform, never a prescribed curve.
    rigid_parents={}
    for name in cache['rigid_names'].tolist():
        if name not in ['door','doorstop']:continue
        root=bpy.data.objects.new(name+' native transform',None);bpy.context.collection.objects.link(root);root.rotation_mode='QUATERNION';rigid_parents[name]=root
        if name=='door':
            dy=LAYOUT['door_center_y']+.010
            o=cube('Pale oak cabinet door',[.47,.018,.65],[.235,LAYOUT['door_center_y'],.445],oak,.001,root);uv_cabinet(o)
            for dz in [-.045,.045]:cylinder('Handle mounting post',.005,.026,[.415,-.030+dy,.69+dz],metal,(math.pi/2,0,0),root)
            cylinder('Vertical brushed steel handle',.005,.112,[.415,-.046+dy,.69],metal,parent=root)
            for dz in [-.045,.045]:
                cylinder('Handle escutcheon washer',.008,.0015,[.415,-.0198+dy,.69+dz],metal,(math.pi/2,0,0),root)
            # Hinge mounting hardware is tied to its actual supporting components.
            for z in [.22,.67]:
                cylinder('Hinge pin',.004,.026,[0,LAYOUT['hinge_axis_y'],z],metal,parent=root)
                cube('Hinge leaf',[.028,.002,.03],[.020,-.018+dy,z],metal,.0004,root)
                # Screw heads and stamped cup detail on the interior surface.
                cylinder('Concealed hinge cup',.014,.002,[.032,.001+dy,z],metal,(math.pi/2,0,0),root)
                for dz in [-.010,.010]:
                    cylinder('Hinge screw head',.0026,.0015,[.045,.002+dy,z+dz],metal,(math.pi/2,0,0),root)
                    cube('Screwdriver slot',[.0033,.0002,.00055],[.045,.0029+dy,z+dz],dark,.0001,root)
        else:
            g=np.load(a.cache.parent/'doorstop_geometry.npz')
            mesh=bpy.data.meshes.new('Wedge collision-identical surface');mesh.from_pydata(g['vertices'].tolist(),[],g['faces'].tolist());mesh.update()
            o=bpy.data.objects.new('Added solid oak wedge',mesh);bpy.context.collection.objects.link(o);o.parent=root;o.data.materials.append(oak);uv_cabinet(o)
            bevel=o.modifiers.new('Wedge edge radius','BEVEL');bevel.width=.0004;bevel.segments=3
        idx=cache['rigid_names'].tolist().index(name)
        for frame,T in enumerate(cache['rigid_transforms'][:,idx],1):
            loc,rot,scale=Matrix(T.tolist()).decompose();root.location=loc;root.rotation_quaternion=rot;root.scale=scale
            for path in ['location','rotation_quaternion','scale']:root.keyframe_insert(data_path=path,frame=frame)
    mesh=bpy.data.meshes.new('Native cotton shell topology');mesh.from_pydata(cache['positions'][0].tolist(),[],cache['faces'].tolist());mesh.update()
    cloth=bpy.data.objects.new('Cotton towel',mesh);bpy.context.collection.objects.link(cloth);cloth.data.materials.append(cotton)
    uv=mesh.uv_layers.new(name='Material coordinates')
    for loop in mesh.loops:uv.data[loop.index].uv=cache['uv'][loop.vertex_index]
    for poly in mesh.polygons:poly.use_smooth=True
    cloth.shape_key_add(name='Basis');cloth.data.shape_keys.use_relative=False
    for i,positions in enumerate(cache['positions'][1:],1):
        key=cloth.shape_key_add(name='Native state %03d'%i);key.data.foreach_set('co',positions.astype(np.float32).ravel())
    keys=cloth.data.shape_keys
    for i,key in enumerate(keys.key_blocks):keys.eval_time=key.frame;keys.keyframe_insert('eval_time',frame=i+1)
    # Every output frame has an exact native key. No subframe interpolation is
    # used by the 24 FPS renderer (motion blur is disabled).
    solid=cloth.modifiers.new('Physical cotton thickness','SOLIDIFY');solid.thickness=.0008;solid.offset=0
    # A narrow stitched hem uses the same shell vertices and shape animation.
    # Optical seam follows material coordinates; no independent cloth path.
    area('Large kitchen window',[-.75,-.8,1.65],[.3,0,.55],110,.68,color=(1,.92,.81),size_y=1.25)
    area('Soft room bounce',[1.25,-.3,1.4],[.3,0,.55],23,1.2,color=(.8,.88,1))
    area('Countertop reflection',[-.2,.3,1.9],[.25,.1,.7],40,.8,color=(1,.95,.85))
    view=camera_for(LAYOUT)
    bpy.ops.object.camera_add(location=view['location_m']);cam=bpy.context.object;cam.name='Fixed handle-side camera'
    cam.rotation_euler=(Vector(view['target_m'])-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.lens=view['lens_mm'];cam.data.sensor_width=36
    cam.data.dof.use_dof=True;cam.data.dof.focus_distance=(cam.location-Vector([.39,-.025,.62])).length;cam.data.dof.aperture_fstop=9
    scene.camera=cam;scene.render.film_transparent=False
    bpy.context.view_layer.update()
    save(a.out/'scene_audit.json',dict(worker=socket.gethostname(),gpu_uuid=os.environ.get('CUDA_VISIBLE_DEVICES'),blender=bpy.app.version_string,
        camera=LAYOUT,render_camera=view,imported_objects=imported,execution_job_name=os.environ.get('PCVE_JOB_NAME'),asset_manifest_sha256=sha(ASSETS/'asset_manifest.json'),
        upper_counter_cabinet_assembly={'collision_box_dimensions_m':COUNTER_DIMENSIONS,'collision_box_center_m':COUNTER_CENTER,
            'wood_frame_panel_dimensions_m':list(upper_panel.dimensions),'wood_frame_panel_center_m':list(upper_panel.location),
            'stone_dimensions_m':list(stone_slab.dimensions),'stone_center_m':list(stone_slab.location),
            'two_layers_tile_collision_volume':bool(np.allclose(np.array(COUNTER_FRAME_PANEL_CENTER)-np.array(COUNTER_FRAME_PANEL_DIMENSIONS)/2,np.array(COUNTER_CENTER)-np.array(COUNTER_DIMENSIONS)/2,atol=1e-12)
                and np.allclose(np.array(COUNTER_STONE_CENTER)+np.array(COUNTER_STONE_DIMENSIONS)/2,np.array(COUNTER_CENTER)+np.array(COUNTER_DIMENSIONS)/2,atol=1e-12)
                and abs((COUNTER_FRAME_PANEL_CENTER[2]+COUNTER_FRAME_PANEL_DIMENSIONS[2]/2)-(COUNTER_STONE_CENTER[2]-COUNTER_STONE_DIMENSIONS[2]/2))<1e-12)},
        cloth_vertices=len(mesh.vertices),cloth_triangles=len(mesh.polygons),native_states=len(cache['positions']),
        background_static_asset_bounds={key:[min((bpy.data.objects[name].matrix_world@Vector(c))[i]for name in names for c in bpy.data.objects[name].bound_box)for i in range(3)]+[max((bpy.data.objects[name].matrix_world@Vector(c))[i]for name in names for c in bpy.data.objects[name].bound_box)for i in range(3)]for key,names in imported.items()},
        texture_images=[{'name':im.name,'width':im.size[0],'height':im.size[1],'packed':bool(im.packed_file)}for im in bpy.data.images if im.size[0]],
        static_oak_front_representation={'operation':'EXACT union of the same stile, front-stretcher and adjacent-front boxes in the native collider','input_boxes':len(oak_front_parts),'hidden_overlap_faces_removed':True,'physical_envelope_or_body_states_changed':False,'inclusion_exclusion_reference_volume_m3':expected_front_volume,'blender_boolean_volume_m3':actual_front_volume,'volume_equivalence_verified':True},
        cache_sha256=sha(a.cache)if a.cache else None,render_backend=a.backend,postprocessed_motion=False,
        geometry_only_reference=a.cache is None))
    return scene,cloth

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cache',type=Path);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--width',type=int,default=1280)
    ap.add_argument('--samples',type=int,default=64);ap.add_argument('--frames',type=str);ap.add_argument('--save-blend',action='store_true')
    ap.add_argument('--backend',choices=['OPTIX','CUDA','CPU'],default='OPTIX')
    a=ap.parse_args(sys.argv[sys.argv.index('--')+1:])
    a.out.mkdir(parents=True,exist_ok=True)
    if a.cache:cache=dict(np.load(a.cache))
    else:
        x,rest,faces,uv=towel();cache=dict(positions=x[None],faces=faces,uv=uv,rigid_names=np.array(['door']),rigid_transforms=door_transform()[None,None])
    if a.cache:
        cfg=json.loads((a.cache.parent/'simulation_config.json').read_text())
        if cfg['layout']!=LAYOUT:raise ValueError('The rendered common geometry differs from the native geometry')
    scene,cloth=build(a,cache);scene.frame_set(1)
    if a.save_blend:bpy.ops.wm.save_as_mainfile(filepath=str(a.out/'scene.blend'),compress=True)
    frames=[int(v)for v in a.frames.split(',')]if a.frames else list(range(1,len(cache['positions'])+1))
    start=time.monotonic()
    for frame in frames:
        scene.frame_set(frame);scene.render.filepath=str(a.out/'frames'/('%04d.png'%frame));bpy.ops.render.render(write_still=True)
        print('RENDER_FRAME',frame,'wall',round(time.monotonic()-start,1),flush=True)
    save(a.out/'render_completion.json',dict(complete=True,frames=frames,seconds=time.monotonic()-start,width=scene.render.resolution_x,height=scene.render.resolution_y,fps=24,samples=a.samples,worker=socket.gethostname(),gpu_uuid=os.environ['CUDA_VISIBLE_DEVICES']))

if __name__=='__main__':main()
