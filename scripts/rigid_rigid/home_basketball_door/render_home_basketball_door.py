"""Build the home_basketball_door scene in Blender, solve it in PyBullet, render it.

The bedroom is built in code on the simulator's own wall planes
(``appearance/room_shell.py``) around the door leaf stored in
``assets/scenes/home_basketball_door/door_leaf.json``. The same leaf file is
handed to the simulator, so the door that swings on screen is the door that was
solved. The ball is rescaled to a real 24.2 cm basketball.

``door_start_angle_deg`` in scenario.json is the leaf's angle from closed.

The ball can only push the leaf towards closed -- it is thrown from inside the
room at the room-facing face -- so the swing is 45 deg down to a hair short of
the jamb, not open.

Run with the repository's render runtime (bpy is installed there):
    <render-python> scripts/rigid_rigid/home_basketball_door/render_home_basketball_door.py --mode keyframes

or through Blender:
    blender -b --python scripts/rigid_rigid/home_basketball_door/render_home_basketball_door.py -- --mode animation

Modes:
    build      write the .blend, the trajectory and the metadata, render nothing
    preview    frame 1, the impact frame and the last frame
    keyframes  the frames in layout.keyframes (default: 9 frames across the clip)
    frames     every frame as PNG
    animation  the 4 s MP4
"""
from __future__ import annotations

# PCVE_UNIFIED_ENTRY_BEGIN
if __name__ == "__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0, str(_Path(__file__).resolve().parents[2]))
        # This scene also renders from a Python that has the bpy module
        # (--render-python). Load bpy first for real runs so prepare_entry keeps
        # the render in this process instead of relaunching Blender; planning
        # calls (--help/--dry-run/--describe) stay import-free.
        if not {"-h", "--help", "--dry-run", "--describe"} & set(_sys.argv[1:]):
            try:
                import bpy  # noqa: F401
            except ImportError:
                pass
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__, "render")
# PCVE_UNIFIED_ENTRY_END

# Resolve the shared scripts directory, then this scene's module folders.
import sys as _clean_sys
from pathlib import Path as _CleanPath
_clean_scene_dir = _CleanPath(__file__).resolve().parent
_scripts_dir = _clean_scene_dir.parents[1]
_PCVE_PROJECT_ROOT = next(p for p in _clean_scene_dir.parents if (p / 'scripts').is_dir())
if str(_scripts_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_scripts_dir))
if str(_clean_scene_dir) not in _clean_sys.path:
    _clean_sys.path.insert(0, str(_clean_scene_dir))
# Shared modules live in scripts/; scene-local modules live in this directory and
# its physics/, appearance/ and tools/ subdirectories.
for _scene_sub in ("", "physics", "appearance", "tools"):
    _scene_sub_dir = _clean_scene_dir / _scene_sub if _scene_sub else _clean_scene_dir
    if _scene_sub_dir.is_dir() and str(_scene_sub_dir) not in _clean_sys.path:
        _clean_sys.path.insert(1, str(_scene_sub_dir))





from pcve_blender_compat import (set_color_property)

import argparse
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterable

import bpy
from mathutils import Quaternion, Vector

HERE = Path(__file__).resolve().parent
ROOT = _PCVE_PROJECT_ROOT
import scene_config  # noqa: E402
import pcve_door_asset as door_asset  # noqa: E402
import room_shell  # noqa: E402

from pcve_assets import asset as _pcve_asset
MODEL_DIRS = (_pcve_asset('') / 'models',)
RESOLVED_NAME = 'resolved_scenario.json'
TRAJECTORY_NAME = 'physics_transforms.json'
GROUND_TRUTH_NAME = 'ground_truth_transforms.json'
METADATA_NAME = 'scenario_metadata.json'
LEAF_NAME = 'door_leaf.json'
# The leaf the simulator swings, measured once and stored with the scene: the
# room is built around it, so nothing is measured at render time.
STORED_LEAF = _pcve_asset('') / 'scenes' / 'home_basketball_door' / LEAF_NAME
# The bedroom pieces and textures are shared with door_basketball_collision,
# which is the same room seen from the other side; this scene adds its own.
ROOM_ASSETS = (_pcve_asset('') / 'polyhaven' / 'door_basketball_collision',
               _pcve_asset('') / 'polyhaven' / 'home_basketball_door')


from pcve_scene_runtime import parse_render_args, run_renderer

def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--mode',
        choices=('build', 'preview', 'keyframes', 'frames', 'animation'),
        default='preview',
    )
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'renders' / 'home_basketball_door')
    parser.add_argument('--models-dir', type=Path, default=None)
    parser.add_argument('--scenario', type=Path, default=None)
    parser.add_argument('--scenario-overrides-json', type=Path, default=None)
    parser.add_argument('--physics-python', type=Path, default=None)
    parser.add_argument('--resolution', nargs=2, type=int, default=[1280, 720])
    parser.add_argument('--fps', type=int, default=None)
    parser.add_argument('--duration-sec', type=float, default=None)
    parser.add_argument('--samples', type=int, default=96)
    parser.add_argument('--device', choices=('auto', 'cpu'), default='auto')
    parser.add_argument('--keyframes', default=None, help='comma-separated frame numbers')
    return parse_render_args(parser, argv)


# ------------------------------------------------------------------- assets


def model_path(name: str, args: argparse.Namespace) -> Path:
    directories = (args.models_dir,) if args.models_dir else MODEL_DIRS
    for directory in directories:
        candidate = Path(directory) / name
        if candidate.is_file():
            return candidate
    raise FileNotFoundError(
        f'{name} not found in {[str(d) for d in directories]}. '
        'Pass --models-dir with the directory that holds the GLBs.'
    )


def import_glb(path: Path) -> list[bpy.types.Object]:
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    # Some GLBs carry turntable/NLA animation. Left in place those keys fight
    # the physics keys written further down.
    for obj in imported:
        obj.animation_data_clear()
        if obj.data is not None and hasattr(obj.data, 'animation_data_clear'):
            obj.data.animation_data_clear()
    return imported


def tame_glb_emission(imported: Iterable[bpy.types.Object], layout: dict[str, Any]) -> int:
    """Turn off the emission glTF bakes into every material it imports.

    glTF's ``emissiveFactor`` imports as Emission Colour 1,1,1 with Emission
    Strength 1.0. This asset's material names are all ``None.00x`` -- there is
    no name to whitelist a window or a lamp on -- so the scene simply sets the
    whole room to ``glb_emission_scale`` (0) and lights it itself.
    """
    scale = float(layout.get('glb_emission_scale', 0.0))
    seen = 0
    for obj in imported:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type != 'BSDF_PRINCIPLED':
                    continue
                strength = node.inputs.get('Emission Strength')
                if strength is not None:
                    strength.default_value = scale
            seen += 1
    return seen


def tame_glb_gloss(imported: Iterable[bpy.types.Object], layout: dict[str, Any]) -> int:
    """Floor the roughness of the room's flat-shaded stylised materials.

    The asset is low-poly with a painted wood floor and blue lacquered closet
    doors. Under the area lights those come back as broad specular sheens
    brighter than the door leaf. There is no useful material name to filter on,
    so every material gets the same floor.
    """
    floor = float(layout.get('glb_roughness_min', 0.55))
    seen = 0
    for obj in imported:
        if obj.type != 'MESH':
            continue
        for slot in obj.material_slots:
            material = slot.material
            if material is None or not material.use_nodes:
                continue
            for node in material.node_tree.nodes:
                if node.type != 'BSDF_PRINCIPLED':
                    continue
                rough = node.inputs.get('Roughness')
                metallic = node.inputs.get('Metallic')
                if rough is not None and not rough.is_linked and rough.default_value < floor:
                    rough.default_value = floor
                if metallic is not None and not metallic.is_linked:
                    metallic.default_value = min(metallic.default_value, 0.05)
            seen += 1
    return seen


# ---------------------------------------------------------------- hallway

DEFAULT_HALLWAY = {
    'length_m': 2.60,
    'inset_m': -0.002,
    'mouth_back_m': 0.070,
    'headroom_m': 0.012,
    'skirt_height_m': 0.11,
    'skirt_proud_m': 0.008,
    'picture_depth_m': 0.80,
    'picture_size_m': [0.40, 0.52],
    'picture_center_z_m': 1.38,
    'floor_color': [0.23, 0.15, 0.10],
    'wall_color': [0.52, 0.50, 0.46],
    'ceiling_color': [0.58, 0.57, 0.54],
    'skirt_color': [0.17, 0.11, 0.08],
    'door_color': [0.24, 0.15, 0.10],
    'frame_color': [0.13, 0.09, 0.07],
    'canvas_color': [0.62, 0.56, 0.44],
    'roughness': 0.76,
    'lamp_power': 11.0,
    'lamp_size': 0.34,
    'lamp_color': [1.0, 0.84, 0.64],
    'lamp_depth_m': 1.35,
}


def flat_material(name: str, colour: Iterable[float], roughness: float) -> bpy.types.Material:
    material = bpy.data.materials.new(name)
    material.use_nodes = True
    bsdf = material.node_tree.nodes['Principled BSDF']
    bsdf.inputs['Base Color'].default_value = (*[float(c) for c in colour], 1.0)
    bsdf.inputs['Roughness'].default_value = float(roughness)
    metallic = bsdf.inputs.get('Metallic')
    if metallic is not None:
        metallic.default_value = 0.0
    return material


def newell_normal(corners: list[Vector]) -> Vector:
    normal = Vector((0.0, 0.0, 0.0))
    for index, point in enumerate(corners):
        following = corners[(index + 1) % len(corners)]
        normal.x += (point.y - following.y) * (point.z + following.z)
        normal.y += (point.z - following.z) * (point.x + following.x)
        normal.z += (point.x - following.x) * (point.y + following.y)
    if normal.length < 1e-9:
        return Vector((0.0, 0.0, 1.0))
    return normal.normalized()


def add_quad(
    name: str,
    corners: list[Vector],
    normal: Vector,
    material: bpy.types.Material,
) -> bpy.types.Object:
    """One flat four-sided face, wound so its normal points where asked."""
    ordered = list(corners)
    if newell_normal(ordered).dot(Vector(normal)) < 0.0:
        ordered.reverse()
    mesh = bpy.data.meshes.new(name)
    mesh.from_pydata([tuple(c) for c in ordered], [], [(0, 1, 2, 3)])
    mesh.validate()
    if mesh.polygons:
        mesh.polygons[0].use_smooth = False
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    obj.data.materials.append(material)
    return obj


def build_hallway_picture(
    path: Path,
    layout: dict[str, Any],
    spec: dict[str, Any],
    layout_spec: dict[str, Any],
    *,
    wall_x: float,
    centre_y: float,
    centre_z: float,
) -> dict[str, Any]:
    """Hang the asset's framed picture in the corridor instead of a flat canvas.

    Without the asset the fallback is two quads -- a frame plate and a bare
    canvas -- which leave only a blank rectangle as a scale reference. The café pictures
    GLB brings a real moulded frame, a mat and a print, and it arrives already
    in metres with the wall plane on its +X face, which is exactly how the
    corridor's left wall is oriented: no rotation, only a placement.

    Its origin sits inside the frame, so the drop is computed from the asset's
    own bounding box: back plate flush to the wall, then centred on the spec's
    picture position.
    """
    wanted = str(spec.get('picture_object') or 'wall_picture_2')
    previous = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in previous]
    for obj in imported:
        obj.animation_data_clear()
    tame_glb_emission(imported, layout_spec)
    tame_glb_gloss(imported, layout_spec)

    meshes = [o for o in imported if o.type == 'MESH' and wanted in o.name]
    if not meshes:
        meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{path.name} has no mesh; the picture cannot be hung')
    body = meshes[0]
    for obj in imported:
        if obj is not body:
            obj.hide_render = True

    # The picture hangs off an empty that carries the GLB's own unit scaling.
    # Keep the world matrix, drop the parent, so the drop below is in metres.
    world = body.matrix_world.copy()
    body.parent = None
    body.matrix_world = world
    bpy.context.view_layer.update()

    points = [body.matrix_world @ v.co for v in body.data.vertices]
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    middle_y = (lo.y + hi.y) / 2.0
    middle_z = (lo.z + hi.z) / 2.0

    scale = float(spec.get('picture_scale') or 1.0)
    if abs(scale - 1.0) > 1e-9:
        body.scale = tuple(component * scale for component in body.scale)
        bpy.context.view_layer.update()
        points = [body.matrix_world @ v.co for v in body.data.vertices]
        lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
        hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
        middle_y = (lo.y + hi.y) / 2.0
        middle_z = (lo.z + hi.z) / 2.0

    body.location = Vector(body.location) + Vector((
        wall_x + float(spec.get('picture_proud_m') or 0.0) - lo.x,
        centre_y - middle_y,
        centre_z - middle_z,
    ))
    for obj in imported:
        obj.animation_data_clear()
    bpy.context.view_layer.update()

    points = [body.matrix_world @ v.co for v in body.data.vertices]
    lo = Vector((min(p.x for p in points), min(p.y for p in points), min(p.z for p in points)))
    hi = Vector((max(p.x for p in points), max(p.y for p in points), max(p.z for p in points)))
    info = {
        'object': body.name,
        'asset': path.name,
        'size_m': [round(hi.y - lo.y, 4), round(hi.z - lo.z, 4)],
        'depth_m': round(hi.x - lo.x, 4),
        'centre': [round((lo.y + hi.y) / 2.0, 4), round((lo.z + hi.z) / 2.0, 4)],
    }
    print(
        f'[scene] hallway picture {body.name!r} {info["size_m"][0]:.3f} x {info["size_m"][1]:.3f} m '
        f'at y={info["centre"][0]:.3f} z={info["centre"][1]:.3f}'
    )
    return info


def build_hallway(
    layout: dict[str, Any],
    leaf_info: dict[str, Any],
    floor_z: float,
    picture_path: Path | None = None,
    wall: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Stand a hallway behind the doorway so the opening leads somewhere.

    The bedroom is one closed shell: with nothing behind the door, the moment
    the leaf swings ajar the doorway would open onto the outside. Five
    inward-facing planes fix that.

    Geometry, and why it is this geometry:

    * The hallway's cross-section **is** the aperture's, 2 mm wider so its side
      walls tuck behind the frame's liners instead of standing in front of them,
      and its mouth is recessed 70 mm *behind* the room's wall face. Recessing it
      is what makes the doorway's edge a jamb: brought flush, the corridor's side
      wall becomes the doorway's edge, the camera meets it at 88 deg and it
      renders as a striped, badly sampled band rather than a surface. Set back,
      the asset's casing covers it and the eye gets a 70 mm reveal instead -- a
      step, a shadow line, a readable thickness.
    * Because the corridor is only 0.95 m wide, a camera 44 deg off the doorway
      axis never sees the far end -- it sees *one side wall*, 0.6 m of it,
      stretching away. So the depth has to be carried by that one wall: a
      skirting board, a framed picture at 0.8 m whose foreshortened rectangle is
      the only scale reference in shot, a dark floor against light walls, and
      light that falls off with distance. A uniformly lit wall reads as a flat
      cream card no matter how deep it really is.

    The far door panel is kept because the PCVE keyframe cameras do look down
    the axis; it costs one quad.
    """
    spec = {**DEFAULT_HALLWAY, **dict(layout.get('hallway') or {})}
    hinge = leaf_info['hinge_world']
    hx, hy = float(hinge[0]), float(hinge[1])
    width = float(leaf_info['width_m'])
    height = float(leaf_info['height_m'])

    existing_objects = set(bpy.data.objects)
    bounds = layout.get('room_bounds') or {}
    room_face = float(bounds['y'][0]) if bounds.get('y') else hy + 0.154
    y_mouth = room_face - float(spec['mouth_back_m'])
    y_back = y_mouth - float(spec['length_m'])

    inset = float(spec['inset_m'])
    x_lo = hx + inset
    x_hi = hx + width - inset
    z_lo = float(floor_z)
    z_hi = float(floor_z) + height + float(spec['headroom_m'])
    roughness = float(spec['roughness'])

    floor_mat = flat_material('hallway_floor', spec['floor_color'], roughness * 0.72)
    wall_mat = flat_material('hallway_wall', spec['wall_color'], roughness)
    ceiling_mat = flat_material('hallway_ceiling', spec['ceiling_color'], min(0.95, roughness + 0.15))
    skirt_mat = flat_material('hallway_skirting', spec['skirt_color'], roughness * 0.8)
    door_mat = flat_material('hallway_door', spec['door_color'], roughness * 0.7)

    def face(name: str, points: list[Vector], normal: Vector, material: bpy.types.Material) -> None:
        add_quad(name, points, normal, material)

    z_up, z_down = Vector((0.0, 0.0, 1.0)), Vector((0.0, 0.0, -1.0))
    x_right, x_left = Vector((1.0, 0.0, 0.0)), Vector((-1.0, 0.0, 0.0))
    y_back_n = Vector((0.0, 1.0, 0.0))

    face('hallway_floor', [Vector((x_lo, y_mouth, z_lo)), Vector((x_hi, y_mouth, z_lo)),
                           Vector((x_hi, y_back, z_lo)), Vector((x_lo, y_back, z_lo))], z_up, floor_mat)
    face('hallway_ceiling', [Vector((x_lo, y_mouth, z_hi)), Vector((x_hi, y_mouth, z_hi)),
                             Vector((x_hi, y_back, z_hi)), Vector((x_lo, y_back, z_hi))], z_down, ceiling_mat)
    face('hallway_wall_left', [Vector((x_lo, y_mouth, z_lo)), Vector((x_lo, y_back, z_lo)),
                               Vector((x_lo, y_back, z_hi)), Vector((x_lo, y_mouth, z_hi))], x_right, wall_mat)
    face('hallway_wall_right', [Vector((x_hi, y_mouth, z_lo)), Vector((x_hi, y_back, z_lo)),
                                Vector((x_hi, y_back, z_hi)), Vector((x_hi, y_mouth, z_hi))], x_left, wall_mat)
    face('hallway_wall_back', [Vector((x_lo, y_back, z_lo)), Vector((x_hi, y_back, z_lo)),
                               Vector((x_hi, y_back, z_hi)), Vector((x_lo, y_back, z_hi))], y_back_n, wall_mat)

    # The mouth collar: the hallway's own jamb, 70 mm deep, carrying the opening
    # from the aperture back to where the hallway's walls start. Without it the
    # doorway's edge is whatever the carve left in the room's wall, and rays can
    # slip through the 2 mm the hallway is wider by into the void between the two.
    # Its inboard edge is pulled 2 mm behind the measured wall plane, so it can
    # never poke out through a wall face that sits 2 mm off its bounding box.
    y_near = room_face - 0.002
    for name, near_x, far_x, normal in (
        ('left', hx, x_lo, Vector((1.0, 0.0, 0.0))),
        ('right', hx + width, x_hi, Vector((-1.0, 0.0, 0.0))),
    ):
        face(f'hallway_jamb_{name}',
             [Vector((near_x, y_near, z_lo)), Vector((far_x, y_mouth, z_lo)),
              Vector((far_x, y_mouth, z_hi)), Vector((near_x, y_near, z_hi))],
             normal, wall_mat)

    # Skirting: the strongest depth cue available on a wall seen this obliquely,
    # and the only thing that tells the eye where the wall meets the floor once
    # the far half has fallen into shadow.
    skirt_h = float(spec['skirt_height_m'])
    proud = float(spec['skirt_proud_m'])
    skirt_top = min(z_lo + skirt_h, z_hi - 0.02)
    for name, wall_x, inward in (('left', x_lo, 1.0), ('right', x_hi, -1.0)):
        offset = wall_x + inward * proud
        face(f'hallway_skirt_{name}',
             [Vector((offset, y_mouth, z_lo)), Vector((offset, y_back, z_lo)),
              Vector((offset, y_back, skirt_top)), Vector((offset, y_mouth, skirt_top))],
             Vector((inward, 0.0, 0.0)), skirt_mat)
        face(f'hallway_skirt_{name}_top',
             [Vector((wall_x, y_mouth, skirt_top)), Vector((offset, y_mouth, skirt_top)),
              Vector((offset, y_back, skirt_top)), Vector((wall_x, y_back, skirt_top))], z_up, skirt_mat)
    face('hallway_skirt_back',
         [Vector((x_lo, y_back + proud, z_lo)), Vector((x_hi, y_back + proud, z_lo)),
          Vector((x_hi, y_back + proud, skirt_top)), Vector((x_lo, y_back + proud, skirt_top))],
         y_back_n, skirt_mat)

    # A framed picture on the left wall. Flat colour and a skirting only tell you
    # the wall is long; a rectangle at a known size, foreshortened by the view,
    # tells you *how far* it recedes -- the only object in the shot whose width
    # is a readable scale reference. When the scene has a picture asset the
    # modelling replaces the two quads; the quads stay as the fallback.
    picture_w, picture_h = (float(v) for v in spec['picture_size_m'])
    picture_y = y_mouth - float(spec['picture_depth_m'])
    picture_z = z_lo + float(spec['picture_center_z_m'])
    picture_info: dict[str, Any] = {}
    if picture_path is not None and bool(spec.get('picture_enabled', True)):
        picture_info = build_hallway_picture(
            picture_path,
            layout,
            spec,
            layout,
            wall_x=x_lo,
            centre_y=picture_y,
            centre_z=picture_z,
        )
    else:
        canvas_mat = flat_material('hallway_canvas', spec['canvas_color'], 0.85)
        frame_mat = flat_material('hallway_frame', spec['frame_color'], roughness * 0.6)
        for name, lift, shrink, material in (
            ('frame', 0.030, 0.000, frame_mat),
            ('canvas', 0.037, 0.030, canvas_mat),
        ):
            half_w = picture_w / 2.0 - shrink
            half_h = picture_h / 2.0 - shrink
            face(f'hallway_picture_{name}',
                 [Vector((x_lo + lift, picture_y - half_w, picture_z - half_h)),
                  Vector((x_lo + lift, picture_y + half_w, picture_z - half_h)),
                  Vector((x_lo + lift, picture_y + half_w, picture_z + half_h)),
                  Vector((x_lo + lift, picture_y - half_w, picture_z + half_h))],
                 x_right, material)

    # The far door, for the on-axis keyframe cameras.
    door_w = min(0.82, (x_hi - x_lo) - 0.18)
    door_h = min(1.98, (z_hi - z_lo) - 0.26)
    centre_x = (hx + hx + width) / 2.0
    face('hallway_door_panel',
         [Vector((centre_x - door_w / 2.0, y_back + 0.012, z_lo + 0.01)),
          Vector((centre_x + door_w / 2.0, y_back + 0.012, z_lo + 0.01)),
          Vector((centre_x + door_w / 2.0, y_back + 0.012, z_lo + 0.01 + door_h)),
          Vector((centre_x - door_w / 2.0, y_back + 0.012, z_lo + 0.01 + door_h))],
         y_back_n, door_mat)

    # A dim lamp deep in the hallway. The hallway is a closed box, so with no
    # source at all it renders as a black hole, but a bright source near the
    # mouth flattens it back into a
    # card. Low power, 1.7 m in, gives the falloff that reads as distance.
    lamp_power = float(spec['lamp_power'])
    if lamp_power > 0.0:
        lamp = Vector((centre_x, y_mouth - float(spec['lamp_depth_m']), z_hi - 0.06))
        add_area_light(
            'hallway_lamp',
            lamp,
            Vector((centre_x, lamp.y, z_lo)),
            energy=lamp_power,
            size=float(spec['lamp_size']),
            color=tuple(float(c) for c in spec['lamp_color']),
        )

    # The doorway is in a splayed wall, so the two sides have different mouth
    # depths. A mouth built from room_bounds.y projects through the plaster.
    # Move only the entrance vertices; the picture and far end stay in place.
    if wall is not None:
        normal = Vector(wall['normal'])
        for obj in set(bpy.data.objects) - existing_objects:
            if obj.type != 'MESH' or not obj.name.startswith('hallway_'):
                continue
            inverse = obj.matrix_world.inverted()
            for vertex in obj.data.vertices:
                point = obj.matrix_world @ vertex.co
                if abs(point.y - y_mouth) < 1e-5 or abs(point.y - y_near) < 1e-5:
                    wall_y = (wall['offset'] - normal.x * point.x) / normal.y
                    point.y += wall_y - room_face
                    vertex.co = inverse @ point
            obj.data.update()

    info = {
        'entrance_follows_wall': wall is not None,
        'x': [round(x_lo, 4), round(x_hi, 4)],
        'y': [round(y_back, 4), round(y_mouth, 4)],
        'z': [round(z_lo, 4), round(z_hi, 4)],
        'length_m': round(float(spec['length_m']), 3),
        'picture': picture_info,
    }
    print(
        f'[scene] hallway x[{x_lo:+.3f},{x_hi:+.3f}] y[{y_back:+.3f},{y_mouth:+.3f}] '
        f'z[{z_lo:+.3f},{z_hi:+.3f}] - {spec["length_m"]:.2f} m long, lamp at '
        f'{lamp_power:.0f} W'
    )
    return info


def import_ball(path: Path, layout: dict[str, Any]) -> bpy.types.Object:
    """Bake the basketball into one mesh, sized to a real ball, origin at its centre."""
    imported = import_glb(path)
    meshes = [o for o in imported if o.type == 'MESH']
    if not meshes:
        raise RuntimeError(f'{path.name} has no mesh')
    bpy.ops.object.select_all(action='DESELECT')
    for obj in meshes:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = meshes[0]
    if len(meshes) > 1:
        bpy.ops.object.join()
    ball = bpy.context.view_layer.objects.active

    # glTF exports wrap the mesh in an empty that carries the Y-up -> Z-up
    # correction. Left parented, the pose written further down goes through
    # that rotation and the ball lands outside the room (measured: z = -2.23
    # instead of +1.42). Keep the world position, drop the parent.
    world = ball.matrix_world.copy()
    ball.parent = None
    ball.matrix_world = world
    for obj in imported:
        if obj is not ball and obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)

    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    extent = max(ball.dimensions)
    factor = float(layout['ball_scale_to_diameter_m']) / extent
    ball.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME')
    ball.location = (0.0, 0.0, 0.0)
    ball.name = 'basketball'
    ball.data.name = 'basketball'
    bpy.context.view_layer.update()
    print(f'[scene] ball {extent:.4f} model units -> {max(ball.dimensions):.4f} m (scale {factor:.5f})')
    return ball


# ---------------------------------------------------------------- physics


def physics_python(explicit: Path | None) -> str:
    candidates = [explicit, os.environ.get('PCVE_PHYSICS_PYTHON') or None,
                  ROOT / '.runtime' / 'sim' / 'python.exe', ROOT / '.runtime' / 'sim' / 'bin' / 'python']
    for candidate in candidates:
        if candidate is not None and Path(candidate).exists():
            return str(Path(candidate))
    found = shutil.which('python3') or shutil.which('python')
    if not found:
        raise RuntimeError('No Python with pybullet found; pass --physics-python.')
    return found


def run_simulation(
    args: argparse.Namespace,
    *,
    out_dir: Path,
    scenario_path: Path,
    leaf_path: Path,
    fps: int,
    duration: float,
) -> dict[str, Any]:
    trajectory = out_dir / TRAJECTORY_NAME
    command = [
        physics_python(args.physics_python),
        str(HERE / 'simulate_home_basketball_door.py'),
        '--out', str(trajectory),
        '--scenario', str(scenario_path),
        '--door-leaf-json', str(leaf_path),
        '--fps', str(int(fps)),
        '--duration-sec', str(float(duration)),
    ]
    subprocess.run(command, check=True)
    return scene_config.read_json(trajectory)


def apply_physics_animation(
    leaf: bpy.types.Object,
    ball: bpy.types.Object,
    physics: dict[str, Any],
    origin: Vector,
) -> None:
    """Key the door as a hinge angle and the ball as a rigid pose.

    The leaf's origin is its hinge line and its mesh lies along +X, so the
    simulated opening angle is a single rotation about the object's Z. The
    simulation's axes are the room's axes: +X along the closed leaf, +Y into
    the room. Swinging the leaf from +X towards +Y is a positive Z rotation,
    so the keyed angle is the simulated angle with its sign kept.
    """
    leaf.rotation_mode = 'XYZ'
    if ball is not None:
        ball.rotation_mode = 'QUATERNION'
    for record in physics['frames']:
        frame = int(record['frame_index'])
        leaf.rotation_euler = (0.0, 0.0, float(record['door_angle_rad']) +
                               float(physics['geometry']['leaf'].get('closed_yaw_deg', 0)) * math.pi / 180)
        leaf.keyframe_insert('rotation_euler', frame=frame)
        if ball is None:
            continue
        x, y, z, w = record['ball_quaternion_xyzw']
        ball.location = Vector(record['ball_location']) + origin
        ball.rotation_quaternion = Quaternion((w, x, y, z))
        ball.keyframe_insert('location', frame=frame)
        ball.keyframe_insert('rotation_quaternion', frame=frame)
    for obj in (leaf, ball):
        if obj is None:
            continue
        action = obj.animation_data.action
        for curve in action.fcurves:
            for point in curve.keyframe_points:
                point.interpolation = 'LINEAR'


# ------------------------------------------------------------------- scene


def add_area_light(
    name: str,
    location: Vector,
    target: Vector,
    *,
    energy: float,
    size: float,
    color: tuple[float, float, float],
) -> None:
    bpy.ops.object.light_add(type='AREA', location=location)
    light = bpy.context.object
    light.name = name
    light.data.shape = 'DISK'
    light.data.energy = energy
    light.data.size = size
    light.data.color = color
    light.rotation_euler = (target - location).to_track_quat('-Z', 'Y').to_euler()


def build_camera(layout: dict[str, Any]) -> bpy.types.Object:
    location = Vector([float(v) for v in layout['camera_location']])
    target = Vector([float(v) for v in layout['camera_target']])
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = 'home_basketball_door_camera'
    camera.rotation_euler = (target - location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens = float(layout['camera_lens_mm'])
    camera.data.clip_start = 0.05
    camera.data.clip_end = 100.0
    bpy.context.scene.camera = camera
    return camera


DEFAULT_GRADE = {
    'view_transform': 'AgX',
    'look': 'AgX - Punchy',
    'exposure': -0.2,
}


def setup_render(
    scene: bpy.types.Scene,
    args: argparse.Namespace,
    layout: dict[str, Any],
    *,
    fps: int,
    frame_end: int,
) -> None:
    scene.render.engine = 'CYCLES'
    scene.cycles.samples = int(args.samples)
    scene.cycles.use_denoising = True
    scene.cycles.max_bounces = 8
    scene.cycles.transmission_bounces = 6
    scene.cycles.device = 'CPU' if args.device == 'cpu' else 'GPU'
    if args.device != 'cpu':
        prefs = bpy.context.preferences.addons['cycles'].preferences
        try:
            prefs.compute_device_type = 'CUDA'; prefs.get_devices()
            available = [dev for dev in prefs.devices if dev.type == 'CUDA']
            for dev in prefs.devices:
                dev.use = (dev.type == 'CUDA')
            if available:
                scene.cycles.device = 'GPU'
                scene.cycles.denoiser = 'OPTIX' if any(dev.type == 'OPTIX' for dev in prefs.devices) else 'OPENIMAGEDENOISE'
                print('[render] CUDA: ' + ', '.join(dev.name for dev in available), flush=True)
        except Exception as exc:
            scene.cycles.device = 'CPU'
            print('[render] CPU fallback: ' + str(exc), flush=True)
    scene.render.resolution_x, scene.render.resolution_y = (int(v) for v in args.resolution)
    scene.render.resolution_percentage = 100
    scene.render.fps = int(fps)
    scene.frame_start = 1
    scene.frame_end = int(frame_end)
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False
    # A real camera's shutter: the thrown ball and the swinging leaf smear a
    # little along their motion instead of strobing. The throw is fast, so the
    # shutter is kept short (layout.motion_blur_shutter, in frames).
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = float(layout.get('motion_blur_shutter', 0.25))

    grade = {**DEFAULT_GRADE, **dict(layout.get('grade') or {})}
    set_color_property(scene.view_settings, 'view_transform', str(grade['view_transform']))
    set_color_property(scene.view_settings, 'look', str(grade['look']))
    scene.view_settings.exposure = float(grade['exposure'])


def enable_video_output(scene: bpy.types.Scene, path: Path) -> None:
    scene.render.image_settings.file_format = 'FFMPEG'
    scene.render.ffmpeg.format = 'MPEG4'
    scene.render.ffmpeg.codec = 'H264'
    scene.render.ffmpeg.constant_rate_factor = 'MEDIUM'
    scene.render.filepath = str(path)


def export_ground_truth(
    out_dir: Path,
    *,
    leaf: bpy.types.Object,
    ball: bpy.types.Object,
    camera: bpy.types.Object,
    physics: dict[str, Any],
    scenario: dict[str, Any],
    origin: Vector,
    fps: int,
) -> None:
    scene = bpy.context.scene
    records: dict[str, Any] = {
        'schema_version': 1,
        'fps': int(fps),
        'frame_start': 1,
        'frame_end': int(scene.frame_end),
        'resolution': [int(scene.render.resolution_x), int(scene.render.resolution_y)],
        'world_origin': list(origin),
        'coordinate_system': 'Blender world space; quaternions XYZW',
        'physics': {k: v for k, v in physics.items() if k != 'frames'},
        'objects': {
            'door': {
                'object_name': leaf.name,
                'hinge_world': list(origin),
                'width_m': float(physics['geometry']['door_width_m']),
                'height_m': float(physics['geometry']['door_height_m']),
                'note': 'single rigid leaf on a vertical revolute joint; rotation about its own Z',
            },
            'ball': {
                'object_name': ball.name if ball is not None else None,
                'radius_m': float(physics['geometry']['ball_radius_m']),
                'note': 'single rigid sphere',
                **({} if ball is not None else {'present': False}),
            },
        },
        'camera': {
            'object_name': camera.name,
            'lens_mm': float(camera.data.lens),
            'sensor_width_mm': float(camera.data.sensor_width),
            'matrix_world': [[float(v) for v in row] for row in camera.matrix_world],
            'world_to_camera_matrix': [
                [float(v) for v in row] for row in camera.matrix_world.inverted()
            ],
        },
        'scenario': scenario,
        'frames': [],
    }
    for record in physics['frames']:
        scene.frame_set(int(record['frame_index']))
        records['frames'].append(
            {
                'frame_index': int(record['frame_index']),
                'time_sec': float(record['time_sec']),
                'door_angle_deg': math.degrees(float(record['door_angle_rad'])),
                'door_angular_velocity': float(record['door_angular_velocity']),
                'door_matrix_world': [[float(v) for v in row] for row in leaf.matrix_world],
                # A deleted ball has no pose at all (its fields are left out, not set to null).
                **({} if ball is None else {
                'ball_matrix_world': [[float(v) for v in row] for row in ball.matrix_world],
                'ball_location': [float(v) for v in ball.location],
                'ball_quaternion_xyzw': [
                    float(ball.rotation_quaternion.x),
                    float(ball.rotation_quaternion.y),
                    float(ball.rotation_quaternion.z),
                    float(ball.rotation_quaternion.w),
                ],
                'ball_linear_velocity': [float(v) for v in record['ball_linear_velocity']],
                'ball_angular_velocity': [float(v) for v in record['ball_angular_velocity']],
                }),
                'ball_contacting_door': bool(record['ball_contacting_door']),
            }
        )
    scene_config.write_json(out_dir / GROUND_TRUTH_NAME, records)


def render_still(scene: bpy.types.Scene, frame: int, path: Path) -> None:
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.frame_set(int(frame))
    scene.render.filepath = str(path)
    bpy.ops.render.render(write_still=True)
    print(f'[render] frame {frame} -> {path}')


def keyframe_list(args: argparse.Namespace, layout: dict[str, Any], frame_end: int) -> list[int]:
    if args.keyframes:
        frames = [int(part) for part in args.keyframes.split(',') if part.strip()]
    else:
        frames = [int(f) for f in layout.get('keyframes') or []]
    if not frames:
        frames = [round(1 + (frame_end - 1) * i / 8) for i in range(9)]
    return sorted({min(max(1, f), frame_end) for f in frames})


# -------------------------------------------------------------------- main


def main() -> None:
    args = parse_args()
    scenario = scene_config.load_scenario(args.scenario, args.scenario_overrides_json)
    physics_cfg = scenario['physics']
    layout = scenario['layout']
    assets = scenario['assets']

    fps = int(args.fps if args.fps is not None else physics_cfg['fps'])
    duration = float(
        args.duration_sec if args.duration_sec is not None else physics_cfg['duration_sec']
    )
    out_dir = Path(args.out_dir).expanduser().resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    ball_path = model_path(assets['ball'], args)
    door_path = model_path(assets['door_leaf'], args)
    door_spec = dict(layout.get('door_asset') or {})
    print(f'[scene] ball={ball_path}')
    print(f'[scene] door leaf={door_path}')
    picture_spec = dict(layout.get('hallway') or {})
    picture_path = None
    if picture_spec.get('picture_glb') and bool(picture_spec.get('picture_enabled', True)):
        picture_path = model_path(picture_spec['picture_glb'], args)
        print(f'[scene] hallway picture={picture_path}')

    scenario_path = out_dir / RESOLVED_NAME
    scene_config.write_json(scenario_path, scenario)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene

    # The room is built on the simulator's planes around the stored leaf; the
    # door asset's leaf and fitted frame are then hung in its opening, and the
    # same leaf file is handed to the simulator below.
    leaf_info = scene_config.read_json(STORED_LEAF)
    origin = Vector([float(v) for v in leaf_info['hinge_world']])
    floor_z = float(origin.z)
    wall, aperture = room_shell.door_wall(leaf_info)
    room_info = room_shell.build_room(layout, leaf_info, wall, floor_z, ROOM_ASSETS)
    leaf, _door_frame, door_info = door_asset.build_door_from_asset(
        door_path,
        door_spec,
        leaf_width_m=float(leaf_info['width_m']),
        leaf_height_m=float(leaf_info['height_m']),
        hinge_world=origin,
        floor_z=floor_z,
        aperture=aperture,
        wall=wall,
    )
    leaf.location = origin
    door_info['collision_fit'] = door_asset.fit_leaf_to_collision(
        leaf, leaf_info['width_m'], leaf_info['height_m'],
        leaf_info['thickness_m'], leaf_info['bottom_clearance_m'])
    hallway_info = build_hallway(layout, layout['hallway']['opening'], floor_z, picture_path, wall=wall)
    bpy.context.view_layer.update()

    ball = import_ball(ball_path, layout) if scene_config.present(physics_cfg, 'ball') else None

    # The simulator reads the leaf next to its output, so the case directory
    # keeps its own copy of the stored leaf.
    leaf_path = out_dir / LEAF_NAME
    scene_config.write_json(leaf_path, leaf_info)

    physics = run_simulation(
        args,
        out_dir=out_dir,
        scenario_path=scenario_path,
        leaf_path=leaf_path,
        fps=fps,
        duration=duration,
    )
    # Furniture stands where the simulator has nothing: refuse to render a take
    # whose ball would pass through any of it.
    centres = [origin + Vector(record['ball_location']) for record in physics['frames']
               if record['ball_location'] is not None]
    room_info['clearance'] = room_shell.check_clearance(
        room_info['furniture'],
        centres,
        float(physics['geometry']['ball_radius_m']),
    ) if centres else {}
    frame_end = int(physics['frame_end'])
    setup_render(scene, args, layout, fps=fps, frame_end=frame_end)
    apply_physics_animation(leaf, ball, physics, origin)

    camera = build_camera(layout)

    scene.frame_set(1)
    enable_video_output(scene, out_dir / 'basketball_door.mp4')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / 'basketball_door.blend'))

    export_ground_truth(
        out_dir,
        leaf=leaf,
        ball=ball,
        camera=camera,
        physics=physics,
        scenario=scenario,
        origin=origin,
        fps=fps,
    )
    scene_config.write_json(
        out_dir / METADATA_NAME,
        {
            'scene': scenario.get('scene', 'home_basketball_door'),
            'fps': fps,
            'duration_sec': duration,
            'total_frames': frame_end,
            'resolution': [int(v) for v in args.resolution],
            'samples': int(args.samples),
            'assets': {
                'ball': str(ball_path),
                'door_leaf': str(door_path),
                'hallway_picture': str(picture_path) if picture_path is not None else None,
                'room': [str(folder) for folder in ROOM_ASSETS],
            },
            'room': room_info,
            'door': {
                'width_m': leaf_info['width_m'],
                'height_m': leaf_info['height_m'],
                'thickness_m': leaf_info['thickness_m'],
                'hinge_world': [float(v) for v in origin],
                'asset_open_angle_deg': leaf_info['asset_open_angle_deg'],
                'joint': 'vertical revolute, Coulomb hinge friction as a scripted resisting torque',
                'visual_from_asset': True,
                'door_asset': door_info,
            },
            'hallway': hallway_info,
            'ball': {
                'radius_m': float(physics['geometry']['ball_radius_m']),
                'diameter_m': 2.0 * float(physics['geometry']['ball_radius_m']),
            },
            'quality': physics['quality'],
            'scenario': scenario,
        },
    )

    if args.mode == 'build':
        return

    if args.mode == 'preview':
        impact = physics['quality']['impact_frame'] or 1
        for frame in dict.fromkeys([args.preview_frame] if args.preview_frame is not None else [1, int(impact), frame_end]):
            render_still(scene, frame, out_dir / f'preview_frame_{frame:04d}.png')
    elif args.mode == 'keyframes':
        target_dir = out_dir / 'keyframes'
        target_dir.mkdir(parents=True, exist_ok=True)
        for frame in keyframe_list(args, layout, frame_end):
            render_still(scene, frame, target_dir / f'frame_{frame:04d}.png')
    elif args.mode == 'frames':
        target_dir = out_dir / 'frames'
        target_dir.mkdir(parents=True, exist_ok=True)
        scene.render.image_settings.file_format = 'PNG'
        scene.render.image_settings.color_mode = 'RGB'
        scene.render.filepath = str(target_dir / 'frame_')
        bpy.ops.render.render(animation=True)
    else:
        enable_video_output(scene, out_dir / 'basketball_door.mp4')
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    run_renderer(main, 'home_basketball_door')
