"""Cycles capture of the closed-ribbon physical cache (replay of the accepted states; the look module adds the environment)."""
import platform
import argparse,datetime,hashlib,json,math,os,random,subprocess,sys
from pathlib import Path
import bpy
import numpy as np
from mathutils import Matrix,Vector
sys.path.insert(0,str(Path(__file__).resolve().parent))
import render_base as old
S=Path(__file__).resolve().parent;A=old.A

def library_endgrain():
    # Retain licensed photographic colour; rebuild a transparent shader rather
    # than relying on potentially nested inherited bump/normal controls.
    with bpy.data.libraries.load(str(A/'wood_endgrain/asset.blend'),link=False) as (src,dst):
        dst.materials=[name for name in src.materials if 'Wood End Grain' in name]
    original=next(m for m in dst.materials if m)
    def images(tree):
        result=[]
        for node in tree.nodes:
            if node.bl_idname=='ShaderNodeTexImage' and node.image:result.append(node.image)
            if node.bl_idname=='ShaderNodeGroup' and node.node_tree:result+=images(node.node_tree)
        return result
    source=images(original.node_tree)
    diffuse=next(im for im in source if 'diffuse' in im.name.lower())
    normal=next((im for im in source if 'normal' in im.name.lower()),None)
    material=old.mat('scanned_endgrain',(.4,.28,.16),.66)
    nt=material.node_tree;uv=nt.nodes.new('ShaderNodeUVMap');uv.uv_map='endgrain_uv';bs=nt.nodes.get('Principled BSDF')
    photo=nt.nodes.new('ShaderNodeTexImage');photo.image=diffuse;nt.links.new(uv.outputs[0],photo.inputs['Vector'])
    mix=nt.nodes.new('ShaderNodeMixRGB');mix.inputs[0].default_value=.12;mix.inputs[2].default_value=(.32,.235,.14,1.)
    nt.links.new(photo.outputs['Color'],mix.inputs[1]);nt.links.new(mix.outputs[0],bs.inputs['Base Color'])
    bs.inputs['Specular IOR Level'].default_value=.3
    if normal:
        normal.colorspace_settings.name='Non-Color';tex=nt.nodes.new('ShaderNodeTexImage');tex.image=normal
        nm=nt.nodes.new('ShaderNodeNormalMap');nm.uv_map='endgrain_uv';nm.inputs['Strength'].default_value=.06
        nt.links.new(uv.outputs[0],tex.inputs['Vector']);nt.links.new(tex.outputs[0],nm.inputs['Color']);nt.links.new(nm.outputs[0],bs.inputs['Normal'])
    bpy.data.materials.remove(original)
    return material


def end_uv(obj,axes,tile=0):
    uv=obj.data.uv_layers.new(name='endgrain_uv')
    # Crop one real end-grain tile in the licensed atlas, avoiding the glued
    # block seams. One texture UV unit corresponds to 150 mm of wood; one tile is 50 mm wide.
    for li,loop in enumerate(obj.data.loops):
        co=obj.data.vertices[loop.vertex_index].co
        uv.data[li].uv=((tile%3+.5)/3+co[axes[0]]/.15,(tile//3+.5)/3+co[axes[1]]/.15)
    obj.data.uv_layers.active_index=0
    for index,layer in enumerate(obj.data.uv_layers):layer.active_render=index==0

def layered_birch_edge():
    m=old.mat('cut_birch_lamination_edge',(.48,.35,.22),.67);nt=m.node_tree;n=nt.nodes;l=nt.links;bs=n.get('Principled BSDF')
    tc=n.new('ShaderNodeTexCoord');xyz=n.new('ShaderNodeSeparateXYZ');l.new(tc.outputs['Object'],xyz.inputs[0])
    scale=n.new('ShaderNodeMath');scale.operation='MULTIPLY';scale.inputs[1].default_value=1/.0012;l.new(xyz.outputs['Z'],scale.inputs[0])
    fraction=n.new('ShaderNodeMath');fraction.operation='FRACT';l.new(scale.outputs[0],fraction.inputs[0])
    seam=n.new('ShaderNodeMath');seam.operation='LESS_THAN';seam.inputs[1].default_value=.055;l.new(fraction.outputs[0],seam.inputs[0])
    mapping=n.new('ShaderNodeVectorMath');mapping.operation='MULTIPLY';mapping.inputs[1].default_value=(55,2700,800);l.new(tc.outputs['Object'],mapping.inputs[0])
    grain=n.new('ShaderNodeTexNoise');grain.inputs['Scale'].default_value=1.;grain.inputs['Detail'].default_value=3.;l.new(mapping.outputs[0],grain.inputs[0])
    ramp=n.new('ShaderNodeValToRGB');ramp.color_ramp.elements[0].color=(.30,.205,.12,1);ramp.color_ramp.elements[1].color=(.56,.415,.27,1);l.new(grain.outputs['Fac'],ramp.inputs[0])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MIX';mix.inputs[2].default_value=(.15,.096,.052,1);l.new(seam.outputs[0],mix.inputs[0]);l.new(ramp.outputs[0],mix.inputs[1]);l.new(mix.outputs[0],bs.inputs['Base Color'])
    bump=n.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.18;bump.inputs['Distance'].default_value=.000018;l.new(grain.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    return m

def clean_long_grain(name,lighten=.94):
    material=old.scanned_wood(name,'oak_veneer_05',lighten,.49)
    nt=material.node_tree
    # Keep photographed metre-scale grain, with restrained sanded relief.
    for node in nt.nodes:
        if node.bl_idname=='ShaderNodeHueSaturation':node.inputs['Saturation'].default_value=.88
        if node.bl_idname=='ShaderNodeMapRange':node.inputs['To Min'].default_value=.43;node.inputs['To Max'].default_value=.62
    for node in nt.nodes:
        if node.bl_idname=='ShaderNodeNormalMap':node.inputs['Strength'].default_value=.10
        if node.bl_idname=='ShaderNodeBump':node.inputs['Strength'].default_value=.07;node.inputs['Distance'].default_value=.000002
    return material

def ribbon_coordinates(vertices,triangles,h,reference_areas=None):
    normal=np.zeros_like(vertices)
    cross=np.cross(vertices[triangles[:,1]]-vertices[triangles[:,0]],vertices[triangles[:,2]]-vertices[triangles[:,0]])
    for j in range(3):np.add.at(normal,triangles[:,j],cross)
    normal/=np.maximum(np.linalg.norm(normal,axis=1)[:,None],1e-16)
    if reference_areas is not None:
        area=np.linalg.norm(cross,axis=1)/2
        per_face_h=h*reference_areas/np.maximum(area,1e-16)
        weights=np.zeros(len(vertices));thickness=np.zeros(len(vertices))
        for j in range(3):
            np.add.at(weights,triangles[:,j],reference_areas)
            np.add.at(thickness,triangles[:,j],reference_areas*per_face_h)
        h=(thickness/np.maximum(weights,1e-16))[:,None]
    return np.concatenate([vertices+h*.5*normal,vertices-h*.5*normal])

def ribbon_mesh(vertices,triangles,uv,h,material,reference_areas,loop_length):
    n=len(vertices);faces=[tuple(t) for t in triangles]+[tuple(t[::-1]+n) for t in triangles]
    boundary={}
    for t in triangles:
        for a,b in zip(t,np.roll(t,-1)):
            key=tuple(sorted((int(a),int(b))))
            if key in boundary:boundary.pop(key)
            else:boundary[key]=(int(a),int(b))
    faces += [(b,a,a+n,b+n) for a,b in boundary.values()]
    mesh=bpy.data.meshes.new('closed_rubber_shell_mesh');mesh.from_pydata(ribbon_coordinates(vertices,triangles,h,reference_areas),[],faces);mesh.materials.append(material)
    obj=bpy.data.objects.new('physical_closed_rubber_loop',mesh);bpy.context.scene.collection.objects.link(obj)
    uv_layer=mesh.uv_layers.new(name='material_metre_coordinates')
    L=float(loop_length)
    for poly in mesh.polygons:
        coords=uv[np.asarray(poly.vertices)%n].copy()
        if np.ptp(coords[:,0])>L/2:coords[coords[:,0]<L/2,0]+=L
        for li,co in zip(poly.loop_indices,coords):uv_layer.data[li].uv=co
        poly.use_smooth=True
    bevel=obj.modifiers.new('cut_rubber_edge_rounding_25um','BEVEL');bevel.width=.000025;bevel.segments=2;bevel.angle_limit=.85
    return obj

def peg(name,x,wood,parent=None):
    shaft=old.cylinder(name,(x,0,.0095),.003,.007,wood)
    lower=old.cylinder(name+'_lower_lip',(x,0,.0080),.00365,.0004,wood)
    upper=old.cylinder(name+'_upper_lip',(x,0,.0110),.00365,.0004,wood)
    for ob in [shaft,lower,upper]:
        ob.modifiers['rounded_cut'].width=.00007
        capmat=bpy.data.materials.get('scanned_endgrain')
        if capmat:
            ob.data.materials.append(capmat);end_uv(ob,(0,1))
            for face in ob.data.polygons:
                if abs(face.normal.z)>.5:face.material_index=1
        if parent:ob.parent=parent

def secured_peg(name,x,wood,endgrain,metal,parent=None,side=-1):
    peg(name,x,wood,parent)
    cap=old.cylinder(name+'_wooden_compression_cap',(x,0,.0135),.0046,.001,wood)
    cap.modifiers['rounded_cut'].width=.00013
    cap.data.materials.append(endgrain);end_uv(cap,(0,1),7)
    for face in cap.data.polygons:
        if abs(face.normal.z)>.5:face.material_index=1
    head=old.cylinder(name+'_brass_slotted_screw',(x,0,.01425),.00145,.00065,metal)
    head.modifiers['rounded_cut'].width=.00012
    cutter=old.box(name+'_slot_tool',(x,0,.01461),(.0024,.00030,.00043),None,0.)
    boolean=head.modifiers.new('actual_machined_slot','BOOLEAN');boolean.operation='DIFFERENCE';boolean.object=cutter
    bpy.context.view_layer.objects.active=head;bpy.ops.object.modifier_apply(modifier=boolean.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    # A narrow compression saddle follows the actual fixed material arc.
    # The ideal no-slip attachment is solved by the body-frame boundary,
    # rather than a stiff penalty spring between rubber and fixture.
    angles=np.linspace(math.pi/2,3*math.pi/2,25) if side<0 else np.linspace(-math.pi/2,math.pi/2,25)
    coords=[]
    for angle in angles:
        for radius,z in [(.00364,.00865),(.00390,.00865),(.00364,.01035),(.00390,.01035)]:
            coords.append((x+radius*math.cos(angle),radius*math.sin(angle),z))
    faces=[]
    for i in range(len(angles)-1):
        a=4*i;b=a+4
        faces += [(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)]
    faces += [(0,1,3,2),(len(coords)-4,len(coords)-2,len(coords)-1,len(coords)-3)]
    mesh=bpy.data.meshes.new(name+'_saddle_mesh');mesh.from_pydata(coords,[],faces);mesh.materials.append(metal)
    saddle=bpy.data.objects.new(name+'_material_clamping_saddle',mesh);bpy.context.scene.collection.objects.link(saddle)
    rounding=saddle.modifiers.new('fine_folded_metal_edges','BEVEL');rounding.width=.000035;rounding.segments=2
    for obj in [cap,head,saddle]:
        if parent:obj.parent=parent

def fixed_left_clamp(x,wood,ply,endgrain):
    # The same original anvil remains inside the new jaws; active native
    # contacts and the fixed material arc are unchanged. The jaw exit plane
    # is x, and every added solid stays behind that plane.
    peg('anchor_wooden_pin',x,wood)
    pad=old.mat('dense_dark_cork_gripping_pads',(.025,.028,.022),.82)
    steel=old.mat('brushed_zinc_steel_clamp_strap',(.19,.205,.215),.38,.92)
    ns=steel.node_tree.nodes;ls=steel.node_tree.links;bs=ns.get('Principled BSDF')
    anisotropy=bs.inputs.get('Anisotropic IOR Level') or bs.inputs.get('Anisotropic')
    if anisotropy is not None:anisotropy.default_value=.18
    tc=ns.new('ShaderNodeTexCoord');stretch=ns.new('ShaderNodeVectorMath');stretch.operation='MULTIPLY';stretch.inputs[1].default_value=(90.,28000.,2000.)
    ls.new(tc.outputs['Object'],stretch.inputs[0]);noise=ns.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=1.;noise.inputs['Detail'].default_value=2.
    ls.new(stretch.outputs[0],noise.inputs['Vector']);rough=ns.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.31;rough.inputs['To Max'].default_value=.44
    ls.new(noise.outputs['Fac'],rough.inputs[0]);ls.new(rough.outputs[0],bs.inputs['Roughness'])
    screwmat=old.mat('worn_steel_wood_screw_heads',(.115,.125,.135),.32,.95)
    lower=old.box('anchor_clamp_lower_plywood_jaw',(x-.014,0,.007225),(.028,.024,.00245),ply,.00012)
    upper=old.box('anchor_clamp_upper_solid_wood_jaw',(x-.014,0,.01355),(.028,.024,.006),wood,.00022)
    for ob in [lower,upper]:
        ob.data.materials.append(endgrain);end_uv(ob,(1,2),5)
        for face in ob.data.polygons:
            if abs(face.normal.x)>.5:face.material_index=1
    # 1.6 mm clear throat exactly matches the original clamped material width.
    old.box('anchor_clamp_lower_grip_pad',(x-.014,0,.008575),(.028,.0238,.00025),pad,.000035)
    old.box('anchor_clamp_upper_grip_pad',(x-.014,0,.010425),(.028,.0238,.00025),pad,.000035)
    strap=old.box('anchor_clamp_load_spreading_steel_strap',(x-.0145,0,.01685),(.024,.023,.0006),steel,.00012)
    # Common M3-sized wood screws pass through the upper jaw into the base.
    for side in [-1,1]:
        sx=x-.0155;sy=side*.0083;tag='anchor_clamp_screw_'+str(side)
        shaft=old.cylinder(tag+'_shank',(sx,sy,.0096),.00125,.0152,screwmat,48)
        shaft.modifiers['rounded_cut'].width=.00004
        washer=old.cylinder(tag+'_washer',(sx,sy,.0173),.0035,.0003,steel,64)
        washer.modifiers['rounded_cut'].width=.00007
        profile=[(.00245,0),(.0028,.0003),(.0028,.00115),(.00255,.0019),(.00185,.00235)]
        verts=[];faces=[];segments=64;bottom=.01745
        for radius,z in profile:
            for i in range(segments):
                a=i*math.tau/segments;verts.append((sx+radius*math.cos(a),sy+radius*math.sin(a),bottom+z))
        for j in range(len(profile)-1):
            for i in range(segments):
                q=j*segments+i;n=j*segments+(i+1)%segments;faces.append((q,n,n+segments,q+segments))
        faces += [tuple(range(segments-1,-1,-1)),tuple((len(profile)-1)*segments+i for i in range(segments))]
        mesh=bpy.data.meshes.new(tag+'_pan_head_mesh');mesh.from_pydata(verts,[],faces);mesh.materials.append(screwmat)
        head=bpy.data.objects.new(tag+'_pan_head',mesh);bpy.context.scene.collection.objects.link(head)
        for face in mesh.polygons:face.use_smooth=len(face.vertices)==4
        for angle in [0.,math.pi/2]:
            cutter=old.box(tag+'_recess_tool',(sx,sy,.01972),(.00305,.00044,.00085),None,0.)
            cutter.rotation_euler.z=angle+.18*side
            boolean=head.modifiers.new('actual_phillips_recess','BOOLEAN');boolean.operation='DIFFERENCE';boolean.object=cutter
            bpy.context.view_layer.objects.active=head;bpy.ops.object.modifier_apply(modifier=boolean.name);bpy.data.objects.remove(cutter,do_unlink=True)
        bevel=head.modifiers.new('small_machined_edge_rounds','BEVEL');bevel.width=.000045;bevel.segments=2


def main(args,look=None):
    if not args.cpu and not os.environ.get('PCVE_GPU_POLICY_PASSED'):raise RuntimeError('Use the UUID-gated launcher')
    info=json.loads((args.input/'physics.json').read_text());p=info['physics']
    physics_audit=None
    if not args.preview:
        physics_audit=json.loads((args.audit).read_text())
        if args.review_candidate:
            if not (physics_audit.get('visual_candidate_eligible') or physics_audit.get('render_review_eligible')) or not args.revision.endswith('_review'):raise RuntimeError('Candidate audit missing or candidate not explicitly labelled')
        elif not physics_audit.get('passed'):raise RuntimeError('Full physical gate has not passed')
    z=np.load(args.input/'states.npz');positions=z['band_vertices'];trace=z['trace'];tri=z['triangles'];uv=z['uv'];times=z['times']
    if p['band_present'][0]:
        left=z['clamped_left_ids'];right=z['clamped_right_ids']
        if np.linalg.norm(positions[:,left]-positions[0,left],axis=2).max()>1e-9:raise RuntimeError('Fixed rubber material anchor moved')
        displacement=trace[:,1]-trace[0,1]
        if np.linalg.norm(positions[:,right]-positions[0,right]-displacement[:,None,None]*np.array([1.,0.,0.]),axis=2).max()>1e-9:raise RuntimeError('Rubber detached from slider')
    bpy.ops.wm.read_factory_settings(use_empty=True);scene=bpy.context.scene;scene.unit_settings.system='METRIC'
    birch=clean_long_grain('sanded_oak_face_on_plywood',.91)
    for node in birch.node_tree.nodes:
        if node.bl_idname=='ShaderNodeNormalMap':node.inputs['Strength'].default_value=.10
        if node.bl_idname=='ShaderNodeBump':node.inputs['Strength'].default_value=.08;node.inputs['Distance'].default_value=.000004
    pine=clean_long_grain('light_sanded_wood_rails',.83)
    endgrain=library_endgrain();edge=layered_birch_edge()
    table=old.imported('farmhouse_table');lo,hi=old.bounds(table)
    old.transformed_group(table,Matrix.Translation(Vector((-(lo.x+hi.x)/2,-(lo.y+hi.y)/2,-hi.z))))
    base=old.box('six_mm_plywood_guide',(0,0,.003),(.300,.066,.006),birch,.00030);base.data.materials.append(edge)
    for face in base.data.polygons:
        if abs(face.normal.z)<.5:face.material_index=1
    iron=old.mat('oxidized_brad_steel',(.11,.115,.12),.58,.75)
    glue=old.mat('dry_wood_glue',(.35,.24,.12),.72)
    for sign in [-1,1]:
        rail=old.box('handmade_guide_rail_'+str(sign),(0,sign*.0275,.012),(.300,.010,.012),pine,.00030)
        rail.data.materials.append(endgrain);end_uv(rail,(1,2),1 if sign<0 else 2)
        for face in rail.data.polygons:
            if abs(face.normal.x)>.5:face.material_index=1
        for x in [-.134,-.030,.127]:
            nail=old.cylinder('flush_small_brad',(x,sign*.0275,.01801),.00052,.00012,iron,24);nail.modifiers['rounded_cut'].width=.00002
        old.stroke('thin_glue_squeeze_out_'+str(sign),[(x,sign*(.0325+.00003*math.sin(91*x)),.00609) for x in np.linspace(-.132,.135,39)],.00010,glue)
    brass=old.mat('satin_worn_brass_fasteners',(.29,.20,.085),.34,.94)
    fixed_left_clamp(p['anchor_x_m'],pine,birch,endgrain)
    root=bpy.data.objects.new('slider_rigid_root',None);scene.collection.objects.link(root)
    blockwood=clean_long_grain('separately_sanded_solid_block',.85)
    body=old.box('solid_wood_slider',(0,0,.018),(.055,.042,.024),blockwood,.00065);body.parent=root;body.data.materials.append(endgrain)
    end_uv(body,(1,2))
    for face in body.data.polygons:
        if abs(face.normal.x)>.5:face.material_index=1
    tab=old.box('low_wooden_pull_tab',(-.035,0,.007),(.020,.020,.002),birch,.00009);tab.parent=root;tab.data.materials.append(edge)
    for face in tab.data.polygons:
        if abs(face.normal.z)<.5:face.material_index=1
    secured_peg('slider_pin',p['attachment_offset_m'],pine,endgrain,brass,root,side=1)
    if p['stopper_present'][0]:
        for sign in [-1,1]:old.box('added_stop_ear_'+str(sign),(p['stopper_position_m'][0],sign*.016,.016),(.006,.010,.020),pine,.00016)
    for i,(x,y,sx,angle) in enumerate([(.105,.074,.055,.12),(.096,.092,.070,-.10)]):
        ob=old.box('sawn_offcut_'+str(i),(x,y,.004),(sx,.009,.008),pine,.00013);ob.rotation_euler.z=angle
        ob.data.materials.append(endgrain);end_uv(ob,(1,2),3+i)
        for face in ob.data.polygons:
            if abs(face.normal.x)>.5:face.material_index=1
    # A few actual small wood chips remain beside the offcuts, outside the
    # moving toy. Static story detail, common to source and every edit.
    rng=random.Random(20261102)
    for i in range(19):
        x=rng.uniform(-.139,-.074);y=rng.uniform(-.098,-.054)
        if -.087<y<-.058:continue
        chip=old.box('small_saw_chip_'+str(i),(x,y,.00012),(rng.uniform(.00045,.00120),rng.uniform(.00015,.00032),.00024),pine,.000035)
        chip.rotation_euler.z=rng.uniform(-math.pi,math.pi)
    graphite=old.mat('workshop_pencil_marks',(.045,.042,.037),.9)
    for i,x in enumerate([-.077,-.025,.027,.079]):
        old.stroke('hand_pencil_measurement_tick_'+str(i),[(x+rng.uniform(-.00005,.00005),-.0185+j*.00023,.006018) for j in range(9)],.000055,graphite)
    old.handwritten_paper()
    for ob in scene.objects:
        if ob.name.startswith('handdrawn_pencil_line_'):ob.data.bevel_depth*=1.7
    paper_ink=bpy.data.materials.get('faint_graphite')
    if paper_ink:paper_ink.node_tree.nodes.get('Principled BSDF').inputs['Base Color'].default_value=(.035,.033,.029,1.)
    # Handwritten dimension note on the physical sheet, sharing its warp.
    paper_root=bpy.data.objects.get('paper_and_ink')
    glyphs={
        '3':[(0,.9),(.3,1),(.8,.95),(1,.7),(.8,.55),(.4,.5),(.8,.45),(1,.2),(.8,.04),(.25,0),(0,.12)],
        '0':[(.45,0),(.1,.15),(0,.5),(.15,.9),(.5,1),(.85,.85),(1,.5),(.9,.15),(.45,0)],
        'm':[(0,0),(0,.65),(.35,.7),(.45,.45),(.45,0),(.45,.5),(.7,.68),(1,.5),(1,0)]}
    for i,char in enumerate('300mm'):
        points=[]
        for xx,yy in glyphs[char]:
            x=-.016+i*.0034+xx*.0023+rng.uniform(-.00007,.00007);y=.029+yy*.0045
            ink_height=.00036+.00025*(x/.061)**4+.00010*math.sin(y*65);points.append((x,y,ink_height))
        mark=old.stroke('handwritten_dimension_'+str(i),points,.000052,graphite);mark.parent=paper_root
    pencils=old.imported('pencil');kept=[]
    for ob in pencils:
        if ob.name in {'pencil.004','graphite.004'}:kept.append(ob)
        else:bpy.data.objects.remove(ob,do_unlink=True)
    lo,hi=old.bounds(kept);mid=(lo+hi)/2
    transform=Matrix.Translation(Vector((.025,-.046,0)))@Matrix.Rotation(math.pi/2-.13,4,'Z')@Matrix.Translation(Vector((-mid.x,-mid.y,-lo.z+.0001)))
    old.transformed_group(kept,transform)
    rubber=old.mat('natural_latex_matte_tan',(.32,.16,.055),.59)
    bs=rubber.node_tree.nodes.get('Principled BSDF');bs.inputs['IOR'].default_value=1.47
    bs.inputs['Subsurface Weight'].default_value=.025;bs.inputs['Subsurface Scale'].default_value=.00015
    nt=rubber.node_tree;tc=nt.nodes.new('ShaderNodeTexCoord');noise=nt.nodes.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=8000
    nt.links.new(tc.outputs['UV'],noise.inputs[0]);bump=nt.nodes.new('ShaderNodeBump');bump.inputs['Strength'].default_value=.05;bump.inputs['Distance'].default_value=.0000015
    nt.links.new(noise.outputs[0],bump.inputs['Height']);nt.links.new(bump.outputs[0],bs.inputs['Normal'])
    rest=z['rest_vertices'];reference_areas=np.linalg.norm(np.cross(rest[tri[:,1]]-rest[tri[:,0]],rest[tri[:,2]]-rest[tri[:,0]]),axis=1)/2
    moving=None
    if p['band_present'][0]:moving=ribbon_mesh(positions[0],tri,uv,p['band_thickness_m'],rubber,reference_areas,p['loop_rest_m'])
    if moving:
        moving.cycles.use_deform_motion=True
        moving.cycles.motion_steps=3  # 2^3+1 = 9 deformation evaluations per shutter.
    # Indoor capture with one large physical window and a weak cool return.
    scene.world=bpy.data.worlds.new('indoor_workshop_HDRI');scene.world.use_nodes=True
    nt=scene.world.node_tree;bg=nt.nodes.get('Background');env=nt.nodes.new('ShaderNodeTexEnvironment');env.image=bpy.data.images.load(str(A/'artist_workshop/artist_workshop_2k.exr'))
    tc=nt.nodes.new('ShaderNodeTexCoord');mapping=nt.nodes.new('ShaderNodeMapping');mapping.inputs['Rotation'].default_value[2]=1.12
    nt.links.new(tc.outputs['Generated'],mapping.inputs[0]);nt.links.new(mapping.outputs[0],env.inputs[0]);nt.links.new(env.outputs[0],bg.inputs[0]);bg.inputs[1].default_value=.08
    def area(name,loc,energy,size,color):
        data=bpy.data.lights.new(name,'AREA');data.energy=energy;data.shape='RECTANGLE';data.size=size[0];data.size_y=size[1];data.color=color
        ob=bpy.data.objects.new(name,data);scene.collection.objects.link(ob);ob.location=loc;ob.rotation_euler=(Vector((0,0,.012))-ob.location).to_track_quat('-Z','Y').to_euler()
    area('soft_window',(.18,-.26,.46),18.,(.32,.44),(1.,.97,.93))
    area('weak_wall_return',(-.28,.20,.32),.45,(.50,.50),(.88,.94,1.))
    bpy.ops.object.camera_add(location=(.085,-.365,.365));cam=bpy.context.object
    target=Vector((-.002,.008,.012));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler()
    cam.data.lens=58.;cam.data.sensor_width=36.;cam.data.dof.use_dof=True;cam.data.dof.focus_distance=(Vector((0,0,.013))-cam.location).length;cam.data.dof.aperture_fstop=11.;scene.camera=cam
    scene.render.engine='CYCLES';scene.cycles.samples=args.samples;scene.cycles.use_denoising=True;scene.cycles.denoiser='OPENIMAGEDENOISE';scene.cycles.denoising_use_gpu=not args.cpu
    scene.cycles.denoising_prefilter='ACCURATE';scene.cycles.use_adaptive_sampling=True;scene.cycles.adaptive_threshold=.003 if not args.preview else .025;scene.cycles.adaptive_min_samples=128 if not args.preview else 16
    devices=[]
    if args.cpu:
        scene.cycles.device='CPU';scene.render.threads_mode='FIXED';scene.render.threads=int(os.environ.get('PCVE_CPU_RENDER_THREADS','4'));devices=[{'name':'remote CPU','type':'CPU','used':True}]
    else:
        prefs=bpy.context.preferences.addons['cycles'].preferences;prefs.compute_device_type='OPTIX';prefs.get_devices()
        for device in prefs.devices:device.use=device.type=='OPTIX';devices.append({'name':device.name,'type':device.type,'used':device.use})
        scene.cycles.device='GPU'
    scene.cycles.seed=17;scene.cycles.use_animated_seed=False;scene.cycles.max_bounces=12;scene.cycles.diffuse_bounces=5;scene.cycles.glossy_bounces=5
    scene.render.use_persistent_data=True;scene.render.resolution_x=args.width;scene.render.resolution_y=round(args.width*9/16);scene.render.resolution_percentage=100
    scene.render.fps=24;scene.frame_start=1;scene.frame_end=round(float(times[-1])*24);scene.render.use_motion_blur=True;scene.render.motion_blur_shutter=1/3
    scene.render.image_settings.file_format='PNG';scene.render.image_settings.color_mode='RGB';scene.view_settings.view_transform='AgX';scene.view_settings.look='AgX - Medium High Contrast';scene.view_settings.exposure=-.30
    for ob in scene.objects:
        if ob.parent==root:ob.pass_index=1
        if ob==moving:ob.pass_index=2
        if ob.name.startswith('added_stop'):ob.pass_index=3
        if ob.name.startswith(('anchor_clamp_','anchor_wooden_pin')):ob.pass_index=4
    scene.view_layers[0].use_pass_object_index=True;scene.use_nodes=True;nt=scene.node_tree;nt.nodes.clear();rl=nt.nodes.new('CompositorNodeRLayers');comp=nt.nodes.new('CompositorNodeComposite');nt.links.new(rl.outputs['Image'],comp.inputs[0])
    out=args.out;out.mkdir(parents=True,exist_ok=True)
    for index,key in [(1,'slider'),(2,'band'),(3,'stopper'),(4,'clamp')]:
        mask=nt.nodes.new('CompositorNodeIDMask');mask.index=index;mask.use_antialiasing=True;nt.links.new(rl.outputs['IndexOB'],mask.inputs[0]);writer=nt.nodes.new('CompositorNodeOutputFile');writer.base_path=str(out/'masks'/key);writer.file_slots[0].path='';writer.format.file_format='PNG';writer.format.color_mode='BW';nt.links.new(mask.outputs[0],writer.inputs[0])
    if look is not None:look(scene,cam,p,moving,out)
    frames=1+times*24
    if moving:
        moving.shape_key_add(name='Basis');moving.data.shape_keys.use_relative=False
        for i in range(1,len(times)):
            key=moving.shape_key_add(name=f'solver_{i:04d}');key.data.foreach_set('co',ribbon_coordinates(positions[i],tri,p['band_thickness_m'],reference_areas).astype(np.float32).ravel())
        keys=moving.data.shape_keys
        for frame,key in zip(frames,keys.key_blocks):keys.eval_time=key.frame;keys.keyframe_insert(data_path='eval_time',frame=float(frame))
        for curve in keys.animation_data.action.fcurves:
            for point in curve.keyframe_points:point.interpolation='LINEAR'
    for i,frame in enumerate(frames):root.location.x=float(trace[i,1]);root.keyframe_insert(data_path='location',frame=float(frame))
    for curve in root.animation_data.action.fcurves:
        for point in curve.keyframe_points:point.interpolation='LINEAR'
    scene.frame_set(1);bpy.context.view_layer.update()
    new_jaws=[ob for ob in scene.objects if ob.name.startswith('anchor_clamp_')]
    jaw_max_x=max((ob.matrix_world@Vector(co)).x for ob in new_jaws for co in ob.bound_box)
    if jaw_max_x>p['anchor_x_m']+1e-7:raise RuntimeError('New fixture extends into the free-band domain; recompute physics before capture')
    free_ids=np.setdiff1d(np.arange(len(positions[0])),z['clamped_left_ids'])
    free_clearance=float(positions[:,free_ids,0].min()-jaw_max_x-p['band_thickness_m']*.5-.000025)
    if p['band_present'][0] and free_clearance<.0007:raise RuntimeError('Cached free particles do not clear the new static jaws')
    snapshot={}
    for ob in scene.objects:
        row={'type':ob.type,'matrix_world':[list(r) for r in ob.matrix_world]}
        if ob.type=='MESH':
            coordinates=np.array([list(vertex.co) for vertex in ob.data.vertices],dtype='<f4')
            row.update(mesh_vertices_sha256=hashlib.sha256(coordinates.tobytes()).hexdigest(),vertices=len(coordinates),materials=[slot.material.name if slot.material else None for slot in ob.material_slots])
        if ob.type=='LIGHT':row.update(energy_w=ob.data.energy,color=list(ob.data.color))
        snapshot[ob.name]=row
    (out/'scene_snapshot.json').write_text(json.dumps({'frame':1,'physical_time_s':0.,'objects':snapshot,'common_baseline_layout':True},indent=2),encoding='utf-8')
    uuid=os.environ.get('CUDA_VISIBLE_DEVICES','')
    try:active=subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid,process_name,used_memory','--format=csv,noheader,nounits'],text=True)
    except (OSError,subprocess.CalledProcessError):active=''
    shared=[]
    for line in active.splitlines():
        fields=[x.strip() for x in line.split(',')]
        if not args.cpu and fields and fields[0]==uuid and int(fields[1])!=os.getpid():shared.append(fields[1])
    prov={'case':args.case,'revision':args.revision,'hostname':platform.node(),'worker_ip':os.environ.get('PCVE_WORKER_IP',platform.node()),'gpu_uuid':uuid,'cuda_visible_devices':uuid,
        'other_processes_on_gpu_at_first_frame':shared,
        'blender':bpy.app.version_string,'cycles_devices':devices,'samples':args.samples,'fps':24,'resolution':[args.width,round(args.width*9/16)],
        'simulation_cache_sha256':hashlib.sha256((args.input/'states.npz').read_bytes()).hexdigest(),
        'camera_matrix_world':[list(row) for row in cam.matrix_world],'lens_mm':58.,'fstop':11.,'motion_blur_shutter_fraction':1/3,'exposure_s':1/72,
        'real_physical_time':True,'before_first_frame_processes':active,'cache':args.cache,'mesh':'closed ribbon shell with actual width direction','render_backend':'CPU' if args.cpu else 'GPU',
        'diagnostic_preview':args.preview,'cache_duration_s':float(times[-1])}
    prov.update(review_candidate=args.review_candidate,accepted_benchmark_gt=False,material_calibrated=False)
    prov['boundary_conditions']=info['boundary_conditions']
    prov['native_cache_reused_without_physics_change']=True
    prov['native_origin_revision']='accepted_increment'
    prov['native_reuse_geometry_check']={'new_jaw_max_x_m':jaw_max_x,'fixed_interface_x_m':p['anchor_x_m'],'sampled_free_particle_clearance_m':free_clearance,
        'all_added_solids_behind_fixed_material_exit_plane':True,'original_anvil_contacts_retained':True,'scope':'fixed material interface and unchanged native anvil; no new free-particle or wooden-slider collisions; ideal bonded clamp, not a resolved screw-preload/contact-pressure model'}
    prov['reconstruction_revision']='visible_two_screw_clamp'
    prov['fixed_clamp_design']={'jaw_dimensions_m':[.028,.024,.006],'jaw_front_x_m':p['anchor_x_m'],'slot_lower_z_m':.0087,'slot_upper_z_m':.0103,'screw_count':2,'wood_screw_nominal_diameter_m':.003,'bond_scope':'same finite left material arc as original native cache; additional geometry remains behind its exit plane'}
    from bpy_extras.object_utils import world_to_camera_view
    clamp=[ob for ob in scene.objects if ob.pass_index==4];points=[world_to_camera_view(scene,cam,ob.matrix_world@Vector(co)) for ob in clamp for co in ob.bound_box]
    prov['fixture_readability']={'bbox_pixels':[min(co.x for co in points)*args.width,min(1-co.y for co in points)*scene.render.resolution_y,max(co.x for co in points)*args.width,max(1-co.y for co in points)*scene.render.resolution_y],
        'camera_sees_exit_side':bool(cam.location.x>p['anchor_x_m']),'same_static_assembly_in_all_six_cases':True,'exit_rays':[]}
    if moving:
        centers=positions[0].reshape(-1,2,3).mean(axis=1)
        for sign in [-1,1]:
            candidates=centers[(centers[:,1]*sign>0)&(centers[:,0]>p['anchor_x_m']+.0025)&(centers[:,0]<p['anchor_x_m']+.01)]
            target=Vector(candidates[np.argmin(candidates[:,0])]);direction=target-cam.location
            hit,loc,normal,face,obj,matrix=scene.ray_cast(bpy.context.evaluated_depsgraph_get(),cam.location,direction.normalized(),distance=direction.length+.001)
            prov['fixture_readability']['exit_rays'].append({'leg_sign':sign,'target_world_m':list(target),'first_visible_object':obj.name if hit else None,'rubber_visible':bool(hit and obj.name==moving.name)})
    prov['deformation_motion_step_setting']=3
    prov['shutter_deformation_samples']=9 if moving else 0
    prov['asset_manifest_sha256']={key:hashlib.sha256((A/key/'manifest.json').read_bytes()).hexdigest() for key in ['farmhouse_table','pencil','oak_veneer_05','wood_endgrain','artist_workshop']}
    if physics_audit is not None:
        prov['capture_start_audit_path']='verification/capture_start_audit.json'
        prov['numerical_validation_passed']=physics_audit['passed'];prov['known_physical_limitations']=physics_audit['remaining_limitations']
    (out/'render_provenance.json').write_text(json.dumps(prov,indent=2),encoding='utf-8')
    for frame in args.frames or range(args.start,args.end+1):
        target=out/f'{frame:04d}.png'
        if target.exists() and not args.overwrite:continue
        scene.frame_set(frame);bpy.context.view_layer.update();scene.render.filepath=str(target);bpy.ops.render.render(write_still=True)
        record={**prov,'frame':frame,'physical_time_s':(frame-1)/24,'pid':os.getpid(),'utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'rgb_sha256':hashlib.sha256(target.read_bytes()).hexdigest()}
        folder=out/'frame_provenance';folder.mkdir(exist_ok=True);(folder/f'{frame:04d}.json').write_text(json.dumps(record,indent=2));print('FRAME_DONE',args.case,frame,flush=True)
    if args.save_blend:
        scene.frame_set(1)
        for im in list(bpy.data.images):
            if im.users==0:bpy.data.images.remove(im)
        bpy.ops.file.pack_all();bpy.ops.wm.save_as_mainfile(filepath=str(out/'source_scene.blend'),compress=True)

def parse_args(extra=None):
    ap=argparse.ArgumentParser();ap.add_argument('--case',default='source');ap.add_argument('--cache',default='accepted_increment');ap.add_argument('--revision',default='base_look')
    ap.add_argument('--width',type=int,default=1280);ap.add_argument('--samples',type=int,default=512);ap.add_argument('--start',type=int,default=1);ap.add_argument('--end',type=int,default=96);ap.add_argument('--frames',nargs='*',type=int)
    ap.add_argument('--input',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--audit',type=Path,required=True);ap.add_argument('--preview',action='store_true');ap.add_argument('--review-candidate',action='store_true');ap.add_argument('--save-blend',action='store_true');ap.add_argument('--overwrite',action='store_true');ap.add_argument('--cpu',action='store_true')
    for add in extra or []:add(ap)
    return ap.parse_args(sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else [])

if __name__=='__main__':
    main(parse_args())
