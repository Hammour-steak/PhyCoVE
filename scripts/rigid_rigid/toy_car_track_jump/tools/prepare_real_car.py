"""Normalize the CC0 Khronos toy-car mesh and separate its four real wheel assemblies.

Run inside Blender: blender -b --python-exit-code 1 --python prepare_real_car.py -- [--out DIR | --replace-registered-asset]
Writes red_toy_car_library.blend and car_dimensions.json to --out (default renders/toy_car_track_jump/prepared/car_150mm).
--replace-registered-asset writes assets/scenes/toy_car_track_jump/car_150mm instead; a rebuilt .blend does not match the
sha256 registered in assets.json.
"""
import argparse
import json
import sys
import math
from pathlib import Path
import bpy
from mathutils import Vector

ROOT=Path(__file__).resolve().parents[4]
SOURCE=ROOT/'assets/scenes/toy_car_track_jump/room_dressing/toy_car/ToyCar.glb'
ASSETS=ROOT/'assets/scenes/toy_car_track_jump/car_150mm'
DEFAULT_OUT=ROOT/'renders/toy_car_track_jump/prepared/car_150mm'
LENGTH=.15
AXLE_Y=[-.013357255,.010600236]
AXLE_Z=.00362124
BODY_MIN_Y=-.01897447369992733
BODY_MAX_Y=.019404949620366096
SCALE=LENGTH/(BODY_MAX_Y-BODY_MIN_Y)
MID_Y=sum(AXLE_Y)/2
COM_ABOVE_AXLE=.0078
SOURCE_RADIUS=(AXLE_Z-.0009924222249537706)*SCALE
RADIUS=.0127
WHEEL_RADIAL_SCALE=RADIUS/SOURCE_RADIUS
TRACK=.0572

def components(data):
    adj=[[] for _ in data.vertices]
    for edge in data.edges:
        a,b=edge.vertices;adj[a].append(b);adj[b].append(a)
    seen=set()
    for v in range(len(adj)):
        if v in seen:continue
        stack=[v];seen.add(v);ids=[]
        while stack:
            i=stack.pop();ids.append(i)
            for k in adj[i]:
                if k not in seen:seen.add(k);stack.append(k)
        yield ids

def mapped(v):
    return Vector(((-v.y+MID_Y)*SCALE,v.x*SCALE,(v.z-AXLE_Z)*SCALE-COM_ABOVE_AXLE))

def red_paint(m):
    n,l=m.node_tree.nodes,m.node_tree.links
    bs=n.get('Principled BSDF')
    old=bs.inputs['Base Color'].links[0].from_socket
    sep=n.new('ShaderNodeSeparateColor');sep.mode='RGB';l.new(old,sep.inputs[0])
    def math_node(operation,a,b):
        o=n.new('ShaderNodeMath');o.operation=operation
        if hasattr(a,'is_output'):l.new(a,o.inputs[0])
        else:o.inputs[0].default_value=a
        if hasattr(b,'is_output'):l.new(b,o.inputs[1])
        else:o.inputs[1].default_value=b
        return o.outputs[0]
    mask=math_node('MULTIPLY',math_node('GREATER_THAN',sep.outputs['Green'],math_node('MULTIPLY',sep.outputs['Red'],1.13)),
        math_node('GREATER_THAN',sep.outputs['Green'],math_node('MULTIPLY',sep.outputs['Blue'],1.12)))
    bw=n.new('ShaderNodeRGBToBW');l.new(old,bw.inputs[0])
    tint=n.new('ShaderNodeMixRGB');tint.blend_type='MULTIPLY';tint.inputs[0].default_value=1.
    tint.inputs[1].default_value=(3.6,.035,.05,1);l.new(bw.outputs[0],tint.inputs[2])
    mix=n.new('ShaderNodeMixRGB');mix.blend_type='MIX';l.new(mask,mix.inputs[0]);l.new(old,mix.inputs[1]);l.new(tint.outputs[0],mix.inputs[2])
    l.new(mix.outputs[0],bs.inputs['Base Color'])
    bs.inputs['Coat Weight'].default_value=.22;bs.inputs['Coat Roughness'].default_value=.18
    m.name='Red painted die-cast toy, original mapped chrome, rubber and printed decals'

def parse_args():
    argv=sys.argv[sys.argv.index('--')+1:] if '--' in sys.argv else []
    p=argparse.ArgumentParser(prog='prepare_real_car.py',description='Build the 150 mm red toy-car library (Blender).')
    g=p.add_mutually_exclusive_group()
    g.add_argument('--out',type=Path,default=DEFAULT_OUT,help='output folder (default: renders/toy_car_track_jump/prepared/car_150mm)')
    g.add_argument('--replace-registered-asset',action='store_true',help='write into assets/scenes/toy_car_track_jump/car_150mm')
    a=p.parse_args(argv)
    return ASSETS if a.replace_registered_asset else a.out.expanduser().resolve()

def main():
    out=parse_args()
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(SOURCE))
    originals=list(bpy.context.scene.objects)
    roots={}
    for name in ['car_body','wheel_0','wheel_1','wheel_2','wheel_3']:
        obj=bpy.data.objects.new(name,None);bpy.context.collection.objects.link(obj);roots[name]=obj
    wheelbase=(AXLE_Y[1]-AXLE_Y[0])*SCALE
    positions=[Vector((x,y,-COM_ABOVE_AXLE)) for x in [wheelbase/2,-wheelbase/2] for y in [-TRACK/2,TRACK/2]]
    for i,pos in enumerate(positions):roots['wheel_'+str(i)].location=pos
    counts=[0]*5
    for source in originals:
        if source.type!='MESH' or source.name.startswith('Fabric'):continue
        data=source.data;pts=[source.matrix_world@v.co for v in data.vertices]
        groups={i:0 for i in range(len(pts))}
        if source.name=='ToyCar':
            for ids in components(data):
                xs=[pts[i].x for i in ids]
                if min(xs)<0<max(xs) or max(abs(x) for x in xs)<.0048:continue
                nearest=min(range(2),key=lambda j:abs(sum(pts[i].y for i in ids)/len(ids)-AXLE_Y[j]))
                radius=max(math.hypot(pts[i].y-AXLE_Y[nearest],pts[i].z-AXLE_Z) for i in ids)
                if radius>.00272:continue
                side=0 if sum(xs)<0 else 1
                index=nearest*2+side+1
                for i in ids:groups[i]=index
        for group in sorted(set(groups.values())):
            polys=[p for p in data.polygons if groups[p.vertices[0]]==group]
            if not polys:continue
            used=sorted({i for p in polys for i in p.vertices});lookup={old:i for i,old in enumerate(used)}
            offset=positions[group-1] if group else Vector((0,0,0))
            vertices=[mapped(pts[i])-offset for i in used]
            if group:
                for v in vertices:
                    v.x*=WHEEL_RADIAL_SCALE;v.z*=WHEEL_RADIAL_SCALE
            faces=[[lookup[i] for i in p.vertices] for p in polys]
            mesh=bpy.data.meshes.new(source.name+' normalized '+str(group));mesh.from_pydata(vertices,[],faces);mesh.update()
            for mat in data.materials:mesh.materials.append(mat)
            obj=bpy.data.objects.new('Original detailed '+source.name+' part '+str(group),mesh);bpy.context.collection.objects.link(obj)
            obj.parent=roots['car_body' if group==0 else 'wheel_'+str(group-1)]
            if data.uv_layers.active:
                layer=mesh.uv_layers.new(name='Original asset UV')
                normals=[];normal_matrix=source.matrix_world.to_3x3().inverted().transposed()
                for old,new in zip(polys,mesh.polygons):
                    new.material_index=old.material_index;new.use_smooth=True
                    for a,b in zip(old.loop_indices,new.loop_indices):
                        layer.data[b].uv=data.uv_layers.active.data[a].uv
                        normal=normal_matrix@data.corner_normals[a].vector
                        normal=Vector((-normal.y,normal.x,normal.z))
                        if group:
                            normal.x/=WHEEL_RADIAL_SCALE;normal.z/=WHEEL_RADIAL_SCALE
                        normals.append(normal.normalized())
                mesh.normals_split_custom_set(normals)
            counts[group]+=len(vertices)
    for obj in originals:bpy.data.objects.remove(obj,do_unlink=True)
    for m in bpy.data.materials:
        if m.name=='ToyCar':red_paint(m)
        if m.name=='Glass':
            bs=m.node_tree.nodes.get('Principled BSDF');bs.inputs['Roughness'].default_value=.075
            bs.inputs['Transmission Weight'].default_value=.85;bs.inputs['IOR'].default_value=1.47
            # Neutral smoked glazing; the source's green tint reads as an unpainted patch on a red car.
            if bs.inputs['Base Color'].is_linked:m.node_tree.links.remove(bs.inputs['Base Color'].links[0])
            bs.inputs['Base Color'].default_value=(.62,.68,.72,1)
    assert min(counts)>200,counts
    bpy.context.view_layer.update()
    points=[o.matrix_world@v.co for o in bpy.context.scene.objects if o.type=='MESH' for v in o.data.vertices]
    bounds=[[min(v[i] for v in points) for i in range(3)],[max(v[i] for v in points) for i in range(3)]]
    ledger={'source':'https://github.com/KhronosGroup/glTF-Sample-Assets/blob/main/Models/ToyCar/README.md',
        'authors':['Guido Odendahl','Eric Chadwick'],'license':'CC0-1.0','scale_from_measured_longitudinal_bounds':SCALE,
        'source_car_bounds_m':[[ -.0093537644,BODY_MIN_Y,.0009924222],[.0093537644,BODY_MAX_Y,.0126166223]],
        'length_m':LENGTH,'wheelbase_m':wheelbase,'wheel_radius_m':RADIUS,'wheel_width_m':.0127,
        'source_normalized_wheel_radius_m':SOURCE_RADIUS,'wheel_radial_scale':WHEEL_RADIAL_SCALE,
        'wheel_center_track_m':TRACK,'com_above_axle_m':COM_ABOVE_AXLE,'local_bounds_m':bounds,
        'vertices_per_rigid_root':dict(zip(roots,counts)),
        'normalization':'uniform body scaling to a 150 mm toy; original wheel assemblies centered to physical axles, 12.7 mm wheel radius; original mesh UVs and normals preserved'}
    # Underside height per 10 mm of length, for the chassis collision proxy.
    body=[o.matrix_world@v.co for o in bpy.context.scene.objects if o.type=='MESH' and o.parent is roots['car_body'] for v in o.data.vertices]
    profile={}
    for v in body:
        key=round(v.x*100)/100;profile[key]=[min(profile.get(key,[9,-9])[0],v.z),max(profile.get(key,[9,-9])[1],v.z)]
    ledger['body_z_range_by_x_m']={str(k):[round(a,4),round(b,4)] for k,(a,b) in sorted(profile.items())}
    out.mkdir(parents=True,exist_ok=True)
    (out/'car_dimensions.json').write_text(json.dumps(ledger,indent=2)+'\n')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out/'red_toy_car_library.blend'))
    print(json.dumps(ledger,indent=2))

if __name__=='__main__':main()
