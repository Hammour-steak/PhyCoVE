"""The plywood track, carton markings and the render-time prop checks; no physics overrides."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math,random
from look_u_track_ball import box,material,textured_material,mesh_object,set_ply_t,tag_prop,PROP_TAG,TILE_M

# Cheek and rib stock: 18 mm Baltic birch, the same figure the collision rails use.
CHEEK=.018;CHEEK_HEIGHT=.07

def _stations(c):
    n=c['segments_per_branch']
    return [-c['drive_length']+c['drive_length']*i/n for i in range(n)]+[c['exit_length']*i/n for i in range(n+1)]

def _arc_lengths(xs,c):
    from track_geometry import surface
    s=[0.]
    for a,b in zip(xs,xs[1:]):s.append(s[-1]+math.hypot(b-a,surface(b,c)[0]-surface(a,c)[0]))
    return s

def track_bed(bpy,c,running,ply_face,ply_edges):
    """The collision trough itself (track_mesh), dressed: linoleum running surface on
    top, plywood underneath, plies on the cut ends. Geometry is untouched."""
    from track_geometry import track_mesh
    vertices,faces=track_mesh(c);t=c['track_thickness']
    obj=mesh_object(bpy,'Asymmetric U track bed',vertices,faces,[running,ply_face,ply_edges],smooth=True)
    mesh=obj.data
    for poly in mesh.polygons:
        rows={v%4 for v in poly.vertices}
        poly.material_index=0 if rows<={0,1} else (1 if rows<={2,3} else 2)
    set_ply_t(obj,[t if i%4<2 else 0. for i in range(len(vertices))])
    s=_arc_lengths(_stations(c),c);uv=mesh.uv_layers.new(name='UVMap')
    for poly in mesh.polygons:
        for li in poly.loop_indices:
            vi=mesh.loops[li].vertex_index;co=mesh.vertices[vi].co
            uv.data[li].uv=(s[vi//4],co.y)
    mesh.set_sharp_from_angle(angle=.5)
    normal=obj.modifiers.new('Formed bed normals','WEIGHTED_NORMAL');normal.keep_sharp=True
    return obj

def continuous_rails(bpy,c,ply_face,ply_edges):
    """CNC-cut birch-ply cheeks. Inner face and top are the collision rails exactly
    (y = +-track_width/2 .. +18 mm, 0 .. 70 mm above the running surface); below the
    running surface each cheek carries on down over the bed's edge, as a screwed-on
    cheek does, so the bed is not seen floating beside it."""
    from track_geometry import surface
    xs=_stations(c);s=_arc_lengths(xs,c);w=c['track_width']/2;t=c['track_thickness']
    for side in (-1,1):
        vertices=[];faces=[];plyt=[];uvs=[]
        for x in xs:
            z,slope=surface(x,c);angle=math.atan(slope)
            for y,offset in ((side*w,-t),(side*(w+CHEEK),-t),(side*w,CHEEK_HEIGHT),(side*(w+CHEEK),CHEEK_HEIGHT)):
                vertices.append([x-offset*math.sin(angle),y,z+offset*math.cos(angle)]);plyt.append(abs(y)-w)
        last=len(vertices)-4
        for i in range(len(xs)-1):
            a=4*i;b=a+4
            faces.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)])
        faces.extend([(0,1,3,2),(last,last+2,last+3,last+1)])
        if side>0:faces=[tuple(reversed(face)) for face in faces]
        obj=mesh_object(bpy,f'Birch ply cheek {side:+d}',vertices,faces,[ply_face,ply_edges],smooth=True)
        mesh=obj.data
        for poly in mesh.polygons:poly.material_index=0 if abs(poly.normal.y)>.5 else 1
        set_ply_t(obj,plyt)
        uv=mesh.uv_layers.new(name='UVMap')
        for poly in mesh.polygons:
            for li in poly.loop_indices:
                vi=mesh.loops[li].vertex_index;row=vi%4
                uv.data[li].uv=(s[vi//4],(-t if row<2 else CHEEK_HEIGHT)+(.3 if side>0 else 0))
        mesh.set_sharp_from_angle(angle=.5)
        bevel=obj.modifiers.new('Sanded arris','BEVEL');bevel.width=.0015;bevel.segments=3;bevel.limit_method='ANGLE';bevel.angle_limit=.5
        normal=obj.modifiers.new('Cheek normals','WEIGHTED_NORMAL');normal.keep_sharp=True

def _underside_z(x,c):
    """Height of the bed's underside above world x (the mesh offsets it along the normal)."""
    from track_geometry import surface
    t=c['track_thickness'];X=x
    for _ in range(8):
        z,slope=surface(X,c);a=math.atan(slope);X=x-t*math.sin(a)
    z,slope=surface(X,c);a=math.atan(slope)
    return z-t*math.cos(a)

RIB_X=(-.80,-.52,-.24,.04,.32,.60)
BASE_X=(-.93,.72)

def track_stand(bpy,c,ply_face,ply_edges):
    """Plywood ribs on a base board, with a spine between them: how a museum workshop
    stands a formed channel on a table. Visual only; checked against every pose."""
    w=c['track_width']/2+CHEEK;base_top=c['table_height']+CHEEK
    x0,x1=BASE_X
    from look_u_track_ball import plate
    tag_prop(plate(bpy,'Track base board',[(x0+x1)/2,0,c['table_height']+CHEEK/2],[x1-x0,.30,CHEEK],ply_face,ply_edges,'z'))
    for i,x in enumerate(RIB_X):
        xa,xb=x-CHEEK/2,x+CHEEK/2;za,zb=_underside_z(xa,c)-.0008,_underside_z(xb,c)-.0008
        verts=[(xa,-w,base_top),(xb,-w,base_top),(xb,w,base_top),(xa,w,base_top),(xa,-w,za),(xb,-w,zb),(xb,w,zb),(xa,w,za)]
        faces=[(0,3,2,1),(4,5,6,7),(0,1,5,4),(2,3,7,6),(0,4,7,3),(1,2,6,5)]
        rib=tag_prop(mesh_object(bpy,f'Plywood rib {i+1}',verts,faces,[ply_face,ply_edges]))
        for poly in rib.data.polygons:poly.material_index=0 if abs(poly.normal.x)>.5 else 1
        set_ply_t(rib,[v[0]-xa for v in verts]);_uv_planar(rib)
        bevel=rib.modifiers.new('Sanded arris','BEVEL');bevel.width=.0012;bevel.segments=2;rib.modifiers.new('Weighted normals','WEIGHTED_NORMAL')
    # Spine: one sheet on edge along the centre line, its top following the bed.
    xs=[RIB_X[0]+(RIB_X[-1]-RIB_X[0])*i/60 for i in range(61)];verts=[];faces=[]
    for x in xs:
        z=_underside_z(x,c)-.0008
        verts.extend([(x,-CHEEK/2,base_top),(x,-CHEEK/2,z),(x,CHEEK/2,base_top),(x,CHEEK/2,z)])
    for i in range(len(xs)-1):
        a=4*i;b=a+4
        faces.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a+1,b+1,b+3,a+3),(a,a+2,b+2,b)])
    faces.extend([(0,1,3,2),(len(verts)-4,len(verts)-2,len(verts)-1,len(verts)-3)])
    spine=tag_prop(mesh_object(bpy,'Plywood spine',verts,faces,[ply_face,ply_edges]))
    for poly in spine.data.polygons:poly.material_index=0 if abs(poly.normal.y)>.5 else 1
    set_ply_t(spine,[v[1]+CHEEK/2 for v in verts]);_uv_planar(spine)

def _uv_planar(obj):
    from look_u_track_ball import _uv_box
    _uv_box(obj,TILE_M['plywood'])

def carton_details(bpy,target,c):
    w,d,h=c['box_size'];paper=textured_material(bpy,'Shipping label paper',(.76,.74,.66),.86,scale=280,bump_distance=.00005)
    ink=material(bpy,'Carton charcoal ink',(.018,.024,.022),roughness=.87)
    def attach(name,pos,size,mat):
        obj=box(bpy,name,pos,size,mat);obj.parent=target;return obj
    attach('Shipping label',[0,-d/2-.00035,.01],[w*.72,.00055,h*.40],paper)
    rng=random.Random(42)
    for i in range(20):
        x=-w*.26+i*w*.026
        attach('Barcode bar',[x,-d/2-.00070,.005],[w*rng.uniform(.005,.013),.0002,h*.10],ink)
    for z in (.031,.025):attach('Printed address line',[-w*.055,-d/2-.00075,z],[w*.43,.0002,.0018],ink)
    bpy.ops.object.text_add(location=[-.051,-d/2-.0008,-.020],rotation=[math.pi/2,0,0]);text=bpy.context.object;text.name='Handle with care label';text.data.body='HANDLE WITH CARE';text.data.size=.009;text.data.extrude=0;text.data.materials.append(ink);text.parent=target
    tape=textured_material(bpy,'Matte paper packing tape',(.39,.25,.12),.60,scale=240,bump_distance=.00008)
    attach('Top packing tape',[0,0,h/2+.00065],[w,.032,.0012],tape)
    attach('Front tape fold',[0,-d/2-.0004,h/2-.018],[.032,.0008,.036],tape)
    crease=material(bpy,'Fold seams',(.13,.08,.035),roughness=.9)
    attach('Box flap seam',[0,0,h/2+.0002],[.00065,d,.0003],crease)
    # Fine fluting at the upper edge communicates corrugated board thickness.
    for i in range(24):attach('Corrugation edge',[-w/2+.003+i*(w-.006)/24,-d/2-.00015,h/2-.002],[.0008,.0004,.002],crease)

def check_props(bpy,scene,camera,records,c,clearance=.02):
    """Fail the render if a visual-only prop comes within `clearance` of the ball or
    the carton in any frame, or stands between the camera and either of them.

    Props are the objects tagged with PROP_TAG; the track bed and cheeks, the table,
    its legs and the floor are the collision geometry and are not props.
    """
    from mathutils import Vector,Matrix
    from mathutils.bvhtree import BVHTree
    from bpy_extras.object_utils import world_to_camera_view
    deps=bpy.context.evaluated_depsgraph_get()
    trees=[]
    for obj in scene.objects:
        if not obj.get(PROP_TAG) or obj.type not in ('MESH','CURVE','FONT'):continue
        ev=obj.evaluated_get(deps);mesh=ev.to_mesh()
        verts=[obj.matrix_world@v.co for v in mesh.vertices];polys=[tuple(p.vertices) for p in mesh.polygons]
        ev.to_mesh_clear()
        if not polys:continue
        lo=Vector([min(v[i] for v in verts) for i in range(3)]);hi=Vector([max(v[i] for v in verts) for i in range(3)])
        trees.append((obj.name,BVHTree.FromPolygons(verts,polys),lo,hi))
    radius=c['ball_radius'];hx,hy,hz=[v/2 for v in c['box_size']]
    grid=[-1+2*i/8 for i in range(9)]
    box_local=[Vector((a*hx,b*hy,s*hz)) for s in (-1,1) for a in grid for b in grid]
    box_local+=[Vector((a*hx,s*hy,b*hz)) for s in (-1,1) for a in grid for b in grid]
    box_local+=[Vector((s*hx,a*hy,b*hz)) for s in (-1,1) for a in grid for b in grid]
    worst=dict(ball=(1e9,None),box=(1e9,None))
    for frame in records['frames']:
        bodies=[('ball',[Vector(frame['ball']['location'])],radius)] if frame['ball'].get('present',True) else []
        if frame['box'].get('present',True):
            m=Matrix(frame['box']['matrix_world']);bodies.append(('box',[m@p for p in box_local],0.))
        for key,points,r in bodies:
            lo=Vector([min(p[i] for p in points)-r-.1 for i in range(3)]);hi=Vector([max(p[i] for p in points)+r+.1 for i in range(3)])
            for name,tree,tlo,thi in trees:
                if any(thi[i]<lo[i] or tlo[i]>hi[i] for i in range(3)):continue
                for p in points:
                    hit=tree.find_nearest(p)
                    if hit[0] is None:continue
                    gap=hit[3]-r
                    if gap<worst[key][0]:worst[key]=(gap,(frame['frame_index'],name))
                    if gap<clearance:raise RuntimeError(f'Prop {name!r} within {gap:.4f} m of the {key} at frame {frame["frame_index"]}')
        # Line of sight from the camera to the centre of each body that is in frame.
        origin=camera.matrix_world.translation
        for key,point in (('ball',Vector(frame['ball']['location']) if frame['ball'].get('present',True) else None),('box',Vector(frame['box']['location']) if frame['box'].get('present',True) else None)):
            if point is None:continue
            ndc=world_to_camera_view(scene,camera,point)
            if not (0<=ndc.x<=1 and 0<=ndc.y<=1 and ndc.z>0):continue
            direction=point-origin;distance=direction.length-(radius if key=='ball' else min(hx,hy,hz))
            hit,loc,normal,index,obj,matrix=scene.ray_cast(deps,origin,direction.normalized(),distance=distance)
            if hit and obj is not None and obj.get(PROP_TAG):raise RuntimeError(f'Prop {obj.name!r} hides the {key} at frame {frame["frame_index"]}')
    # None: nothing tagged as a prop came within 0.1 m of that body in any frame.
    return {k:dict(min_gap_m=round(v[0],4) if v[1] else None,at=v[1]) for k,v in worst.items()}
