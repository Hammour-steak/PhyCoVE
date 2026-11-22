"""Lighting and ceramic overrides; these never modify simulation inputs."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
from copy import deepcopy

import bpy
from mathutils import Vector

from bathroom_details import SCREEN_SETTINGS
from bathroom_finish import CERAMIC_SETTINGS, FINISH_SETTINGS


BASE_LIGHTING = {
    'key_position_m': [0.55, -1.25, 2.35], 'key_target_m': [0, .05, .30],
    'key_power_w': 260, 'key_size_m': [.45, .35],
    'fill_position_m': [-1.15, .55, 1.80], 'fill_target_m': [0, 0, .30],
    'fill_power_w': 55, 'fill_size_m': 1.5,
    'ceiling_strip_position_m': [.50, -.80, 1.80], 'ceiling_strip_target_m': [0, 0, .43],
    'ceiling_strip_power_w': 15, 'ceiling_strip_size_m': [.80, .025],
    'world_color': [.055, .075, .10], 'world_strength': .42, 'exposure': -.75,
}
DAYLIGHT_LIGHTING = {
    **BASE_LIGHTING,
    # The base window key is outside the walls. This area is inside the
    # room and below the ceiling, with an unobstructed path to the interaction.
    'key_position_m': [.22, .55, 2.15], 'key_power_w': 35, 'key_size_m': [.35, .65],
    'fill_power_w': 6, 'ceiling_strip_power_w': 2, 'world_strength': .10,
}
PRESETS = {
    'daylight': {'lighting': DAYLIGHT_LIGHTING,
                    'tub_glaze': {'base_color_linear': [.74, .755, .77], 'roughness': .20,
                                   'coat_weight': .22, 'coat_roughness': .08}},
}
PRESETS['brass_glass'] = {
    **deepcopy(PRESETS['daylight']),
    'screen_details': deepcopy(SCREEN_SETTINGS),
}
NATURAL_LIGHTING = {
    **DAYLIGHT_LIGHTING,
    'key_power_w': 45, 'fill_power_w': 3, 'exposure': -.90,
    'key_color_linear': [1.0, .955, .90],
    'fill_color_linear': [.85, .92, 1.0],
}
PRESETS['natural_finish'] = {
    **deepcopy(PRESETS['brass_glass']),
    'lighting': deepcopy(NATURAL_LIGHTING),
    'tub_glaze': deepcopy(CERAMIC_SETTINGS),
    'finish_details': deepcopy(FINISH_SETTINGS),
}


def aim(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def apply_tub_glaze(scene, settings):
    if settings is None:
        return []
    tub = scene.objects.get('PCVE_BathtubShell')
    if tub is None:
        tub = next(obj for obj in scene.objects if obj.type == 'MESH' and
                   obj.name.startswith('Duravit_Starck_free standing'))
    changes = []
    for slot in tub.material_slots:
        original = slot.material
        if original is None or not original.use_nodes:
            raise RuntimeError('Expected a node-based bathtub material')
        mat = original.copy()
        mat.name = 'PCVE_TubGlazedCeramic'
        slot.material = mat
        bsdf = next(node for node in mat.node_tree.nodes if node.type == 'BSDF_PRINCIPLED')
        before = {'base_color_linear': list(bsdf.inputs['Base Color'].default_value)[:3],
                  'roughness': bsdf.inputs['Roughness'].default_value,
                  'coat_weight': bsdf.inputs['Coat Weight'].default_value,
                  'coat_roughness': bsdf.inputs['Coat Roughness'].default_value}
        for link in list(bsdf.inputs['Base Color'].links):
            mat.node_tree.links.remove(link)
        bsdf.inputs['Base Color'].default_value = (*settings['base_color_linear'], 1)
        bsdf.inputs['Roughness'].default_value = settings['roughness']
        bsdf.inputs['Coat Weight'].default_value = settings['coat_weight']
        bsdf.inputs['Coat Roughness'].default_value = settings['coat_roughness']
        changes.append({'object': tub.name, 'source_material': original.name,
                        'material': mat.name, 'before': before, 'after': deepcopy(settings)})
    return changes


def apply_lighting(scene, settings):
    world = bpy.data.worlds.new('PCVE_SoftBathroomWorld')
    world.use_nodes = True
    nodes, links = world.node_tree.nodes, world.node_tree.links
    nodes.clear()
    output, bg = nodes.new('ShaderNodeOutputWorld'), nodes.new('ShaderNodeBackground')
    bg.inputs['Color'].default_value = (*settings['world_color'], 1)
    bg.inputs['Strength'].default_value = settings['world_strength']
    links.new(bg.outputs['Background'], output.inputs['Surface'])
    scene.world = world
    specs = [
        ('PCVE_WindowKey', 'key', 'RECTANGLE', settings['key_size_m']),
        ('PCVE_BathroomFill', 'fill', 'SQUARE', [settings['fill_size_m']] * 2),
        ('PCVE_CeilingStrip', 'ceiling_strip', 'RECTANGLE', settings['ceiling_strip_size_m']),
    ]
    lights = {}
    for name, prefix, shape, size in specs:
        obj = scene.objects.get(name)
        if obj is None:
            obj = bpy.data.objects.new(name, bpy.data.lights.new(name, 'AREA'))
            scene.collection.objects.link(obj)
        obj.location = settings[f'{prefix}_position_m']
        obj.data.energy = settings[f'{prefix}_power_w']
        obj.data.color = settings.get(f'{prefix}_color_linear', (1, 1, 1))
        obj.data.shape = shape
        obj.data.size = size[0]
        if shape == 'RECTANGLE':
            obj.data.size_y = size[1]
        aim(obj, settings[f'{prefix}_target_m'])
        lights[prefix] = obj
    scene.view_settings.exposure = settings['exposure']
    return lights, deepcopy(settings)
