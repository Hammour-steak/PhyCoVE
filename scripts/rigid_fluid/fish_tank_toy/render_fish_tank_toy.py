"""Build, bake and render the fish-tank toy-car scene (rigid_fluid).

A 90 mm die-cast rally car falls into an aquarium standing on a toy chest under
the window of a children's bedroom.  The tank holds only water -- no gravel,
plants or decoration.  The car splashes, sinks and settles on the glass bottom.
The room, aquarium and toy are BlenderKit assets.  The car follows the analytic
trajectory from ``simulate_fish_tank_toy.py`` and drives a Mantaflow FLIP
obstacle (one-way coupling).

Run with Blender 4.3.2 from the repository root, e.g.::

    blender -b --python-exit-code 1 --python \
        scripts/rigid_fluid/fish_tank_toy/render_fish_tank_toy.py -- --out-dir <fresh dir>
"""

from __future__ import annotations
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _pcve_sys
    from pathlib import Path as _PcvePath
    # Portable native snapshots may omit the repository CLI adapter.
    if _PcvePath(__file__).with_name("entrypoints.json").is_file():
        _pcve_sys.path.insert(0, str(_PcvePath(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry as _pcve_prepare_entry
        _pcve_prepare_entry(__file__, 'render')
# PCVE_UNIFIED_ENTRY_END

import argparse
import gzip
import hashlib
import json
import math
import shutil
import struct
import subprocess
import sys
import time
from dataclasses import asdict, replace
from pathlib import Path

import bmesh
import bpy
from mathutils import Matrix, Vector
from mathutils.bvhtree import BVHTree

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(HERE))
from simulate_fish_tank_toy import PhysicsConfig, place_config, simulate  # noqa: E402

BLENDERKIT = ROOT / "assets/blenderkit"
SKETCHFAB = ROOT / "assets/sketchfab"
AQUARIUM_BLEND = BLENDERKIT / "aquarium_aquascape/aquarium.blend"
TOY_BLEND = BLENDERKIT / "rally_toy_car/rally_toy_car.blend"
# Cabinet dressing: a Sketchfab plant replaces
# the vase, with a compact stack of books balancing the right side. Tuple fields are
# (blend, tank-local (lx, ly), yaw offset, z lift, uniform scale,
#  child object names to hide).
DECOR = {
    "plant_pot": (
        SKETCHFAB / "plant_pot_ae825dd0d3c5437a953b4236d6cef08b/plant_pot.blend",
        (-0.40, 0.015), 0.28, 0.0, 0.32, (),
    ),
    "books": (
        BLENDERKIT / "books_stack/books_stack.blend",
        (0.40, -0.015), -0.18, 0.0, 0.82, (),
    ),
}
# A small photoscanned moss rock sits on the back-right of the glass floor,
# away from the car's central prescribed trajectory.  It is appearance-only:
# the accepted Mantaflow cache was baked without this negligible-volume rock.
# (blend, tank-local xyz, yaw offset, uniform scale).
TANK_DECOR = {
    "moss_rock": (
        BLENDERKIT / "moss_rock_photoscan/moss_rock_photoscan.blend",
        (0.14, 0.08, 0.057), 0.60, 0.55,
    ),
}
CAMERA_FSTOP = 5.6

# Rooms the scene can be built in.  "origin" is the tank's base centre; with a
# "support" object its z is taken from that object's top.  The tank's front
# pane faces +X when yaw = +pi/2 and -X when yaw = -pi/2.
ROOMS = {
    # Kids' bedroom: on the toy chest under the window, back edge flush with
    # the chest's back edge (x 1.80), 5 mm in front of the wall.
    "kids_bedroom": {
        "blend": BLENDERKIT / "cosmic_kids_bedroom/cosmic_kids_bedroom.blend",
        "origin": (1.625, -1.18, 0.428),
        "yaw": -math.pi / 2.0,
        "support": None,
        "cameras": {
            # Chosen from an eight-angle camera survey and moved +0.155 m
            # in x with the tank.
            "front_eye": ((0.675, -1.20, 0.95), (1.575, -1.22, 0.68), 35.0),
        },
    },
    # Living room: on the round glass coffee table in
    # front of the white sectional; the camera looks back toward the sofa.
    "sofa_living_room": {
        "blend": BLENDERKIT / "modern_cozy_living_room/modern_cozy_living_room.blend",
        "origin": (0.565, 0.0, None),
        "yaw": math.pi / 2.0,
        "support": "Passy round low table",
        "cameras": {},
    },
}
TANK_WATER_TOP_LOCAL = 0.33          # authored water level of the asset
GLASS_INNER_HALF = (0.2400, 0.1652)  # measured inner faces of the 5 mm panes
GLASS_OVERLAP = 0.0025               # liquid domain reaches into the panes
DOMAIN_BOTTOM_LOCAL = 0.0545         # inside the 10 mm glass base
DOMAIN_TOP_LOCAL = 0.46             # 7 cm above the glass rim
TOY_SCALE = 0.302                    # 298 mm asset -> 90 mm die-cast
LAMP_EMISSION = 30.0
LAMP_POWER_W = 40.0
# Everything inside the glass goes: the authored water, fish and the whole
# aquascape.  Only the glass, base, stand and LED bar remain.
DROP_MATERIALS = {"Aqua_Water", "Aqua_Fish", "Aqua_Leaves 1", "Aqua_Leaves 2", "Aqua_Sand",
                  "Aqua_Stones", "Aqua_Branch", "Aqua_Branch 2", "Aqua_Grass"}
SUBSTRATE_MATERIALS = {"Aqua_Base"}



def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
    defaults = PhysicsConfig()
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--out-dir", type=Path, required=True)
    p.add_argument("--toy-mass-kg", type=float, default=defaults.toy_mass_kg)
    p.add_argument("--water-density-kg-m3", type=float, default=defaults.water_density_kg_m3)
    p.add_argument("--water-kinematic-viscosity-m2-s", type=float,
                   default=defaults.water_kinematic_viscosity_m2_s)
    p.add_argument("--toy-presence", nargs=1, type=int, choices=(0, 1), default=list(defaults.toy_presence))
    p.add_argument("--water-presence", nargs=1, type=int, choices=(0, 1), default=list(defaults.water_presence))
    p.add_argument("--room", default="kids_bedroom", choices=sorted(ROOMS))
    p.add_argument("--camera", default=None, help="camera preset of the room (default: its first)")
    p.add_argument("--camera-survey", type=Path, default=None,
                   help="JSON list of {name, loc, target, lens}; renders stills per camera and exits")
    p.add_argument("--survey-frames", type=int, nargs="+", default=[11, 17, 40])
    p.add_argument("--resolution", type=int, nargs=2, default=[1280, 720])
    p.add_argument("--samples", type=int, default=96)
    p.add_argument("--exposure", type=float, default=0.0)
    p.add_argument("--domain-resolution", type=int, default=160)
    p.add_argument("--effector-subframes", type=int, default=24)
    p.add_argument("--time-scale", type=float, default=1.0)
    p.add_argument("--still-frames", type=int, nargs="*", default=None,
                   help="after baking, render only these frames (diagnostics)")
    p.add_argument("--skip-fluid-bake", action="store_true")
    p.add_argument("--skip-render", action="store_true")
    p.add_argument("--keep-intermediates", action="store_true")
    p.add_argument("--rerender-baked", action="store_true",
                   help="re-render a kept case directory with the current materials, no re-bake")
    p.add_argument("--scenario-overrides-json", type=Path, default=None,
                   help="PCVE {\"physics\": {field: value}} override; fields are PhysicsConfig names")
    p.add_argument("--led-size", type=float, nargs=2, default=[0.36, 0.08], metavar=("LONG", "SHORT"))
    p.add_argument("--mnee", action="store_true", help="Cycles shadow caustics from the LED through the water")
    p.add_argument("--no-dof", action="store_true")
    p.add_argument("--no-bubbles", action="store_true")
    p.add_argument("--bubble-trappedair-min", type=float, default=3.0)
    p.add_argument("--bubble-sampling", type=int, default=6)
    p.add_argument("--bubble-wavecrest-sampling", type=int, default=5)
    p.add_argument("--bubble-energy-min", type=float, default=2.0)
    p.add_argument("--no-motion-blur", action="store_true")
    p.add_argument("--blur-glossy", type=float, default=0.3)
    p.add_argument("--hide-bubbles", action="store_true", help="diagnostics: render without the bubble meshes")
    p.add_argument("--bake-frame-end", type=int, default=None, help="diagnostics: bake only the first N frames")
    p.add_argument("--clear-base", action="store_true")
    p.add_argument("--review-tag", default="review_stills")
    p.add_argument("--back-film", type=int, choices=(0, 1), default=0,
                   help="dark foil on the outside of the back pane")
    # Diagnostics for the volume-loss investigation.  Fractional obstacles
    # leaked water continuously once the car was submerged (64-cell test:
    # 0.970 of the volume by frame 32 and falling; without them 0.992, flat).
    p.add_argument("--fractions", action="store_true")
    p.add_argument("--cfl", type=float, default=2.0)
    p.add_argument("--method", choices=("FLIP", "APIC"), default="FLIP")
    p.add_argument("--timesteps", type=int, nargs=2, default=[2, 8], metavar=("MIN", "MAX"))
    p.add_argument("--viscosity-mode", choices=("diffusion", "solver"), default="diffusion",
                   help="how a raised viscosity is simulated (see README)")
    p.add_argument("--particle-number", type=int, default=2)
    p.add_argument("--particle-band-width", type=float, default=3.0)
    p.add_argument("--mesh-particle-radius", type=float, default=2.0,
                   help="Mantaflow liquid mesh reconstruction radius")
    p.add_argument("--mesh-smoothen-pos", type=int, default=2)
    p.add_argument("--mesh-smoothen-neg", type=int, default=1)
    return p.parse_args(argv)


ARGS = parse_args()
OUT = ARGS.out_dir.expanduser().resolve()
ROOM = ROOMS[ARGS.room]
ROOM_BLEND = ROOM["blend"]
TANK_YAW = ROOM["yaw"]
# z is resolved from the support's top once the room is open.
TANK_ORIGIN = Vector((ROOM["origin"][0], ROOM["origin"][1], ROOM["origin"][2] or 0.0))
CAMERA_NAME = ARGS.camera or next(iter(ROOM["cameras"]), None)


def tank_to_world(lx: float, ly: float, lz: float) -> Vector:
    return TANK_ORIGIN + Matrix.Rotation(TANK_YAW, 3, "Z") @ Vector((lx, ly, lz))


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def append_objects(path: Path) -> list[bpy.types.Object]:
    with bpy.data.libraries.load(str(path), link=False) as (src, dst):
        dst.objects = list(src.objects)
    objects = [o for o in dst.objects if o is not None]
    for obj in objects:
        bpy.context.scene.collection.objects.link(obj)
    return objects


def world_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
    return (Vector([min(p[i] for p in pts) for i in range(3)]),
            Vector([max(p[i] for p in pts) for i in range(3)]))


# --------------------------------------------------------------------- assets
def build_aquarium() -> dict:
    objects = append_objects(AQUARIUM_BLEND)
    root = next(o for o in objects if o.type == "EMPTY")
    tank = next(o for o in objects if o.type == "MESH")
    root.name, tank.name = "PCVE_Aquarium", "PCVE_AquariumTank"
    root.location, root.rotation_euler = TANK_ORIGIN, (0.0, 0.0, TANK_YAW)
    names = {i: s.material.name for i, s in enumerate(tank.material_slots) if s.material}

    bm = bmesh.new()
    bm.from_mesh(tank.data)
    dropped = [f for f in bm.faces if names.get(f.material_index) in DROP_MATERIALS]
    bmesh.ops.delete(bm, geom=dropped, context="FACES")
    bm.to_mesh(tank.data)
    bm.free()
    bpy.context.view_layer.update()

    # Collision BVH of the glass base, used for the landing height check.
    bm = bmesh.new()
    bm.from_mesh(tank.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if names.get(f.material_index) not in SUBSTRATE_MATERIALS],
                     context="FACES")
    bm.transform(tank.matrix_world)
    substrate = BVHTree.FromBMesh(bm)
    bm.free()

    add_background_film_and_lamp(names, tank)
    return {"root": root, "tank": tank, "substrate_bvh": substrate, "dropped_faces": len(dropped)}


def add_background_film_and_lamp(names: dict[int, str], tank: bpy.types.Object) -> None:
    """Dress the tank like a real aquarium.

    An optional matte black-blue film on the outside of the back pane (standard
    aquarium background foil) stops the bedroom wall reading through the water,
    and the LED bar gets a real downward area light so the interior is lit from
    above as aquariums are, rather than only by the dim room.
    """
    film = bpy.data.materials.new("PCVE_AquariumBackFilm")
    film.use_nodes = True
    bsdf = film.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.004, 0.008, 0.014, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.55
    half_x = GLASS_INNER_HALF[0] + 0.005
    y = GLASS_INNER_HALF[1] + 0.0055
    me = bpy.data.meshes.new("PCVE_AquariumBackFilm")
    me.from_pydata([(-half_x, y, 0.057), (half_x, y, 0.057), (half_x, y, 0.388), (-half_x, y, 0.388)],
                   [], [(0, 1, 2, 3)])
    me.materials.append(film)
    # The asset's root empty is scaled 0.3217, so nothing new is parented to
    # it: the film and LED are placed directly in world space.
    me.transform(Matrix.Translation(TANK_ORIGIN) @ Matrix.Rotation(TANK_YAW, 4, "Z"))
    obj = bpy.data.objects.new("PCVE_AquariumBackFilm", me)
    if ARGS.back_film:
        bpy.context.scene.collection.objects.link(obj)

    for i, name in names.items():
        if name == "Aqua_Light":
            emission = next(n for n in tank.material_slots[i].material.node_tree.nodes if n.type == "EMISSION")
            emission.inputs["Strength"].default_value = LAMP_EMISSION
    light = bpy.data.lights.new("PCVE_AquariumLED", "AREA")
    light.shape = "RECTANGLE"
    light.size, light.size_y = 0.36, 0.08
    light.energy = LAMP_POWER_W
    light.color = (0.97, 0.99, 1.0)
    lamp = bpy.data.objects.new("PCVE_AquariumLED", light)
    bpy.context.scene.collection.objects.link(lamp)
    place_led(lamp)


def place_led(lamp: bpy.types.Object) -> None:
    """Put the LED area light just under the lamp bar, in world space.

    Parented to the asset's 0.3217-scaled root it would sit inside the water
    8.5 cm above the glass bottom (world z 0.57) instead of under the lamp bar
    (z 0.86).
    """
    lamp.parent = None
    lamp.matrix_world = Matrix.Translation(tank_to_world(0.0, 0.0, 0.432)) @ Matrix.Rotation(TANK_YAW, 4, "Z")
    lamp.data.energy = LAMP_POWER_W
    lamp.data.size, lamp.data.size_y = ARGS.led_size


def tank_depth_vector(nt: bpy.types.NodeTree, geometry: bpy.types.Node) -> bpy.types.NodeSocket:
    """Vector whose X is the shading point's depth along the tank's front-to-back axis.

    Depth is measured from the tank centre in metres, positive toward the back
    pane (tank-local +Y), so the same thresholds work for any room and yaw.
    """
    rel = nt.nodes.new("ShaderNodeVectorMath")
    rel.operation = "SUBTRACT"
    nt.links.new(geometry.outputs["Position"], rel.inputs[0])
    rel.inputs[1].default_value = tuple(TANK_ORIGIN)
    dot = nt.nodes.new("ShaderNodeVectorMath")
    dot.operation = "DOT_PRODUCT"
    nt.links.new(rel.outputs["Vector"], dot.inputs[0])
    dot.inputs[1].default_value = tuple(Matrix.Rotation(TANK_YAW, 3, "Z") @ Vector((0.0, 1.0, 0.0)))
    combine = nt.nodes.new("ShaderNodeCombineXYZ")
    nt.links.new(dot.outputs["Value"], combine.inputs["X"])
    return combine.outputs["Vector"]


def drop_pane_reflections(mat: bpy.types.Material, back_x: float, front_x: float) -> None:
    """No mirror images in the back pane and no room reflection on the front pane.

    The asset's panes are IOR-1.0 glass plus a fixed 6 % glossy layer, so the
    back pane mirrored the toy into the middle of the tank (and, with no water,
    still did).  The image has to go entirely, so
    for the camera's specular chain -- no diffuse bounce yet, not a shadow ray
    -- the back pane (tank depth > back_x) is a plain Transparent BSDF.  This
    includes rays reaching it straight through the open top (depth 0), which
    showed the floating car mirrored above the waterline.  The front pane
    (tank depth < front_x) is Transparent for the same rays too: the user asked
    for no room reflections on the front glass (the striped rug behind the
    camera showed in it).  The side panes keep the authored shader, and
    diffuse/shadow paths keep it everywhere so the light bouncing around the
    tank is unchanged.
    """
    nt = mat.node_tree
    output = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    authored = output.inputs["Surface"].links[0].from_socket
    path = nt.nodes.new("ShaderNodeLightPath")
    geometry = nt.nodes.new("ShaderNodeNewGeometry")
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tank_depth_vector(nt, geometry), split.inputs["Vector"])

    def math(op, a, b):
        node = nt.nodes.new("ShaderNodeMath")
        node.operation = op
        for socket, value in zip(node.inputs, (a, b)):
            if isinstance(value, bpy.types.NodeSocket):
                nt.links.new(value, socket)
            else:
                socket.default_value = value
        return node.outputs["Value"]

    camera_chain_on_back_pane = math(
        "MULTIPLY",
        math("MAXIMUM", math("GREATER_THAN", split.outputs["X"], back_x),
             math("LESS_THAN", split.outputs["X"], front_x)),
        math("MULTIPLY", math("SUBTRACT", 1.0, path.outputs["Is Shadow Ray"]),
             math("LESS_THAN", path.outputs["Diffuse Depth"], 0.5)))
    # Shadow rays pass every pane: the asset's Glass BSDF blocked direct light,
    # so with the tank against the back of the chest the wall behind it (lit
    # only through the tank) rendered black.  Thin flat panes transmit ~92 %.
    transparent = nt.nodes.new("ShaderNodeBsdfTransparent")
    final = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(math("MAXIMUM", camera_chain_on_back_pane, path.outputs["Is Shadow Ray"]), final.inputs["Fac"])
    nt.links.new(authored, final.inputs[1])
    nt.links.new(transparent.outputs["BSDF"], final.inputs[2])
    nt.links.new(final.outputs["Shader"], output.inputs["Surface"])


def localise_wall_ao() -> None:
    """Stop room shaders darkening whatever stands behind the tank.

    The bedroom's wall material multiplies in an Ambient Occlusion node with a
    1 m distance.  AO ignores transparency, so with the tank 5 mm in front of
    the wall, the wall behind it rendered black through the water.  Every AO node in the room is set to "Only Local", which keeps
    an object's own crease darkening and ignores other objects.
    """
    for mat in bpy.data.materials:
        if mat.use_nodes and mat.node_tree:
            for node in mat.node_tree.nodes:
                if node.type == "AMBIENT_OCCLUSION":
                    node.only_local = True


def resolve_support_height() -> None:
    """Set the tank base on top of the room's support object, if it has one."""
    global TANK_ORIGIN
    if ROOM["support"] is None:
        return
    support = bpy.data.objects[ROOM["support"]]
    top = max((support.matrix_world @ Vector(c)).z for c in support.bound_box)
    TANK_ORIGIN = Vector((TANK_ORIGIN.x, TANK_ORIGIN.y, top))


def clear_tank_footprint() -> list[str]:
    """Hide small decor that would stand inside the tank (books, cups ...)."""
    corners = [tank_to_world(sx * 0.27, sy * 0.195, 0.0) for sx in (-1, 1) for sy in (-1, 1)]
    x0, x1 = min(c.x for c in corners), max(c.x for c in corners)
    y0, y1 = min(c.y for c in corners), max(c.y for c in corners)
    hidden = []
    for obj in bpy.context.scene.objects:
        if obj.type != "MESH" or obj.name.startswith("PCVE_") or obj.hide_render:
            continue
        pts = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
        lo = Vector([min(p[i] for p in pts) for i in range(3)])
        hi = Vector([max(p[i] for p in pts) for i in range(3)])
        if max(hi - lo) > 1.0 or hi.z <= TANK_ORIGIN.z + 0.002 or lo.z > TANK_ORIGIN.z + 0.9:
            continue
        if hi.x > x0 and lo.x < x1 and hi.y > y0 and lo.y < y1:
            obj.hide_render = obj.hide_viewport = True
            hidden.append(obj.name)
    return hidden


def back_wall_x() -> float:
    """Tank depth beyond which only the back pane / back water face lie.

    Back pane inner face is at tank-local +y = GLASS_INNER_HALF[1]; the liquid
    surface sits 2.5 mm beyond it.  1.5 cm of margin keeps the car and its
    splash out of the selection.
    """
    return GLASS_INNER_HALF[1] - 0.015


def front_wall_x() -> float:
    """Tank depth below which only the front pane / front water face lie (1 cm in)."""
    return -GLASS_INNER_HALF[1] + 0.010


def clear_glass_base_and_tint_panes() -> None:
    """Real-glass look for the tank.

    * The panes get a float-glass green volume absorption, so their polished
      edges read green.
    * ``--clear-base`` turns the asset's black smoked base into a clear plate
      over the wooden stand top.  Tried for floor caustics and rejected: from
      this near-horizontal camera the caustics are not visible and the clear
      floor reads as more water, so the car seems to float.
    """
    tint_panes()
    if not ARGS.clear_base:
        return
    base = bpy.data.materials["Aqua_Base"]
    nt = base.node_tree
    output = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    for link in list(output.inputs["Surface"].links):
        nt.links.remove(link)
    transparent = nt.nodes.new("ShaderNodeBsdfTransparent")
    gloss = nt.nodes.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Roughness"].default_value = 0.05
    mix = nt.nodes.new("ShaderNodeMixShader")
    mix.inputs["Fac"].default_value = 0.05
    nt.links.new(transparent.outputs["BSDF"], mix.inputs[1])
    nt.links.new(gloss.outputs["BSDF"], mix.inputs[2])
    path = nt.nodes.new("ShaderNodeLightPath")
    shadow = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(path.outputs["Is Shadow Ray"], shadow.inputs["Fac"])
    nt.links.new(mix.outputs["Shader"], shadow.inputs[1])
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs["BSDF"], shadow.inputs[2])
    nt.links.new(shadow.outputs["Shader"], output.inputs["Surface"])


def tint_panes() -> None:
    for mat in bpy.data.materials:
        if mat.name.startswith("Aqua_Glass Clear"):
            gnt = mat.node_tree
            gout = next(n for n in gnt.nodes if n.type == "OUTPUT_MATERIAL")
            if gout.inputs["Volume"].links:
                continue
            absorb = gnt.nodes.new("ShaderNodeVolumeAbsorption")
            absorb.inputs["Color"].default_value = (0.55, 0.80, 0.70, 1.0)
            absorb.inputs["Density"].default_value = 8.0  # 25 turned pane edges black
            gnt.links.new(absorb.outputs["Volume"], gout.inputs["Volume"])


def place_decor() -> list[str]:
    """Place grounded photoreal decor without obscuring the interaction."""
    # A kept bake file can already contain a dressing pass.  Replace it instead
    # of stacking multiple generations at nearly the same coordinates.
    for obj in list(bpy.data.objects):
        if obj.name.startswith(("PCVE_Prop_", "PCVE_Decor_", "PCVE_TankDecor_")):
            bpy.data.objects.remove(obj, do_unlink=True)
    placed = []
    for name, (blend, (lx, ly), yaw, lift, scale, hidden_children) in DECOR.items():
        objects = append_objects(blend)
        for obj in objects:
            if obj.name in hidden_children:
                obj.hide_render = obj.hide_viewport = True
        roots = [o for o in objects if o.parent is None]
        p = tank_to_world(lx, ly, 0.0)
        for root in roots:
            root.location = (p.x, p.y, TANK_ORIGIN.z + lift)
            root.rotation_euler = (0.0, 0.0, TANK_YAW + yaw)
            # Some BlenderKit files carry their normalization on the root
            # (the rattan basket ships at 0.153).  Multiply rather than replace
            # that authored transform, otherwise a 22 cm basket becomes >1 m.
            root.scale = tuple(component * scale for component in root.scale)
        for obj in objects:
            obj.name = f"PCVE_Decor_{name}_{obj.name}"
        placed.append(name)
    for name, (blend, (lx, ly, lz), yaw, scale) in TANK_DECOR.items():
        objects = append_objects(blend)
        roots = [o for o in objects if o.parent is None]
        p = tank_to_world(lx, ly, lz)
        for root in roots:
            root.location = p
            root.rotation_euler = (0.0, 0.0, TANK_YAW + yaw)
            root.scale = tuple(component * scale for component in root.scale)
        for obj in objects:
            obj.name = f"PCVE_TankDecor_{name}_{obj.name}"
        placed.append(name)
    return placed


def animate_dynamic_rock(trajectory: dict, add_effector: bool) -> str | None:
    """Drive the scanned moss rock and, when needed, a smooth fluid proxy."""
    if trajectory["quality"].get("rock_first_lift_frame") is None:
        return None
    roots = [
        obj for obj in bpy.data.objects
        if obj.parent is None and obj.name.startswith("PCVE_TankDecor_moss_rock_")
    ]
    if len(roots) != 1:
        raise RuntimeError(f"Expected one moss-rock root, found {[obj.name for obj in roots]}")
    root = roots[0]
    keys = trajectory.get("rock_fractional_keyframes", []) + trajectory["rock_frames"]
    half_h = 0.5 * trajectory["objects"]["moss_rock"]["dimensions_m"][2]
    for key in sorted(keys, key=lambda item: item["frame"]):
        x, y, center_z = key["location"]
        root.location = (x, y, center_z - half_h)
        root.keyframe_insert("location", frame=key["frame"])
    for curve in root.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"

    if not add_effector:
        return root.name
    dims = trajectory["objects"]["moss_rock"]["dimensions_m"]
    bpy.ops.mesh.primitive_ico_sphere_add(subdivisions=2, radius=1.0)
    proxy = bpy.context.object
    proxy.name = "PCVE_MossRockCollisionProxy"
    proxy.scale = (0.5 * dims[0], 0.5 * dims[1], 0.5 * dims[2])
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    for key in sorted(keys, key=lambda item: item["frame"]):
        proxy.location = key["location"]
        proxy.keyframe_insert("location", frame=key["frame"])
    for curve in proxy.animation_data.action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = "LINEAR"
    modifier = proxy.modifiers.new("Fluid", "FLUID")
    modifier.fluid_type = "EFFECTOR"
    modifier.effector_settings.surface_distance = 0.0005
    modifier.effector_settings.subframes = ARGS.effector_subframes
    return root.name


def focus_camera(camera: bpy.types.Object) -> None:
    """Shallow depth of field focused on the drop point, like a phone/DSLR shot."""
    camera.data.dof.use_dof = True
    # The bedroom's camera ships with a focus object, which overrides
    # focus_distance; left in place it threw the whole tank out of focus.
    camera.data.dof.focus_object = None
    camera.data.dof.focus_distance = (camera.location - tank_to_world(0.0, -0.11, 0.17)).length
    camera.data.dof.aperture_fstop = CAMERA_FSTOP


def enable_shadow_caustics() -> None:
    """MNEE: sharp, low-noise caustics of the LED through the water surface."""
    bpy.data.objects["PCVE_AquariumLED"].data.cycles.is_caustics_light = True
    for name in ("PCVE_LiquidDomain", "PCVE_StillWater"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.cycles.is_caustics_caster = True
    for obj in bpy.context.scene.objects:
        if obj.type == "MESH" and not obj.name.startswith(("PCVE_LiquidDomain", "PCVE_StillWater", "PCVE_InitialWater")):
            obj.cycles.is_caustics_receiver = True


def realism_pass(camera: bpy.types.Object, *, refresh_decor: bool = True) -> list[str]:
    # Motion blur on the car only: Mantaflow's per-vertex speed vectors are
    # noisy and smeared the surface highlights into white foam-like bands and
    # the entry cavity into white streaks.
    for name in ("PCVE_LiquidDomain", "PCVE_StillWater"):
        obj = bpy.data.objects.get(name)
        if obj is not None:
            obj.cycles.use_motion_blur = False
    clear_glass_base_and_tint_panes()
    # A baked scene already contains the accepted dressing and any animation
    # applied to it (notably the density-edit moss rock).  Replacing that
    # dressing during ``--rerender-baked`` would silently discard those
    # keyframes and turn the rock back into a static floor prop.
    decor = place_decor() if refresh_decor else []
    if not ARGS.no_dof:
        focus_camera(camera)
    if ARGS.mnee:
        enable_shadow_caustics()
    return decor


def rerender_baked() -> None:
    """Re-render a kept case with the current materials, without re-baking.

    Opens the case's saved scene (``scene_baked.blend`` when it has a fluid
    cache, else ``scene.blend``), swaps in a fresh copy of the asset glass and
    a fresh water material, applies the current shading fixes and re-renders.
    The fluid cache, trajectory and ground truth are untouched.
    """
    blend = OUT / "scene_baked.blend"
    if not blend.is_file():
        blend = OUT / "scene.blend"
    bpy.ops.wm.open_mainfile(filepath=str(blend), load_ui=False)
    scene = bpy.context.scene
    resolve_support_height()
    with bpy.data.libraries.load(str(AQUARIUM_BLEND), link=False) as (src, dst):
        dst.materials = ["Aqua_Glass Clear"]
    glass = dst.materials[0]
    tank = bpy.data.objects["PCVE_AquariumTank"]
    for slot in tank.material_slots:
        if slot.material and slot.material.name.startswith("Aqua_Glass Clear") and slot.material != glass:
            slot.material = glass
    drop_pane_reflections(glass, back_wall_x(), front_wall_x())
    place_led(bpy.data.objects["PCVE_AquariumLED"])
    localise_wall_ao()
    domain = bpy.data.objects.get("PCVE_LiquidDomain")
    still = bpy.data.objects.get("PCVE_StillWater")
    for obj in (domain, still):
        if obj is not None:
            obj.data.materials[0] = water_material(back_wall_x(), front_wall_x())
    configure_render(scene, scene.frame_end)
    realism_pass(scene.camera, refresh_decor=False)
    if ARGS.hide_bubbles and "PCVE_Bubbles" in bpy.data.collections:
        bpy.data.collections["PCVE_Bubbles"].hide_render = True
    if ARGS.still_frames:
        stills = OUT / ARGS.review_tag
        stills.mkdir(exist_ok=True)
        for frame in ARGS.still_frames:
            scene.frame_set(frame)
            scene.render.filepath = str(stills / f"frame_{frame:04d}.png")
            bpy.ops.render.render(write_still=True)
        return
    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    t0 = time.time()
    for frame in range(1, scene.frame_end + 1):
        scene.frame_set(frame)
        scene.render.filepath = str(frames_dir / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    encode(frames_dir, OUT / "video.mp4", scene.frame_end)
    shutil.rmtree(frames_dir)
    metadata_path = OUT / "scenario_metadata.json"
    metadata = json.loads(metadata_path.read_text())
    metadata["rerendered"] = {"from": blend.name, "seconds": time.time() - t0,
                              "reason": "no glass/water-wall reflections; caustics on; LED under the lamp bar; panes shadow-transparent; wall AO local only"}
    metadata_path.write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    print("RERENDERED", OUT / "video.mp4")


def ground(bvh: BVHTree, x: float, y: float) -> float:
    hit = bvh.ray_cast(Vector((x, y, 2.0)), Vector((0, 0, -1)))
    if hit[0] is None:
        raise RuntimeError(f"No substrate under ({x:.3f}, {y:.3f})")
    return hit[0].z


def build_toy() -> tuple[bpy.types.Object, bpy.types.Object, dict]:
    """Return (collision hull carrying the animation, visual car, metrics)."""
    car = next(o for o in append_objects(TOY_BLEND) if o.type == "MESH")
    car.name = "PCVE_ToyCar"
    me = car.data
    me.transform(Matrix.Scale(TOY_SCALE, 4))
    lo = Vector([min(v.co[i] for v in me.vertices) for i in range(3)])
    hi = Vector([max(v.co[i] for v in me.vertices) for i in range(3)])
    me.transform(Matrix.Translation(-(lo + hi) * 0.5))
    car.location = (0, 0, 0)
    car.scale = (1, 1, 1)
    bm = bmesh.new()
    bm.from_mesh(me)
    volume = bm.calc_volume(signed=False)
    hull = bm.copy()
    result = bmesh.ops.convex_hull(hull, input=hull.verts[:])
    bmesh.ops.delete(hull, geom=[g for g in result["geom_interior"] if isinstance(g, bmesh.types.BMVert)],
                     context="VERTS")
    hull_volume = hull.calc_volume(signed=False)
    hull_mesh = bpy.data.meshes.new("PCVE_ToyCarHull")
    hull.to_mesh(hull_mesh)
    hull.free()
    bm.free()
    proxy = bpy.data.objects.new("PCVE_ToyCarCollisionHull", hull_mesh)
    bpy.context.scene.collection.objects.link(proxy)
    proxy.display_type = "WIRE"
    proxy.hide_render = True
    car.parent = proxy
    dims = hi - lo
    return proxy, car, {"dimensions_m": [dims.x, dims.y, dims.z], "mesh_volume_m3": volume,
                        "hull_volume_m3": hull_volume}


def check_config(config: PhysicsConfig, measured: dict) -> None:
    """The analytic model's geometry constants must match the built scene."""
    checks = {
        "water_surface_z_m": (config.water_surface_z_m, measured["water_surface_z_m"], 1e-3),
        "substrate_z_m": (config.substrate_z_m, measured["substrate_z_m"], 2.5e-3),
        "toy_length_m": (config.toy_length_m, measured["toy"]["dimensions_m"][1], 1e-3),
        "toy_width_m": (config.toy_width_m, measured["toy"]["dimensions_m"][0], 1e-3),
        "toy_height_m": (config.toy_height_m, measured["toy"]["dimensions_m"][2], 1e-3),
        "toy_volume_m3": (config.toy_volume_m3, measured["toy"]["mesh_volume_m3"], 3e-6),
        "tank_inner_x_lo": (config.tank_inner_x_m[0], measured["tank_inner_x_m"][0], 1e-3),
        "tank_inner_x_hi": (config.tank_inner_x_m[1], measured["tank_inner_x_m"][1], 1e-3),
        "tank_inner_y_lo": (config.tank_inner_y_m[0], measured["tank_inner_y_m"][0], 1e-3),
        "tank_inner_y_hi": (config.tank_inner_y_m[1], measured["tank_inner_y_m"][1], 1e-3),
    }
    bad = {k: (a, b) for k, (a, b, tol) in checks.items() if abs(a - b) > tol}
    if bad:
        raise RuntimeError(f"PhysicsConfig does not match the scene: {json.dumps(bad)}")


def landing_height(bvh: BVHTree, x: float, y: float, yaw: float, config: PhysicsConfig) -> float:
    rot = Matrix.Rotation(yaw, 3, "Z")
    best = -1.0
    for i in range(7):
        for j in range(5):
            off = rot @ Vector(((j / 4 - 0.5) * config.toy_width_m * 0.9,
                                (i / 6 - 0.5) * config.toy_length_m * 0.9, 0.0))
            best = max(best, ground(bvh, x + off.x, y + off.y))
    return best


# ------------------------------------------------------------------ materials
def water_material(back_wall_x: float, front_wall_x: float) -> bpy.types.Material:
    mat = bpy.data.materials.new("PCVE_AquariumWater")
    mat.use_nodes = True
    nt = mat.node_tree
    bsdf = nt.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (1.0, 1.0, 1.0, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.0
    bsdf.inputs["IOR"].default_value = 1.333
    bsdf.inputs["Transmission Weight"].default_value = 1.0
    # The back wall of the water (world +X, against the back pane) refracts
    # without reflecting for the camera's specular chain: the user does not
    # want the toy's mirror image in the back of the tank.  A
    # ray trace of the ghost pixels found exactly one path: in through the
    # front face, a 2 % Fresnel reflection off this face, onto the car.  The
    # face is selected by position because Cycles flips normals toward the
    # incoming ray, so from inside the water it reads as -X.  The front face
    # (against the front pane) gets the same treatment because the user asked
    # for no room reflections on the front glass; it is selected
    # by position plus |normal.x|, so the top surface next to the glass keeps
    # its reflections.  Diffuse-bounce and shadow paths keep the full Fresnel
    # interface, so the car's lighting is unchanged.
    refract = nt.nodes.new("ShaderNodeBsdfRefraction")
    refract.inputs["IOR"].default_value = 1.333
    refract.inputs["Roughness"].default_value = 0.0
    geometry = nt.nodes.new("ShaderNodeNewGeometry")
    path = nt.nodes.new("ShaderNodeLightPath")
    split = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(tank_depth_vector(nt, geometry), split.inputs["Vector"])

    def math(op, x, y):
        node = nt.nodes.new("ShaderNodeMath")
        node.operation = op
        for socket, value in zip(node.inputs, (x, y)):
            if isinstance(value, bpy.types.NodeSocket):
                nt.links.new(value, socket)
            else:
                socket.default_value = value
        return node.outputs["Value"]

    normal = nt.nodes.new("ShaderNodeSeparateXYZ")
    nt.links.new(geometry.outputs["Normal"], normal.inputs["Vector"])
    front_face = math("MULTIPLY", math("LESS_THAN", split.outputs["X"], front_wall_x),
                      math("GREATER_THAN", math("ABSOLUTE", normal.outputs["X"], 0.0), 0.7))
    wall_camera_chain = math(
        "MULTIPLY",
        math("MAXIMUM", math("GREATER_THAN", split.outputs["X"], back_wall_x), front_face),
        math("MULTIPLY", math("LESS_THAN", path.outputs["Diffuse Depth"], 0.5),
             math("SUBTRACT", 1.0, path.outputs["Is Shadow Ray"])))
    mix = nt.nodes.new("ShaderNodeMixShader")
    nt.links.new(wall_camera_chain, mix.inputs["Fac"])
    nt.links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    nt.links.new(refract.outputs["BSDF"], mix.inputs[2])
    nt.links.new(mix.outputs["Shader"], nt.nodes["Material Output"].inputs["Surface"])
    absorb = nt.nodes.new("ShaderNodeVolumeAbsorption")
    # Lighter than the first pass (0.80/0.94/0.90 at 1.2), which together with
    # the blue wall made the water read as a solid blue block.
    absorb.inputs["Color"].default_value = (0.88, 0.96, 0.94, 1.0)
    absorb.inputs["Density"].default_value = 0.5
    nt.links.new(absorb.outputs["Volume"], nt.nodes["Material Output"].inputs["Volume"])
    return mat


def add_box(name: str, lo: Vector, hi: Vector) -> bpy.types.Object:
    me = bpy.data.meshes.new(name)
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bm.transform(Matrix.Diagonal((*(hi - lo), 1.0)))
    bm.to_mesh(me)
    bm.free()
    obj = bpy.data.objects.new(name, me)
    obj.location = (lo + hi) * 0.5
    bpy.context.scene.collection.objects.link(obj)
    return obj


def viscosity_parts(nu: float) -> tuple[float, int]:
    exponent = max(0, int(math.ceil(-math.log10(nu))))
    base = nu * 10.0 ** exponent
    while base < 1.0:
        exponent += 1
        base *= 10.0
    return base, exponent


# --------------------------------------------------------------------- render
def bubble_material() -> bpy.types.Material:
    """Air inside water: IOR 1/1.333, so bubble rims show total internal reflection."""
    mat = bpy.data.materials.new("PCVE_AirBubble")
    mat.use_nodes = True
    nt = mat.node_tree
    for node in list(nt.nodes):
        if node.type != "OUTPUT_MATERIAL":
            nt.nodes.remove(node)
    output = next(n for n in nt.nodes if n.type == "OUTPUT_MATERIAL")
    glass = nt.nodes.new("ShaderNodeBsdfGlass")
    glass.inputs["IOR"].default_value = 1.0 / 1.333
    glass.inputs["Roughness"].default_value = 0.0
    shadow = nt.nodes.new("ShaderNodeMixShader")
    path = nt.nodes.new("ShaderNodeLightPath")
    nt.links.new(path.outputs["Is Shadow Ray"], shadow.inputs["Fac"])
    nt.links.new(glass.outputs["BSDF"], shadow.inputs[1])
    nt.links.new(nt.nodes.new("ShaderNodeBsdfTransparent").outputs["BSDF"], shadow.inputs[2])
    nt.links.new(shadow.outputs["Shader"], output.inputs["Surface"])
    return mat


BUBBLE_FLAG = 1 << 2      # Mantaflow ParticleTypeBubble
DELETED_FLAG = 1 << 10    # ParticleTypeDelete


def add_bubble_geometry(domain: bpy.types.Object, frame_end: int, surface_z: float) -> dict:
    """Turn Mantaflow's baked bubble particles into per-frame bubble meshes.

    Background renders do not draw Mantaflow's secondary particle systems, so
    the ppSnd cache (PB02: count + grid size, then x, y, z, flag per particle in
    grid units) is read directly, as the bowling-pool scene does for spray.
    Only live bubble particles below the water surface are kept; each becomes a
    small icosphere (0.8-2.2 mm radius, deterministic per index and frame).
    """
    cache = OUT / "fluid_cache" / "particles"
    corners = [domain.matrix_world @ v.co for v in domain.data.vertices]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    size = Vector([max(c[i] for c in corners) for i in range(3)]) - lo
    mat = bubble_material()
    collection = bpy.data.collections.new("PCVE_Bubbles")
    bpy.context.scene.collection.children.link(collection)
    phi = (1.0 + math.sqrt(5.0)) / 2.0
    unit = 1.0 / math.sqrt(1.0 + phi * phi)
    ico_v = [Vector(v) * unit for v in ((-1, phi, 0), (1, phi, 0), (-1, -phi, 0), (1, -phi, 0), (0, -1, phi),
                                        (0, 1, phi), (0, -1, -phi), (0, 1, -phi), (phi, 0, -1), (phi, 0, 1),
                                        (-phi, 0, -1), (-phi, 0, 1))]
    ico_f = ((0, 11, 5), (0, 5, 1), (0, 1, 7), (0, 7, 10), (0, 10, 11), (1, 5, 9), (5, 11, 4), (11, 10, 2),
             (10, 7, 6), (7, 1, 8), (3, 9, 4), (3, 4, 2), (3, 2, 6), (3, 6, 8), (3, 8, 9), (4, 9, 5), (2, 4, 11),
             (6, 2, 10), (8, 6, 7), (9, 8, 1))
    counts = {}
    for frame in range(1, frame_end + 1):
        path = cache / f"ppSnd_{frame:04d}.uni"
        if not path.exists():
            continue
        payload = gzip.open(path, "rb").read()
        if payload[:4] != b"PB02":
            raise RuntimeError(f"Unsupported Mantaflow particle cache: {path}")
        count, sx, sy, sz = struct.unpack_from("<4i", payload, 4)
        cell = max(size) / max(sx, sy, sz)
        verts, faces = [], []
        kept = 0
        for i in range(count):
            x, y, z, flag = struct.unpack_from("<fffi", payload, 292 + i * 16)
            if not flag & BUBBLE_FLAG or flag & DELETED_FLAG:
                continue
            p = lo + Vector((x, y, z)) * cell
            if p.z > surface_z - 0.002:
                continue
            r = 0.0008 + 0.0014 * (((i * 2654435761 + frame * 40503) % 1000) / 1000.0)
            base = len(verts)
            verts.extend(tuple(p + v * r) for v in ico_v)
            faces.extend(tuple(base + k for k in f) for f in ico_f)
            kept += 1
        counts[frame] = kept
        if not kept:
            continue
        mesh = bpy.data.meshes.new(f"PCVE_Bubbles_{frame:04d}")
        mesh.from_pydata(verts, [], faces)
        for poly in mesh.polygons:
            poly.use_smooth = True
        mesh.materials.append(mat)
        obj = bpy.data.objects.new(f"PCVE_Bubbles_{frame:04d}", mesh)
        collection.objects.link(obj)
        for f, hidden in ((1, True), (frame - 1, True), (frame, False), (frame + 1, True)):
            if f >= 1:
                obj.hide_render = hidden
                obj.keyframe_insert("hide_render", frame=f)
        for curve in obj.animation_data.action.fcurves:
            for key in curve.keyframe_points:
                key.interpolation = "CONSTANT"
    print("BUBBLES", {f: c for f, c in counts.items() if c})
    return {"per_frame": counts, "peak": max(counts.values(), default=0)}


def liquid_volume_log(scene: bpy.types.Scene, domain: bpy.types.Object, frame_end: int) -> list[dict]:
    """Baked liquid-mesh volume and surface level per sampled frame.

    With fractional obstacles a bake lost 29 % of its water after the car
    entered (42.9 L -> 30.6 L, level -7.7 cm).  Every bake records this so a
    leak shows up in the metadata instead of in the video.
    """
    rows = []
    for frame in sorted(frame for frame in {1, 12, 24, 36, 48, 60, 72, 84, frame_end}
                        if frame <= frame_end):
        scene.frame_set(frame)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        evaluated = domain.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        bm = bmesh.new()
        bm.from_mesh(mesh)
        volume = abs(bm.calc_volume(signed=True))
        bm.free()
        tops = sorted((domain.matrix_world @ v.co).z for v in mesh.vertices if v.normal.z > 0.9)
        evaluated.to_mesh_clear()
        rows.append({"frame": frame, "volume_l": volume * 1000.0,
                     "surface_median_z_m": tops[len(tops) // 2] if tops else None})
        print("VOLUME", rows[-1])
    return rows


def configure_render(scene: bpy.types.Scene, frame_end: int) -> None:
    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    for backend in ("OPTIX", "CUDA"):
        try:
            prefs.compute_device_type = backend
            prefs.get_devices()
            break
        except Exception:
            continue
    for device in prefs.devices:
        device.use = device.type == prefs.compute_device_type
    scene.cycles.device = "GPU"
    scene.cycles.samples = ARGS.samples
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 16
    scene.cycles.transmission_bounces = 16
    scene.cycles.transparent_max_bounces = 16
    # Refractive caustics must be on: with them off, Cycles renders the view
    # *through* the water (the wall behind the tank) black, and the LED above
    # the water cannot light the toy through the surface.
    scene.cycles.caustics_refractive = True
    scene.cycles.caustics_reflective = True
    scene.cycles.blur_glossy = ARGS.blur_glossy
    scene.render.use_persistent_data = True
    scene.render.resolution_x, scene.render.resolution_y = ARGS.resolution
    scene.render.resolution_percentage = 100
    # Half-frame shutter, as a real 24 fps camera; the liquid mesh carries
    # Mantaflow speed vectors so the splash blurs too.
    scene.render.use_motion_blur = not ARGS.no_motion_blur
    scene.render.motion_blur_shutter = 0.5
    scene.render.fps = PhysicsConfig.fps
    scene.frame_start, scene.frame_end = 1, frame_end
    scene.view_settings.exposure = ARGS.exposure
    scene.render.image_settings.file_format = "PNG"


def aim(camera: bpy.types.Object, loc, target, lens: float) -> None:
    camera.location = Vector(loc)
    camera.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat("-Z", "Y").to_euler()
    camera.data.lens = lens
    camera.data.dof.use_dof = False


def encode(frames_dir: Path, video: Path, frame_end: int) -> None:
    subprocess.run([
        "ffmpeg", "-v", "error", "-y", "-framerate", str(PhysicsConfig.fps),
        "-i", str(frames_dir / "frame_%04d.png"), "-frames:v", str(frame_end),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-crf", "16", str(video),
    ], check=True)
    probe = json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "v:0", "-count_frames",
        "-show_entries", "stream=width,height,avg_frame_rate,nb_read_frames", "-of", "json", str(video),
    ], text=True))["streams"][0]
    assert (probe["width"], probe["height"]) == tuple(ARGS.resolution), probe
    assert probe["avg_frame_rate"] == f"{PhysicsConfig.fps}/1", probe
    assert int(probe["nb_read_frames"]) == frame_end, probe


# ----------------------------------------------------------------------- main
def main() -> None:
    if ARGS.rerender_baked:
        rerender_baked()
        return
    survey = ARGS.camera_survey is not None
    suite_inputs = {"scenario_overrides.json", "prompts.json"}  # written by the PCVE builder
    if OUT.exists() and any(p.name not in suite_inputs for p in OUT.iterdir()) and not ARGS.skip_fluid_bake:
        raise FileExistsError(f"Refusing to reuse non-empty output directory {OUT}")
    OUT.mkdir(parents=True, exist_ok=True)
    started = time.time()
    bpy.ops.wm.open_mainfile(filepath=str(ROOM_BLEND), load_ui=False)
    scene = bpy.context.scene
    resolve_support_height()
    hidden_decor = clear_tank_footprint()

    aquarium = build_aquarium()
    localise_wall_ao()
    proxy, car, toy_metrics = build_toy()

    base = place_config(PhysicsConfig(), tuple(TANK_ORIGIN), TANK_YAW)
    config = replace(
        base,
        toy_mass_kg=ARGS.toy_mass_kg,
        water_density_kg_m3=ARGS.water_density_kg_m3,
        water_kinematic_viscosity_m2_s=ARGS.water_kinematic_viscosity_m2_s,
        toy_presence=tuple(ARGS.toy_presence),
        water_presence=tuple(ARGS.water_presence),
    )
    if ARGS.scenario_overrides_json:
        physics = json.loads(ARGS.scenario_overrides_json.read_text())["physics"]
        timed_edits = physics.pop("timed_edits", [])
        unknown = set(physics) - set(asdict(base))
        if unknown:
            # A silently ignored key would render a copy of the source video.
            raise KeyError(f"Unknown physics override(s): {sorted(unknown)}")
        config = replace(config, **{k: tuple(v) if isinstance(v, list) else v for k, v in physics.items()})
    else:
        timed_edits = []
    # Landing footprint of the source trajectory (geometry check only).
    source_final = simulate(base)["frames"][-1]
    measured = {
        "water_surface_z_m": tank_to_world(0, 0, TANK_WATER_TOP_LOCAL).z,
        "substrate_z_m": landing_height(aquarium["substrate_bvh"], source_final["location"][0],
                                        source_final["location"][1], source_final["rotation_euler"][2], base),
        "toy": toy_metrics,
        "tank_inner_x_m": sorted((tank_to_world(0, -GLASS_INNER_HALF[1], 0).x,
                                  tank_to_world(0, GLASS_INNER_HALF[1], 0).x)),
        "tank_inner_y_m": sorted((tank_to_world(-GLASS_INNER_HALF[0], 0, 0).y,
                                  tank_to_world(GLASS_INNER_HALF[0], 0, 0).y)),
    }
    print("MEASURED", json.dumps(measured))
    check_config(config, measured)
    trajectory = simulate(config, include_fractional_keys=True, schedule=timed_edits)
    frame_end = trajectory["frame_end"]

    toy_present = bool(config.toy_presence[0])
    water_present = bool(config.water_presence[0])
    if toy_present:
        keys = trajectory["fractional_keyframes"] + [
            {"frame": r["frame"], "location": r["location"], "rotation_euler": r["rotation_euler"]}
            for r in trajectory["frames"]
        ]
        for key in sorted(keys, key=lambda k: k["frame"]):
            proxy.location = key["location"]
            proxy.rotation_euler = key["rotation_euler"]
            proxy.keyframe_insert("location", frame=key["frame"])
            proxy.keyframe_insert("rotation_euler", frame=key["frame"])
        for curve in proxy.animation_data.action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = "LINEAR"
    else:
        car.hide_render = car.hide_viewport = True

    lo_d = tank_to_world(-(GLASS_INNER_HALF[0] + GLASS_OVERLAP), -(GLASS_INNER_HALF[1] + GLASS_OVERLAP),
                         DOMAIN_BOTTOM_LOCAL)
    hi_d = tank_to_world(GLASS_INNER_HALF[0] + GLASS_OVERLAP, GLASS_INNER_HALF[1] + GLASS_OVERLAP,
                         DOMAIN_TOP_LOCAL)
    lo_d, hi_d = (Vector([min(lo_d[i], hi_d[i]) for i in range(3)]),
                  Vector([max(lo_d[i], hi_d[i]) for i in range(3)]))
    water_mat = water_material(back_wall_x(), front_wall_x())
    gel_mode = config.water_kinematic_viscosity_m2_s >= 0.1
    if gel_mode:
        water_bsdf = water_mat.node_tree.nodes["Principled BSDF"]
        water_bsdf.inputs["Base Color"].default_value = (0.82, 0.94, 0.92, 1.0)
        water_bsdf.inputs["Roughness"].default_value = 0.16
        water_bsdf.inputs["IOR"].default_value = 1.38
        for node in water_mat.node_tree.nodes:
            if node.type == "BSDF_REFRACTION":
                node.inputs["Roughness"].default_value = 0.08
    drop_pane_reflections(bpy.data.materials["Aqua_Glass Clear"], back_wall_x(), front_wall_x())
    # Blender 4.3's high-viscosity liquid path is numerically invalid in this
    # thin aquarium (it climbs the glass before impact).  The gel edit uses a
    # stable reduced-order car trajectory in a still translucent gel volume;
    # this is explicitly recorded as an appearance/trajectory approximation.
    run_fluid = toy_present and water_present and not survey and not gel_mode
    domain = None
    if water_present and not run_fluid:
        # Survey and DELETE-toy cases: a still, source-matched water volume.
        still = add_box("PCVE_StillWater", lo_d, Vector((hi_d.x, hi_d.y, config.water_surface_z_m)))
        still.data.materials.append(water_mat)
    if run_fluid:
        domain = add_box("PCVE_LiquidDomain", lo_d, hi_d)
        for poly in domain.data.polygons:
            poly.use_smooth = True
        domain.data.materials.append(water_mat)
        ds_mod = domain.modifiers.new("Fluid", "FLUID")
        ds_mod.fluid_type = "DOMAIN"
        ds = ds_mod.domain_settings
        ds.domain_type = "LIQUID"
        ds.resolution_max = ARGS.domain_resolution
        ds.cache_type = "ALL"
        ds.cache_directory = str(OUT / "fluid_cache")
        ds.cache_frame_start, ds.cache_frame_end = 1, frame_end
        ds.cache_data_format = "UNI"
        ds.cache_mesh_format = "BOBJECT"
        ds.use_mesh = True
        ds.mesh_scale = 2
        ds.mesh_generator = "IMPROVED"
        # Radius 1.0 / smoothing 1 left droplet islands floating on the surface
        # for seconds in the 112-cell probe; these values merge them back.
        ds.mesh_particle_radius = ARGS.mesh_particle_radius
        ds.mesh_smoothen_pos = ARGS.mesh_smoothen_pos
        ds.mesh_smoothen_neg = ARGS.mesh_smoothen_neg
        ds.simulation_method = ARGS.method
        if ARGS.method == "FLIP":
            ds.flip_ratio = 0.90
        ds.particle_number = ARGS.particle_number
        ds.particle_band_width = ARGS.particle_band_width
        ds.particle_radius = 1.0
        ds.use_adaptive_timesteps = True
        ds.cfl_condition = ARGS.cfl
        ds.timesteps_min, ds.timesteps_max = ARGS.timesteps
        ds.time_scale = ARGS.time_scale
        ds.use_fractions = ARGS.fractions
        ds.fractions_threshold = 0.05
        ds.gravity = (0.0, 0.0, -config.gravity_m_s2)
        nu = config.water_kinematic_viscosity_m2_s
        ds.viscosity_base, ds.viscosity_exponent = viscosity_parts(min(nu, 9.99))
        # Blender 4.3's high-viscosity solver makes the liquid climb the glass
        # walls within 3 frames here (nu = 0.01, with or without diffusion),
        # so viscosity edits default to Mantaflow's diffusion term.
        ds.use_viscosity = ARGS.viscosity_mode == "solver" and nu >= 1.0e-2
        ds.use_diffusion = not ds.use_viscosity
        if ds.use_viscosity:
            # Same convention as coffee_ice_drop: the high-viscosity solver
            # takes the kinematic value (Mantaflow normalises density to 1).
            ds.viscosity_value = nu
        ds.use_collision_border_top = False
        ds.use_speed_vectors = not ARGS.no_motion_blur
        # Entrained air: Mantaflow's trapped-air secondary particles become
        # rendered bubbles after the bake (see add_bubble_geometry).
        ds.use_bubble_particles = not ARGS.no_bubbles
        ds.use_spray_particles = False
        ds.use_foam_particles = False
        ds.use_tracer_particles = False
        ds.sndparticle_potential_min_trappedair = ARGS.bubble_trappedair_min
        ds.sndparticle_potential_max_trappedair = ARGS.bubble_trappedair_min * 4.0
        ds.sndparticle_sampling_trappedair = ARGS.bubble_sampling
        # Wave-crest sampling (200 by default) produced most of the particles;
        # inside the liquid they are classified as bubbles too, which gave a
        # dense grey cloud of ~35k bubbles in the first 112-cell test.
        ds.sndparticle_sampling_wavecrest = ARGS.bubble_wavecrest_sampling
        ds.sndparticle_potential_min_wavecrest = 4.0
        ds.sndparticle_potential_min_energy = ARGS.bubble_energy_min
        ds.sndparticle_life_min, ds.sndparticle_life_max = 8.0, 24.0
        if ARGS.bake_frame_end:
            ds.cache_frame_end = ARGS.bake_frame_end
        scene.use_gravity = True
        scene.gravity = (0.0, 0.0, -config.gravity_m_s2)

        initial = add_box("PCVE_InitialWater", lo_d, Vector((hi_d.x, hi_d.y, config.water_surface_z_m)))
        flow = initial.modifiers.new("Fluid", "FLUID")
        flow.fluid_type = "FLOW"
        flow.flow_settings.flow_type = "LIQUID"
        flow.flow_settings.flow_behavior = "GEOMETRY"
        flow.flow_settings.surface_distance = 0.0
        initial.hide_render = True
        initial.display_type = "WIRE"

        eff = proxy.modifiers.new("Fluid", "FLUID")
        eff.fluid_type = "EFFECTOR"
        eff.effector_settings.surface_distance = 0.0005
        eff.effector_settings.subframes = ARGS.effector_subframes

    configure_render(scene, frame_end)
    camera = scene.camera
    loc, target, lens = ROOM["cameras"][CAMERA_NAME] if CAMERA_NAME else ((0, 0, 1), tuple(TANK_ORIGIN), 35.0)
    aim(camera, loc, target, lens)
    realism_decor = realism_pass(camera)
    dynamic_rock = animate_dynamic_rock(trajectory, add_effector=run_fluid)

    metadata = {
        "scene_id": "fish_tank_toy",
        "interaction_category": "rigid_fluid",
        "software": "Blender 4.3.2 / Mantaflow FLIP / Cycles",
        "coupling": trajectory["coupling"],
        "physics": asdict(config),
        "timed_edits": timed_edits,
        "gel_approximation": gel_mode,
        "gel_approximation_note": (
            "analytic viscous-drag trajectory plus a still translucent gel volume; "
            "Mantaflow high-viscosity solve rejected because it climbs the aquarium walls"
            if gel_mode else None
        ),
        "measured_geometry": measured,
        "trajectory_quality": trajectory["quality"],
        "back_film": bool(ARGS.back_film),
        "dropped_asset_faces": aquarium["dropped_faces"],
        "domain_world_bounds_m": [list(lo_d), list(hi_d)],
        "domain_resolution": ARGS.domain_resolution if run_fluid else None,
        "liquid_mesh_reconstruction": ({
            "particle_radius": ARGS.mesh_particle_radius,
            "smoothen_positive": ARGS.mesh_smoothen_pos,
            "smoothen_negative": ARGS.mesh_smoothen_neg,
        } if run_fluid else None),
        "approx_cell_size_m": max(hi_d - lo_d) / ARGS.domain_resolution if run_fluid else None,
        "room": ARGS.room,
        "tank_origin_m": list(TANK_ORIGIN),
        "tank_yaw_rad": TANK_YAW,
        "hidden_decor": hidden_decor,
        "decor": realism_decor,
        "dynamic_rock": dynamic_rock,
        "render": {"resolution": ARGS.resolution, "samples": ARGS.samples, "camera": CAMERA_NAME,
                   "camera_location": list(loc), "camera_target": list(target), "lens_mm": lens},
        "assets": {p.name: sha256(p) for p in (ROOM_BLEND, AQUARIUM_BLEND, TOY_BLEND)},
    }
    (OUT / "scenario_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
    (OUT / "ground_truth_transforms.json").write_text(
        json.dumps({k: v for k, v in trajectory.items() if k != "fractional_keyframes"}, indent=2) + "\n",
        encoding="utf-8")

    if survey:
        cams = json.loads(ARGS.camera_survey.read_text())
        for cam in cams:
            aim(camera, cam["loc"], cam["target"], cam.get("lens", 35.0))
            for frame in ARGS.survey_frames:
                scene.frame_set(frame)
                scene.render.filepath = str(OUT / f"{cam['name']}_f{frame:03d}.png")
                bpy.ops.render.render(write_still=True)
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "survey_scene.blend"))
        print("SURVEY_DONE", round(time.time() - started, 1))
        return

    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene.blend"))
    timings = {}
    if run_fluid and not ARGS.skip_fluid_bake:
        t0 = time.time()
        bpy.ops.object.select_all(action="DESELECT")
        domain.select_set(True)
        bpy.context.view_layer.objects.active = domain
        result = bpy.ops.fluid.bake_all()
        if "FINISHED" not in result:
            raise RuntimeError(f"Mantaflow bake failed: {result}")
        timings["bake_seconds"] = time.time() - t0
        print("BAKE_SECONDS", round(timings["bake_seconds"], 1))
        if ARGS.bake_frame_end:
            frame_end = ARGS.bake_frame_end
            scene.frame_end = frame_end
        metadata["liquid_volume"] = liquid_volume_log(scene, domain, frame_end)
        if not ARGS.no_bubbles:
            metadata["bubbles"] = add_bubble_geometry(domain, frame_end, config.water_surface_z_m)
        (OUT / "scenario_metadata.json").write_text(json.dumps(metadata, indent=2) + "\n", encoding="utf-8")
        bpy.ops.wm.save_as_mainfile(filepath=str(OUT / "scene_baked.blend"))
    if ARGS.skip_render:
        return
    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    frames = ARGS.still_frames if ARGS.still_frames else range(1, frame_end + 1)
    t0 = time.time()
    for frame in frames:
        scene.frame_set(frame)
        scene.render.filepath = str(frames_dir / f"frame_{frame:04d}.png")
        bpy.ops.render.render(write_still=True)
    timings["render_seconds"] = time.time() - t0
    (OUT / "timings.json").write_text(json.dumps(timings, indent=2) + "\n", encoding="utf-8")
    if ARGS.still_frames:
        return
    encode(frames_dir, OUT / "video.mp4", frame_end)
    if not ARGS.keep_intermediates:
        for name in ("fluid_cache", "frames", "scene.blend", "scene_baked.blend"):
            path = OUT / name
            if path.is_dir():
                shutil.rmtree(path)
            elif path.exists():
                path.unlink()
    print("VIDEO", OUT / "video.mp4")


main()
