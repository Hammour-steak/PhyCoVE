"""Build the pot_lid_drop scene in Blender, solve it in PyBullet, render it.

The renderer owns the geometry: it imports the pot, cuts the lid off it,
measures it, and hands its convex hull to the simulator. That is the only place
the two halves of the scene have to agree, and it is why the lid that tumbles
on screen is exactly the body that was solved. The kitchen around it is built
to measure by appearance/coastal_kitchen.py (the floor's top face is the
simulator's floor plane) and dressed by appearance/kitchen_props.py.

Run from the repository root with a Python that has bpy:
    <render-python> scripts/rigid_rigid/pot_lid_drop/render_pot_lid_drop.py --mode keyframes

or through Blender:
    blender -b --python scripts/rigid_rigid/pot_lid_drop/render_pot_lid_drop.py -- --mode animation

Modes:
    build      write the .blend, the trajectory and the metadata, render nothing
    preview    frame 1, the first-contact frame and the last frame
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


from pcve_blender_compat import set_color_property

import argparse
import math
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import bpy
import numpy as np
from mathutils import Quaternion, Vector

HERE = Path(__file__).resolve().parent
ROOT = _PCVE_PROJECT_ROOT
import scene_config  # noqa: E402
import coastal_kitchen  # noqa: E402
import cookware  # noqa: E402
import kitchen_props  # noqa: E402

from pcve_assets import asset as _pcve_asset
MODEL_DIRS = (_pcve_asset('') / 'models',)
RESOLVED_NAME = 'resolved_scenario.json'
TRAJECTORY_NAME = 'physics_transforms.json'
GROUND_TRUTH_NAME = 'ground_truth_transforms.json'
METADATA_NAME = 'scenario_metadata.json'
HULL_NAME = 'lid_hull.json'


from pcve_scene_runtime import parse_render_args, run_renderer

def parse_args() -> argparse.Namespace:
    argv = sys.argv[sys.argv.index('--') + 1:] if '--' in sys.argv else sys.argv[1:]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        '--mode',
        choices=('build', 'preview', 'keyframes', 'frames', 'animation'),
        default='preview',
    )
    parser.add_argument('--out-dir', type=Path, default=ROOT / 'renders' / 'pot_lid_drop')
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


def bake_part(imported: list[bpy.types.Object], node_name: str, name: str) -> bpy.types.Object:
    """Flatten the meshes under one GLB node into a single world-space object."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    baked: list[bpy.types.Object] = []
    for obj in imported:
        if obj.type != 'MESH':
            continue
        if (obj.parent.name if obj.parent else obj.name) != node_name:
            continue
        evaluated = obj.evaluated_get(depsgraph)
        mesh = bpy.data.meshes.new_from_object(
            evaluated, preserve_all_data_layers=True, depsgraph=depsgraph
        )
        mesh.transform(obj.matrix_world)
        part = bpy.data.objects.new(f'{name}_part', mesh)
        bpy.context.collection.objects.link(part)
        baked.append(part)
    if not baked:
        raise RuntimeError(f'GLB has no mesh under node {node_name!r}')

    bpy.ops.object.select_all(action='DESELECT')
    for part in baked:
        part.select_set(True)
    bpy.context.view_layer.objects.active = baked[0]
    if len(baked) > 1:
        bpy.ops.object.join()
    obj = bpy.context.view_layer.objects.active
    obj.name = name
    bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)

    # Origin at the volume centroid: the lid's own frame should sit where its
    # mass is, or a hull handed to PyBullet would spin about the wrong point.
    try:
        bpy.ops.object.origin_set(type='ORIGIN_CENTER_OF_VOLUME')
    except RuntimeError:
        bpy.ops.object.origin_set(type='ORIGIN_GEOMETRY', center='MEDIAN')
    obj.location = (0.0, 0.0, 0.0)
    bpy.context.view_layer.update()
    return obj


def local_bounds(obj: bpy.types.Object) -> tuple[Vector, Vector]:
    corners = [Vector(corner) for corner in obj.bound_box]
    lo = Vector([min(c[i] for c in corners) for i in range(3)])
    hi = Vector([max(c[i] for c in corners) for i in range(3)])
    return lo, hi


def scale_part(obj: bpy.types.Object, factor: float) -> None:
    bpy.ops.object.select_all(action='DESELECT')
    obj.select_set(True)
    bpy.context.view_layer.objects.active = obj
    obj.scale = (factor, factor, factor)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    bpy.context.view_layer.update()


def horizontal_diameter(obj: bpy.types.Object) -> float:
    """The lid's disc diameter, ignoring whatever sticks out sideways.

    The GLB lid has a grip tab on one side, so the raw x extent is not the
    diameter; the larger of the two horizontal extents is.
    """
    lo, hi = local_bounds(obj)
    return max(hi.x - lo.x, hi.y - lo.y)


def import_pot(path: Path, layout: dict[str, Any]) -> tuple[bpy.types.Object, bpy.types.Object]:
    """Split the pot GLB into its static body and the lid that will move.

    The asset is one pot with its lid on: node ``pCylinder3`` is the body,
    ``pCylinder2`` is the lid. They are baked into two independent objects and
    the imported hierarchy is removed, so the lid can be keyframed on its own.
    """
    imported = import_glb(path)
    nodes = sorted({(o.parent.name if o.parent else o.name) for o in imported if o.type == 'MESH'})
    body = bake_part(imported, str(layout['pot_node_name']), 'pot_body')
    lid = bake_part(imported, str(layout['lid_node_name']), 'pot_lid')
    # The source GLB has a tilted lid. Fit the outer rim, excluding the dome
    # and knob, so local +Z really is the lid normal used by the simulator.
    points = np.array([tuple(v.co) for v in lid.data.vertices])
    radii = np.linalg.norm(points[:, :2], axis=1)
    rim = points[radii > 0.8 * radii.max()]
    centered = rim - rim.mean(axis=0)
    _, axes = np.linalg.eigh(centered.T @ centered)
    normal = Vector(axes[:, 0])
    if normal.z < 0:
        normal.negate()
    correction = normal.rotation_difference(Vector((0, 0, 1)))
    lid.data.transform(correction.to_matrix().to_4x4())
    lid.data.update()
    bpy.context.view_layer.update()
    print(f'[scene] aligned source lid rim by {math.degrees(correction.angle):.2f} degrees')
    for obj in list(imported):
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    print(f'[scene] pot GLB mesh nodes: {nodes}')
    return body, lid


def collision_payload(
    lid: bpy.types.Object,
    *,
    mode: str,
    rim_thickness_m: float,
    segments: int,
    source_asset: str,
    source_node: str,
) -> dict[str, Any]:
    """Collision vertices in the aligned lid frame, including dome and knob.

    mesh_hull encloses the full visible lid in every orientation. rim_disc is
    retained only for comparisons; it cannot support the dome when inverted.
    The convex hull fills the hollow underside, which is acceptable for this
    floor-only scene (no objects enter the lid cavity).
    """
    lo, hi = local_bounds(lid)
    if mode == 'mesh_hull':
        vertices = [[round(c, 6) for c in v.co] for v in lid.data.vertices]
        payload: dict[str, Any] = {
            'mode': 'mesh_hull',
            'vertices': vertices,
            'vertex_count': len(vertices),
        }
    elif mode == 'rim_disc':
        radius = round(0.5 * max(hi.x - lo.x, hi.y - lo.y), 6)
        bottom = round(lo.z, 6)
        vertices = []
        for z in (bottom, bottom + float(rim_thickness_m)):
            for i in range(segments):
                angle = i * math.tau / segments
                vertices.append(
                    [
                        round(radius * math.cos(angle), 6),
                        round(radius * math.sin(angle), 6),
                        round(z, 6),
                    ]
                )
        payload = {
            'mode': 'rim_disc',
            'vertices': vertices,
            'vertex_count': len(vertices),
            'radius_m': radius,
            'thickness_m': float(rim_thickness_m),
            'bottom_z_m': bottom,
        }
    else:
        raise ValueError(f'unknown collision_shape {mode!r} in layout.collision_shape')

    payload.update(
        {
            'units': 'm',
            'origin': 'volume centroid of the lid mesh',
            'axis': '+Z through the dome; the lid lies flat in the XY plane',
            'diameter_m': round(max(lid.dimensions.x, lid.dimensions.y), 5),
            'height_m': round(float(lid.dimensions.z), 5),
            'source_asset': source_asset,
            'source_node': source_node,
        }
    )
    return payload


def surface_z(x: float, y: float, fallback: float) -> float:
    """Top of whatever is under (x, y): the hob on the worktop the pot stands on."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    # Start below the ceiling and the wall cabinets so the first hit is the
    # worktop and not something above it.
    origin = Vector((x, y, 1.5))
    hit, location, _normal, _index, obj, _matrix = bpy.context.scene.ray_cast(
        depsgraph, origin, Vector((0.0, 0.0, -1.0))
    )
    if hit:
        print(f'[scene] pot support surface at z={location.z:.3f} ({obj.name})')
        return float(location.z)
    print('[scene] no surface under the pot, using layout.counter_top_z')
    return fallback


# ---------------------------------------------------------------- physics


def physics_python(explicit: Path | None) -> str:
    candidates = [explicit, ROOT / '.runtime' / 'sim' / 'python.exe', ROOT / '.runtime' / 'sim' / 'bin' / 'python']
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
    hull_path: Path,
    fps: int,
    duration: float,
) -> dict[str, Any]:
    trajectory = out_dir / TRAJECTORY_NAME
    command = [
        physics_python(args.physics_python),
        str(HERE / 'simulate_pot_lid_drop.py'),
        '--out', str(trajectory),
        '--scenario', str(scenario_path),
        '--lid-hull-json', str(hull_path),
        '--fps', str(int(fps)),
        '--duration-sec', str(float(duration)),
    ]
    subprocess.run(command, check=True)
    return scene_config.read_json(trajectory)


def build_bowl(bpy, radius: float):
    """Ceramic bowl lathed from the shared kitchen_tableware profile.

    Vertices are generated around the profile with the object origin at the
    physics body's centre of mass, so a physics location maps straight onto
    ``obj.location``. The profile constants live in edit_vocab.py (the
    simulator reads the same ones); the glaze is cookware.glaze_bowl.
    """
    import edit_vocab as _clean_scene_bundle
    scale = radius / _clean_scene_bundle.BOWL_PROFILE_BASE_RADIUS_M
    com = _clean_scene_bundle.BOWL_COM_HEIGHT_M * scale
    profile = [(r * scale, z * scale - com)
               for r, z in _clean_scene_bundle.BOWL_PROFILE]
    segments = 96
    count = len(profile)
    verts: list[tuple[float, float, float]] = []
    for i in range(segments):
        ang = 2.0 * math.pi * i / segments
        cos_a, sin_a = math.cos(ang), math.sin(ang)
        for r, z in profile:
            verts.append((r * cos_a, r * sin_a, z))
    faces: list[tuple[int, int, int, int]] = []
    for i in range(segments):
        i_next = (i + 1) % segments
        for j in range(count - 1):
            a = i * count + j
            b = i * count + j + 1
            c = i_next * count + j
            d = i_next * count + j + 1
            faces.append((a, b, d, c))
    mesh = bpy.data.meshes.new('bowl_added')
    mesh.from_pydata(verts, [], faces)
    mesh.update()
    obj = bpy.data.objects.new('bowl_added', mesh)
    bpy.context.collection.objects.link(obj)
    # The foot ring and the underside inside it (profile z < 4.5 mm) are left
    # unglazed, as on any thrown bowl.
    cookware.glaze_bowl(obj, 0.0045 * scale - com)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def apply_bowl_animation(bowl, physics: dict[str, Any], origin: Vector) -> None:
    """Keyframe the knocked bowl from the per-frame body pose the sim wrote."""
    bowl.rotation_mode = 'QUATERNION'
    for record in physics['frames']:
        location = record.get('bowl_location')
        if location is None:
            continue
        frame = int(record['frame_index'])
        x, y, z, w = record['bowl_quaternion_xyzw']
        bowl.location = Vector(location) + origin
        bowl.rotation_quaternion = Quaternion((w, x, y, z))
        bowl.keyframe_insert('location', frame=frame)
        bowl.keyframe_insert('rotation_quaternion', frame=frame)
    action = bowl.animation_data.action
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'


def apply_physics_animation(lid: bpy.types.Object, physics: dict[str, Any], origin: Vector) -> None:
    lid.rotation_mode = 'QUATERNION'
    for record in physics['frames']:
        frame = int(record['frame_index'])
        x, y, z, w = record['lid_quaternion_xyzw']
        lid.location = Vector(record['lid_location']) + origin
        lid.rotation_quaternion = Quaternion((w, x, y, z))
        lid.keyframe_insert('location', frame=frame)
        lid.keyframe_insert('rotation_quaternion', frame=frame)
    action = lid.animation_data.action
    for curve in action.fcurves:
        for point in curve.keyframe_points:
            point.interpolation = 'LINEAR'


# ------------------------------------------------------------------- scene


def build_camera(layout: dict[str, Any], origin: Vector) -> bpy.types.Object:
    location = Vector([float(v) for v in layout['camera_location']]) + origin
    target = Vector([float(v) for v in layout['camera_target']]) + origin
    bpy.ops.object.camera_add(location=location)
    camera = bpy.context.object
    camera.name = 'pot_lid_drop_camera'
    camera.rotation_euler = (target - location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens = float(layout['camera_lens_mm'])
    camera.data.clip_start = 0.05
    camera.data.clip_end = 100.0
    bpy.context.scene.camera = camera
    return camera


DEFAULT_GRADE = {
    'view_transform': 'AgX',
    'look': 'AgX - Base Contrast',
    'exposure': 0.0,
}

# Half a frame of shutter, the 180-degree rule a film camera would use.
MOTION_BLUR_SHUTTER = 0.5


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
    scene.cycles.diffuse_bounces = 5
    scene.cycles.glossy_bounces = 5
    scene.cycles.transmission_bounces = 6
    scene.cycles.transparent_max_bounces = 8
    # A room lit through one window converges slowly; clamping only indirect
    # light keeps rare caustic paths off the polished steel without dimming
    # anything the eye can check.
    scene.cycles.sample_clamp_indirect = 8.0
    scene.cycles.caustics_reflective = False
    scene.cycles.caustics_refractive = False
    scene.cycles.device = 'CPU'
    if args.device == 'auto':
        preferences = bpy.context.preferences.addons['cycles'].preferences
        for backend in ('OPTIX', 'CUDA', 'HIP'):
            try:
                preferences.compute_device_type = backend
                preferences.get_devices()
            except (TypeError, RuntimeError):
                continue
            devices = [d for d in preferences.devices if d.type == backend]
            if devices:
                for device in preferences.devices:
                    device.use = device.type == backend
                scene.cycles.device = 'GPU'
                print(f'[render] {backend}: {", ".join(d.name for d in devices)}')
                break
    scene.render.resolution_x, scene.render.resolution_y = (int(v) for v in args.resolution)
    scene.render.resolution_percentage = 100
    scene.render.fps = int(fps)
    scene.frame_start = 1
    scene.frame_end = int(frame_end)
    # The falling lid moves up to 19 cm between frames; a real shutter smears
    # it. Persistent data stays off: Blender 4.3 with persistent data and
    # motion blur drops an object that has come to rest from every later
    # frame rendered in the same session (the lid lies still from frame 32).
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = MOTION_BLUR_SHUTTER
    scene.render.use_persistent_data = False
    scene.render.image_settings.file_format = 'PNG'
    scene.render.image_settings.color_mode = 'RGB'
    scene.render.film_transparent = False

    # AgX with its base contrast and no exposure trim: the room is exposed for
    # the interior and the overcast sea outside the window rolls off softly
    # instead of clipping to a white card.
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
    lid: bpy.types.Object,
    pot: bpy.types.Object,
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
            'lid': {
                'object_name': lid.name,
                'diameter_m': float(max(lid.dimensions.x, lid.dimensions.y)),
                'height_m': float(lid.dimensions.z),
            },
            'pot': {'object_name': pot.name, 'note': 'static set dressing, not simulated'},
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
                'lid_matrix_world': [[float(v) for v in row] for row in lid.matrix_world],
                'lid_location': [float(v) for v in lid.location],
                'lid_quaternion_xyzw': [
                    float(lid.rotation_quaternion.x),
                    float(lid.rotation_quaternion.y),
                    float(lid.rotation_quaternion.z),
                    float(lid.rotation_quaternion.w),
                ],
                'lid_linear_velocity': [float(v) for v in record['lid_linear_velocity']],
                'lid_angular_velocity': [float(v) for v in record['lid_angular_velocity']],
                'lid_point_gap': float(record['lid_point_gap']),
                'contacting': bool(record['contacting']),
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

    pot_path = model_path(assets['pot'], args)
    print(f'[scene] pot={pot_path}')

    scenario_path = out_dir / RESOLVED_NAME
    scene_config.write_json(scenario_path, scenario)

    bpy.ops.wm.read_factory_settings(use_empty=True)
    scene = bpy.context.scene
    room = coastal_kitchen.build_kitchen(scene, layout)
    print(f'[scene] kitchen built: {room}')

    pot, lid = import_pot(pot_path, layout)

    # One scale for both parts: the lid is measured first so the pot keeps the
    # proportions it was modelled with.
    target_diameter = float(layout['lid_diameter_m'])
    observed = horizontal_diameter(lid)
    factor = target_diameter / observed
    scale_part(pot, factor)
    scale_part(lid, factor)
    print(
        f'[scene] lid diameter {observed:.4f} model units -> '
        f'{horizontal_diameter(lid):.4f} m (scale {factor:.5f})'
    )
    # Shading only (materials, smooth normals); no vertex moves, so the hull
    # written below is the mesh as measured.
    dressing = cookware.dress_pot_and_lid(pot, lid)
    print(f'[scene] cookware: {dressing}')

    origin = Vector(
        (
            float(layout['action_origin'][0]),
            float(layout['action_origin'][1]),
            float(layout['floor_z']),
        )
    )

    # Pot: static set dressing on the hob, standing where the lid came from.
    pot_lo, _pot_hi = local_bounds(pot)
    pot_x = origin.x + float(layout['pot_location'][0])
    pot_y = origin.y + float(layout['pot_location'][1])
    support = surface_z(pot_x, pot_y, float(layout.get('counter_top_z', 0.945)))
    pot.location = Vector((pot_x, pot_y, support - pot_lo.z - float(layout['pot_sink_m'])))
    bpy.context.view_layer.update()

    # The ADDed bowl: kitchen_tableware_collision's ceramic rice bowl,
    # lathed from the same shared profile the simulator builds its convex
    # hull from, so the visible bowl and the collision body are the same
    # shape by construction. Its pose is animated per frame from the
    # physics replay -- the lid knocks it over, so it is anything but set
    # dressing.
    bowl = None
    if bool((scenario['physics'].get('bowl_presence') or [0])[0]):
        bowl = build_bowl(bpy, float(scenario['physics']['bowl_radius_m']))

    # Collision body for the solver, in the lid's own frame, metres, +Z through
    # the dome. Written next to the render and, the first time, into the scene
    # directory so the simulator also runs standalone.
    hull_payload = collision_payload(
        lid,
        mode=str(layout.get('collision_shape', 'rim_disc')),
        rim_thickness_m=float(physics_cfg['lid_rim_thickness_m']),
        segments=int(layout.get('collision_segments', 64)),
        source_asset=pot_path.name,
        source_node=str(layout['lid_node_name']),
    )
    print(
        f"[scene] collision shape {hull_payload['mode']}: "
        f"{hull_payload['vertex_count']} vertices, "
        f"{hull_payload['diameter_m']} m across"
    )
    hull_path = out_dir / HULL_NAME
    scene_config.write_json(hull_path, hull_payload)

    physics = run_simulation(
        args,
        out_dir=out_dir,
        scenario_path=scenario_path,
        hull_path=hull_path,
        fps=fps,
        duration=duration,
    )
    frame_end = int(physics['frame_end'])
    setup_render(scene, args, layout, fps=fps, frame_end=frame_end)
    apply_physics_animation(lid, physics, origin)
    if bowl is not None:
        apply_bowl_animation(bowl, physics, origin)

    camera = build_camera(layout, origin)

    # Scanned props on the worktop and the floor, then the take is refused if
    # anything static that is not the floor comes within 2 cm of the lid (or
    # the bowl) in any frame, or hides it from the camera.
    props = kitchen_props.add_props(start_z=float(layout['floor_z']) + coastal_kitchen.WALL_CAB_Z[0] - 0.05)
    clearance = kitchen_props.check_clearance(
        lid=lid,
        physics=physics,
        origin=origin,
        hull_vertices=hull_payload['vertices'],
        camera=camera,
        bowl=bowl,
    )
    print(f'[scene] clearance: {clearance}')

    scene.frame_set(1)
    enable_video_output(scene, out_dir / 'pot_lid_drop.mp4')
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(out_dir / 'pot_lid_drop.blend'))

    export_ground_truth(
        out_dir,
        lid=lid,
        pot=pot,
        camera=camera,
        physics=physics,
        scenario=scenario,
        origin=origin,
        fps=fps,
    )
    scene_config.write_json(
        out_dir / METADATA_NAME,
        {
            'scene': scenario.get('scene', 'pot_lid_drop'),
            'fps': fps,
            'duration_sec': duration,
            'total_frames': frame_end,
            'resolution': [int(v) for v in args.resolution],
            'samples': int(args.samples),
            'assets': {'pot': str(pot_path), 'polyhaven': str(coastal_kitchen.TEXTURES)},
            'appearance': {
                'room': room,
                'cookware': dressing,
                'props': props,
                'clearance': clearance,
                'motion_blur_shutter': MOTION_BLUR_SHUTTER,
            },
            'lid': {
                'diameter_m': float(horizontal_diameter(lid)),
                'height_m': float(lid.dimensions.z),
                'hull_vertex_count': hull_payload['vertex_count'],
                'collision_model': f"{hull_payload['mode']} convex hull, rigid, no deformation",
            },
            'quality': physics['quality'],
            'scenario': scenario,
        },
    )

    if args.mode == 'build':
        return

    if args.mode == 'preview':
        frames = [args.preview_frame] if args.preview_frame is not None else [1, int(physics['quality']['first_contact_frame'] or 1), frame_end]
        for frame in dict.fromkeys(frames):
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
        enable_video_output(scene, out_dir / 'pot_lid_drop.mp4')
        bpy.ops.render.render(animation=True)


if __name__ == '__main__':
    run_renderer(main, 'pot_lid_drop')
