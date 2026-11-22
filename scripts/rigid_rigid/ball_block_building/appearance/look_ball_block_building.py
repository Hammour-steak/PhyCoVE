"""A joinery workshop in morning sun, and the hardwood ball and blocks; appearance only."""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)

from pcve_assets import asset as _pcve_asset
ASSETS=_pcve_asset('')/'polyhaven'/'ball_block_building'
ENVIRONMENT_THEME='joinery_workshop_morning_sun'

# Room lines are the inner faces of the brick walls. The simulator's bench
# stands in the middle of the room; the ball and blocks move along y = 0 between
# x = -0.66 and x = 1.13 (edit_low_block_friction), on the bench top z = 0.72.
# The camera (scene_config) stands in the south-east corner looking north-west.
ROOM=dict(x=(-3.00,2.95),y=(-3.95,1.30),ceiling_m=2.75)

LOOK=dict(
    # Poly Haven scans and the real size each was photographed at.
    brick=dict(stem='whitewashed_brick',tile_m=2.0),
    floor=dict(stem='garage_floor',tile_m=1.886),
    board=dict(stem='oriented_strand_board',tile_m=2.51),
    bench_top='ash_veneer',
    # The back (north) window is in the frame; the east window is behind its
    # right edge and is the one the low morning sun comes through. Its single
    # mullion throws its shadow behind the ball's lane, not across it.
    windows=[dict(wall='north',span=(-1.35,.25),z=(1.00,2.35),panes=(4,4)),
             dict(wall='east',span=(-1.50,.60),z=(.90,2.50),panes=(2,1))],
    daylight=dict(sun_elevation_deg=24.,sun_heading_deg=160.,sun_energy=4.0,sun_color=(1.0,.93,.85),
        sky_strength=1.0,view_strength=2.0,hdri='ludwikowice_farmland_4k.hdr',
        # Azimuth of the HDRI's sun in its equirectangular image (brightest pixel).
        hdri_sun_u=.6002),
    tool_board=dict(x=(.45,2.05),z=(.98,1.95)),
)

# The moving bodies: a ball turned from teak and two blocks sawn from cherry
# and walnut offcuts, every one oiled. Grain axes are in each body's own frame;
# ``figure`` lifts the grain contrast so a 12 cm ball still reads as timber at
# the size it has in the frame.
# The ball and the cherry block are graded to a measured colour (linear RGB):
# ``scan_mean`` is the veneer scan's mean colour, ``albedo`` the oiled timber's,
# sRGB (105, 70, 48) for a deep oiled teak and (130, 88, 72), hue 16 deg, for
# aged cherry; the raw scans are the pale orange of fresh-cut wood.
WOODS=dict(ball=dict(stem='teak_veneer',axis='x',pith=(.21,.16),offset=(.31,.12),figure=.8,
        scan_mean=(.434,.2196,.0953),albedo=(.1413,.0612,.0296),oil=0.,roughness_range=(.30,.45),coat=.30),
    block_00=dict(stem='cherry_veneer',axis='z',pith=(.18,-.26),offset=(.62,.40),figure=.8,
        scan_mean=(.753,.4285,.242),albedo=(.223,.0976,.0648),oil=0.,roughness_range=(.38,.58),coat=.10),
    # The walnut veneer scan is the grey of raw sapwood-free walnut; oil turns it chocolate.
    block_01=dict(stem='american_walnut_veneer',axis='x',pith=(-.20,.31),offset=(.15,.70),tint=(.85,.60,.42),figure=.25,
        oil=.9,roughness_range=(.38,.58),coat=.10))
NAMES=dict(ball='teak',block_00='cherry',block_01='walnut')


def _wood(key):
    from workshop import solid_wood
    spec=WOODS[key]
    return solid_wood(f'Oiled {NAMES[key]} {"ball" if key=="ball" else "block"}',ASSETS,spec['stem'],axis=spec['axis'],
        pith=spec['pith'],offset=spec['offset'],oil=spec['oil'],roughness_range=spec['roughness_range'],coat=spec['coat'],
        ring_m=.0035 if key=='ball' else .0045,tint=spec.get('tint',(1.,1.,1.)),figure=spec['figure'],
        albedo=spec.get('albedo'),scan_mean=spec.get('scan_mean'))


def build_room(bpy,c):
    from workshop import build_workshop
    from building_geometry import table_parts
    return build_workshop(ROOM,LOOK,ASSETS,table_parts(c))


def make_ball(bpy,radius):
    """A turned ball at the simulated radius, origin at its centre."""
    bpy.ops.mesh.primitive_uv_sphere_add(segments=96,ring_count=48,radius=radius,location=(0,0,0))
    ball=bpy.context.object;ball.name='Rolling ball'
    for polygon in ball.data.polygons:polygon.use_smooth=True
    ball.data.materials.append(_wood('ball'))
    return ball


def make_block(bpy,key,size):
    """A sawn block exactly the size of its collision box, edges eased by 1.2 mm."""
    from workshop import box
    return box(key,(0,0,0),size,_wood(key),bevel=.0012)
