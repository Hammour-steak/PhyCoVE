"""Lighting and materials of the oil kitchen (applied by render_cooking_oil_pan.py after the template is loaded).

The kitchen model is closed except towards the room behind and left of the camera (azimuth 240-270 deg, below ~40 deg
elevation; wall cabinets 0.5 m above the counter). Daylight comes from that side: a sky (world) and a low sun (az 250,
el 28 deg); the template's area lights are off; a weak warm under-cabinet strip. Nonstick pan interior as dark-grey
semi-gloss PTFE, brushed utensils, honed countertop, no path-traced caustics."""
import math

import bpy
from mathutils import Euler, Vector

TEMPLATE_LIGHTS = ("PCVE_ModernKitchen_CeilingBounce", "PCVE_ModernKitchen_WindowFill", "SoftFrontFill",
                   "WarmKitchenKey", "WindowDaylight")


def _world_sky(strength, color=(0.50, 0.66, 0.95)):
    w = bpy.context.scene.world
    nt = w.node_tree
    bg = next(n for n in nt.nodes if n.type == "BACKGROUND")
    bg.inputs["Color"].default_value = (*color, 1)
    bg.inputs["Strength"].default_value = strength


def _sun(az_deg, el_deg, strength, angle_deg=1.5, color=(1.0, 0.93, 0.84)):
    sun = bpy.data.lights.new("LookSun", "SUN")
    sun.energy = strength; sun.angle = math.radians(angle_deg); sun.color = color
    ob = bpy.data.objects.new("LookSun", sun)
    bpy.context.scene.collection.objects.link(ob)
    # direction the light travels: from (az, el) towards the scene
    d = -Vector((math.cos(math.radians(el_deg)) * math.cos(math.radians(az_deg)),
                 math.cos(math.radians(el_deg)) * math.sin(math.radians(az_deg)), math.sin(math.radians(el_deg))))
    ob.rotation_euler = d.to_track_quat("-Z", "Y").to_euler()
    return ob


def _under_cabinet(strength, color=(1.0, 0.80, 0.60)):
    """LED strip under the wall cabinets (bottom z ~1.80), near the back wall, shining down"""
    L = bpy.data.lights.new("LookUnderCabinet", "AREA")
    L.shape = "RECTANGLE"; L.size = 1.4; L.size_y = 0.03; L.energy = strength; L.color = color
    ob = bpy.data.objects.new("LookUnderCabinet", L)
    bpy.context.scene.collection.objects.link(ob)
    ob.location = (1.05, 3.66, 1.795)
    ob.rotation_euler = Euler((0.0, 0.0, 0.0))          # area lights point along -Z
    return ob


def _pan_ptfe():
    m = bpy.data.materials.get("Pan non-stick interior")
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    b.inputs["Base Color"].default_value = (0.020, 0.020, 0.022, 1)
    b.inputs["Roughness"].default_value = 0.36


def _brushed_utensils():
    """the hanging ladles / spoons / whisk share the cabinet hardware's mirror 'Chrome': give them their own brushed
    stainless steel (kitchen utensils are satin, not mirror-polished)"""
    ob = bpy.data.objects.get("utilitys.001_Chrome_0")
    if not ob:
        return
    src = ob.material_slots[0].material
    m = src.copy(); m.name = "Look brushed stainless"
    b = next(n for n in m.node_tree.nodes if n.type == "BSDF_PRINCIPLED")
    for k in ("Base Color", "Metallic", "Roughness"):
        for l in list(b.inputs[k].links):
            m.node_tree.links.remove(l)
    b.inputs["Base Color"].default_value = (0.78, 0.77, 0.75, 1)
    b.inputs["Metallic"].default_value = 1.0
    b.inputs["Roughness"].default_value = 0.22
    for slot in ob.material_slots:
        if slot.material == src:
            slot.material = m


def _honed_counter():
    """the quartz countertop's roughness map is ~0.075 (mirror polish) with sharp rims around the chips: in a shadow the
    counter's reflection of the sunlit surroundings shows the rims as bright letter-like squiggles. Honed finish:
    roughness 0.32 + 0.6 x map (0.37 on the stone, ~0.55 on the chips)."""
    m = bpy.data.materials.get("Countertop")
    nt = m.node_tree
    b = next(n for n in nt.nodes if n.type == "BSDF_PRINCIPLED")
    link = b.inputs["Roughness"].links[0]
    src = link.from_socket
    nt.links.remove(link)
    ma = nt.nodes.new("ShaderNodeMath"); ma.operation = "MULTIPLY_ADD"
    ma.inputs[1].default_value = 0.6; ma.inputs[2].default_value = 0.32
    nt.links.new(src, ma.inputs[0]); nt.links.new(ma.outputs[0], b.inputs["Roughness"])


def apply():
    sc = bpy.context.scene
    for n in TEMPLATE_LIGHTS:
        ob = bpy.data.objects.get(n)
        if ob:
            ob.hide_render = True
    _pan_ptfe()
    _brushed_utensils()
    _honed_counter()
    # path-traced caustics (sun reflected off the hob's printed badge, focused through the bottle) come out as
    # blotchy bright patches on the counter after denoising
    sc.cycles.caustics_reflective = False
    sc.cycles.caustics_refractive = False
    _world_sky(1.3)
    _sun(250, 28, 5.5)
    _under_cabinet(12)
    sc.view_settings.exposure = -0.4
