"""SI dimensions shared by collision geometry and imported visuals.

The desk is an analytic box; the visible desk is built on exactly this box, so
physics and visuals agree by construction. The
bottle is `assets/models/water_bottle__plastic_bottle.glb` scaled to bottle size;
its collision hull, centre of mass and inertia come from one exported mesh
(`assets/scenes/basketball_cup_collision/bottle_collision.json`), so hull,
visuals and mass properties can never drift apart. The thrown launch is an
aimed ballistic solution so every initial speed -- baseline or a TIMES 3 edit
-- still meets the bottle.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
from pcve_assets import asset as _pcve_asset
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import hashlib,json,math

SIM_HZ=1440
KEYS=('basketball','bottle')

# --- the desk: appearance/studio_room.py builds the visible desk on this box --
TABLE_TOP_Z=.80           # desk-top surface height
TABLE_CENTER=(2.09,-.53)  # desk footprint centre (world)
TABLE_HALF=(.40,.72)      # half extents of the desk top
TABLE_BODY=.40            # collider depth below the top (covers the desk body)
FLOOR_Z=0.

# --- the room's other static colliders ----------------------------------------
# Far safety walls, flush with the room's west, east, south and north planes
# (half extents, centre), and boxes for the solid wall, carton, coffee table and
# five furniture pieces (name, half extents, centre). The
# simulator creates them in exactly this order. In appearance/studio_room.py
# a visible surface stands on each box a moving body touches in the cases --
# the solid wall behind the desk (its x=2.50 face is the studio's east wall),
# the flat carton beside the desk and the low coffee table at the bottom-left
# corner of the frame. The bed, pillow, vent, sofa and chair boxes are never
# touched by any case and have no visible counterpart.
SAFETY_WALLS=(((.05,6,3),(-2.95,0,3)),((.05,6,3),(6.01,0,3)),
              ((6,.05,3),(1,-3.435,3)),((6,.05,3),(1,2.61,3)))
ROOM_PROPS=(('back_wall',(.06,1.94,1.23),(2.56,.52,1.23)),     # solid wall behind the desk
            ('bed',(1.18,1.11,.34),(1.32,1.35,.34)),
            ('bed_pillows',(.23,.755,.40),(2.26,1.345,.40)),
            ('vent_column',(.25,.055,1.275),(1.11,.465,1.455)),
            ('carton',(.32,.31,.09),(1.94,-1.58,.09)),          # flat carton beside the desk
            ('coffee_table',(.37,.775,.165),(-1.40,-.745,.165)),
            ('sofa',(.46,1.095,.40),(-2.51,-.655,.395)),
            ('chair',(.575,.59,.45),(-.895,1.01,.45)))

def prop_box(name):
    """World (min corner, max corner) of one of the ROOM_PROPS boxes."""
    half,centre=next((h,c) for n,h,c in ROOM_PROPS if n==name)
    return (tuple(c-h for c,h in zip(centre,half)),tuple(c+h for c,h in zip(centre,half)))

# --- bodies ----------------------------------------------------------------
BALL_RADIUS=.12           # size-7 basketball
BOTTLE_ASSET='water_bottle__plastic_bottle.glb'
_BOTTLE_PATH=(_pcve_asset('scenes')/'basketball_cup_collision'/'bottle_collision.json')
def _load_bottle():
    data=json.loads(_BOTTLE_PATH.read_text(encoding='utf-8'))
    asset=_pcve_asset('models')/data['asset']
    if hashlib.sha256(asset.read_bytes()).hexdigest()!=data['asset_sha256']:
        raise ValueError('Bottle collider is stale; export it again')
    return data
BOTTLE_DATA=_load_bottle()
BOTTLE_HEIGHT=BOTTLE_DATA['height_m']
BOTTLE_RADIUS=BOTTLE_DATA['max_radius_m']
COM_HEIGHT=BOTTLE_DATA['com_height_m']
BOTTLE_VERTICES=[tuple(v) for v in BOTTLE_DATA['vertices']]
BOTTLE_FACES=[tuple(f) for f in BOTTLE_DATA['faces']]

def _second_moments(vertices,faces):
    """Divergence-theorem volume and second moments of the bottle mesh."""
    volume=0.;squares=[0.,0.,0.]
    for ia,ib,ic in faces:
        a,b,c=vertices[ia],vertices[ib],vertices[ic]
        v=(a[0]*(b[1]*c[2]-b[2]*c[1])+a[1]*(b[2]*c[0]-b[0]*c[2])+a[2]*(b[0]*c[1]-b[1]*c[0]))/6.
        volume+=v
        for i in range(3):
            squares[i]+=v*(a[i]*a[i]+b[i]*b[i]+c[i]*c[i]+a[i]*b[i]+a[i]*c[i]+b[i]*c[i])/10.
    sign=1 if volume>=0 else -1
    return abs(volume),[x*sign for x in squares]

BOTTLE_MESH_VOLUME,_MESH_SQUARES=_second_moments(BOTTLE_VERTICES,BOTTLE_FACES)
# Inertia per unit mass of the bottle mesh about its COM (vertices already
# sit at the COM origin, so no parallel-axis shift is needed).
BOTTLE_INERTIA_PER_KG=[(_MESH_SQUARES[1]+_MESH_SQUARES[2])/BOTTLE_MESH_VOLUME,
                       (_MESH_SQUARES[0]+_MESH_SQUARES[2])/BOTTLE_MESH_VOLUME,
                       (_MESH_SQUARES[0]+_MESH_SQUARES[1])/BOTTLE_MESH_VOLUME]

# --- placement -------------------------------------------------------------
BOTTLE_X=1.84
BOTTLE_Y=-.53
BOTTLE_POSITION=[BOTTLE_X,BOTTLE_Y,TABLE_TOP_Z+COM_HEIGHT+.0001]
BALL_START=[.55,-.53,1.06]
# Thrown from the open side of the room, straight along the desk's long axis
# at the bottle: this is the launch pose the clip was framed around -- the
# ball enters frame from the left, chest-high, 1.15 m short of the desk edge
# and 1.37 m short of the bottle.
# Aimed at the ball's own first-contact point: with the ball centre at rim
# height one ball+body radius up-range of the bottle along the throw line,
# the sphere touches the bottle wall with a near-horizontal normal, so the
# impulse acts well above the bottle's COM without pressing it into the desk.
_THROW_DX=BOTTLE_X-BALL_START[0];_THROW_DY=BOTTLE_Y-BALL_START[1]
_THROW_D=math.hypot(_THROW_DX,_THROW_DY)
AIM_TARGET=[BOTTLE_X-_THROW_DX/_THROW_D*(BALL_RADIUS+BOTTLE_RADIUS),
            BOTTLE_Y-_THROW_DY/_THROW_D*(BALL_RADIUS+BOTTLE_RADIUS),
            TABLE_TOP_Z+BOTTLE_HEIGHT]

def throw_velocity(speed,start,target,g=9.81):
    """Low-arc ballistic launch direction that passes exactly through target.

    The throw is aimed, so every initial speed -- the baseline and any TIMES
    edit of it -- still meets the bottle instead of sailing over it.
    """
    dx=target[0]-start[0];dy=target[1]-start[1];h=target[2]-start[2]
    d=math.hypot(dx,dy)
    if d<=0:raise ValueError('Throw start and target share a vertical line')
    s2=speed*speed
    disc=s2*s2-g*(g*d*d+2*h*s2)
    if disc<0:
        raise ValueError(f'Throw speed {speed:g} m/s cannot reach the target {d:g} m away')
    theta=math.atan((s2-math.sqrt(disc))/(g*d))
    c=math.cos(theta)
    return [speed*c*dx/d,speed*c*dy/d,speed*math.sin(theta)]

def presence_index(key):
    """Slot of the bottle in the physics bottle_presence mask."""
    return {'bottle':0}[key]

def present(ph,key):
    if key=='basketball':
        return bool(ph.get('ball_presence',[1])[0])
    return bool(ph['bottle_presence'][presence_index(key)])

def layout(ph):
    return {'basketball':list(BALL_START),
            'bottle':list(ph['bottle_position'])}

def on_table(pos,margin=0.):
    """Whether a world point lies inside the desk footprint."""
    return (abs(pos[0]-TABLE_CENTER[0])<TABLE_HALF[0]-margin
            and abs(pos[1]-TABLE_CENTER[1])<TABLE_HALF[1]-margin)

def fixed_constants():
    return dict(table_top_z=TABLE_TOP_Z,table_center=TABLE_CENTER,table_half=TABLE_HALF,
                table_body=TABLE_BODY,floor_z=FLOOR_Z,ball_radius=BALL_RADIUS,
                bottle_asset=BOTTLE_ASSET,bottle_height=BOTTLE_HEIGHT,bottle_radius=BOTTLE_RADIUS,
                com_height=COM_HEIGHT,bottle_mesh_volume_m3=BOTTLE_MESH_VOLUME,
                ball_start=BALL_START,aim_target=AIM_TARGET,
                gravity_z=-9.81,sim_hz=SIM_HZ,solver_iterations=120,collision_margin_m=.0001)
