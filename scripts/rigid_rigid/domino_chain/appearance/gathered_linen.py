"""A frozen, independently generated drape asset; no live cloth or rigid-body edits."""
from pathlib import Path
import math,json
import bpy
from mathutils import Matrix,Vector
ROOT=Path(__file__).resolve().parents[4]
REVISION='gathered_linen_no_chair'
def bounds(o,evaluated=False):
    if evaluated:
        e=o.evaluated_get(bpy.context.evaluated_depsgraph_get());m=e.to_mesh()
        ps=[e.matrix_world@v.co for v in m.vertices];e.to_mesh_clear()
    else:ps=[o.matrix_world@v.co for v in o.data.vertices]
    return [[min(v[k] for v in ps) for k in range(3)],[max(v[k] for v in ps) for k in range(3)]]
def remove_chairs():
    names=[]
    for o in list(bpy.context.scene.objects):
        if o.name.startswith(('Real dining chair | ','PolyHaven worn painted dining chair','Chair ')) or o.name in ['Photographic dining chair placement','Painted dining chair placement','Domestic oak dining chair - 430 x 430 x 930 mm']:
            names.append(o.name);bpy.data.objects.remove(o,do_unlink=True)
    return names
def cloth_material(cfg,side):
    from furniture_textile_realism import linen_material
    mat,mapping=linen_material(cfg);mat.name='Linen drapes | relaxed oatmeal woven panel '+str(side)
    mapping.inputs['Scale'].default_value=(1,1,1)
    n=mat.node_tree.nodes;bs=n.get('Principled BSDF')
    bs.inputs['Sheen Weight'].default_value=.12
    bs.inputs['Sheen Roughness'].default_value=.90
    bs.inputs['Subsurface Weight'].default_value=0
    dye=bs.inputs['Base Color'].links[0].from_node;dye.inputs[1].default_value=(.70,.67,.59,1)
    tone=dye.inputs[2].links[0].from_node;tone.inputs['From Min'].default_value=.14;tone.inputs['From Max'].default_value=.66;tone.inputs['To Min'].default_value=.70;tone.inputs['To Max'].default_value=1.12
    rough=bs.inputs['Roughness'].links[0].from_node;rough.inputs['To Min'].default_value=.86;rough.inputs['To Max'].default_value=.97
    bump=bs.inputs['Normal'].links[0].from_node;bump.inputs['Strength'].default_value=.22;bump.inputs['Distance'].default_value=.000060
    bump.inputs['Normal'].links[0].from_node.inputs['Strength'].default_value=.28
    mat['material_note']='Photographic linen in metres, matte yarn and low diffuse cloth transmission. Opaque alpha; no additive transparency, emission or glass.'
    return mat
def rebuild_surface(cfg,ledger,shape_file):
    removed=remove_chairs()
    for o in list(bpy.context.scene.objects):
        if o.name.startswith('Linen drape hem | '):bpy.data.objects.remove(o,do_unlink=True)
    source=json.loads(Path(shape_file).read_text());rows=[]
    for side,panel in enumerate(source['panels']):
        name=['Plane.004','Plane.005'][side];ob=bpy.data.objects['Linen window | '+name]
        mesh=bpy.data.meshes.new('Gravity-draped cut linen | '+name)
        faces=[tuple(reversed(f)) for f in panel['faces']]
        mesh.from_pydata(panel['vertices'],[],faces);mesh.update()
        uv=mesh.uv_layers.new(name='UVMap')
        uvs=[]
        for i in range(0,len(panel['uv_loops']),4):uvs.extend(reversed(panel['uv_loops'][i:i+4]))
        for d,v in zip(uv.data,uvs):d.uv=v
        for p in mesh.polygons:p.use_smooth=True
        ob.data=mesh;ob.matrix_world=Matrix.Identity(4);ob.modifiers.clear()
        material=cloth_material(cfg,side);mesh.materials.append(material)
        smooth=ob.modifiers.new('One subdivision of the frozen cloth surface','SUBSURF');smooth.levels=1;smooth.render_levels=1
        thick=ob.modifiers.new('0.45 mm physical linen thickness','SOLIDIFY');thick.thickness=.00045;thick.offset=0;thick.use_even_offset=False
        ob['curtain_revision']=REVISION;ob['source_asset']='PCVE original cut-and-gathered static linen asset'
        ob['appearance_geometry_modified']=True;ob['static_decorative_prop']=True
        ob['asset_shape_frame']=panel['shape_frame'];ob['no_live_cloth_solver']=True
        # Rear-facing loose turned hem, 1.2 mm from the SAME evaluated surface.
        # Subdividing a narrow extracted strip separately changes its boundary
        # shape and caused it to cross the main cloth in the rejected build.
        thick.show_viewport=False;bpy.context.view_layer.update()
        deps=bpy.context.evaluated_depsgraph_get()
        evaluated=ob.evaluated_get(deps);surface=evaluated.to_mesh()
        source_uv=surface.uv_layers.active
        umin=min(v.uv.x for v in source_uv.data);umax=max(v.uv.x for v in source_uv.data)
        vmin=min(v.uv.y for v in source_uv.data);vmax=max(v.uv.y for v in source_uv.data)
        umargin=(umax-umin)/panel['nx'];vmargin=(vmax-vmin)*4/panel['nz']
        indices={};hv=[];hf=[];hu=[]
        for poly in surface.polygons:
            values=[source_uv.data[li].uv for li in poly.loop_indices]
            selected=(all(v.x<=umin+umargin+1e-6 for v in values) or
                      all(v.x>=umax-umargin-1e-6 for v in values) or
                      all(v.y<=vmin+vmargin+1e-6 for v in values) or
                      all(v.y>=vmax-vmargin-1e-6 for v in values))
            if not selected:continue
            f=[]
            for li in poly.loop_indices:
                idx=surface.loops[li].vertex_index
                if idx not in indices:
                    indices[idx]=len(hv)
                    hv.append(surface.vertices[idx].co+surface.vertices[idx].normal*(-.0012))
                f.append(indices[idx]);hu.append(source_uv.data[li].uv.copy())
            hf.append(f)
        evaluated.to_mesh_clear();thick.show_viewport=True;bpy.context.view_layer.update()
        hm=bpy.data.meshes.new('Turned sewn linen edge | '+name);hm.from_pydata(hv,[],hf);hm.update();hl=hm.uv_layers.new(name='UVMap')
        for d,v in zip(hl.data,hu):d.uv=v
        hem=bpy.data.objects.new('Linen drape hem | '+name,hm);bpy.context.collection.objects.link(hem);hm.materials.append(material)
        for p in hm.polygons:p.use_smooth=True
        sol=hem.modifiers.new('Folded linen thickness','SOLIDIFY');sol.thickness=.00045;sol.offset=0;sol.use_even_offset=False
        hem['static_decorative_prop']=True;hem['source_asset']='PCVE original turned linen header, side and bottom hems'
        bpy.context.view_layer.update()
        rows.append({'object':ob.name,'hem_object':hem.name,'source_vertices':len(mesh.vertices),'world_bounds_m':bounds(ob,True),'cloth_thickness_m':.00045,'rest_cut_width_m':panel['parameters']['rest_width_m'],'rest_cut_height_m':panel['parameters']['cut_height_m'],'photographic_repeat_m':[.2707081393,.2712999880],'frozen_shape_frame':panel['shape_frame'],'self_collision_distance_during_asset_solve_m':panel['parameters']['self_collision_distance_m']})
    result={k:v for k,v in ledger.items() if not k.startswith('background_chair_')}
    return {**result,'background_chair_present':False,'removed_chair_objects':removed,'furniture_textile_revision':REVISION,'curtain_reconstruction':rows,'window_linen_bounds_m':{v['object']:v['world_bounds_m'] for v in rows},'curtain_geometry_note':'Independent pinned-header cloth-asset relaxation, then frozen static mesh with real thickness and turned hems. No live cloth dynamics in the four domino videos. Domino physics and trajectories are untouched.','curtain_material':'Existing Poly Haven Rough Linen maps, rest-cut metre UVs, reduced sheen and diffuse backlight.'}


def tiebacks(cfg,shape_file):
    from look_domino_chain import material,box
    src=json.loads(Path(shape_file).read_text());details=[]
    brass=material('Linen tieback | small aged brass wall hooks',(.16,.12,.065,1),.40,.68)
    for side,p in enumerate(src['panels']):
        cx,cy=p['parameters']['tieback_center_xy_m'];z=cfg['appearance']['room']['curtain_tieback_height_m']
        near=[Vector(v) for v in p['vertices'] if abs(v[2]-z)<.035]
        rx=max(abs(v.x-cx) for v in near)+.0015;ry=max(abs(v.y-cy) for v in near)+.0015
        factor=max(((v.x-cx)/rx)**2+((v.y-cy)/ry)**2 for v in near)**.5
        rx*=max(1,factor)*1.015;ry*=max(1,factor)*1.015
        n=96;vs=[];fs=[];uvs=[];arc=0.;arcs=[0.]
        ring=[Vector((cx+rx*math.cos(2*math.pi*i/n),cy+ry*math.sin(2*math.pi*i/n),z)) for i in range(n+1)]
        for a,b in zip(ring,ring[1:]):arcs.append(arcs[-1]+(b-a).length)
        for i,v in enumerate(ring):
            for dz in [-.018,.018]:vs.append((v.x,v.y,v.z+dz))
        for i in range(n):
            fs.append((2*i,2*i+2,2*i+3,2*i+1))
            uvs += [(arcs[i]/.2707081393,0),(arcs[i+1]/.2707081393,0),(arcs[i+1]/.2707081393,.036/.2712999880),(arcs[i]/.2707081393,.036/.2712999880)]
        # A textile return strap joins the loop to an actual wall hook.
        outer=1 if side==0 else -1
        hook=Vector(([.40,-2.03][side],1.792,z+.004));start=Vector((cx,cy+ry,z))
        base=len(vs);segments=20
        for i in range(segments+1):
            u=i/segments;v=start.lerp(hook,u);v.z-=.008*math.sin(math.pi*u)
            for dz in [-.014,.014]:vs.append((v.x,v.y,v.z+dz))
        length=(hook-start).length
        for i in range(segments):
            fs.append((base+2*i,base+2*i+2,base+2*i+3,base+2*i+1))
            uvs += [(length*i/segments/.2707081393,0),(length*(i+1)/segments/.2707081393,0),(length*(i+1)/segments/.2707081393,.028/.2712999880),(length*i/segments/.2707081393,.028/.2712999880)]
        mesh=bpy.data.meshes.new('Sewn tieback loop and return strap '+str(side));mesh.from_pydata(vs,[],fs);mesh.update()
        layer=mesh.uv_layers.new(name='UVMap')
        for d,v in zip(layer.data,uvs):d.uv=v
        ob=bpy.data.objects.new('Linen tieback | woven loop and return '+str(side),mesh);bpy.context.collection.objects.link(ob)
        mesh.materials.append(bpy.data.objects['Linen window | '+['Plane.004','Plane.005'][side]].data.materials[0])
        for f in mesh.polygons:f.use_smooth=True
        solid=ob.modifiers.new('0.8 mm doubled linen tieback','SOLIDIFY');solid.thickness=.0008;solid.offset=0
        ob['static_decorative_prop']=True;ob['source_asset']='PCVE authored linen tieback'
        plate=box('Linen tieback | wall plate '+str(side),(hook.x,1.7985,hook.z),(.018,.0029,.027),brass,.001)
        plate['static_decorative_prop']=True
        stem=box('Linen tieback | hook stem '+str(side),(hook.x,1.7935,hook.z+.008),(.003,.009,.003),brass,.0005)
        stem['static_decorative_prop']=True
        # Closed metal ring normal to the wall; no hidden animated support.
        tv=[];tf=[]
        for i in range(32):
            a=2*math.pi*i/32
            for j in range(8):
                b=2*math.pi*j/8;r=.008+.0013*math.cos(b)
                tv.append((hook.x+r*math.cos(a),1.789+.0013*math.sin(b),hook.z+r*math.sin(a)))
        for i in range(32):
            for j in range(8):
                tf.append((i*8+j,((i+1)%32)*8+j,((i+1)%32)*8+(j+1)%8,i*8+(j+1)%8))
        tm=bpy.data.meshes.new('Tieback hook ring '+str(side));tm.from_pydata(tv,[],tf);tm.update()
        tor=bpy.data.objects.new('Linen tieback | brass hook '+str(side),tm);bpy.context.collection.objects.link(tor);tm.materials.append(brass)
        for f in tm.polygons:f.use_smooth=True
        tor['static_decorative_prop']=True
        details.append({'side':side,'center_m':[cx,cy,z],'loop_radii_m':[rx,ry],'loop_width_m':.036,'cloth_tie_thickness_m':.0008,'return_strap_width_m':.028,'wall_anchor_m':list(hook)})
    return details

def rebuild(cfg,ledger,shape_file):
    result=rebuild_surface(cfg,ledger,shape_file)
    result['curtain_tiebacks']=tiebacks(cfg,shape_file)
    return result


def enhance_environment(cfg,ledger):
    if cfg['appearance']['room'].get('furniture_textile_revision')!=REVISION:return ledger
    return rebuild(cfg,ledger,ROOT/cfg['appearance']['room']['curtain_geometry_asset'])
