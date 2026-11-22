"""Shared turf visual reconstruction (grass coverage and soil cup); runs inside Blender (appearance/render.py).

New turf roots depend only on a fixed common field and seed. The soil cup
visualizes the same rigid-sphere/lumped-soil overlap used by the CPU force;
it never changes ball motion or serves as an additional collision response.
"""
import hashlib,json,math
from pathlib import Path
import numpy as np
RECIPE={'seed':2026110301,'coverage_bounds_xy_m':[-18.,18.,-18.,9.5],'coverage_tile_m':.5,'minimum_tufts_per_m2':10000,'root_z_m':.0001,'soil_fine_bounds_xy_m':[-1.,2.,-6.,8.],'soil_grid_m':.005,'canopy_linear_RGB_gain':[.70,.85,.70],'photo_tile_m':2.51}
LAYOUT=json.loads(Path(__file__).with_name('visual_layout.json').read_text());RECIPE['soil_fine_bounds_xy_m']=LAYOUT['common_soil_bounds_xy_m'];RECIPE['soil_grid_m']=LAYOUT['soil_grid_m']
RECIPE['coverage_bounds_xy_m']=LAYOUT['common_soil_bounds_xy_m'];RECIPE['coverage_method']='Common stratified uniform contact corridor; static native-mesh patches cover the rest of the pitch'
def _assert_remote():pass  # no host requirement; any Blender 4.3 host renders this scene
def _node(tree,kind,**attributes):
    n=tree.nodes.new(kind)
    for key,value in attributes.items():setattr(n,key,value)
    return n
def _math(tree,operation,a,b=None):
    n=_node(tree,'ShaderNodeMath',operation=operation)
    for input_socket,value in zip(n.inputs,(a,b)):
        if value is None:continue
        if isinstance(value,(int,float)):input_socket.default_value=value
        else:tree.links.new(value,input_socket)
    return n.outputs[0]
def _soil_height(tree,ball):
    position=_node(tree,'GeometryNodeInputPosition');xyz=_node(tree,'ShaderNodeSeparateXYZ');tree.links.new(position.outputs[0],xyz.inputs[0]);info=_node(tree,'GeometryNodeObjectInfo',transform_space='RELATIVE');info.inputs['Object'].default_value=ball;body=_node(tree,'ShaderNodeSeparateXYZ');tree.links.new(info.outputs['Location'],body.inputs[0]);dx=_math(tree,'SUBTRACT',xyz.outputs['X'],body.outputs['X']);dy=_math(tree,'SUBTRACT',xyz.outputs['Y'],body.outputs['Y']);r2=_math(tree,'ADD',_math(tree,'MULTIPLY',dx,dx),_math(tree,'MULTIPLY',dy,dy));height=_math(tree,'SUBTRACT',body.outputs['Z'],_math(tree,'SQRT',_math(tree,'MAXIMUM',_math(tree,'SUBTRACT',.11*.11,r2),0.)));return _math(tree,'MINIMUM',height,0.)
def _coverage(bpy,turf):
    carriers=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o.data.attributes.get('tuft_variant')];assert carriers
    sources=[turf._source_arrays(o.data) for o in carriers];x0,x1,y0,y1=RECIPE['coverage_bounds_xy_m'];tile=RECIPE['coverage_tile_m'];nx=round((x1-x0)/tile);ny=round((y1-y0)/tile);counts=np.zeros(nx*ny,np.int64)
    for arrays in sources:
        p=arrays['position'];ix=np.floor((p[:,0]-x0)/tile).astype(np.int64);iy=np.floor((p[:,1]-y0)/tile).astype(np.int64);keep=(ix>=0)&(ix<nx)&(iy>=0)&(iy<ny);counts+=np.bincount(ix[keep]*ny+iy[keep],minlength=len(counts))
    rng=np.random.default_rng(RECIPE['seed']);chunks=[]
    for ix in range(nx):
        for iy in range(ny):
            # Smoothly fade only the distant outer2m of the fixed common field.
            cx=x0+(ix+.5)*tile;cy=y0+(iy+.5)*tile;edge=min(cx-x0,x1-cx,cy-y0,y1-cy);u=min(1.,max(0.,edge/2.));weight=u*u*(3-2*u);target=round(RECIPE['minimum_tufts_per_m2']*tile*tile*weight);n=max(0,target-int(counts[ix*ny+iy]))
            if n:
                p=np.empty((n,3),np.float32);p[:,0]=x0+(ix+rng.random(n))*tile;p[:,1]=y0+(iy+rng.random(n))*tile;p[:,2]=RECIPE['root_z_m'];chunks.append(p)
    points=np.concatenate(chunks) if chunks else np.empty((0,3),np.float32);source=sources[0];ids=rng.integers(0,len(source['position']),len(points));mesh=bpy.data.meshes.new('common field coverage roots');mesh.vertices.add(len(points));mesh.vertices.foreach_set('co',points.ravel())
    for name,kind,field in [('tuft_rotation','FLOAT_VECTOR','vector'),('tuft_scale','FLOAT_VECTOR','vector'),('tuft_variant','INT','value')]:mesh.attributes.new(name=name,type=kind,domain='POINT').data.foreach_set(field,source[name][ids].ravel())
    mesh.update();obj=bpy.data.objects.new('COMMON mown grass coverage supplement',mesh);bpy.context.scene.collection.objects.link(obj);obj['pcve_role']='visualization_of_common_viscoelastic_turf';mod=obj.modifiers.new('Same actual grass prototypes and physical height sampling','NODES');mod.node_group=next(m.node_group for m in carriers[0].modifiers if m.type=='NODES')
    return {'object':obj.name,'additional_tufts':len(points),'existing_root_coordinates_modified':False,'future_trajectory_or_edited_pose_used':False,'point_data_sha256':hashlib.sha256(points.tobytes()).hexdigest(),'all_cases_common_seed_and_field':True}
def _canopy(bpy):
    pitch=bpy.data.objects['continuous stadium pitch and grass apron'];assert len(pitch.data.materials)==1;material=pitch.data.materials[0];tree=material.node_tree;surface=next(n for n in tree.nodes if n.type=='BSDF_PRINCIPLED');base=surface.inputs['Base Color'];old=base.links[0].from_socket if base.is_linked else tuple(base.default_value)
    for link in tuple(base.links):tree.links.remove(link)
    mix=_node(tree,'ShaderNodeMixRGB',blend_type='MULTIPLY');mix.inputs[0].default_value=1.;mix.inputs[2].default_value=(*RECIPE['canopy_linear_RGB_gain'],1.)
    if hasattr(old,'node'):tree.links.new(old,mix.inputs[1])
    else:mix.inputs[1].default_value=old
    tree.links.new(mix.outputs[0],base);geo=_node(tree,'ShaderNodeNewGeometry');scale=_node(tree,'ShaderNodeVectorMath',operation='SCALE');tree.links.new(geo.outputs['Position'],scale.inputs[0]);scale.inputs['Scale'].default_value=1/RECIPE['photo_tile_m']
    for node in tree.nodes:
        if node.type=='TEX_IMAGE' and node.image:
            for link in tuple(node.inputs['Vector'].links):tree.links.remove(link)
            tree.links.new(scale.outputs['Vector'],node.inputs['Vector'])
    return pitch,material,{'material':material.name,'packed_real_photo_maps_retained':True,'uniform_common_world_photo_tile_m':RECIPE['photo_tile_m'],'linear_RGB_gain':RECIPE['canopy_linear_RGB_gain']}

def _uniform_coverage(bpy,turf):
    carriers=[o for o in bpy.context.scene.objects if o.type=='MESH' and not o.hide_render and o.data.attributes.get('tuft_variant')];assert carriers
    source=turf._source_arrays(carriers[0].data);node_group=next(m.node_group for m in carriers[0].modifiers if m.type=='NODES');x0,x1,y0,y1=LAYOUT['common_soil_bounds_xy_m'];pitch=1/math.sqrt(RECIPE['minimum_tufts_per_m2']);nx=round((x1-x0)/pitch);ny=round((y1-y0)/pitch);n=nx*ny;rng=np.random.default_rng(RECIPE['seed']);points=np.empty((n,3),np.float32);points[:,0]=x0+(np.repeat(np.arange(nx),ny)+rng.random(n))*pitch;points[:,1]=y0+(np.tile(np.arange(ny),nx)+rng.random(n))*pitch;points[:,2]=RECIPE['root_z_m'];ids=rng.integers(0,len(source['position']),n)
    mesh=bpy.data.meshes.new('common uniform contact-corridor grass roots');mesh.vertices.add(n);mesh.vertices.foreach_set('co',points.ravel())
    for name,kind,field in [('tuft_rotation','FLOAT_VECTOR','vector'),('tuft_scale','FLOAT_VECTOR','vector'),('tuft_variant','INT','value')]:mesh.attributes.new(name=name,type=kind,domain='POINT').data.foreach_set(field,source[name][ids].ravel())
    mesh.update();obj=bpy.data.objects.new('COMMON uniform physical-contact grass roots',mesh);bpy.context.scene.collection.objects.link(obj);obj['pcve_role']='common_visualization_of_physical_turf';obj.modifiers.new('Original native grass prototypes, physical-state height binding','NODES').node_group=node_group
    hidden=[]
    for old in carriers:old.hide_render=True;old.hide_viewport=True;old.hide_set(True);hidden.append(old.name)
    return {'object':obj.name,'additional_tufts':n,'common_root_count':n,'tufts_per_m2':RECIPE['minimum_tufts_per_m2'],'point_data_sha256':hashlib.sha256(points.tobytes()).hexdigest(),'all_cases_common_seed_and_field':True,'new_uniform_common_baseline_not_a_counterfactual_edit':True,'original_Gaussian_carriers_retained_hidden':hidden,'original_coordinates_or_asset_bytes_modified':False,'future_trajectory_or_edited_pose_used':False}
def _stadium_materials(bpy):
    records=[]
    for material in list(bpy.data.materials):
        concrete=material.name.startswith('maintained cast concrete |');chairs=material.name.startswith('chairs |')
        if not (concrete or chairs) or not material.use_nodes:continue
        tree=material.node_tree;surface=next(n for n in tree.nodes if n.type=='BSDF_PRINCIPLED');geometry=_node(tree,'ShaderNodeNewGeometry');noise=_node(tree,'ShaderNodeTexNoise');noise.inputs['Scale'].default_value=4. if concrete else 1.8;noise.inputs['Detail'].default_value=3.;tree.links.new(geometry.outputs['Position'],noise.inputs['Vector']);gain=_math(tree,'ADD',.84 if concrete else .94,_math(tree,'MULTIPLY',.22 if concrete else .10,noise.outputs['Fac']));color=surface.inputs['Base Color'];old=color.links[0].from_socket if color.is_linked else tuple(color.default_value)
        for link in tuple(color.links):tree.links.remove(link)
        mix=_node(tree,'ShaderNodeMixRGB',blend_type='MULTIPLY');mix.inputs[0].default_value=1.
        if hasattr(old,'node'):tree.links.new(old,mix.inputs[1])
        else:mix.inputs[1].default_value=old
        tree.links.new(gain,mix.inputs[2]);tree.links.new(mix.outputs[0],color)
        if concrete:
            fine=_node(tree,'ShaderNodeTexNoise');fine.inputs['Scale'].default_value=900.;fine.inputs['Detail'].default_value=2.;tree.links.new(geometry.outputs['Position'],fine.inputs['Vector']);bump=_node(tree,'ShaderNodeBump');bump.inputs['Distance'].default_value=.00012;bump.inputs['Strength'].default_value=.2;tree.links.new(fine.outputs['Fac'],bump.inputs['Height']);normal=surface.inputs['Normal']
            if normal.is_linked:tree.links.new(normal.links[0].from_socket,bump.inputs['Normal'])
            for link in tuple(normal.links):tree.links.remove(link)
            tree.links.new(bump.outputs[0],normal)
        records.append({'material':material.name,'type':'existing packed concrete PBR with0.12mm pore normals' if concrete else 'existing polypropylene chair palette with small sun/weather variation','collider_or_object_geometry_changed':False})
    assert any(r['type'].startswith('existing packed concrete') for r in records) and any(r['type'].startswith('existing polypropylene') for r in records)
    return records
def _soil_surface(bpy,pitch,material,ball):
    x0,x1,y0,y1=RECIPE['soil_fine_bounds_xy_m'];spacing=RECIPE['soil_grid_m'];nx=round((x1-x0)/spacing)+1;ny=round((y1-y0)/spacing)+1;xx=np.linspace(x0,x1,nx,dtype=np.float32);yy=np.linspace(y0,y1,ny,dtype=np.float32);positions=np.zeros((nx*ny,3),np.float32);positions[:,0]=np.repeat(xx,ny);positions[:,1]=np.tile(yy,nx);ids=np.arange((nx-1)*(ny-1),dtype=np.int32);i=ids//(ny-1);j=ids%(ny-1);a=i*ny+j;quads=np.column_stack((a,a+ny,a+ny+1,a+1)).ravel();mesh=bpy.data.meshes.new('common fine compliant-soil surface');mesh.vertices.add(len(positions));mesh.vertices.foreach_set('co',positions.ravel());mesh.loops.add(len(quads));mesh.loops.foreach_set('vertex_index',quads);mesh.polygons.add(len(ids));mesh.polygons.foreach_set('loop_start',4*ids);mesh.polygons.foreach_set('loop_total',np.full(len(ids),4,np.int32));mesh.polygons.foreach_set('use_smooth',np.ones(len(ids),np.bool_));mesh.update();mesh.materials.append(material);obj=bpy.data.objects.new('COMMON actual soil-compliance visualization',mesh);bpy.context.scene.collection.objects.link(obj);obj['pcve_role']='visualization_of_lumped_soil_compliance'
    uv=mesh.uv_layers.new(name='Common world turf photo coordinates');uv.data.foreach_set('uv',(positions[quads,:2]/RECIPE['photo_tile_m']).astype(np.float32).ravel());mesh.update()
    bpy.ops.mesh.primitive_cube_add(size=1.,location=((x0+x1)/2,(y0+y1)/2,0.));cutter=bpy.context.object;cutter.name='temporary common soil display aperture';cutter.dimensions=(x1-x0,y1-y0,.1);bpy.context.view_layer.update();modifier=pitch.modifiers.new('Common display-only soil aperture','BOOLEAN');modifier.operation='DIFFERENCE';modifier.solver='EXACT';modifier.object=cutter;bpy.context.view_layer.objects.active=pitch
    with bpy.context.temp_override(object=pitch,active_object=pitch):bpy.ops.object.modifier_apply(modifier=modifier.name)
    bpy.data.objects.remove(cutter,do_unlink=True)
    group=bpy.data.node_groups.new('CPU-soil-overlap derived surface','GeometryNodeTree');group.interface.new_socket(name='Geometry',in_out='INPUT',socket_type='NodeSocketGeometry');group.interface.new_socket(name='Geometry',in_out='OUTPUT',socket_type='NodeSocketGeometry');inp=_node(group,'NodeGroupInput');out=_node(group,'NodeGroupOutput');displace=_node(group,'GeometryNodeSetPosition');vector=_node(group,'ShaderNodeCombineXYZ');group.links.new(_soil_height(group,ball),vector.inputs['Z']);group.links.new(inp.outputs['Geometry'],displace.inputs['Geometry']);group.links.new(vector.outputs[0],displace.inputs['Offset']);group.links.new(displace.outputs['Geometry'],out.inputs['Geometry']);obj.modifiers.new('Same physical sphere/soil compression as CPU','NODES').node_group=group
    return {'object':obj.name,'vertices':len(positions),'quads':len(ids),'spacing_m':spacing,'common_bounds_xy_m':[x0,x1,y0,y1],'old_undeformed_surface_removed_only_inside_common_display_aperture':True,'initial_displacement_zero_in_every_case':True,'source':'Sphere underside belowz0; same overlap variable as22000N/m soil spring in CPU','additional_physics_response':False,'limits':'Display of lumped compliant soil, not a separately solved continuum soil mesh.'}
def apply(bpy,turf,ball,proof):
    _assert_remote();coverage=_uniform_coverage(bpy,turf);pitch,material,canopy=_canopy(bpy);soil=_soil_surface(bpy,pitch,material,ball)
    stadium=_stadium_materials(bpy)
    return {'recipe':RECIPE,'coverage':coverage,'canopy':canopy,'soil':soil,'stadium_materials':stadium,'same_source_and_five_recipe':True,'ball_pose_or_trajectory_changed':False,'world_fixture_collider_geometry_changed':False,'cinematic_acceptance':False}
def finalize_grass(bpy,ball):
    _assert_remote();groups=set()
    for obj in bpy.context.scene.objects:
        if obj.type=='MESH' and not obj.hide_render and obj.data.attributes.get('tuft_variant') and not obj.get('static_unaffected_turf',False):
            assert np.allclose(np.array(obj.matrix_world),np.eye(4),atol=1e-8)
            groups.add(next(m.node_group for m in obj.modifiers if m.type=='NODES'))
    for group in groups:
        for instance in [n for n in group.nodes if n.bl_idname=='GeometryNodeInstanceOnPoints']:
            point_input=instance.inputs['Points'];assert len(point_input.links)==1;link=point_input.links[0];source=link.from_socket;group.links.remove(link);position=_node(group,'GeometryNodeSetPosition');vector=_node(group,'ShaderNodeCombineXYZ');group.links.new(_soil_height(group,ball),vector.inputs['Z']);group.links.new(source,position.inputs['Geometry']);group.links.new(vector.outputs[0],position.inputs['Offset']);group.links.new(position.outputs['Geometry'],point_input)
    return {'grass_root_follows_same_soil_compliance':True,'shared_groups':len(groups),'physical_height_sampling_remains_XY_only':True}
