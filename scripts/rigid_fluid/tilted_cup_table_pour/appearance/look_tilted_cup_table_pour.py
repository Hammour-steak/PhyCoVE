"""Sunlit look on top of the refined kitchen (appearance_kitchen.py): a low morning sun through the window behind the
cup (directional key: crisp cup shadow across the puddle, glints on the water), glossier glaze, an oiled-walnut tone
on the support block, wet-oak darkening wherever the water is or has been (per-frame map written by
surface_tilted_cup_table_pour.py), f/8, and a 180-degree shutter: motion blur from the per-vertex water velocity, as a
24 fps camera records the stream. The refined kitchen alone keeps only a large window area light (~24 W/m^2 on the
table), which renders flat."""
import math
from pathlib import Path

import bpy
import numpy as np
from mathutils import Vector

WET_TINT = (.68, .62, .56)       # oak darkens and saturates when its pores fill with water
WET_ROUGHNESS = .16


def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def wet_wood(table, wet_npz):
    """table Base Color x WET_TINT and roughness -> WET_ROUGHNESS, weighted by the wetness image over the film grid"""
    with np.load(wet_npz) as d:
        x0, y0, c, shape = float(d['x0']), float(d['y0']), float(d['cell']), d['wet'].shape
    img = bpy.data.images.new('Wet oak map', width=shape[0], height=shape[1], alpha=False, float_buffer=True)
    img.colorspace_settings.name = 'Non-Color'
    mat = table.data.materials[0]
    n, l = mat.node_tree.nodes, mat.node_tree.links
    p = n.get('Principled BSDF')
    geo = n.new('ShaderNodeNewGeometry')
    mapping = n.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1 / (shape[0] * c), 1 / (shape[1] * c), 1)
    mapping.inputs['Location'].default_value = (-(x0 - c / 2) / (shape[0] * c), -(y0 - c / 2) / (shape[1] * c), 0)
    tex = n.new('ShaderNodeTexImage'); tex.image = img; tex.extension = 'CLIP'; tex.interpolation = 'Linear'
    l.new(geo.outputs['Position'], mapping.inputs['Vector']); l.new(mapping.outputs['Vector'], tex.inputs['Vector'])
    base_src = p.inputs['Base Color'].links[0].from_socket
    tint = n.new('ShaderNodeMix'); tint.data_type = 'RGBA'; tint.blend_type = 'MULTIPLY'
    tint.inputs[7].default_value = (*WET_TINT, 1)
    l.new(tex.outputs['Color'], tint.inputs['Factor']); l.new(base_src, tint.inputs[6]); l.new(tint.outputs[2], p.inputs['Base Color'])
    rough_src = p.inputs['Roughness'].links[0].from_socket
    rough = n.new('ShaderNodeMix'); rough.data_type = 'FLOAT'
    rough.inputs[3].default_value = WET_ROUGHNESS
    l.new(tex.outputs['Color'], rough.inputs['Factor']); l.new(rough_src, rough.inputs[2]); l.new(rough.outputs[0], p.inputs['Roughness'])
    return img


def walnut(support):
    mat = support.data.materials[0]
    n, l = mat.node_tree.nodes, mat.node_tree.links
    p = n.get('Principled BSDF')
    src = p.inputs['Base Color'].links[0].from_socket
    gamma = n.new('ShaderNodeGamma'); gamma.inputs['Gamma'].default_value = 1.35          # stronger figure
    tone = n.new('ShaderNodeMix'); tone.data_type = 'RGBA'; tone.blend_type = 'MULTIPLY'
    tone.inputs['Factor'].default_value = 1.0; tone.inputs[7].default_value = (.42, .30, .24, 1)
    l.new(src, gamma.inputs['Color']); l.new(gamma.outputs[0], tone.inputs[6]); l.new(tone.outputs[2], p.inputs['Base Color'])
    for link in list(p.inputs['Roughness'].links):
        l.remove(link)
    p.inputs['Roughness'].default_value = .36
    p.inputs['Coat Weight'].default_value = .3                                              # oiled finish
    p.inputs['Coat Roughness'].default_value = .18


def apply(scene, args, run):
    bpy.ops.object.light_add(type='SUN')
    sun = bpy.context.object
    sun.name = 'Morning sun through kitchen window'
    sun.data.energy = args.sun_strength
    sun.data.angle = math.radians(1.2)
    sun.data.color = (1.0, .93, .82)
    el, az = math.radians(args.sun_elevation), math.radians(args.sun_azimuth)
    travel = Vector((math.cos(el) * math.cos(az), math.cos(el) * math.sin(az), -math.sin(el)))
    sun.rotation_euler = travel.to_track_quat('-Z', 'Y').to_euler()
    if args.bounce_energy > 0:
        bpy.ops.object.light_add(type='AREA', location=(.62, .06, .30))
        bounce = bpy.context.object
        bounce.name = 'Room bounce from the right wall'
        bounce.data.size = .6
        bounce.data.energy = args.bounce_energy
        bounce.data.color = (1.0, .97, .93)
        look_at(bounce, (.06, 0.0, .03))
    window = bpy.data.objects['Daylight through kitchen window']
    window.data.energy *= args.window_scale
    for mat in bpy.data.materials:
        if 'feldspathic glaze' in mat.name:
            p = mat.node_tree.nodes.get('Principled BSDF')
            p.inputs['Coat Weight'].default_value = .6
            p.inputs['Coat Roughness'].default_value = .045
    walnut(bpy.data.objects['SquareCupSupport'])
    table = bpy.data.objects['RealScaleWoodTable']
    wet_dir = Path(run) / 'wetmap'
    img = wet_wood(table, next(iter(sorted(wet_dir.glob('wet_*.npz'))))) if wet_dir.is_dir() else None
    scene.view_settings.exposure = args.exposure
    scene.camera.data.dof.aperture_fstop = args.fstop
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.5

    def update(frame):
        if img is None:
            return
        with np.load(wet_dir / f'wet_{frame:04d}.npz') as d:
            w = d['wet'].astype(np.float32).T                      # rows along y, as Blender stores images
        rgba = np.ones((*w.shape, 4), np.float32); rgba[..., :3] = w[..., None]
        img.pixels.foreach_set(rgba.ravel()); img.update()

    ledger = {'look': 'sunlit', 'sun_strength_w_m2': args.sun_strength, 'sun_elevation_deg': args.sun_elevation,
              'sun_azimuth_deg': args.sun_azimuth, 'bounce_w': args.bounce_energy,
              'window_scale': args.window_scale, 'exposure': args.exposure, 'fstop': args.fstop,
              'motion_blur_shutter_frames': 0.5, 'wet_wood_map': img is not None, 'support': 'oiled walnut tone'}
    return ledger, update
