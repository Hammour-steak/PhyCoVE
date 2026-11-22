"""Common 45-degree open door and a developable drape over the top of that moving door.

LAYOUT is the frozen common reconstruction shared by the source and every edit. It is
read from the layout recorded with the native seed (assets scenes/cabinet_towel_pinch/
initial_state/simulation_config.json); simulate.py re-checks that every seed and cache
was produced with exactly this layout.
"""
import json
import numpy as np
from common import ASSETS

LAYOUT = json.loads((ASSETS / 'initial_state/simulation_config.json').read_text(encoding='utf8'))['layout']
# Only the open-door-rim reconstruction defines a fold angle on the moving leaf.
assert 'door_fold_cos' in LAYOUT and 'counter_fold_q' not in LAYOUT, 'Unexpected frozen layout'

COUNTER_DIMENSIONS=[2.46,.565,.032]
COUNTER_CENTER=[.36,.2375,LAYOUT['counter_bottom_z']+.016]
COUNTER_TOP_Z=LAYOUT['counter_bottom_z']+.032
# The fixed collision box is the exact outer volume of this real assembly:
# a 6 mm wooden upper carcass panel beneath a 26 mm stone worktop.
COUNTER_FRAME_PANEL_DIMENSIONS=[2.46,.565,.006]
COUNTER_FRAME_PANEL_CENTER=[.36,.2375,LAYOUT['counter_bottom_z']+.003]
COUNTER_STONE_DIMENSIONS=[2.46,.565,.026]
COUNTER_STONE_CENTER=[.36,.2375,LAYOUT['counter_bottom_z']+.006+.013]
NEIGHBOR_CENTERS=[-.2375,.7075,1.1775]

STRUCTURAL_BOXES={
    'Front cabinet stretcher':([2.42,.04,.020],[.36,.020,.762]),
    'Rear countertop support rail':([2.42,.06,.034],[.36,.47,LAYOUT['counter_bottom_z']-.017]),
    'Left cabinet end panel':([.018,.50,LAYOUT['counter_bottom_z']-.12],[-.841,.25,(LAYOUT['counter_bottom_z']+.12)/2]),
    'Right cabinet end panel':([.018,.50,LAYOUT['counter_bottom_z']-.12],[1.561,.25,(LAYOUT['counter_bottom_z']+.12)/2]),
    **{f'Countertop mounting block {i}':([.06,.03,LAYOUT['counter_bottom_z']-LAYOUT['frame_top']],[x,.020,(LAYOUT['counter_bottom_z']+LAYOUT['frame_top'])/2])for i,x in enumerate([-.60,-.10,1.35])}}

def structural_boxes():
    result={name:(list(dim),list(center))for name,(dim,center)in STRUCTURAL_BOXES.items()}
    for name,(dim,center)in result.items():
        if name=='Front cabinet stretcher'or name.startswith('Countertop mounting block'):center[1]+=LAYOUT.get('frame_front_y',0.)
    return result

def neighbor_handle_x(x):
    # The towel bay has a handleless push-to-open front; other bays use pulls.
    return x

def neighbor_has_handle(x):
    if abs(x-.7075)<1e-8:return False
    return True

def door_transform():
    a=LAYOUT['door_initial_angle'];c,s=np.cos(a),np.sin(a)
    T=np.eye(4);T[:2,:2]=[[c,-s],[s,c]]
    origin=np.array([0.,LAYOUT['hinge_axis_y'],0.]);T[:3,3]=origin-T[:3,:3]@origin
    return T

def towel(pitch=.008):
    w,h=LAYOUT['towel_width'],LAYOUT['towel_length']
    # Align triangle strips to bend-coordinate q. A rectangular UV grid cut
    # obliquely across a narrow fold otherwise introduces spurious pre-stretch.
    # Reference axes remain the towel's true warp/weft s,t, not the fold axes.
    r=.002;inside=LAYOUT['inner_leg_drop'];arc=4*r*np.sin(np.pi/8)
    # Start outside the finite-thickness contact activation band, allowing
    # gravity to establish the drape rather than an initial barrier impulse.
    inner_y=LAYOUT['door_back_y']+.0011
    # The open door's real pull protrudes 41 mm from its center plane.
    # Start the free outside leg beyond it, then let gravity drape the
    # unsupported bridge naturally; do not initialize cloth through the pull.
    edge_y=LAYOUT['door_center_y']-.0421
    flat=inner_y-2*r-edge_y
    cs=LAYOUT['door_fold_cos']
    sn=float(np.sqrt(1-cs*cs))
    qmax=sn*w+cs*h
    special=np.unique(np.round(np.r_[0,qmax,sn*w,cs*h,
        inside+np.linspace(0,arc,3),inside+arc+flat+np.linspace(0,arc,3)],14))
    regular=np.linspace(0,qmax,round(qmax/pitch)+1)
    # Keep non-neighbor mid-surfaces farther apart than the 0.8 mm full
    # thickness plus the contact activation band, including in the flat rest
    # mesh. Do not weaken self-contact to accommodate tiny sliver strips.
    regular=np.array([a for a in regular if np.min(abs(special-a))>.0013])
    qs=np.sort(np.r_[special,regular])
    pp=[];qq=[];rows=[]
    for level in qs:
        low=max(-sn*level/cs,(cs*level-h)/sn)
        high=min((w-sn*level)/cs,cs*level/sn)
        count=1 if high-low<1e-10 else max(2,int(np.ceil((high-low)/pitch))+1)
        values=np.linspace(low,high,count);rows.append(np.arange(len(pp),len(pp)+count))
        pp.extend(values);qq.extend([level]*count)
    p=np.asarray(pp);q=np.asarray(qq);s=cs*p+sn*q;t=-sn*p+cs*q
    u=s/w;v=t/h
    faces=[]
    for row0,row1 in zip(rows[:-1],rows[1:]):
        i=j=0
        while i<len(row0)-1 or j<len(row1)-1:
            ai=(i+1)/(len(row0)-1)if i<len(row0)-1 else 2.
            bj=(j+1)/(len(row1)-1)if j<len(row1)-1 else 2.
            if ai<=bj:
                faces.append((row0[i],row0[i+1],row1[j]));i+=1
            else:
                faces.append((row0[i],row1[j+1],row1[j]));j+=1
    # A small free inner corner hangs inside the top of the open door. The
    # sheet turns over both edges of the door top; most material remains
    # outside. Contact friction, rather than a pin, supports this common
    # initial drape before the door closes.
    top=LAYOUT['door_bottom']+LAYOUT['door_height']
    y=np.full_like(q,inner_y);z=top-inside+q
    k=(q>inside)&(q<=inside+arc);a=(q[k]-inside)/arc*(np.pi/2)
    y[k]=inner_y-r*(1-np.cos(a));z[k]=top+r*np.sin(a)
    k=(q>inside+arc)&(q<=inside+arc+flat)
    y[k]=inner_y-r-(q[k]-inside-arc);z[k]=top+r
    k=(q>inside+arc+flat)&(q<=inside+2*arc+flat);a=(q[k]-inside-arc-flat)/arc*(np.pi/2)
    y[k]=inner_y-r-flat-r*np.sin(a);z[k]=top+r*np.cos(a)
    k=q>inside+2*arc+flat
    y[k]=edge_y;z[k]=top-(q[k]-inside-2*arc-flat)
    x=LAYOUT['drape_anchor_x']-p
    # The developable initial fold needs no artificial pre-strain or pleat gain.
    placed=np.stack([x,y,z],-1).reshape(-1,3)
    T=door_transform();placed=placed@T[:3,:3].T+T[:3,3]
    rest=np.stack([s,np.zeros_like(s),-t],-1).reshape(-1,3)
    return placed,rest,np.array(faces,np.int32),np.stack([u,v],-1).reshape(-1,2)

def doorstop_mesh(p):
    """A floor-supported wedge, broad below the door with a thin rear nose."""
    import trimesh
    w,d,h=p['stop_dimensions'];front_h=.140
    vertices=np.array([[-w/2,-d/2,0],[w/2,-d/2,0],[-w/2,d/2,0],[w/2,d/2,0],
        [-w/2,-d/2,front_h],[w/2,-d/2,front_h],[-w/2,d/2,h],[w/2,d/2,h]])
    faces=np.array([[0,2,3],[0,3,1],[0,1,5],[0,5,4],[2,6,7],[2,7,3],[0,4,6],[0,6,2],
        [1,3,7],[1,7,5],[4,5,7],[4,7,6]])
    mesh=trimesh.Trimesh(vertices+np.array(p['stop_location']),faces,process=True);mesh.fix_normals()
    assert mesh.is_watertight and mesh.volume>0
    return mesh

def boxes():
    front=LAYOUT.get('frame_front_y',0.)
    return {'right_stile':([.07,.018,.652],[.455,.009+front,.446]),
            'left_stile':([.03,.018,.652],[-.025,.009+front,.446]),
            'bottom_rail':([.418,.06,.022],[.210,.03+front,.107]),
            'rear_panel':([.50,.016,.675],[.22,.50,.445])}

def cabinet_parts():
    """The fixed cabinet surfaces, including adjoining doors, before their union."""
    import trimesh
    parts=[]
    recipe=list(boxes().values())+[
        ([.42,.45,.018],[.21,.265,.125]),
        ([2.42,.44,.024],[.36,.275,.108]),
        (COUNTER_DIMENSIONS,COUNTER_CENTER),
        ([2.42,.055,.0995],[.36,.075,.05025])]
    recipe+=list(structural_boxes().values())
    for dimensions,center in recipe:
        m=trimesh.creation.box(dimensions);m.apply_translation(center);parts.append(m)
    for x in NEIGHBOR_CENTERS:
        m=trimesh.creation.box([.465,.018,.65]);m.apply_translation([x,-.010,.445]);parts.append(m)
        if not neighbor_has_handle(x):continue
        hx=neighbor_handle_x(x)
        for dx in [-.045,.045]:
            m=trimesh.creation.cylinder(radius=.005,height=.027,sections=12)
            m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1.,0.,0.]));m.apply_translation([hx+dx,-.032,.714]);parts.append(m)
        m=trimesh.creation.cylinder(radius=.005,height=.115,sections=12)
        m.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[0.,1.,0.]));m.apply_translation([hx,-.048,.714]);parts.append(m)
    for x in [.12,.28]:
        for j in range(3):
            m=trimesh.creation.cylinder(radius=.041,height=.012,sections=48)
            m.apply_translation([x,.29,.140+j*.012]);parts.append(m)
    return parts

def cabinet_collider():
    """Union the visible fixed cabinet surfaces, including adjoining doors.

    Joining manufacturing overlaps removes internal contact triangles rather
    than disabling checks between intersecting static components.
    """
    import trimesh
    mesh=trimesh.boolean.union(cabinet_parts(),engine='manifold');mesh.fix_normals()
    assert mesh.is_watertight and mesh.volume>0
    return mesh
