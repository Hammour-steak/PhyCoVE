"""Desk-action geometry shared by the solver and the renderer.

Units are metres. The imported desk GLB is placed with its feet on z=0 and is
not touched afterwards; DESK_Z is the desktop's top surface in that placement
(measured off the model: the desktop slab tops out at z=0.864 and the model's
lowest point sits 0.004 above the origin, so the shifted top is 0.860).

Dynamic bodies use a lathe/compound construction whose origin is each body's
centre of mass, so a replayed transform can be applied to the appearance mesh
directly. Every constant here is also baked into the fixed_constants payload.
"""
from pcve_project_paths import project_root as _pcve_project_root, scene_root as _pcve_scene_root
_PCVE_ROOT = _pcve_project_root(__file__)
_PCVE_SCENE_ROOT = _pcve_scene_root(__file__)
import math

KEYS = ('kettle', 'pen_holder', 'pen')
DESK_Z = 0.860
# Desktop slab footprint in the desk GLB's own placement (x/y ranges of the
# deskoffice... slab mesh), used for the static solver box and the stay-on-desk
# guard: centre (-0.0255, 0.3465), half extents (0.4275, 0.7525).
DESK_CENTRE_XY = (-0.0255, 0.3465)
DESK_HALF_XY = (0.4275, 0.7525)
SIM_HZ = 1440
GRAVITY = -9.81

# --- kettle: the bottle GLB's own silhouette, base plane at local z=0.002 ----
# A 17 cm PET water bottle with a flip-spout cap.  What matters for the action
# is the bottom: a flat disc with a sharp rim edge, and that edge acts as a
# fixed hinge while the bottle topples, so the cap sweeps into the pen cup
# instead of the base rolling backwards out of reach.
# Kettle collision profile: the water bottle GLB's measured silhouette times
# the single uniform scale 1.4015.  Each ring is (radius, z, centre_y).
#
# The bottle is NOT a concentric solid of revolution.  A least-squares circle
# through the body vertices gives centre (0.00000, -0.00478) and radius
# 0.03065 -- the body's axis sits 4.8 mm off the object's own z axis, so the
# body is 53 mm across in +y but 71 mm across in -y.  A per-height MAX radius
# about the object axis would turn that into a concentric 62 mm barrel; the
# solver would rest the barrel on the desk while the real flank hangs 8.6 mm in
# the air, for 85% of the clip.
#
# Every ring below is measured off the mesh in 2.5 mm bands, radius about the
# fitted axis, so the hull IS the skin's envelope: whichever face of the bottle
# ends up down, it is the skin that touches the desk.  z is measured from the
# base plane at 0.002 (the flat bottom disc), which is where make_kettle puts
# the model's own bottom plane -- so the table spans the skin's 170 mm exactly.
KETTLE_PROFILE = (
    (0.00000, 0.0020, -0.0048), (0.02863, 0.0020, -0.0048),   # flat bottom disc + rim
    (0.03036, 0.0037, -0.0048), (0.03065, 0.0067, -0.0048),   # rim flare into the body
    (0.03065, 0.1217, -0.0048),                               # straight body, 170 mm tall bottle
    (0.03036, 0.1237, -0.0048), (0.02939, 0.1267, -0.0048),   # shoulder
    (0.02794, 0.1287, -0.0048), (0.02515, 0.1317, -0.0048),
    (0.02386, 0.1337, -0.0048), (0.02383, 0.1367, -0.0048),   # neck
    (0.02371, 0.1387, -0.0048), (0.02355, 0.1417, -0.0048),
    (0.02349, 0.1437, -0.0048),                               # cap ring, widest part of the lid
    (0.02220, 0.1487, -0.0048), (0.02150, 0.1567, -0.0048),   # cap taper
    (0.02070, 0.1617, -0.0048), (0.01840, 0.1667, -0.0048),
    (0.00620, 0.1721, -0.0076), (0.00000, 0.1721, -0.0076),   # lid knob, offset to -y
)
# The flip spout: a lever arm on the +y flank of the cap.  Its cross-section is
# not a circle at any height -- it is a 7 mm wide bar whose y-extent grows from
# 0.020-0.030 where it meets the cap up to 0.034-0.035 at the tip -- so it is
# traced with four rings along its own axis.  It is the widest point of the
# bottle in the direction the topple carries it, so it has to be in the hull:
# without it the cap's leading edge is 16 mm narrower and the strike would
# arrive late enough to change the whole story.
KETTLE_SPOUT_RINGS = (
    (0.00700, 0.1450, +0.0250), (0.00720, 0.1500, +0.0268),
    (0.00600, 0.1560, +0.0300), (0.00470, 0.1677, +0.0311),
)
# The flip lever lying flat on the lid: a 14.6 x 45 mm paddle.  Near the top
# the cap's +y flank is this paddle, not the 47 mm cap cylinder -- at z 0.1672
# the skin still reaches y +0.0229 while the cap ring has already tapered to
# +0.0136, so without this lobe the clamp shaves the paddle's +y edge by up to
# 7.4 mm (a visible dent in the lid).  One narrow lobe covers it; it sits well
# behind the spout in the topple direction, so the strike is unaffected.
# Measured on the finished hull: worst clamp correction anywhere is 2.0 mm (at
# the spout's root, 2 vertices), 87 of 7237 vertices move more than 1 mm, and
# the body flank below z 0.05 is untouched.
KETTLE_LID_RINGS = (
    (0.00780, 0.1625, +0.0170), (0.00780, 0.1682, +0.0170),
)
# Launch pose applied at frame 1 (after the settle pre-roll).
#
# PURE GRAVITY TOPPLE, IN PLACE.  The bottle is tipped to 16 deg -- short of
# its 18.6 deg balance angle -- and a small angular velocity about the base
# rim's front edge carries it over that angle.  From there gravity does all
# the work.  The kick is a PIVOT-CONSISTENT velocity field (see the solver):
# omega about the resting base edge, so the edge stays planted at zero speed
# and the body never translates.  Measured: the COM drifts 108 mm over the
# whole topple, against 100.5 mm for the geometric in-place distance (base
# rim radius 0.0253 in the topple direction + COM height 0.0752 m) -- the
# bottle rotates over its own rim instead of lunging across the desk.
# There is no linear nudge (KETTLE_KICK_VY = 0): a forward COM velocity makes
# the bottle read as leaping up and smashing the cup.
#
# 5.35 rad/s is the smallest launch spin that survives the whole edit suite
# for THIS hull.  Below it the strike arrives late and nearly vertical: the
# cap lands on the cup's rim TOP ANNULUS, where the contact normal is purely
# vertical, and no amount of cup-mass tuning can tip a body that is only
# being pressed down.  Here the cap flank reaches the cup's OUTER WALL ~9 mm
# below the rim (normal horizontal, tip arm 2.06x the base radius) while the
# cup is still 100 mm from the pivot.
#
# The threshold depends on the hull: a per-height max radius about the object
# axis is 3 mm fatter across the cap, reaches the cup 5 ms early with the same
# spin and passes from 5.0 rad/s.
# Measured on the fitted hull: 5.26 fails the baseline (the pen stays in the
# cup), 5.28 to 5.44+ all pass.  The pen release is knife-edge in spin (it is
# a levering event, not a push), so this sits in the middle of the passing
# band rather than on its edge.
KETTLE_TILT_DEG = 16.0
KETTLE_KICK_OMEGA_X = 5.35           # rad/s about the topple axis
KETTLE_KICK_VY = 0.0                # m/s forward nudge (towards the cup)
# The bottle starts about a body-length away on a diagonal heading,
# staying clear of the keyboard prop (x <= 0.042, y <= 0.386 after the
# keyboard's 3 cm monitorward shift) and the rack stand-in (x >= 0.186):
# spawn x span [0.102, 0.173] threads between them. The hull already grazes
# the rack box by 1.3 mm at spawn -- moving the bottle 5 mm further out
# buries it 5.6 mm and the solver's push-out flips the topple, which is why
# the cup, not the bottle, is the body that gets repositioned when the strike
# needs tuning.
KETTLE_START_XY = (0.1376, 0.4689)
# Cup centre clear of the phone by more than the cup's lying-down diagonal
# (sqrt(0.084^2 + 0.095^2) = 0.127 m): the struck cup must have room to
# topple backwards flat without hitting the prop (phone face y = 0.749).
PEN_HOLDER_XY = (0.000, 0.600)
# Static solver stand-ins for props baked into the desk GLB (measured bounds).
# The keyboard is shifted 3 cm towards the monitor (-y) in the appearance
# module with the same delta applied here: the toppled bottle's base end
# sweeps to y ~ 0.406 and the keyboard's back edge sat at y 0.405 (1.6 mm
# graze); at -y 0.03 the closest approach grows to ~3 cm.
KEYBOARD_BOX = dict(centre=(-0.1575, 0.1705, 0.8790), half=(0.1995, 0.2155, 0.0190))
PHONE_BOX = dict(centre=(-0.0730, 0.9285, 0.9320), half=(0.1820, 0.1795, 0.0720))
# The right-half desk furniture -- two drawer units and the document rack --
# has no solver body; heavier-kettle variants can rebound into this area, so
# the stand-ins keep the solver from sending the bottle through visible furniture.
# Each stand-in is the measured sub-mesh bbox EXACTLY: the strike swing in
# every case grazes the drawer's front-left corner by ~9 mm (hull reach
# x=0.098 vs face x=0.102 -- a 1 cm outset box catches the swing and kills
# the baseline, an inset box lets the rebound bury into the skin), so only
# the exact box both leaves the strike alone and catches the rebound flush.
# The rack's back panel (x from 0.16, 3 mm from the baseline spawn hull)
# gets NO box: no body ever reaches its y-band. The upper tray tier
# (z >= 1.06) is beyond every body's reach.
RACK_BOXES = (
    dict(centre=(+0.2139, +0.6734, +0.9576), half=(0.1119, 0.0788, 0.0981)),  # front drawer unit
    dict(centre=(+0.2139, +0.9920, +0.9576), half=(0.1119, 0.0788, 0.0981)),  # rear drawer unit
    dict(centre=(+0.2999, +0.3449, +1.0085), half=(0.1141, 0.1370, 0.1485)),  # rack main frame (x face +5 mm, dropped to the desktop: the lying kettle's tail otherwise slides through the 6 mm slot under the box and grazes the shelf edge)
    dict(centre=(+0.3025, +0.3781, +0.8918), half=(0.1050, 0.1060, 0.0296)),  # rack bottom shelf
    dict(centre=(+0.3025, +0.3434, +1.0254), half=(0.1050, 0.0372, 0.1039)),  # rack mid shelf
    dict(centre=(+0.3279, +0.2982, +0.9747), half=(0.0860, 0.1157, 0.1152)),  # rack paper stack
)

# --- pen cup: wall ring + floor disc ----------------------------------------
HOLDER_RADIUS = 0.042               # outer radius; matches the scaled GLB cup
# Deliberately chunky 10 mm wall, so the mouth is a 32 mm inner radius.  The
# fitted hull's lid is 47 mm, narrower than the 64 mm mouth; the cap arrives
# nearly horizontal and meets the cup's OUTER WALL ~9 mm below the rim, and the
# measured contact normal there is horizontal in every case.  The chunky wall
# shortens the lever for anything that does reach the mouth, and a 32 mm mouth
# is what the whole strike sweep is validated against.
HOLDER_WALL = 0.010
# 9.5 cm tall. The height is a compromise the pure-gravity strike forces: the
# bottle's cap always LEADS the topple, so a short cup gets landed on from
# above (rim top annulus, vertical normal, no topple possible), while a tall
# one turns the strike into a side-wall hit but leaves the pen nowhere to
# drape. At 9.5 cm the cap flank meets the outer wall ~9 mm below the rim
# when the bottle is ~55 deg into the fall, giving a horizontal normal at a
# 2.06x-base-radius tip arm. Cup mass 0.080 kg: swept 0.05..0.12, the topple
# is mass-insensitive across that band, but 0.20 kg (a ceramic mug)
# only rocks to ~20 deg -- the mass ratio is what makes a 0.9 kg bottle able
# to knock the cup over at all.
HOLDER_HEIGHT = 0.095
HOLDER_FLOOR = 0.006                # floor disc thickness = inner floor height
HOLDER_SEGMENTS = 14
HOLDER_MASS_FLOOR = 0.004           # clearance so the cup never starts sunk

# --- pen: pybullet GEOM_CYLINDER, axis +Z ------------------------------------
PEN_RADIUS = 0.0048                 # the_pen.glb ships at true size: 143.4 mm x 9.6 mm
PEN_HALF_LENGTH = 0.0717
# The 143 mm pen is far longer than the 7 cm cup, so it rests the way pens
# really sit in a short cup: bottom end on the inner floor with its cap edge
# just touching the far (phone-side) inner wall, shaft resting exactly ON the
# near rim, top hanging outside on the kettle side. The angle solves
#   (bottom-to-rim-face run) * cot(lean) = rim height above floor + r / cos(lean)
# with both contacts engaged at spawn, so the settle pre-roll has nothing to
# correct: looser angles leave the shaft proud (the pen tips, slams the rim
# and skates) or embed it (instant ejection). The kettle-side drape is also
# mandatory: the far side is blocked by the phone prop box, which a far-side
# drape would stab straight into.
PEN_LEAN_DEG = 35.5
PEN_BOTTOM_INSET = HOLDER_RADIUS - HOLDER_WALL - PEN_RADIUS
# Horizontal unit vector the pen's TOP leans towards -- derived from the
# topple heading rather than hand-tuned, so it can never drift out of sync
# with the layout. The pen must protrude on the side the cup rotates TOWARDS
# (i.e. back down the kettle->cup heading): there the rim comes down on it and
# its far end strikes the desktop first and gets levered clear. Draped the
# other way the rim lifts instead, and the pen just rides the cup down and
# finishes lying inside the toppled bore -- out of sight and never "thrown".
# Swept the four cardinal directions plus both heading directions: only the
# two that point back along the heading release the pen (0.299 s / 1.45 m/s);
# the other four leave it captive.
_topple_dx = PEN_HOLDER_XY[0] - KETTLE_START_XY[0]
_topple_dy = PEN_HOLDER_XY[1] - KETTLE_START_XY[1]
_topple_len = math.hypot(_topple_dx, _topple_dy)
PEN_DRAPE_DIR = (-_topple_dx / _topple_len, -_topple_dy / _topple_len)

# Frictions from the same sweep that fixed the launch pose. High desk/cup
# friction keeps the struck cup from skidding (the pivot must form at the far
# bottom edge). KETTLE_FRICTION is deliberately LOW: as the bottle topples
# onto the cup its cap slides DOWN the cup's outer wall, and tangential
# friction there drags the near rim downward -- a moment at the maximum lever
# arm that pins the cup flat. With kettle friction at 0.80 the cup never
# rotated more than 0.6 deg no matter how light it was made; at 0.15 (smooth
# PET on glazed ceramic, mu ~ 0.14) the horizontal normal dominates and the
# cup goes clean over. Swept 0.06/0.10/0.15/0.22/0.25 against cup friction
# 1.3/1.6/1.9: the only cells that topple sit at the low-kettle-friction end.
DESK_FRICTION = 0.90
KETTLE_FRICTION = 0.15
HOLDER_FRICTION = 0.90
PEN_FRICTION = 0.60                  # swept 0.3..2.4 against the suite: 0.3 lets
# the hard-struck pen (heavy kettle, 3 m/s) roll ~7 cm to the desk's NW corner
# and drop off the edge; >= 1.0 grips the pen against the cup wall so hard it
# never releases; 0.6 stops the post-landing roll in time in every edit while
# the pen still slides out of the toppling cup.
RESTITUTION = 0.30                  # pairwise coefficient; sqrt is handed to Bullet


def kettle_com_height():
    """Centre of mass height of the kettle lathe (ring offsets do not change it)."""
    volume = 0.0
    moment = 0.0
    for (r1, z1, _), (r2, z2, _) in zip(KETTLE_PROFILE, KETTLE_PROFILE[1:]):
        dz = z2 - z1
        if dz == 0:
            continue
        # Conical frustum between the two rings.
        v = math.pi * dz * (r1 * r1 + r1 * r2 + r2 * r2) / 3.0
        zc = z1 + dz * (r1 * r1 + 2.0 * r1 * r2 + 3.0 * r2 * r2) / (
            4.0 * (r1 * r1 + r1 * r2 + r2 * r2)) if (r1 * r1 + r1 * r2 + r2 * r2) else z1 + dz / 2.0
        volume += v
        moment += v * zc
    return moment / volume if volume else 0.5 * KETTLE_PROFILE[-1][1]


KETTLE_COM_Z = kettle_com_height()
# GLB bottle metrics (measured off water_bottle__plastic_bottle.glb, about the
# bottle's own axis): stands upright, 4 meshes (body, shoulder ring, cap, lid),
# height 0.1213, straight body radius 0.0253 up to h 0.088, shoulder to a
# 0.0202 neck at h 0.100, cap flaring back to 0.0253, bottom plane z=0.0099.
# The skin is that model times ONE uniform scale 1.4015, so the bottle stands
# 170 mm tall -- the length the topple choreography was tuned around -- and the
# profile above is measured OFF that scaled skin.  The skin is the ground truth,
# so the scale is a constant and KETTLE_HEIGHT follows it; deriving the scale
# from the profile's top ring instead would make any profile edit silently
# resize the model (extending the table to the lid's real top, 2 mm higher than
# a flat top, would grow the bottle by 1.2%).
# No radial stretch anywhere: the hull is fitted to the skin, not the reverse.
# The cup's mouth is 0.032 inner radius and the spout reaches 0.0354, so the
# strike lands on the outside of the cup instead of plugging the mouth.
BOTTLE_MODEL_RADIUS = 0.0253
BOTTLE_MODEL_BOTTOM = 0.0099        # outer bottom of the GLB bottle above origin
BOTTLE_MODEL_HEIGHT = 0.1213
KETTLE_HULL_RADIUS = max(r for r, _, _ in KETTLE_PROFILE)
KETTLE_SCALE = 1.4015                # uniform: radius scale == height scale
KETTLE_HEIGHT = BOTTLE_MODEL_HEIGHT * KETTLE_SCALE
KETTLE_VSCALE = KETTLE_SCALE

# GLB cup metrics (measured off pen_holder.glb): outer radius 0.7975, outer
# height 2.128 in model units. The appearance module scales the imported cup
# with exactly these factors (radius true, height stretched to HOLDER_HEIGHT)
# so the wall meets the solver's compound shapes.
CUP_MODEL_RADIUS = 0.7975
CUP_MODEL_BOTTOM = 1.066            # outer bottom of the GLB cup below its centre
CUP_MODEL_HEIGHT = 2.128
CUP_SCALE = HOLDER_RADIUS / CUP_MODEL_RADIUS
CUP_VSCALE = HOLDER_HEIGHT / CUP_MODEL_HEIGHT


def holder_com_height():
    """COM height of the floor-disc + wall-ring compound, in the base frame."""
    disc_v = math.pi * (HOLDER_RADIUS - HOLDER_WALL) ** 2 * HOLDER_FLOOR
    ring_mid_r = HOLDER_RADIUS - HOLDER_WALL / 2.0
    seg_w = 2.0 * math.pi * ring_mid_r / HOLDER_SEGMENTS * 1.3   # overlap closes the ring
    wall_v = HOLDER_SEGMENTS * seg_w * HOLDER_WALL * HOLDER_HEIGHT
    return (disc_v * HOLDER_FLOOR / 2.0 + wall_v * HOLDER_HEIGHT / 2.0) / (disc_v + wall_v)


HOLDER_COM_Z = holder_com_height()
# Where the pen rests: computed from the drape pose in the solver; exposed
# here only for the fixed-constants payload and validators.
PEN_REST_Z_OFFSET = HOLDER_FLOOR + PEN_HALF_LENGTH * math.cos(math.radians(PEN_LEAN_DEG)) \
    + PEN_RADIUS


def kettle_hull_vertices(segments=64):
    """Convex-hull vertices of the kettle in the body (COM) frame.

    Every ring is emitted about its own centre, so the hull follows the skin's
    4.8 mm off-axis body instead of a concentric barrel.  The spout tube and
    the flip lever are extra lobes: a solid of revolution cannot describe
    either, but the convex hull of all three is the shape the solver needs.
    """
    verts = []
    for lobe in KETTLE_HULL_LOBES:
        for r, z, cy in lobe:
            if r <= 1e-9:
                verts.append([0.0, cy, z - KETTLE_COM_Z])
                continue
            for i in range(segments):
                a = i * 2 * math.pi / segments
                verts.append([r * math.cos(a), cy + r * math.sin(a), z - KETTLE_COM_Z])
    return verts


# Every lobe is a z-interpolated revolve: ((radius, z, centre_y), ...).  The
# first is the bottle itself and is extended past its ends (the skin never goes
# there); the other two only exist over their own z span.  The zero-radius
# apex rings are dropped here: for containment the widest ring at a height is
# the answer, and keeping a (0, z) cap would clamp the lid's top face to a
# point.
KETTLE_HULL_LOBES = (KETTLE_PROFILE, KETTLE_SPOUT_RINGS, KETTLE_LID_RINGS)
_KETTLE_LOBES = tuple(tuple((r, z - KETTLE_COM_Z, cy) for r, z, cy in lobe if r > 1e-9)
                      for lobe in KETTLE_HULL_LOBES)


def _ring_at(rings, z):
    """(radius, centre_y) of a ring table at height z, clamped at both ends."""
    if z <= rings[0][1]:
        return rings[0][0], rings[0][2]
    if z >= rings[-1][1]:
        return rings[-1][0], rings[-1][2]
    for (r1, z1, c1), (r2, z2, c2) in zip(rings, rings[1:]):
        if z1 <= z <= z2:
            t = (z - z1) / (z2 - z1) if z2 > z1 else 0.0
            return r1 + (r2 - r1) * t, c1 + (c2 - c1) * t
    return rings[-1][0], rings[-1][2]


def kettle_clamp_xy(x, y, z):
    """(x, y) of a skin vertex pulled inside the hull cross-section at height z.

    The hull is the convex hull of three lobes (bottle, spout, flip lever), so
    a vertex is legal as soon as it is inside ANY of them -- the union is a
    subset of the hull, which makes this test conservative.  A vertex outside
    every lobe is pushed onto the nearest one's surface.

    The profile is the skin's measured envelope, so on the body flank this
    never fires: the skin's widest vertex touches the hull exactly, and that is
    what makes the bottle sit on the desk instead of hovering over it.  What it
    does catch is the two lobes whose cross-sections are not circles -- the
    spout's square tube and the lever's flat paddle -- and it draws those
    corners back onto the circumscribing circle, by well under a millimetre.

    Clamping by RADIUS about the axis instead (the obvious version) is wrong
    here: the cap ring is 22 mm wide, so it would shave the 35 mm spout flat
    into the neck -- a 16 mm deformation of the visible model.
    """
    best = None
    for index, lobe in enumerate(_KETTLE_LOBES):
        if index and not (lobe[0][1] <= z <= lobe[-1][1]):
            continue
        r, cy = _ring_at(lobe, z)
        dy = y - cy
        d = math.hypot(x, dy) - r
        if d <= 0.0:
            return x, y
        if best is None or d < best[0]:
            best = (d, r, cy)
    if best is None:
        return x, y
    _, r, cy = best
    dy = y - cy
    length = math.hypot(x, dy)
    if length <= 1e-12:
        return x, y
    k = r / length
    return x * k, cy + dy * k


def holder_compound_specs():
    """(half_extents, position, yaw) of every wall box, plus the floor disc."""
    ring_mid_r = HOLDER_RADIUS - HOLDER_WALL / 2.0
    seg_w = 2.0 * math.pi * ring_mid_r / HOLDER_SEGMENTS * 1.3
    boxes = []
    for i in range(HOLDER_SEGMENTS):
        yaw = i * 2.0 * math.pi / HOLDER_SEGMENTS
        boxes.append(((seg_w / 2.0, HOLDER_WALL / 2.0, HOLDER_HEIGHT / 2.0),
                      (ring_mid_r * math.cos(yaw), ring_mid_r * math.sin(yaw), HOLDER_HEIGHT / 2.0),
                      yaw))
    return boxes


def fixed_constants():
    return dict(desk_z=DESK_Z, desk_centre_xy=DESK_CENTRE_XY, desk_half_xy=DESK_HALF_XY,
                kettle_profile=KETTLE_PROFILE, kettle_spout_rings=KETTLE_SPOUT_RINGS,
                kettle_com_z=KETTLE_COM_Z, kettle_height=KETTLE_HEIGHT,
                kettle_scale=KETTLE_SCALE, kettle_vscale=KETTLE_VSCALE,
                kettle_tilt_deg=KETTLE_TILT_DEG, kettle_kick_omega_x=KETTLE_KICK_OMEGA_X,
                kettle_kick_vy=KETTLE_KICK_VY, kettle_start_xy=KETTLE_START_XY, pen_holder_xy=PEN_HOLDER_XY,
                holder_radius=HOLDER_RADIUS, holder_wall=HOLDER_WALL, holder_height=HOLDER_HEIGHT,
                holder_floor=HOLDER_FLOOR, holder_segments=HOLDER_SEGMENTS, holder_com_z=HOLDER_COM_Z,
                cup_scale=CUP_SCALE, pen_radius=PEN_RADIUS, pen_half_length=PEN_HALF_LENGTH,
                pen_rest_z_offset=PEN_REST_Z_OFFSET, pen_lean_deg=PEN_LEAN_DEG,
                pen_bottom_inset=PEN_BOTTOM_INSET, pen_drape_dir=list(PEN_DRAPE_DIR),
                desk_friction=DESK_FRICTION, kettle_friction=KETTLE_FRICTION,
                holder_friction=HOLDER_FRICTION, pen_friction=PEN_FRICTION,
                rack_boxes=[dict(centre=list(b['centre']), half=list(b['half'])) for b in RACK_BOXES],
                restitution=RESTITUTION, gravity_z=GRAVITY, sim_hz=SIM_HZ,
                solver_iterations=120, collision_margin_m=0.0001)
