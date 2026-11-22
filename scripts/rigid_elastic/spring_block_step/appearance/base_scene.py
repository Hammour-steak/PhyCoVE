"""Blender Cycles base scene (scaffold) used by appearance/render.py: metric helpers,
launch platform, guide parts, table, camera and render settings. No entry of its own."""
import json
import math
import os
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from scene_common import *
import bpy
import numpy as np
from mathutils import Vector, Matrix

def material(name,color,rough=.5,metal=0):
    m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
    bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Base Color'].default_value=(*color,1)
    bs.inputs['Roughness'].default_value=rough;bs.inputs['Metallic'].default_value=metal
    return m

def pbr(asset):
    manifest=json.loads((ASSETS/'manifest.json').read_text(encoding='utf8'))
    mat=material('Scanned '+asset,(.4,.3,.2));n=mat.node_tree.nodes;l=mat.node_tree.links
    bs=n.get('Principled BSDF')
    uv=n.new('ShaderNodeTexCoord')
    for row in manifest['files']:
        if row['asset']!=asset:continue
        image=bpy.data.images.load(str(ASSETS/row['path']),check_existing=True)
        tex=n.new('ShaderNodeTexImage');tex.image=image;l.new(uv.outputs['UV'],tex.inputs['Vector'])
        if 'nor_gl' in row['path']:
            image.colorspace_settings.name='Non-Color';normal=n.new('ShaderNodeNormalMap')
            normal.inputs['Strength'].default_value=.45
            l.new(tex.outputs['Color'],normal.inputs['Color']);l.new(normal.outputs['Normal'],bs.inputs['Normal'])
        elif 'rough' in row['path']:
            image.colorspace_settings.name='Non-Color';l.new(tex.outputs['Color'],bs.inputs['Roughness'])
        else:l.new(tex.outputs['Color'],bs.inputs['Base Color'])
    return mat

def metric_uv(obj,period=.5,offset=(.13,.27)):
    uv=obj.data.uv_layers.active or obj.data.uv_layers.new()
    for poly in obj.data.polygons:
        axis=max(range(3),key=lambda k:abs(poly.normal[k]))
        a,b=((1,2) if axis==0 else (0,2) if axis==1 else (0,1))
        for li in poly.loop_indices:
            co=obj.data.vertices[obj.data.loops[li].vertex_index].co
            uv.data[li].uv=(co[a]/period+offset[0],co[b]/period+offset[1])

def cube(name,location,size,mat,bevel=.0005,period=.5,offset=(.13,.27)):
    bpy.ops.mesh.primitive_cube_add(size=1,location=location)
    o=bpy.context.object;o.name=name;o.dimensions=size
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    metric_uv(o,period,offset)
    if mat:o.data.materials.append(mat)
    if bevel:
        mod=o.modifiers.new('Small machined edge radius, documented render envelope','BEVEL');mod.width=bevel;mod.segments=3
        o.modifiers.new('Weighted face normals','WEIGHTED_NORMAL')
    return o

def cylinder(name,location,radius,length,mat,axis='X',vertices=64):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=radius,depth=length,location=location)
    o=bpy.context.object;o.name=name
    o.rotation_euler=(0,math.pi/2,0) if axis=='X' else (0,0,0)
    o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    mod=o.modifiers.new('Deburred metal edge','BEVEL');mod.width=.00014;mod.segments=2
    o.modifiers.new('Weighted cap normals','WEIGHTED_NORMAL')
    return o

def tube(name,x0,x1,outer,inner,mat):
    nv=64;vs=[];fs=[]
    for x in [x0,x1]:
        for r in [outer,inner]:
            vs += [(x,r*math.cos(i*2*math.pi/nv),.14+r*math.sin(i*2*math.pi/nv)) for i in range(nv)]
    for i in range(nv):
        j=(i+1)%nv
        fs += [(i,j,2*nv+j,2*nv+i),(nv+j,nv+i,3*nv+i,3*nv+j),
               (i,nv+i,nv+j,j),(2*nv+j,3*nv+j,3*nv+i,2*nv+i)]
    me=bpy.data.meshes.new(name);me.from_pydata(vs,[],fs);me.update()
    o=bpy.data.objects.new(name,me);bpy.context.collection.objects.link(o);me.materials.append(mat)
    for p in me.polygons:p.use_smooth=p.index%4<2
    return o

def coil_points(length,c):
    turns=c['spring_active_turns']+2;N=turns*64;R=c['spring_mean_diameter_m']/2;r=c['spring_wire_diameter_m']/2
    result=[]
    for i in range(N+1):
        t=i/N*turns;theta=t*2*math.pi
        if t<1:x=t*2*r;dx=2*r/(2*math.pi)
        elif t>turns-1:x=length-2*r+(t-(turns-1))*2*r;dx=2*r/(2*math.pi)
        else:x=2*r+(t-1)/(turns-2)*(length-4*r);dx=(length-4*r)/(2*math.pi*(turns-2))
        center=Vector((c['spring_anchor_x_m']+x,R*math.cos(theta),.14+R*math.sin(theta)))
        tangent=Vector((dx,-R*math.sin(theta),R*math.cos(theta))).normalized()
        n=Vector((0,math.cos(theta),math.sin(theta)));b=tangent.cross(n).normalized()
        for j in range(10):
            ph=2*math.pi*j/10;result.append(tuple(center+r*(math.cos(ph)*n+math.sin(ph)*b)))
    return result

def make_coil(c,q):
    rest=c['spring_rest_length_m'];comp=rest-c['spring_initial_compression_m']
    vs=coil_points(comp,c);fs=[]
    for i in range(len(vs)//10-1):
        for j in range(10):
            a=i*10+j;b=i*10+(j+1)%10;fs.append((a,b,b+10,a+10))
    fs += [tuple(reversed(range(10))),tuple(range(len(vs)-10,len(vs)))]
    me=bpy.data.meshes.new('Closed 16-turn steel coil');me.from_pydata(vs,[],fs);me.update()
    o=bpy.data.objects.new('spring | solved axial mode',me);bpy.context.collection.objects.link(o)
    me.materials.append(material('Spring steel, lightly oiled',(.31,.34,.38),.24,.97))
    for p in me.polygons:p.use_smooth=True
    o.shape_key_add(name='Compressed');key=o.shape_key_add(name='Natural length')
    for v,co in zip(key.data,coil_points(rest,c)):v.co=co
    for f,value in enumerate(q):
        key.value=float(value/c['spring_initial_compression_m']);key.keyframe_insert('value',frame=f+1)
    return o

def import_stationery():
    path=ASSETS/'stationery_supplies/stationery_supplies.gltf'
    before=set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    objects=[o for o in bpy.data.objects if o not in before]
    # Source is a metric asset library with vertically exploded presentation.
    # Build one plausible household arrangement before defining interventions.
    root=bpy.data.objects.new('Scanned stationery common baseline',None);bpy.context.collection.objects.link(root)
    for o in objects:
        if o.parent is None:o.parent=root
    bpy.context.view_layer.update()
    points=[o.matrix_world@Vector(p) for o in objects if o.type=='MESH' for p in o.bound_box]
    low=Vector(tuple(min(p[i] for p in points) for i in range(3)))
    high=Vector(tuple(max(p[i] for p in points) for i in range(3)))
    pen_count=0;layout=[]
    for o in objects:
        if o.type!='MESH':continue
        pts=[o.matrix_world@Vector(p) for p in o.bound_box]
        lo=Vector(tuple(min(p[i] for p in pts) for i in range(3)))
        hi=Vector(tuple(max(p[i] for p in pts) for i in range(3)))
        center=(lo+hi)/2;extent=hi-lo
        rotation=Matrix.Identity(4)
        if max(extent.x,extent.y)>.08 and extent.z<.03:
            i=pen_count;pen_count+=1
            if i<3:
                angle=-math.pi/2+.10*(i-1)
                rotation=Matrix.Rotation(angle,4,'Y') if extent.x>extent.y else Matrix.Rotation(-angle,4,'X')
                target=Vector((-.14+(i-1)*.006,.305+(i-1)*.005,.092))
            else:
                rotation=Matrix.Rotation(.10*(i-3)-.12,4,'Z')
                target=Vector((.09+.014*(i%2),.255+.024*(i-3),.002+extent.z/2))
        elif extent.z>.04:
            target=Vector((-.14,.305,.001+extent.z/2))
        else:target=Vector((.15,.345,.001+extent.z/2))
        o.matrix_world=Matrix.Translation(target)@rotation@Matrix.Translation(-center)@o.matrix_world
        layout.append({'object':o.name,'extent_m':list(extent),'baseline_center_m':list(target)})
    for im in bpy.data.images:
        if im.source=='FILE' and not im.packed_file and not Path(bpy.path.abspath(im.filepath,library=im.library)).is_file():
            candidate=ASSETS/'stationery_supplies/textures'/Path(im.filepath.replace('\\','/')).name
            if candidate.is_file():im.filepath=str(candidate);im.reload()
    return {'mesh_count':sum(o.type=='MESH' for o in objects),'original_extent_m':list(high-low),'common_baseline_layout':layout}

def aim(o,target):o.rotation_euler=(Vector(target)-o.location).to_track_quat('-Z','Y').to_euler()

def build(c,states):
    bpy.ops.object.select_all(action='SELECT');bpy.ops.object.delete(use_global=False)
    scene=bpy.context.scene
    table=pbr('wood_table_001');ply=pbr('plywood');wood=pbr('fine_grained_wood')
    steel=material('Brushed guide steel',(.38,.41,.45),.26,.88)
    brass=material('Guide bushing bronze',(.34,.21,.07),.3,.8)
    aluminum=material('Anodized aluminum pusher',(.42,.46,.5),.28,.85)
    cube('Craft table',(.28,0,-.025),(1.8,.9,.05),table,.004,1.5)
    cube('lower | fixed plywood board',c['lower_position_m'],c['lower_size_m'],ply,.00045,.5,offset=(.21,.19))
    cube('upper | fixed plywood board',c['upper_position_m'],c['upper_size_m'],ply,.00045,.5,offset=(.17,.63))
    # Real plywood edge laminations, laid within the nominal board envelope.
    lam1=material('Ply end layers light',(.39,.26,.14),.64);lam2=material('Ply end layers dark',(.19,.105,.046),.68)
    for ident in ['upper','lower']:
        x,y,z=c[ident+'_position_m'];sx,sy,sz=c[ident+'_size_m']
        for side in [-1,1]:
            for j in range(9):
                zz=z-sz/2+(j+.5)*sz/9
                cube(f'{ident} laminated front edge {side} {j}',(x,y+side*(sy/2-.00005),zz),
                     (sx-.001,.00012,sz/9*.84),lam1 if j%2 else lam2,0)
        for j in range(9):
            zz=z-sz/2+(j+.5)*sz/9
            cube(f'{ident} laminated end {j}',(x+sx/2-.00005,y,zz),(.00012,sy-.001,sz/9*.84),lam1 if j%2 else lam2,0)
    for i,x in enumerate([-.26,.075]):cube('Upper spacer '+str(i),(x,0,.0775),(.045,.23,.025),wood,.0006,.6)
    # Under-board supports meet the table and remain clear of the moving path.
    for x in [-.26,.32,.88]:cube('Lower spacer '+str(x),(x,0,.02),(.05,.24,.04),wood,.0006,.6)
    cube('Backstop',(-.291,0,.151),(.022,.10,.072),ply,.001,.5)
    for yy in [-.037,.037]:
        screw=cylinder('Backstop fixing screw',(-.303,yy,.148),.0031,.0018,steel)
        cube('Phillips slot A',(-.304,yy,.148),(.0002,.004,.00065),material('Recess metal'+str(yy),(.06,.064,.07),.4,.6),.0001)
    tube('Fixed hollow guide sleeve',-.279,-.209,.0043,.0035,brass)
    names=list(states['body_names']);positions=states['positions'];quats=states['quaternions']
    block=cube('block',c['block_position_m'],c['block_size_m'],wood,.00045,.6,offset=(.42,.38))
    dynamic={'block':block}
    # End-grain pores, separately assigned only to the cut x faces.
    end=material('Cut end grain',(.20,.125,.062),.57)
    n=end.node_tree.nodes;l=end.node_tree.links;tex=n.new('ShaderNodeTexNoise');tex.inputs['Scale'].default_value=110
    tex.inputs['Detail'].default_value=3;coord=n.new('ShaderNodeTexCoord');mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(.02,1,1)
    l.new(coord.outputs['Generated'],mapping.inputs[0]);l.new(mapping.outputs[0],tex.inputs['Vector'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000025;bump.inputs['Strength'].default_value=.2
    l.new(tex.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs['Normal'],n.get('Principled BSDF').inputs['Normal'])
    block.data.materials.append(end)
    for poly in block.data.polygons:
        if abs(poly.normal.x)>.9:poly.material_index=1
    if 'block' not in names:  # DELETE block: the native states hold no block
        del dynamic['block'];bpy.data.objects.remove(block,do_unlink=True)
    if 'obstacle' in names:
        dynamic['obstacle']=cube('obstacle',c['obstacle_position_m'],c['obstacle_size_m'],ply,.00045,.5,offset=(.64,.31))
    if 'pusher' in names:
        dynamic['pusher']=cube('pusher',(-.196,0,.14),(.002,.042,.030),aluminum,.00035)
        qi=names.index('pusher');q=positions[:,qi,0]-(c['spring_anchor_x_m']+c['spring_rest_length_m']-c['spring_initial_compression_m'])
        make_coil(c,q)
        middle=tube('Moving telescopic guide sleeve',-.268,-.201,.0034,.00265,steel)
        rod=cylinder('Moving inner guide rod',(-.2295,0,.14),.0025,.069,steel)
        for f,v in enumerate(q):
            middle.location.x=float(v*.5);middle.keyframe_insert('location',frame=f+1)
            rod.location.x=-.2295+float(v);rod.keyframe_insert('location',frame=f+1)
        # Fixed guide stop is internal, at the natural-length travel limit.
    for name,o in dynamic.items():
        idx=names.index(name);o.rotation_mode='QUATERNION'
        for f,(pos,quat) in enumerate(zip(positions[:,idx],quats[:,idx])):
            o.location=pos+np.array([-.001,0,0]) if name=='pusher' else pos
            o.rotation_quaternion=quat;o.keyframe_insert('location',frame=f+1);o.keyframe_insert('rotation_quaternion',frame=f+1)
    imported=import_stationery()
    print('SCENE_PHASE imported_stationery',imported,flush=True)
    # Common household craft context outside the interaction corridor.
    paper=material('Warm offwhite paper',(.72,.70,.64),.83)
    cube('Sketch sheet',(.59,.31,.0008),(.29,.18,.0007),paper,.001)
    # A loosely drawn construction diagram on the sheet, shared by all cases.
    ink=material('Graphite sketch',(.10,.105,.11),.85)
    for i in range(4):cube('Sketch pencil line '+str(i),(.54+i*.035,.31,.00118),(.0005,.115,.00005),ink,0)
    for x in [-.45,.99]:
        cube('Table leg '+str(x),(x,.23,-.4),(.065,.065,.76),wood,.003,.6)
    wall=material('Warm lime plaster',(.57,.55,.49),.9)
    cube('Back wall',(0,1.25,.5),(5,.08,3),wall,.0)
    # Photograph-like window softbox, low fill and a real room as reflection context.
    scene.world=bpy.data.worlds.new('Daylight room');scene.world.use_nodes=True
    scene.world.node_tree.nodes['Background'].inputs[0].default_value=(.65,.73,.85,1)
    scene.world.node_tree.nodes['Background'].inputs[1].default_value=.20
    def area(name,loc,target,power,size,color):
        d=bpy.data.lights.new(name,'AREA');d.energy=power;d.shape='DISK';d.size=size;d.color=color
        o=bpy.data.objects.new(name,d);bpy.context.collection.objects.link(o);o.location=loc;aim(o,target)
    area('Large left window',(-.9,-.45,1.25),(.12,0,.06),110,1.05,(1,.91,.79))
    area('Soft far wall bounce',(.75,.6,1.05),(.15,0,.08),35,.9,(.77,.86,1))
    bpy.ops.object.camera_add(location=(.88,-1.62,.72));camera=bpy.context.object;camera.name='Fixed side front camera'
    aim(camera,(.16,0,.065));camera.data.lens=55;camera.data.sensor_width=36
    camera.data.dof.use_dof=True;camera.data.dof.focus_distance=(camera.location-Vector((.2,0,.10))).length
    camera.data.dof.aperture_fstop=10
    scene.camera=camera;scene.render.fps=FPS;scene.frame_start=1;scene.frame_end=FRAMES
    print('SCENE_PHASE camera_lights_ready',flush=True)
    scene.render.engine='CYCLES';scene.cycles.samples=128;scene.cycles.use_denoising=True
    scene.cycles.device='GPU';scene.render.use_persistent_data=True
    backend=os.environ.get('PCVE_CYCLES_BACKEND','CUDA')
    print('SCENE_PHASE configuring_cycles',backend,flush=True)
    prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type=backend;prefs.get_devices()
    for dev in prefs.devices:dev.use=dev.type==backend
    print('SCENE_PHASE devices_ready',[(dev.name,dev.type,dev.use) for dev in prefs.devices],flush=True)
    scene.render.resolution_x=1920;scene.render.resolution_y=1080;scene.render.resolution_percentage=100
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.render.image_settings.color_depth='8'
    scene.render.film_transparent=False
    scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.2
    scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=.25
    for action in bpy.data.actions:
        for curve in action.fcurves:
            for key in curve.keyframe_points:key.interpolation='LINEAR'
    return {'camera':{'location':list(camera.location),'rotation_euler':list(camera.rotation_euler),'lens_mm':camera.data.lens},
            'imported_stationery':imported,'render_bevel_envelope_m':.00045,
            'scene_scope':'Native transforms and axial-mode helix replay; fixed camera, light, textures and existing initial poses across all six cases.'}
