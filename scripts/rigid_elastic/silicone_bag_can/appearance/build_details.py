"""One-off template build of the packed counter kitchen (pear contacts, folded linen, window daylight), plus surface helpers.

The packed result is assets/scenes/silicone_bag_can/source_scene.blend. main() ran once on a CPU over
the base template that Blender opened (`blender -b <template> --python build_details.py -- ...`), with the Poly Haven
rough_linen 2k textures; --linen-dir holds linen_asset_manifest.json and those
textures, --template-out and --out are new paths. render_counter.py imports mesh_surface and contact_gaps from here."""
import hashlib
import json
from math import cos, pi, sin
import os
from pathlib import Path
import socket
import sys


import bpy
from mathutils import Vector
from mathutils.bvhtree import BVHTree

sys.path.insert(0, str(Path(__file__).resolve().parent))
import optics_native as utils

LINEN = None     # --linen-dir
OUT = None       # --out (build report and preview stills)
TEMPLATE = None  # --template-out (new packed template)


def evaluated_points(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    points = [obj.matrix_world @ vertex.co for vertex in mesh.vertices]
    evaluated.to_mesh_clear()
    return points


def mesh_surface(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    mesh = evaluated.to_mesh()
    surface = BVHTree.FromPolygons([obj.matrix_world @ v.co for v in mesh.vertices],
                                   [list(p.vertices) for p in mesh.polygons])
    evaluated.to_mesh_clear()
    return surface


def contact_gaps(obj, surface):
    points = evaluated_points(obj)
    gaps = []
    for point in points:
        hit, *_ = surface.ray_cast((point.x, point.y, 2), (0, 0, -1), 2)
        assert hit is not None, obj.name
        gaps.append(point.z - hit.z)
    return gaps


def settle_pears():
    plate = bpy.data.objects['carved fruit plate / carved_wooden_plate']
    surface = mesh_surface(plate)
    rows = []
    for obj in sorted(bpy.context.scene.objects, key=lambda obj: obj.name):
        if not obj.name.startswith('Asian pears /'):
            continue
        before = min(contact_gaps(obj, surface))
        transform = obj.matrix_world.copy()
        transform.translation.z += .00012 - before
        obj.matrix_world = transform
        bpy.context.view_layer.update()
        after = min(contact_gaps(obj, surface))
        assert abs(after - .00012) < .00002
        rows.append(dict(object=obj.name, before_gap_m=before, contact_gap_m=after,
                         shift_z_m=.00012 - before,
                         evaluated_bottom_m=min(p.z for p in evaluated_points(obj)),
                         support=plate.name, support_geometry='evaluated subdivided mesh'))
    assert len(rows) == 5
    return rows


def linen_material():
    material = bpy.data.materials.new('photographed blue linen, 0.2707 m repeat')
    nodes, links, shader, _ = utils.reset_material(material)
    shader.inputs['Sheen Weight'].default_value = .22
    shader.inputs['Sheen Roughness'].default_value = .65
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = .45
    asset = LINEN
    manifest = json.loads((asset / 'linen_asset_manifest.json').read_text())
    for row in manifest['files']:
        texture = nodes.new('ShaderNodeTexImage')
        texture.image = bpy.data.images.load(str(asset / row['path']), check_existing=True)
        if row['kind'] == 'Diffuse':
            links.new(texture.outputs['Color'], shader.inputs['Base Color'])
        elif row['kind'] == 'Rough':
            texture.image.colorspace_settings.name = 'Non-Color'
            links.new(texture.outputs['Color'], shader.inputs['Roughness'])
        else:
            texture.image.colorspace_settings.name = 'Non-Color'
            links.new(texture.outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], shader.inputs['Normal'])
    return material


def folded_linen():
    """Relax a continuous two-layer fold under gravity, then retain its rest mesh."""
    main_scene = bpy.context.scene
    old = bpy.data.objects['folded cotton tea towel']
    old.hide_render = True
    preparation = bpy.data.scenes.new('separate cloth rest preparation')
    bpy.context.window.scene = preparation
    preparation.render.fps = 24
    preparation.frame_start = 1
    preparation.frame_end = 96
    preparation.gravity = (0, 0, -9.81)
    bpy.ops.mesh.primitive_cube_add(size=1, location=(-.60, .15, .900))
    counter = bpy.context.object
    counter.name = 'temporary cloth support'
    counter.dimensions = (1, .8, .02)
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    counter.modifiers.new('Counter collision', 'COLLISION')
    counter.collision.thickness_outer = .0002
    counter.collision.cloth_friction = 12

    count_x, count_y = 148, 58
    radius, width, depth = .0024, .224, .176
    unfolded = 2 * width + pi * radius
    points, uv, faces = [], [], []
    for j in range(count_y + 1):
        v = j / count_y
        for i in range(count_x + 1):
            distance = unfolded * i / count_x
            if distance <= width:
                x, z = width / 2 - distance, .916
            elif distance <= width + pi * radius:
                angle = (distance - width) / radius
                x = -width / 2 - radius * sin(angle)
                z = .916 + radius * (1 - cos(angle))
            else:
                x = -width / 2 + distance - width - pi * radius
                z = .916 + 2 * radius
            # One loose diagonal crease, falling to almost zero at the edges.
            crease = .0016 * sin(pi * v) ** 2 * sin(2 * pi * i / count_x + 1.4 * v)
            points.append((x, depth * (v - .5), z + crease))
            uv.append((distance / .2707, depth * v / .2707))
            if i and j:
                k = j * (count_x + 1) + i
                faces.append((k - count_x - 2, k - count_x - 1, k, k - 1))
    mesh = bpy.data.meshes.new('continuous folded linen sheet')
    mesh.from_pydata(points, [], faces)
    mesh.update()
    texture_uv = mesh.uv_layers.new(name='Measured textile coordinates')
    for loop in mesh.loops:
        texture_uv.data[loop.index].uv = uv[loop.vertex_index]
    cloth = bpy.data.objects.new('folded linen napkin', mesh)
    preparation.collection.objects.link(cloth)
    cloth.location = (-.60, .128, 0)
    cloth.rotation_euler.z = -.16
    cloth.data.materials.append(linen_material())
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    modifier = cloth.modifiers.new('Gravity and self contact rest preparation', 'CLOTH')
    settings = modifier.settings
    settings.quality = 8
    settings.mass = .00025
    settings.air_damping = 4
    settings.tension_stiffness = 28
    settings.compression_stiffness = 28
    settings.shear_stiffness = 15
    settings.bending_stiffness = .12
    settings.tension_damping = 8
    settings.compression_damping = 8
    settings.shear_damping = 6
    settings.bending_damping = 1
    collision = modifier.collision_settings
    collision.use_self_collision = True
    collision.distance_min = .0006
    collision.self_distance_min = .0011
    collision.self_friction = 8
    collision.collision_quality = 4
    history = []
    for frame in range(1, 97):
        preparation.frame_set(frame)
        if frame % 12 == 0:
            points = evaluated_points(cloth)
            history.append(dict(frame=frame, min_z_m=min(p.z for p in points),
                                max_z_m=max(p.z for p in points)))
            print('LINEN_REST_FRAME', frame, flush=True)
    final_mesh = bpy.data.meshes.new_from_object(cloth.evaluated_get(bpy.context.evaluated_depsgraph_get()),
                                                depsgraph=bpy.context.evaluated_depsgraph_get())
    cloth.modifiers.clear()
    cloth.data = final_mesh
    preparation.collection.objects.unlink(cloth)
    main_scene.collection.objects.link(cloth)
    bpy.context.window.scene = main_scene
    bpy.data.objects.remove(counter, do_unlink=True)
    bpy.data.scenes.remove(preparation)
    cloth.modifiers.new('Linen submillimetre sheet thickness', 'SOLIDIFY').thickness = .00055
    cloth.modifiers[-1].offset = 0
    subdivision = cloth.modifiers.new('Soft sewn fabric edges', 'SUBSURF')
    subdivision.levels = 1
    subdivision.render_levels = 1
    bpy.context.view_layer.update()
    points = evaluated_points(cloth)
    cloth.location.z += .91008 - min(p.z for p in points)
    bpy.context.view_layer.update()
    points = evaluated_points(cloth)
    assert abs(min(p.z for p in points) - .91008) < .00002
    assert max(p.z for p in points) < .95
    return dict(object=cloth.name, counter_z_m=.91, minimum_gap_m=.00008,
                thickness_m=.00055, texture_scale_m=.2707, continuous_two_layer_fold=True,
                prepared_on_cpu=True, history=history, frozen_rest_geometry=True)


def window_daylight():
    scene = bpy.context.scene
    world = scene.world
    environment = next(n for n in world.node_tree.nodes if n.type == 'TEX_ENVIRONMENT')
    for link in list(environment.inputs['Vector'].links):
        world.node_tree.links.remove(link)
    # The environment texture uses actual world ray directions without a generated mesh coordinate.
    background = next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND')
    background.inputs['Strength'].default_value = .55
    glass = bpy.data.objects['photo6 window glass'].data.materials[0]
    shader = glass.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Base Color'].default_value = (.98, .99, 1, 1)
    shader.inputs['Roughness'].default_value = .012
    scene.cycles.max_bounces = 12
    scene.cycles.transmission_bounces = 10
    scene.render.film_transparent = False
    return dict(image=environment.image.filepath,
                hdri_sha256=hashlib.sha256(Path(environment.image.filepath).read_bytes()).hexdigest(),
                strength=.55, world_ray_coordinates=True, solid_glass_thickness_m=.003,
                transmission_bounces=10)


def main():
    global LINEN, OUT, TEMPLATE
    import argparse
    assert sys.platform.startswith("linux"), "run in Blender on a Linux host"
    ap = argparse.ArgumentParser()
    ap.add_argument("--linen-dir", type=Path, required=True)
    ap.add_argument("--template-out", type=Path, required=True)
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args(sys.argv[sys.argv.index("--") + 1:])
    LINEN, OUT, TEMPLATE = a.linen_dir, a.out, a.template_out
    assert os.environ.get('CUDA_VISIBLE_DEVICES') == ''
    OUT.mkdir(parents=True, exist_ok=True)
    scene = bpy.context.scene
    scene.frame_set(1)
    signature = utils.dynamic_signature()
    pears = settle_pears()
    linen = folded_linen()
    daylight = window_daylight()
    assert utils.dynamic_signature() == signature
    report = dict(pear_contacts=pears, linen=linen, daylight=daylight,
                  native_signature=signature, native_dynamics_unchanged=True,
                  host=socket.gethostname(), cpu_only=True)
    scene['counter_contact_report'] = json.dumps(report)
    TEMPLATE.parent.mkdir(parents=True, exist_ok=True)
    assert not TEMPLATE.exists()
    bpy.ops.file.pack_all()
    bpy.ops.wm.save_as_mainfile(filepath=str(TEMPLATE), compress=True)
    bpy.ops.wm.open_mainfile(filepath=str(TEMPLATE), load_ui=False, use_scripts=False)
    assert utils.dynamic_signature() == signature
    report.update(template=str(TEMPLATE), template_sha256=hashlib.sha256(TEMPLATE.read_bytes()).hexdigest(),
                  saved_scene_readback_passed=True)
    (OUT / 'build_report.json').write_text(json.dumps(report, indent=2))
    scene = bpy.context.scene
    scene.cycles.device = 'CPU'
    scene.cycles.samples = 32
    scene.cycles.use_denoising = True
    scene.cycles.denoiser = 'OPENIMAGEDENOISE'
    scene.cycles.denoising_use_gpu = False
    scene.cycles.adaptive_threshold = .025
    scene.render.resolution_percentage = 75
    scene.render.filepath = str(OUT / 'main.png')
    bpy.ops.render.render(write_still=True)
    scene.frame_set(25)
    camera = scene.camera
    camera.location = (.10, -.82, 1.49)
    target = Vector((-.01, .24, .96))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens = 28
    camera.data.dof.focus_distance = (target - camera.location).length
    scene.render.resolution_percentage = 100
    scene.render.filepath = str(OUT / 'counter_detail.png')
    bpy.ops.render.render(write_still=True)
    camera.location = (-.28, -.33, 1.55)
    target = Vector((-.86, .68, 1.58))
    camera.rotation_euler = (target - camera.location).to_track_quat('-Z', 'Y').to_euler()
    camera.data.lens = 24
    camera.data.dof.focus_distance = (target - camera.location).length
    scene.render.filepath = str(OUT / 'window_detail.png')
    bpy.ops.render.render(write_still=True)
    print('COUNTER_DETAILS_READY', flush=True)


if __name__ == '__main__':
    main()
