"""Photographic finish, applied after the joinery pass; appearance only.

No pose, contact surface, solved spring vertex, camera position, lens or render
size is changed here. The pass removes lettering and labels, gives the wall a
scanned painted-plaster finish, turns the window into a physical light opening
(thin glass, overcast garden view, daylight emitter in the opening, open-weave
sheer curtain), removes the hidden opposite-wall fill light and adds a handling
haze to the polished bob.
"""

import json
import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import bpy
from mathutils import Matrix, Vector

from appearance.room import _assign, _bounds, _principled
from scene_paths import ASSET_DIR  # noqa: F401  (puts scripts/ on sys.path)
from pcve_assets import asset

LABEL_PREFIXES = (
    "Inlaid toy badge",
    "Badge wordmark",
    "Badge subtitle",
    "Plaque retaining screw",
    "Engraved scale tick",
)
HIDDEN_FILL = "Diffuse reflection from the opposite room wall"


def _image(name, colorspace):
    """Load a registered asset file; HDR images keep Blender's linear default."""
    image = bpy.data.images.load(str(asset(name)), check_existing=True)
    if colorspace:
        image.colorspace_settings.name = colorspace
    return image


def _remove_labels():
    removed = []
    for obj in list(bpy.data.objects):
        if obj.name.startswith(LABEL_PREFIXES):
            removed.append(obj.name)
            bpy.data.objects.remove(obj, do_unlink=True)
    return sorted(removed)


def _turn_book_spines_to_wall(sc):
    """Rotate the measured book stack 180 degrees about its own vertical axis."""
    root = bpy.data.objects["Measured prop | book_encyclopedia_set_01"]
    books = [o for o in root.children_recursive if o.type == "MESH"]
    low, high = _bounds(books)
    center = Vector(((low[0] + high[0]) / 2, (low[1] + high[1]) / 2, 0.0))
    turn = (
        Matrix.Translation(center)
        @ Matrix.Rotation(math.pi, 4, "Z")
        @ Matrix.Translation(-center)
    )
    root.matrix_world = turn @ root.matrix_world
    bpy.context.view_layer.update()
    low2, high2 = _bounds(books)
    audits = json.loads(sc.get("asset_scale_audit_json", "[]"))
    for entry in audits:
        if entry["asset"] == "book_encyclopedia_set_01":
            entry["world_bbox_min_m"] = low2.tolist()
            entry["world_bbox_max_m"] = high2.tolist()
            entry["world_dimensions_m"] = (high2 - low2).tolist()
            entry["bottom_error_m"] = float(abs(low2[2] - entry["contact_surface_z_m"]))
            entry["finish_rotation"] = "180 deg about vertical; spines face the wall"
    sc["asset_scale_audit_json"] = json.dumps(audits)
    return {
        "footprint_center_m": [center.x, center.y],
        "bottom_before_m": float(low[2]),
        "bottom_after_m": float(low2[2]),
    }


def _plaster_wall(rl):
    """Scanned painted plaster with metre-true planar UVs on the room wall."""
    wall = bpy.data.objects["Continuous home wall"]
    mesh = wall.data
    uv = mesh.uv_layers.get("Finish wall planar") or mesh.uv_layers.new(
        name="Finish wall planar"
    )
    mesh.uv_layers.active = uv
    for face in mesh.polygons:
        for li in face.loop_indices:
            co = wall.matrix_world @ mesh.vertices[mesh.loops[li].vertex_index].co
            uv.data[li].uv = (co.x, co.z)
    m, p = _principled("Scanned matte painted plaster wall", (0.5, 0.5, 0.5), 0, 0.85)
    n, links = m.node_tree.nodes, m.node_tree.links
    coord = n.new("ShaderNodeUVMap")
    coord.uv_map = uv.name
    mapping = n.new("ShaderNodeMapping")
    span = rl["wall_texture_span_m"]
    mapping.inputs["Scale"].default_value = (1 / span, 1 / span, 1)
    mapping.inputs["Location"].default_value = (0.21, 0.37, 0)
    links.new(coord.outputs["UV"], mapping.inputs["Vector"])
    tex = {}
    for role, rel, space in [
        ("diff", rl["wall_diffuse"], "sRGB"),
        ("rough", rl["wall_roughness"], "Non-Color"),
        ("nor", rl["wall_normal_gl"], "Non-Color"),
    ]:
        node = n.new("ShaderNodeTexImage")
        node.image = _image(rel, space)
        links.new(mapping.outputs[0], node.inputs["Vector"])
        tex[role] = node
    # Keep the scan's mottling but re-balance its mean albedo to the room's greige paint.
    gain = n.new("ShaderNodeMixRGB")
    gain.blend_type = "MULTIPLY"
    gain.inputs[0].default_value = 1.0
    gain.inputs[2].default_value = (*rl["wall_albedo_gain"], 1)
    links.new(tex["diff"].outputs["Color"], gain.inputs[1])
    links.new(gain.outputs[0], p.inputs["Base Color"])
    rough = n.new("ShaderNodeMapRange")
    rough.inputs["From Min"].default_value = 0.5
    rough.inputs["From Max"].default_value = 0.75
    rough.inputs["To Min"].default_value = rl["wall_roughness_range"][0]
    rough.inputs["To Max"].default_value = rl["wall_roughness_range"][1]
    links.new(tex["rough"].outputs["Color"], rough.inputs[0])
    links.new(rough.outputs[0], p.inputs["Roughness"])
    normal = n.new("ShaderNodeNormalMap")
    normal.uv_map = uv.name
    normal.inputs["Strength"].default_value = rl["wall_normal_strength"]
    links.new(tex["nor"].outputs["Color"], normal.inputs["Color"])
    links.new(normal.outputs[0], p.inputs["Normal"])
    _assign(wall, m)
    return {"object": wall.name, "texture_span_m": span}


def _casement(helpers, rl):
    """Opening casement sash inside the fixed frame, with glazing bead and handle.

    The fixed frame's head/sill rails and jambs shared their front face; the
    rails are moved 2 mm forward so no two faces are coplanar at the corners.
    """
    for obj in bpy.data.objects:
        if obj.name.startswith("Window horizontal frame"):
            obj.location.y -= 0.002
    cube = helpers["cube"]
    paint = bpy.data.objects["Window vertical frame"].data.materials[0]
    x0, x1 = rl["sash_x_m"]
    z0, z1 = rl["sash_z_m"]
    w, depth, y = rl["sash_profile_m"][0], rl["sash_profile_m"][1], rl["sash_y_m"]
    parts = []
    for x in [x0 + w / 2, x1 - w / 2]:
        parts.append(
            cube("Window sash stile", (x, y, (z0 + z1) / 2), (w, depth, z1 - z0), paint, 0.0015)
        )
    for z in [z0 + w / 2, z1 - w / 2]:
        parts.append(
            cube("Window sash rail", ((x0 + x1) / 2, y - 0.001, z), (x1 - x0 - 0.002, depth, w), paint, 0.0015)
        )
    bead = 0.012
    for x in [x0 + w + bead / 2, x1 - w - bead / 2]:
        parts.append(
            cube("Window glazing bead", (x, y + 0.006, (z0 + z1) / 2), (bead, 0.012, z1 - z0 - 2 * w), paint, 0.0008)
        )
    for z in [z0 + w + bead / 2, z1 - w - bead / 2]:
        parts.append(
            cube("Window glazing bead", ((x0 + x1) / 2, y + 0.005, z), (x1 - x0 - 2 * w - 0.001, 0.012, bead), paint, 0.0008)
        )
    satin, _ = _principled("Anodised aluminium window handle", (0.62, 0.62, 0.60), 1.0, 0.32)
    hx, hz = x1 - w / 2, (z0 + z1) / 2
    base = cube("Window handle rose", (hx, y - depth / 2 - 0.004, hz), (0.030, 0.008, 0.072), satin, 0.003)
    lever = cube("Window handle lever", (hx, y - depth / 2 - 0.020, hz - 0.045), (0.016, 0.014, 0.110), satin, 0.004)
    neck = helpers["cylinder"](
        "Window handle spindle", (hx, y - depth / 2, hz), (hx, y - depth / 2 - 0.022, hz), 0.006, satin, 32
    )
    parts += [base, lever, neck]
    return [o.name for o in parts]


def _thin_glass():
    """Float glass as a thin sheet: Fresnel reflection plus straight transmission."""
    glass = bpy.data.objects["Window glazing"]
    m = bpy.data.materials.new("Thin float glass / two reflecting faces")
    m.use_nodes = True
    n, links = m.node_tree.nodes, m.node_tree.links
    n.clear()
    out = n.new("ShaderNodeOutputMaterial")
    fresnel = n.new("ShaderNodeFresnel")
    fresnel.inputs["IOR"].default_value = 1.52
    clear = n.new("ShaderNodeBsdfTransparent")
    clear.inputs["Color"].default_value = (0.97, 0.985, 0.98, 1)
    gloss = n.new("ShaderNodeBsdfGlossy")
    gloss.inputs["Roughness"].default_value = 0.015
    mix = n.new("ShaderNodeMixShader")
    links.new(fresnel.outputs["Fac"], mix.inputs["Fac"])
    links.new(clear.outputs[0], mix.inputs[1])
    links.new(gloss.outputs[0], mix.inputs[2])
    links.new(mix.outputs[0], out.inputs["Surface"])
    _assign(glass, m)


def _garden_view(sc, rl):
    """Overcast courtyard photographed outside the window, seen by camera rays only."""
    old = bpy.data.objects["Exterior daylight beyond the window"]
    bpy.data.objects.remove(old, do_unlink=True)
    bpy.ops.mesh.primitive_plane_add(size=1, location=rl["view_plane_center_m"])
    view = bpy.context.object
    view.name = "Exterior daylight beyond the window"
    view.rotation_euler = (math.pi / 2, 0, 0)
    view.scale = (rl["view_plane_size_m"][0], rl["view_plane_size_m"][1], 1)
    m = bpy.data.materials.new("Overcast garden through the glass")
    m.use_nodes = True
    n, links = m.node_tree.nodes, m.node_tree.links
    n.clear()
    out = n.new("ShaderNodeOutputMaterial")
    geom = n.new("ShaderNodeNewGeometry")
    flip = n.new("ShaderNodeVectorMath")
    flip.operation = "SCALE"
    flip.inputs["Scale"].default_value = -1.0
    links.new(geom.outputs["Incoming"], flip.inputs[0])
    mapping = n.new("ShaderNodeMapping")
    mapping.vector_type = "VECTOR"
    mapping.inputs["Rotation"].default_value[2] = math.radians(
        rl["view_hdri_rotation_deg"]
    )
    links.new(flip.outputs["Vector"], mapping.inputs["Vector"])
    env = n.new("ShaderNodeTexEnvironment")
    env.image = _image(rl["view_hdri"], None)
    links.new(mapping.outputs[0], env.inputs["Vector"])
    # The daylight emitter in the opening carries the light into the room. This
    # surface is the view the lens records (camera rays, also through the
    # transparent glass and weave); every other ray finds an opaque black
    # exterior, so nothing behind the wall leaks in a second time.
    path = n.new("ShaderNodeLightPath")
    gate = n.new("ShaderNodeMath")
    gate.operation = "MULTIPLY"
    gate.inputs[1].default_value = rl["view_strength"]
    links.new(path.outputs["Is Camera Ray"], gate.inputs[0])
    emit = n.new("ShaderNodeEmission")
    links.new(env.outputs["Color"], emit.inputs["Color"])
    links.new(gate.outputs[0], emit.inputs["Strength"])
    links.new(emit.outputs[0], out.inputs["Surface"])
    m.cycles.emission_sampling = "NONE"
    _assign(view, m)
    return view.name


def _daylight_opening(rl):
    """Move the window emitter into the wall opening behind the glass."""
    light = bpy.data.objects["Large daylight window"]
    light.location = rl["window_light_center_m"]
    light.rotation_euler = (
        (Vector(rl["window_light_center_m"]) + Vector((0, -1, 0)) - light.location)
        .to_track_quat("-Z", "Y")
        .to_euler()
    )
    light.data.shape = "RECTANGLE"
    light.data.size, light.data.size_y = rl["window_light_size_m"]
    light.data.energy = rl["window_light_power_W"]
    light.data.color = rl["window_light_color_linear"]
    light.visible_camera = False
    light.visible_glossy = True
    light.visible_diffuse = True
    if bpy.data.objects.get(HIDDEN_FILL):
        bpy.data.objects.remove(bpy.data.objects[HIDDEN_FILL], do_unlink=True)
    return {
        "lights": sorted(o.name for o in bpy.data.objects if o.type == "LIGHT"),
        "window_light_center_m": list(rl["window_light_center_m"]),
    }


def _sheer_curtain(rl):
    """Open-weave linen: part of the daylight passes straight through the weave."""
    curtain = bpy.data.objects["Sheer linen window curtain"]
    m, p = _principled("Open-weave sheer linen", (0.70, 0.68, 0.61), 0, 0.92)
    n, links = m.node_tree.nodes, m.node_tree.links
    out = n.get("Material Output")
    trans = n.new("ShaderNodeBsdfTranslucent")
    trans.inputs["Color"].default_value = (0.80, 0.78, 0.70, 1)
    hole = n.new("ShaderNodeBsdfTransparent")
    cloth = n.new("ShaderNodeMixShader")
    cloth.inputs["Fac"].default_value = rl["curtain_translucency"]
    links.new(p.outputs[0], cloth.inputs[1])
    links.new(trans.outputs[0], cloth.inputs[2])
    weave = n.new("ShaderNodeMixShader")
    weave.inputs["Fac"].default_value = rl["curtain_openness"]
    links.new(cloth.outputs[0], weave.inputs[1])
    links.new(hole.outputs[0], weave.inputs[2])
    links.new(weave.outputs[0], out.inputs["Surface"])
    _assign(curtain, m)


def _handled_bob(rl):
    """Faint fingerprint haze on the polished bob, fixed to the bob (object space)."""
    bob = bpy.data.objects["Solid steel bob | measured diameter 36 mm"]
    m = bob.data.materials[0]
    n, links = m.node_tree.nodes, m.node_tree.links
    p = n.get("Principled BSDF")
    coord = n.new("ShaderNodeTexCoord")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = rl["bob_haze_scale"]
    noise.inputs["Detail"].default_value = 3.0
    noise.inputs["Roughness"].default_value = 0.55
    links.new(coord.outputs["Object"], noise.inputs["Vector"])
    ramp = n.new("ShaderNodeMapRange")
    ramp.inputs["From Min"].default_value = 0.48
    ramp.inputs["From Max"].default_value = 0.68
    ramp.inputs["To Min"].default_value = rl["bob_roughness_range"][0]
    ramp.inputs["To Max"].default_value = rl["bob_roughness_range"][1]
    links.new(noise.outputs["Fac"], ramp.inputs[0])
    links.new(ramp.outputs[0], p.inputs["Roughness"])


def _room_ambience(sc, rl):
    for node in sc.world.node_tree.nodes:
        if node.type == "BACKGROUND":
            node.inputs["Strength"].default_value = rl["world_strength"]


def finish_scene(sc, c, helpers):
    rl = c["appearance"]["finish"]
    audit = {
        "version": rl["version"],
        "removed_labels": _remove_labels(),
        "books": _turn_book_spines_to_wall(sc),
        "wall": _plaster_wall(rl),
    }
    audit["casement"] = _casement(helpers, rl)
    _thin_glass()
    audit["window_view"] = _garden_view(sc, rl)
    audit["daylight"] = _daylight_opening(rl)
    _sheer_curtain(rl)
    _handled_bob(rl)
    _room_ambience(sc, rl)
    audit["pose_or_contact_geometry_changed"] = False
    sc["finish_audit_json"] = json.dumps(audit)
    return audit
