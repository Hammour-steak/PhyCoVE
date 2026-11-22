"""Painted timber casement window rebuilt inside the room opening; appearance only, all dimensions in SI metres."""
import math
from pathlib import Path
import bpy
ROOT=Path(__file__).resolve().parents[4]
REVISION='painted_casement_garden'

def rebuild_window(cfg,ledger):
    if cfg['appearance']['room'].get('window_context_revision')!=REVISION:return ledger
    from look_domino_chain import box,material,set_socket
    room=cfg['appearance']['room'];b=ledger['window_world_bounds_m']
    x0,x1=b[0][0]+.014,b[1][0]-.014;z0,z1=b[0][2]+.014,b[1][2]-.014
    y=room['back_wall_y_m'];xc=(x0+x1)/2
    for name in ['Linen window | Window','Daylight surface beyond window']:
        bpy.data.objects.remove(bpy.data.objects[name],do_unlink=True)
    paint=material('Window | warm aged eggshell paint',(.56,.535,.48,1),.39)
    n=paint.node_tree.nodes;l=paint.node_tree.links;bs=n.get('Principled BSDF');set_socket(bs,'IOR',1.48)
    pos=n.new('ShaderNodeNewGeometry');noise=n.new('ShaderNodeTexNoise');noise.inputs['Scale'].default_value=110
    noise.inputs['Detail'].default_value=2;noise.inputs['Roughness'].default_value=.6;l.new(pos.outputs['Position'],noise.inputs['Vector'])
    rough=n.new('ShaderNodeMapRange');rough.inputs['To Min'].default_value=.35;rough.inputs['To Max'].default_value=.43;l.new(noise.outputs['Fac'],rough.inputs['Value']);l.new(rough.outputs['Result'],bs.inputs['Roughness'])
    bump=n.new('ShaderNodeBump');bump.inputs['Distance'].default_value=.000009;bump.inputs['Strength'].default_value=.22;l.new(noise.outputs['Fac'],bump.inputs['Height']);l.new(bump.outputs[0],bs.inputs['Normal'])
    seal=material('Window | graphite rubber glazing seals',(.022,.025,.021,1),.76)
    metal=material('Window | satin nickel hardware',(.42,.43,.41,1),.29,.82)
    glass=material('Window | 3 mm clear soda lime glass',(.985,.995,.988,1),room['window_glass_roughness'])
    gb=glass.node_tree.nodes.get('Principled BSDF');set_socket(gb,'Transmission Weight',1);set_socket(gb,'IOR',1.52)
    made=[];glass_objects=[];joints=[]
    def part(name,loc,dims,mat=paint,bevel=.00065):
        o=box('Natural window | '+name,loc,dims,mat,bevel);o['static_decorative_prop']=True
        o['authored_geometry']='PCVE metre-scale painted timber casement';made.append(o);return o
    # Jambs sit inside the actual wall reveal; the casing bridges the reveal edge.
    outer=(x0-.008,x1+.008,z0-.008,z1+.008);w=.060
    part('left jamb',(outer[0]+w/2,y,(outer[2]+outer[3])/2),(w,.14,outer[3]-outer[2]))
    part('right jamb',(outer[1]-w/2,y,(outer[2]+outer[3])/2),(w,.14,outer[3]-outer[2]))
    for label,z in [('sill jamb',outer[2]+w/2),('head jamb',outer[3]-w/2)]:
        part(label,(xc,y,z),(outer[1]-outer[0]-2*w,.14,w))
    for label,x in [('left casing',x0-.020),('right casing',x1+.020)]:
        part(label,(x,y-.080,(z0+z1)/2),(.055,.025,z1-z0+.090),bevel=.001)
    for label,z in [('bottom casing',z0-.020),('top casing',z1+.020)]:
        part(label,(xc,y-.080,z),(x1-x0-.015,.025,.055),bevel=.001)
    clear=(outer[0]+w,outer[1]-w,outer[2]+w,outer[3]-w)
    mullion=.044
    part('fixed centre mullion',(xc,y-.008,(clear[2]+clear[3])/2),(mullion,.115,clear[3]-clear[2]))
    for label,a,c in [('left',clear[0]+.003,xc-mullion/2-.003),('right',xc+mullion/2+.003,clear[1]-.003)]:
        low,high=clear[2]+.003,clear[3]-.003;s=.042;sy=y-.043;sz=(low+high)/2
        part(label+' sash left stile',(a+s/2,sy,sz),(s,.056,high-low))
        part(label+' sash right stile',(c-s/2,sy,sz),(s,.056,high-low))
        for side,z in [('bottom',low+s/2),('top',high-s/2)]:
            part(label+' sash '+side+' rail',((a+c)/2,sy,z),(c-a-2*s,.056,s))
        rail_z=z0+.57;rail=.025
        part(label+' intermediate glazing bar',((a+c)/2,sy,rail_z),(c-a-2*s,.049,rail))
        for level,pz0,pz1 in [('lower',low+s,rail_z-rail/2),('upper',rail_z+rail/2,high-s)]:
            px0,px1=a+s,c-s
            # Glass is a closed 3 mm solid; its perimeter is bedded into a 1.8 mm seal.
            g=part(label+' '+level+' pane',((px0+px1)/2,y-.044,(pz0+pz1)/2),(px1-px0-.002,.003,pz1-pz0-.002),glass,.0001);glass_objects.append(g)
            for edge,x in [('left',px0+.001),('right',px1-.001)]:
                part(label+' '+level+' '+edge+' seal',(x,y-.047,(pz0+pz1)/2),(.0018,.003,pz1-pz0+.002),seal,.00025)
                part(label+' '+level+' '+edge+' glazing bead',(x+(-.004 if edge=='left' else .004),y-.0545,(pz0+pz1)/2),(.006,.012,pz1-pz0+.010),paint,.0005)
            for edge,z in [('bottom',pz0+.001),('top',pz1-.001)]:
                part(label+' '+level+' '+edge+' seal',((px0+px1)/2,y-.047,z),(px1-px0-.002,.003,.0018),seal,.00025)
                part(label+' '+level+' '+edge+' glazing bead',((px0+px1)/2,y-.0545,z+(-.004 if edge=='bottom' else .004)),(px1-px0+.010,.012,.006),paint,.0005)
        # Small functional handle, base plate and paired hinges on each closed sash.
        hx=c-s/2 if label=='left' else a+s/2
        part(label+' handle backplate',(hx,y-.076,1.075),(.022,.007,.074),metal,.002)
        part(label+' handle spindle',(hx,y-.086,1.084),(.010,.016,.010),metal,.002)
        part(label+' handle lever',(hx,y-.095,1.063),(.010,.010,.049),metal,.003)
        hinge_x=a+.003 if label=='left' else c-.003
        for hz in [low+.20,high-.20]:
            bpy.ops.mesh.primitive_cylinder_add(vertices=20,radius=.0045,depth=.058,location=(hinge_x,y-.071,hz))
            o=bpy.context.object;o.name='Natural window | '+label+' hinge '+str(hz);o.data.materials.append(metal);o['static_decorative_prop']=True;made.append(o)
            for p in o.data.polygons:p.use_smooth=True
    # Far-field photograph is carried on a 200 m exterior hemisphere. Every close
    # surface, occlusion, refraction and frame reflection remains path traced 3D.
    image=bpy.data.images.load(str(ROOT/'assets/polyhaven/suburban_field_01/suburban_field_01_4k.hdr'),check_existing=True)
    mat=material('Window exterior | overcast photographic distant sky',(.5,.5,.5,1),1)
    n=mat.node_tree.nodes;l=mat.node_tree.links;n.clear()
    geom=n.new('ShaderNodeNewGeometry')
    sub=n.new('ShaderNodeVectorMath');sub.operation='SUBTRACT';sub.inputs[1].default_value=(0,0,.96);l.new(geom.outputs['Position'],sub.inputs[0])
    rot=n.new('ShaderNodeVectorRotate');rot.rotation_type='AXIS_ANGLE';rot.inputs['Axis'].default_value=(0,0,1);rot.inputs['Angle'].default_value=math.radians(room['window_exterior_rotation_deg']);l.new(sub.outputs['Vector'],rot.inputs['Vector'])
    env=n.new('ShaderNodeTexEnvironment');env.image=image;l.new(rot.outputs['Vector'],env.inputs['Vector'])
    emission=n.new('ShaderNodeEmission');emission.inputs['Strength'].default_value=room['window_exterior_strength'];l.new(env.outputs['Color'],emission.inputs['Color'])
    out=n.new('ShaderNodeOutputMaterial');l.new(emission.outputs[0],out.inputs['Surface'])
    verts=[];faces=[];latitudes=32;longitudes=64;radius=200
    for j in range(latitudes+1):
        lat=-math.pi/2+math.pi*j/latitudes
        for i in range(longitudes+1):
            phi=math.pi*i/longitudes
            verts.append((radius*math.cos(lat)*math.cos(phi),3.0+radius*math.cos(lat)*math.sin(phi),.96+radius*math.sin(lat)))
    for j in range(latitudes):
        for i in range(longitudes):
            k=j*(longitudes+1)+i;faces.append((k,k+1,k+longitudes+2,k+longitudes+1))
    mesh=bpy.data.meshes.new('Distant exterior hemisphere mesh');mesh.from_pydata(verts,[],faces);mesh.update()
    ext=bpy.data.objects.new('Natural window | distant exterior hemisphere',mesh);bpy.context.collection.objects.link(ext);mesh.materials.append(mat);ext['static_decorative_prop']=True;made.append(ext)
    light=bpy.data.objects['Soft fill through linen privacy window'];light.data.energy=room['window_context_fill_w'];light.visible_transmission=False
    bpy.context.view_layer.update()
    def bounds(obs):
        p=[o.matrix_world@v.co for o in obs for v in o.data.vertices]
        return [[min(v[k] for v in p) for k in range(3)],[max(v[k] for v in p) for k in range(3)]]
    return {**ledger,'window_context_revision':REVISION,'window_source_objects':{k:v for k,v in ledger['window_source_objects'].items() if k!='Window'},
        'window_frame_provenance':'New authored 3D timber joinery at the existing opening, not an extracted source asset.',
        'window_glazing_note':'Four closed 3 mm clear glass solids, IOR 1.52, real seals and glazing beads; far-field photographic overcast exterior hemisphere at 200 m.',
        'window_glass_roughness':room['window_glass_roughness'],'window_glass_thickness_m':.003,'window_clear_pane_count':len(glass_objects),
        'window_authored_objects':[o.name for o in made],'window_authored_frame_bounds_m':bounds([o for o in made if o!=ext]),
        'window_exterior_asset':'assets/polyhaven/suburban_field_01/asset_manifest.json','window_exterior_radius_m':radius,
        'window_exterior_strength':room['window_exterior_strength'],'window_exterior_rotation_deg':room['window_exterior_rotation_deg'],
        'window_fill_power_w':light.data.energy,'window_added_joinery':'Replacement authored casements with stepped profiles, 3 mm closing gaps, 1.8 mm seals, hinges and nickel handles.'}
