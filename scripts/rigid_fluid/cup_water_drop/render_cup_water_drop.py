# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import REPO
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
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
import sys
import math
import json
from pathlib import Path

import bpy
import numpy as np
from mathutils import Matrix, Quaternion, Vector

ROOT = REPO
HERE = ROOT / "scripts/rigid_fluid/cup_water_drop"
sys.path.insert(0, str(HERE))
import layout_cup_water_drop as layout

argv = sys.argv[sys.argv.index("--") + 1:] if "--" in sys.argv else []
if len(argv) >= 3:
    run, asset_path_arg, out_dir = (Path(x).expanduser().resolve() for x in argv[:3])
    samples = int(argv[3]) if len(argv) > 3 else 128
    frames = [int(x) for x in argv[4].split(",") if x.strip()] if len(argv) > 4 and argv[4] else None
else:
    raise SystemExit("usage: blender -b --python render_cup_water_drop.py -- RUN COFFEE_CUP_SET_BLEND OUT_DIR [SAMPLES] [FRAMES]")

out_dir.mkdir(parents=True, exist_ok=True)
surf = run / "surfaces"

coffee_set_asset = asset_path_arg if asset_path_arg.is_file() else ROOT / "assets/blenderkit/coffee_cup_set/coffee_cup_set.blend"
kitchen_blend = str(ROOT / "assets/blenderkit/modern_living_kitchen/modern_living_kitchen.blend")
board_blend = str(ROOT / "assets/blenderkit/cutting_board/cutting_board.blend")
apple_blend = str(ROOT / "assets/blenderkit/red_apples/red_apples.blend")

ENV_ASSETS = ROOT / "assets/rigid_fluid/tilted_cup_environment"
WOOD_DIR = ROOT / "assets/polyhaven/wood_table"
HDRI_PATH = ENV_ASSETS / "studio_small_09/studio_small_09_1k.hdr"
TOWEL_BLEND = ENV_ASSETS / "kitchen_towel/kitchen_towel.blend"

def look_at(obj, target):
    obj.rotation_euler = (Vector(target) - obj.location).to_track_quat("-Z", "Y").to_euler()

def bounds_world(obj):
    dg = bpy.context.evaluated_depsgraph_get()
    eo = obj.evaluated_get(dg)
    me = eo.to_mesh()
    pts = [obj.matrix_world @ v.co for v in me.vertices]
    eo.to_mesh_clear()
    return Vector(np.min(pts, axis=0)), Vector(np.max(pts, axis=0))

def assign_material(obj, mat):
    obj.data.materials.clear()
    obj.data.materials.append(mat)

def set_socket(bsdf, key, val):
    if key in bsdf.inputs:
        bsdf.inputs[key].default_value = val

def material_principled(name, color, roughness=0.45, metallic=0.0):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (*color, 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["Metallic"].default_value = metallic
    return mat

def porcelain_material(name, color, roughness=0.07, sss_weight=0.18):
    mat = material_principled(name, color, roughness=roughness, metallic=0.0)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    set_socket(bsdf, "Subsurface Weight", sss_weight)
    set_socket(bsdf, "Subsurface", sss_weight)
    set_socket(bsdf, "Subsurface Radius", (0.0035, 0.0028, 0.0022))
    set_socket(bsdf, "Subsurface Scale", 0.012)
    set_socket(bsdf, "Subsurface IOR", 1.50)
    set_socket(bsdf, "Coat Weight", 0.75)
    set_socket(bsdf, "Coat", 0.75)
    set_socket(bsdf, "Coat Roughness", 0.025)
    set_socket(bsdf, "Coat IOR", 1.52)
    
    tc = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2400.0
    noise.inputs["Detail"].default_value = 2.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.000008
    bump.inputs["Strength"].default_value = 0.04
    links.new(tc.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def carrara_marble_material(name="CarraraWhiteMarble"):
    """Photorealistic Italian Carrara White Marble with soft grey veining and polished lacquer coat."""
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.91, 0.905, 0.90, 1.0)
    bsdf.inputs["Roughness"].default_value = 0.12
    set_socket(bsdf, "Coat Weight", 0.70)
    set_socket(bsdf, "Coat Roughness", 0.035)
    set_socket(bsdf, "Coat IOR", 1.52)

    tc = nodes.new("ShaderNodeTexCoord")
    noise1 = nodes.new("ShaderNodeTexNoise")
    noise1.inputs["Scale"].default_value = 14.0
    noise1.inputs["Detail"].default_value = 5.0
    noise1.inputs["Roughness"].default_value = 0.50
    noise1.inputs["Distortion"].default_value = 1.6

    ramp = nodes.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.40
    ramp.color_ramp.elements[0].color = (0.55, 0.54, 0.53, 1.0)
    ramp.color_ramp.elements[1].position = 0.62
    ramp.color_ramp.elements[1].color = (0.92, 0.915, 0.91, 1.0)

    links.new(tc.outputs["Object"], noise1.inputs["Vector"])
    links.new(noise1.outputs["Fac"], ramp.inputs["Fac"])
    links.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])

    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.000015
    bump.inputs["Strength"].default_value = 0.035
    links.new(noise1.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def steel_material(name="BrushedStainlessSteel"):
    mat = material_principled(name, (0.60, 0.62, 0.64), roughness=0.18, metallic=0.98)
    bsdf = mat.node_tree.nodes["Principled BSDF"]
    set_socket(bsdf, "Anisotropic", 0.32)
    return mat

def glass_material(name="ClearGlassTumbler"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.985, 0.995, 1.0, 1.0)
    set_socket(bsdf, "Transmission Weight", 1.0)
    set_socket(bsdf, "Transmission", 1.0)
    bsdf.inputs["Roughness"].default_value = 0.012
    bsdf.inputs["IOR"].default_value = 1.50
    set_socket(bsdf, "Metallic", 0.0)
    set_socket(bsdf, "Coat Weight", 0.85)
    set_socket(bsdf, "Coat Roughness", 0.02)
    return mat

def coffee_bean_material():
    mat = material_principled("RoastedCoffeeBeanMat", (0.045, 0.022, 0.012), roughness=0.42)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    set_socket(bsdf, "Coat Weight", 0.25)
    set_socket(bsdf, "Coat Roughness", 0.25)
    tc = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 800.0
    noise.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00003
    bump.inputs["Strength"].default_value = 0.15
    links.new(tc.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def wood_table_material():
    mat = material_principled("PolyHaven_WoodTable_4K", (0.24, 0.14, 0.07), roughness=0.26)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    set_socket(bsdf, "Coat Weight", 0.42)
    set_socket(bsdf, "Coat", 0.42)
    set_socket(bsdf, "Coat Roughness", 0.14)
    set_socket(bsdf, "Coat IOR", 1.48)

    empty = bpy.data.objects.new("TableMetricCoords", None)
    bpy.context.scene.collection.objects.link(empty)
    tc = nodes.new("ShaderNodeTexCoord")
    tc.object = empty
    mapping = nodes.new("ShaderNodeMapping")
    mapping.inputs["Scale"].default_value = (1.0 / 0.92, 1.0 / 0.92, 1.0 / 0.92)
    links.new(tc.outputs["Object"], mapping.inputs["Vector"])

    for key, suffix, cs in (
        ("color", "diff", "sRGB"),
        ("rough", "rough", "Non-Color"),
        ("normal", "nor_gl", "Non-Color"),
    ):
        tex = nodes.new("ShaderNodeTexImage")
        tex.image = bpy.data.images.load(str(WOOD_DIR / f"wood_table_{suffix}_4k.jpg"), check_existing=True)
        tex.image.colorspace_settings.name = cs
        tex.projection = "BOX"
        tex.projection_blend = 0.15
        links.new(mapping.outputs["Vector"], tex.inputs["Vector"])
        if key == "color":
            hsv = nodes.new("ShaderNodeHueSaturation")
            hsv.inputs["Saturation"].default_value = 0.96
            hsv.inputs["Value"].default_value = 0.90
            links.new(tex.outputs["Color"], hsv.inputs["Color"])
            links.new(hsv.outputs["Color"], bsdf.inputs["Base Color"])
        elif key == "rough":
            remap = nodes.new("ShaderNodeMapRange")
            remap.inputs["To Min"].default_value = 0.18
            remap.inputs["To Max"].default_value = 0.38
            links.new(tex.outputs["Color"], remap.inputs["Value"])
            links.new(remap.outputs["Result"], bsdf.inputs["Roughness"])
        else:
            nm = nodes.new("ShaderNodeNormalMap")
            nm.inputs["Strength"].default_value = 0.28
            links.new(tex.outputs["Color"], nm.inputs["Color"])
            links.new(nm.outputs["Normal"], bsdf.inputs["Normal"])
    return mat


def make_subway_tile_material(name="GlazedWhiteSubwayTile"):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    nodes.clear()

    out = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    out.location = (700, 0)
    bsdf.location = (400, 0)
    links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    tc = nodes.new("ShaderNodeTexCoord")
    tc.location = (-900, 0)

    sep = nodes.new("ShaderNodeSeparateXYZ")
    comb = nodes.new("ShaderNodeCombineXYZ")
    sep.location = (-700, 0)
    comb.location = (-550, 0)
    links.new(tc.outputs["Object"], sep.inputs["Vector"])
    links.new(sep.outputs["X"], comb.inputs["X"])
    links.new(sep.outputs["Z"], comb.inputs["Y"])

    brick = nodes.new("ShaderNodeTexBrick")
    brick.location = (-350, 0)
    links.new(comb.outputs["Vector"], brick.inputs["Vector"])

    brick.inputs["Scale"].default_value = 1.0
    brick.inputs["Brick Width"].default_value = 0.150
    brick.inputs["Row Height"].default_value = 0.075
    brick.inputs["Mortar Size"].default_value = 0.0028
    brick.inputs["Mortar Smooth"].default_value = 0.40
    brick.inputs["Bias"].default_value = 0.04
    brick.offset = 0.5
    brick.offset_frequency = 2

    brick.inputs["Color1"].default_value = (0.88, 0.88, 0.875, 1.0)
    brick.inputs["Color2"].default_value = (0.85, 0.85, 0.845, 1.0)
    brick.inputs["Mortar"].default_value = (0.55, 0.54, 0.52, 1.0)

    links.new(brick.outputs["Color"], bsdf.inputs["Base Color"])

    ramp_rough = nodes.new("ShaderNodeMapRange")
    ramp_rough.location = (50, -150)
    ramp_rough.inputs["From Min"].default_value = 0.0
    ramp_rough.inputs["From Max"].default_value = 1.0
    ramp_rough.inputs["To Min"].default_value = 0.88
    ramp_rough.inputs["To Max"].default_value = 0.09
    links.new(brick.outputs["Fac"], ramp_rough.inputs["Value"])
    links.new(ramp_rough.outputs["Result"], bsdf.inputs["Roughness"])

    ramp_coat = nodes.new("ShaderNodeMapRange")
    ramp_coat.location = (50, -300)
    ramp_coat.inputs["From Min"].default_value = 0.0
    ramp_coat.inputs["From Max"].default_value = 1.0
    ramp_coat.inputs["To Min"].default_value = 0.0
    ramp_coat.inputs["To Max"].default_value = 0.85
    links.new(brick.outputs["Fac"], ramp_coat.inputs["Value"])
    if "Coat Weight" in bsdf.inputs:
        links.new(ramp_coat.outputs["Result"], bsdf.inputs["Coat Weight"])
    elif "Coat" in bsdf.inputs:
        links.new(ramp_coat.outputs["Result"], bsdf.inputs["Coat"])
    set_socket(bsdf, "Coat Roughness", 0.035)

    noise = nodes.new("ShaderNodeTexNoise")
    noise.location = (-350, -350)
    noise.inputs["Scale"].default_value = 45.0
    noise.inputs["Detail"].default_value = 3.0
    links.new(comb.outputs["Vector"], noise.inputs["Vector"])

    bump_bevel = nodes.new("ShaderNodeBump")
    bump_bevel.location = (50, 150)
    bump_bevel.inputs["Distance"].default_value = 0.0022
    bump_bevel.inputs["Strength"].default_value = 0.90
    links.new(brick.outputs["Fac"], bump_bevel.inputs["Height"])

    bump_micro = nodes.new("ShaderNodeBump")
    bump_micro.location = (220, 150)
    bump_micro.inputs["Distance"].default_value = 0.00025
    bump_micro.inputs["Strength"].default_value = 0.10
    links.new(noise.outputs["Fac"], bump_micro.inputs["Height"])
    links.new(bump_bevel.outputs["Normal"], bump_micro.inputs["Normal"])
    links.new(bump_micro.outputs["Normal"], bsdf.inputs["Normal"])

    return mat

def wall_plaster_material():
    mat = material_principled("WarmPlasterWall", (0.84, 0.81, 0.76), roughness=0.90)
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    bsdf = nodes["Principled BSDF"]
    tc = nodes.new("ShaderNodeTexCoord")
    noise = nodes.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 600.0
    noise.inputs["Detail"].default_value = 3.0
    bump = nodes.new("ShaderNodeBump")
    bump.inputs["Distance"].default_value = 0.00004
    bump.inputs["Strength"].default_value = 0.10
    links.new(tc.outputs["Object"], noise.inputs["Vector"])
    links.new(noise.outputs["Fac"], bump.inputs["Height"])
    links.new(bump.outputs["Normal"], bsdf.inputs["Normal"])
    return mat

def water_material(
    name="PCVE_ClearWater",
    roughness=0.002,
    shadow_min=0.20,
    shadow_max=0.65,
    vol_color=(0.75, 0.92, 0.99, 1.0),
    vol_density=1.6,
):
    mat = bpy.data.materials.new(name)
    mat.use_nodes = True
    nodes, links = mat.node_tree.nodes, mat.node_tree.links
    out = nodes["Material Output"]
    bsdf = nodes["Principled BSDF"]
    bsdf.inputs["Base Color"].default_value = (0.995, 0.998, 1.0, 1.0)
    set_socket(bsdf, "Transmission Weight", 1.0)
    set_socket(bsdf, "Transmission", 1.0)
    bsdf.inputs["Roughness"].default_value = roughness
    bsdf.inputs["IOR"].default_value = 1.333
    set_socket(bsdf, "Specular IOR Level", 0.5)

    lp = nodes.new("ShaderNodeLightPath")
    lw = nodes.new("ShaderNodeLayerWeight")
    lw.inputs["Blend"].default_value = 0.35
    remap = nodes.new("ShaderNodeMapRange")
    remap.inputs["From Min"].default_value = 0.0
    remap.inputs["From Max"].default_value = 1.0
    remap.inputs["To Min"].default_value = shadow_min
    remap.inputs["To Max"].default_value = shadow_max
    mul = nodes.new("ShaderNodeMath")
    mul.operation = "MULTIPLY"
    transp = nodes.new("ShaderNodeBsdfTransparent")
    transp.inputs["Color"].default_value = (0.97, 0.99, 1.0, 1.0)
    mix = nodes.new("ShaderNodeMixShader")

    links.new(lw.outputs["Facing"], remap.inputs["Value"])
    links.new(lp.outputs["Is Shadow Ray"], mul.inputs[0])
    links.new(remap.outputs["Result"], mul.inputs[1])
    links.new(mul.outputs["Value"], mix.inputs["Fac"])
    links.new(bsdf.outputs["BSDF"], mix.inputs[1])
    links.new(transp.outputs["BSDF"], mix.inputs[2])
    links.new(mix.outputs["Shader"], out.inputs["Surface"])

    volume = nodes.new("ShaderNodeVolumeAbsorption")
    volume.inputs["Color"].default_value = vol_color
    volume.inputs["Density"].default_value = vol_density
    links.new(volume.outputs["Volume"], out.inputs["Volume"])
    return mat

def add_box(name, location, size, mat, bevel=0.0):
    bpy.ops.mesh.primitive_cube_add(size=1.0, location=location)
    obj = bpy.context.object
    obj.name = name
    obj.dimensions = size
    bpy.ops.object.transform_apply(location=False, rotation=False, scale=True)
    assign_material(obj, mat)
    if bevel > 0.0:
        mod = obj.modifiers.new("EdgeBevel", "BEVEL")
        mod.width = bevel
        mod.segments = 3
        obj.modifiers.new("PlanarNormals", "WEIGHTED_NORMAL")
    return obj

def add_glass_water_tumbler(name, location, radius=0.034, height=0.088):
    bpy.ops.mesh.primitive_cylinder_add(radius=radius, depth=height, location=(location[0], location[1], location[2] + height / 2.0))
    cyl = bpy.context.object
    cyl.name = name
    mod = cyl.modifiers.new("Bevel", "BEVEL")
    mod.width = 0.002
    mod.segments = 4
    for p in cyl.data.polygons:
        p.use_smooth = True
    assign_material(cyl, glass_material())
    
    bpy.ops.mesh.primitive_cylinder_add(radius=radius * 0.90, depth=height * 0.60, location=(location[0], location[1], location[2] + height * 0.32))
    w_cyl = bpy.context.object
    w_cyl.name = f"{name}_WaterVolume"
    for p in w_cyl.data.polygons:
        p.use_smooth = True
    assign_material(w_cyl, water_material("TumblerWaterMat", vol_density=1.2))

def load_hero_and_dishes():
    bpy.ops.wm.open_mainfile(filepath=str(coffee_set_asset))
    dg = bpy.context.evaluated_depsgraph_get()

    mug = bpy.data.objects[layout.CUP_ASSET_OBJECT]
    coffee = bpy.data.objects[layout.CUP_ASSET_COFFEE]
    saucer = bpy.data.objects[layout.SAUCER_ASSET_OBJECT]
    spoon = bpy.data.objects[layout.SPOON_ASSET_OBJECT]
    bean_objs = [o for o in bpy.data.objects if o.name.startswith("coffee_bean_0")]

    sub_mug = bpy.data.meshes.new_from_object(mug.evaluated_get(dg), depsgraph=dg)
    sub_mug.transform(mug.matrix_world)
    pts = [v.co for v in sub_mug.vertices]
    cl, ch = bounds_world(coffee)
    zlo, zhi = min(p.z for p in pts), max(p.z for p in pts)
    centre = Vector(((cl.x + ch.x) / 2.0, (cl.y + ch.y) / 2.0, (zlo + zhi) / 2.0))
    scale = layout.CUP_HEIGHT / (zhi - zlo)
    for v, p in zip(sub_mug.vertices, pts):
        v.co = (p - centre) * scale
    for p in sub_mug.polygons:
        p.use_smooth = True

    sub_saucer = bpy.data.meshes.new_from_object(saucer.evaluated_get(dg), depsgraph=dg)
    sub_saucer.transform(saucer.matrix_world)
    sub_spoon = bpy.data.meshes.new_from_object(spoon.evaluated_get(dg), depsgraph=dg)
    sub_spoon.transform(spoon.matrix_world)
    sx = [v.co.x for v in sub_saucer.vertices]
    sy = [v.co.y for v in sub_saucer.vertices]
    sz = [v.co.z for v in sub_saucer.vertices]
    saucer_origin = Vector(((min(sx) + max(sx)) / 2.0, (min(sy) + max(sy)) / 2.0, min(sz)))
    
    dish_xf = (
        Matrix.Translation(Vector((-0.30, 0.08, 0.0002)))
        @ Matrix.Rotation(math.radians(layout.SAUCER_YAW_DEG), 4, "Z")
        @ Matrix.Scale(layout.SAUCER_SCALE, 4)
        @ Matrix.Translation(-saucer_origin)
    )
    for m in (sub_saucer, sub_spoon):
        m.transform(dish_xf)
        for p in m.polygons:
            p.use_smooth = True

    baked_bean_mesh = None
    if bean_objs:
        baked_bean_mesh = bpy.data.meshes.new_from_object(bean_objs[0].evaluated_get(dg), depsgraph=dg)
        bx = 0.5 * (min(v.co.x for v in baked_bean_mesh.vertices) + max(v.co.x for v in baked_bean_mesh.vertices))
        by = 0.5 * (min(v.co.y for v in baked_bean_mesh.vertices) + max(v.co.y for v in baked_bean_mesh.vertices))
        bz = min(v.co.z for v in baked_bean_mesh.vertices)
        baked_bean_mesh.transform(Matrix.Translation(Vector((-bx, -by, -bz))))

    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete(use_global=False)

    hero = bpy.data.objects.new("Hero_BlenderKit_Coffee_Cup", sub_mug)
    hero.rotation_mode = "QUATERNION"
    bpy.context.scene.collection.objects.link(hero)
    assign_material(hero, porcelain_material("HeroPorcelainGlaze", (0.84, 0.82, 0.78), roughness=0.07, sss_weight=0.18))

    saucer_obj = bpy.data.objects.new("SidePorcelainSaucer", sub_saucer)
    bpy.context.scene.collection.objects.link(saucer_obj)
    assign_material(saucer_obj, porcelain_material("SaucerPorcelainGlaze", (0.80, 0.78, 0.74), roughness=0.09, sss_weight=0.14))

    spoon_obj = bpy.data.objects.new("SideStainlessSpoon", sub_spoon)
    bpy.context.scene.collection.objects.link(spoon_obj)
    assign_material(spoon_obj, steel_material())

    if baked_bean_mesh:
        bean_mat = coffee_bean_material()
        bean_locs = [
            (-0.48, 0.08, 0.0001, 35.0, 1.25),
            (-0.44, 0.02, 0.0001, -18.0, 1.15),
            (-0.46, -0.05, 0.0001, 72.0, 1.20),
            (-0.25, -0.22, 0.0001, -45.0, 1.30),
            (-0.19, -0.27, 0.0001, 110.0, 1.18),
            (0.38, -0.06, 0.0001, 20.0, 1.20),
            (0.42, 0.00, 0.0001, -65.0, 1.15),
        ]
        for idx, (bx, by, bz, byaw, bscale) in enumerate(bean_locs):
            b_obj = bpy.data.objects.new(f"CoffeeBean_{idx}", baked_bean_mesh.copy())
            bpy.context.scene.collection.objects.link(b_obj)
            b_obj.matrix_world = (
                Matrix.Translation(Vector((bx, by, bz)))
                @ Matrix.Rotation(math.radians(byaw), 4, "Z")
                @ Matrix.Scale(bscale, 4)
            )
            assign_material(b_obj, bean_mat)

    add_glass_water_tumbler("WaterTumbler", (-0.46, 0.22, 0.0002), radius=0.034, height=0.088)

    return hero

def build_folded_linen():
    fabric = None
    if TOWEL_BLEND.is_file():
        with bpy.data.libraries.load(str(TOWEL_BLEND), link=False) as (src, dst):
            dst.objects = [name for name in src.objects if name == "Towel"]
        loaded = [o for o in dst.objects if o]
        fabric = next((m for o in loaded for m in o.data.materials if m and "Fabric" in m.name), None)
        for o in loaded:
            bpy.data.objects.remove(o, do_unlink=True)
    if fabric is None:
        fabric = material_principled("WovenLinenFallback", (0.36, 0.33, 0.28), roughness=0.86)
    elif fabric.use_nodes:
        bsdf = fabric.node_tree.nodes.get("Principled BSDF")
        if bsdf:
            set_socket(bsdf, "Sheen Weight", 0.85)
            set_socket(bsdf, "Sheen", 0.85)
            set_socket(bsdf, "Sheen Roughness", 0.40)

    length, width = layout.NAPKIN_SIZE
    radius = 0.0013
    path = []
    for layer in range(3):
        for i in range(61):
            u = i / 60.0
            x = (-length / 2.0 + u * length) * (-1.0 if layer == 1 else 1.0)
            path.append((x, 0.00065 + 2.0 * radius * layer, float(layer)))
        if layer < 2:
            for i in range(1, 25):
                angle = math.pi * i / 24.0
                sign = 1.0 if layer == 0 else -1.0
                path.append((
                    sign * (length / 2.0 + radius * math.sin(angle)),
                    0.00065 + 2.0 * radius * layer + radius * (1.0 - math.cos(angle)),
                    layer + i / 24.0,
                ))
    vertices, faces, uvs = [], [], []
    ny = 71
    for idx, (x, z, layer) in enumerate(path):
        u = idx / (len(path) - 1)
        for j in range(ny):
            v = j / (ny - 1)
            edge = math.sin(math.pi * v)
            y = (v - 0.5) * width + 0.0005 * math.sin(u * 9.0 + v * 2.0) * edge
            wrinkle = (0.00020 + 0.00024 * layer) * edge * math.sin(8.0 * math.pi * v + 2.6 * math.pi * u)
            vertices.append((x, y, z + wrinkle))
            uvs.append((u, v))
    for i in range(len(path) - 1):
        for j in range(ny - 1):
            k = i * ny + j
            faces.append((k, k + ny, k + ny + 1, k + 1))

    mesh = bpy.data.meshes.new("FoldedWovenLinenMesh")
    mesh.from_pydata(vertices, [], faces)
    mesh.update()
    uv_layer = mesh.uv_layers.new(name="ClothUV")
    for loop in mesh.loops:
        uv_layer.data[loop.index].uv = uvs[loop.vertex_index]
    for p in mesh.polygons:
        p.use_smooth = True

    cloth = bpy.data.objects.new("FoldedKitchenLinen", mesh)
    bpy.context.scene.collection.objects.link(cloth)
    xf = Matrix.Translation(Vector((layout.NAPKIN_XY[0], layout.NAPKIN_XY[1], 0.0003))) @ Matrix.Rotation(
        math.radians(layout.NAPKIN_YAW_DEG), 4, "Z"
    )
    cloth.matrix_world = xf
    assign_material(cloth, fabric)
    solid = cloth.modifiers.new("ClothThickness", "SOLIDIFY")
    solid.thickness = 0.00045
    solid.offset = 1.0
    sub = cloth.modifiers.new("ClothSubsurf", "SUBSURF")
    sub.levels = 2
    sub.render_levels = 2

def build_authentic_kitchen_environment():
    """Build a rich, authentic modern kitchen interior with real high-quality 3D assets.
    Symmetrical, well-spaced, without the green machine or black faucet per user request!
    """
    scene = bpy.context.scene

    # 1. Append materials from modern_living_kitchen
    with bpy.data.libraries.load(kitchen_blend, link=False) as (src, dst):
        dst.materials = ["Brick wall", "Natural Wood", "Wood.001"]
    
    marble_mat = carrara_marble_material("CarraraWhiteMarble")
    brick_mat = make_subway_tile_material()
    wood_cab_mat = bpy.data.materials.get("Natural Wood") or bpy.data.materials.get("Wood.001")
    wall_mat = wall_plaster_material()
    trim_metal_mat = material_principled("DarkBronzeTrim", (0.08, 0.07, 0.06), roughness=0.25, metallic=0.92)

    # 2. Append 3D assets: ceramic vessels, carafe (NO green machine, NO black faucet, NO books)
    kitchen_targets = [
        "Circle.016", "Circle.017", "Circle.018",
    ]
    with bpy.data.libraries.load(kitchen_blend, link=False) as (src, dst):
        dst.objects = [o for o in kitchen_targets if o in src.objects]
    
    appended = {}
    for obj in dst.objects:
        if obj:
            scene.collection.objects.link(obj)
            appended[obj.name] = obj

    # Append Wooden Cutting Board
    with bpy.data.libraries.load(board_blend, link=False) as (src, dst):
        dst.objects = ["Wooden Cutting Board"]
    for obj in dst.objects:
        if obj:
            scene.collection.objects.link(obj)
            appended["Wooden Cutting Board"] = obj

    # Append Red Apple
    with bpy.data.libraries.load(apple_blend, link=False) as (src, dst):
        dst.objects = ["RedXx"]
    for obj in dst.objects:
        if obj:
            scene.collection.objects.link(obj)
            appended["RedXx"] = obj

    # 3. KITCHEN ISLAND / COUNTER STRUCTURE
    counter_top_z = 0.005
    slab_thickness = 0.035
    counter_center_y = 0.63
    counter_width = 3.60
    counter_depth = 0.46

    # Carrara White Marble countertop slab
    add_box(
        "KitchenCounterMarbleSlab",
        (-0.20, counter_center_y, counter_top_z - slab_thickness / 2.0),
        (counter_width, counter_depth, slab_thickness),
        marble_mat,
        bevel=0.003
    )

    # Architectural Bronze Trim Divider separating dining table from marble island
    add_box(
        "TableIslandDividerTrim",
        (-0.20, 0.402, counter_top_z + 0.006),
        (counter_width, 0.016, 0.014),
        trim_metal_mat,
        bevel=0.002
    )

    # Base cabinetry below marble counter
    cab_height = 0.72
    cab_depth = counter_depth - 0.04
    add_box(
        "KitchenBaseCabinets",
        (-0.20, counter_center_y + 0.02, counter_top_z - slab_thickness - cab_height / 2.0),
        (counter_width, cab_depth, cab_height),
        wood_cab_mat,
        bevel=0.004
    )

    # 4. KITCHEN BACK WALL & BACKSPLASH
    back_wall_y = 0.86
    backsplash_height = 0.375
    add_box(
        "KitchenTileBacksplash",
        (-0.20, back_wall_y + 0.015, counter_top_z + backsplash_height / 2.0),
        (counter_width, 0.03, backsplash_height),
        brick_mat
    )

    add_box(
        "KitchenUpperWall",
        (-0.20, back_wall_y + 0.015, counter_top_z + backsplash_height + 0.60),
        (counter_width, 0.03, 1.20),
        wall_mat
    )

    add_box(
        "UpperKitchenShelf",
        (-0.20, back_wall_y - 0.08, 0.42),
        (counter_width - 0.40, 0.18, 0.03),
        wood_cab_mat,
        bevel=0.003
    )

    add_box("KitchenLeftWall", (-1.80, 0.0, 0.50), (0.06, 3.60, 2.20), wall_mat)

    # 5. SYMMETRICAL & SPREAD OUT COUNTERTOP LAYOUT
    # Center axis of camera/cup: screen_x ≈ 640 corresponds to world x ≈ -0.39 at y = 0.60

    # (A) CENTER GROUP: Round Wooden Cutting Board + Red Apple (centered at screen X = 639)
    board = appended.get("Wooden Cutting Board")
    if board:
        board.location = (-0.39, 0.60, counter_top_z + 0.012)
        board.scale = (0.44, 0.44, 0.44)
        board.rotation_euler = (0.0, 0.0, math.radians(18.0))

    apple = appended.get("RedXx")
    if apple:
        apple.location = (-0.39, 0.60, 0.0422)
        apple.scale = (0.88, 0.88, 0.88)
        apple.rotation_euler = (math.radians(15.0), math.radians(-10.0), math.radians(60.0))
        # Enhance apple organic realism: eliminate fake metallic, add subsurface scattering and waxy cuticle
        for m in apple.data.materials:
            if m and m.use_nodes:
                bsdf = m.node_tree.nodes.get("Principled BSDF")
                if bsdf and m.name == "AppleSkin":
                    set_socket(bsdf, "Metallic", 0.0)
                    set_socket(bsdf, "Roughness", 0.28)
                    set_socket(bsdf, "Subsurface Weight", 0.22)
                    set_socket(bsdf, "Subsurface", 0.22)
                    set_socket(bsdf, "Subsurface Radius", (0.04, 0.015, 0.008))
                    set_socket(bsdf, "Subsurface Scale", 0.02)
                    set_socket(bsdf, "Coat Weight", 0.45)
                    set_socket(bsdf, "Coat Roughness", 0.06)

    # (B) LEFT GROUP: Ceramic Vase + Ceramic Canister with lid (centered around screen X ≈ 385)
    c18 = appended.get("Circle.018")  # Ceramic Pitcher / Vase
    if c18:
        c18.location = (-0.78, 0.64, counter_top_z + 0.001)
        c18.scale = (0.68, 0.68, 0.68)
        c18.rotation_euler = (0.0, 0.0, math.radians(25.0))

    c17 = appended.get("Circle.017")  # Ceramic Canister with Lid
    if c17:
        c17.location = (-0.68, 0.55, counter_top_z + 0.001)
        c17.scale = (0.75, 0.75, 0.75)
        c17.rotation_euler = (0.0, 0.0, math.radians(-15.0))

    # (C) RIGHT GROUP: Glass Cup (Books deleted per user request, cup repositioned for symmetry)
    c16 = appended.get("Circle.016")  # Clear Glass Carafe / Cup
    if c16:
        c16.location = (-0.07, 0.58, counter_top_z + 0.001)
        c16.scale = (0.44, 0.44, 0.44)
        c16.rotation_euler = (0.0, 0.0, math.radians(-20.0))
        # Assign real physical glass material with true transmission and realistic caustics
        assign_material(c16, glass_material("IslandGlassCarafeMat"))

def build_environment():
    scene = bpy.context.scene
    world = bpy.data.worlds.new("IndoorKitchenHDRI") if not bpy.data.worlds else bpy.data.worlds[0]
    scene.world = world
    world.use_nodes = True
    wnodes, wlinks = world.node_tree.nodes, world.node_tree.links
    wnodes.clear()
    w_out = wnodes.new("ShaderNodeOutputWorld")
    w_bg = wnodes.new("ShaderNodeBackground")
    if HDRI_PATH.is_file():
        w_tc = wnodes.new("ShaderNodeTexCoord")
        w_map = wnodes.new("ShaderNodeMapping")
        w_map.inputs["Rotation"].default_value = (0.0, 0.0, math.radians(-38.0))
        w_env = wnodes.new("ShaderNodeTexEnvironment")
        w_env.image = bpy.data.images.load(str(HDRI_PATH), check_existing=True)
        # Gentle indoor ambient level so directional lights create rich contrast and shadows
        w_bg.inputs["Strength"].default_value = 0.14
        wlinks.new(w_tc.outputs["Generated"], w_map.inputs["Vector"])
        wlinks.new(w_map.outputs["Vector"], w_env.inputs["Vector"])
        wlinks.new(w_env.outputs["Color"], w_bg.inputs["Color"])
    else:
        w_bg.inputs["Color"].default_value = (0.18, 0.19, 0.21, 1.0)
        w_bg.inputs["Strength"].default_value = 0.20
    wlinks.new(w_bg.outputs["Background"], w_out.inputs["Surface"])

    wood = wood_table_material()
    
    # SOLID DINING TABLE IN FOREGROUND: covers the entire camera field of view in front and left!
    TABLE_SIZE = (2.60, 1.00, 0.065)
    tz = TABLE_SIZE[2]
    add_box("DiningTable", (-0.20, -0.10, -tz / 2.0), TABLE_SIZE, wood, bevel=0.006)

    build_folded_linen()
    build_authentic_kitchen_environment()

    # === CINEMATIC ARCHITECTURAL LIGHTING & SHADOW CRAFTING ===
    # 1. Warm Directional Morning Sunlight (Primary Key Light)
    # Refined angular size and boosted power for crisp contact shadows + warm golden raking light
    sun_data = bpy.data.lights.new("MorningSunWindow", "AREA")
    sun_data.shape = "RECTANGLE"
    sun_data.size = 0.28
    sun_data.size_y = 0.40
    sun_data.energy = 52.0
    sun_data.color = (1.0, 0.93, 0.82)
    sun = bpy.data.objects.new("MorningSunWindow", sun_data)
    scene.collection.objects.link(sun)
    sun.location = (-1.35, -0.38, 1.15)
    look_at(sun, (-0.08, 0.12, 0.02))

    # 2. Cool Sky Daylight Portal (Secondary Soft Fill from window opening)
    # Generates photographic color contrast: warm sunlit highlights vs cool sky-filled shadow penumbras
    sky_data = bpy.data.lights.new("SkyDaylightWindow", "AREA")
    sky_data.shape = "RECTANGLE"
    sky_data.size = 1.20
    sky_data.size_y = 1.40
    sky_data.energy = 10.0
    sky_data.color = (0.78, 0.88, 1.0)
    sky_data.color = (0.82, 0.89, 1.0)  # Cool daylight sky fill (~6500K)
    sky = bpy.data.objects.new("SkyDaylightWindow", sky_data)
    scene.collection.objects.link(sky)
    sky.location = (-1.35, -0.30, 1.15)
    look_at(sky, (-0.15, 0.20, 0.08))

    # 3. Architectural Under-Shelf Warm LED Strip (Linear task light grazing backsplash)
    # Brings out brick mortar relief, warms up back wall, rims the cutting board and vessels
    led_data = bpy.data.lights.new("KitchenUnderShelfLED", "AREA")
    led_data.shape = "RECTANGLE"
    led_data.size = 2.80
    led_data.size_y = 0.06
    led_data.energy = 6.0
    led_data.color = (1.0, 0.86, 0.70)
    led_data.color = (1.0, 0.88, 0.74)  # Cozy warm LED strip (2900K)
    led = bpy.data.objects.new("KitchenUnderShelfLED", led_data)
    scene.collection.objects.link(led)
    led.location = (-0.20, 0.80, 0.405)
    look_at(led, (-0.20, 0.85, 0.05))

    # 4. KitchenAmbientBounce deleted per VarA calibration to preserve deep contact shadows

    # 5. Fluid Splash & Mug Rim Glint Accent
    rim_data = bpy.data.lights.new("SplashRimLight", "AREA")
    rim_data.shape = "RECTANGLE"
    rim_data.size = 0.70
    rim_data.size_y = 0.28
    rim_data.energy = 4.0
    rim_data.color = (0.96, 0.985, 1.0)
    rim = bpy.data.objects.new("SplashRimLight", rim_data)
    scene.collection.objects.link(rim)
    rim.location = (-0.18, 0.78, 0.58)
    look_at(rim, (0.0, 0.0, 0.04))

    # Camera setup
    camera_data = bpy.data.cameras.new("HeroCamera")
    camera = bpy.data.objects.new("HeroCamera", camera_data)
    scene.collection.objects.link(camera)
    camera.location = layout.CAMERA_LOCATION
    camera_data.lens = layout.CAMERA_LENS_MM
    camera_data.sensor_width = layout.CAMERA_SENSOR_MM
    look_at(camera, layout.CAMERA_TARGET)
    
    # No depth of field: the whole table stays in focus.
    camera_data.dof.use_dof = False
    scene.camera = camera

    scene.render.engine = "CYCLES"
    prefs = bpy.context.preferences.addons["cycles"].preferences
    has_optix = False
    try:
        prefs.compute_device_type = "OPTIX"
        prefs.get_devices()
        has_optix = any(d.type == "OPTIX" for d in prefs.devices)
    except Exception:
        has_optix = False
    if not has_optix:
        prefs.compute_device_type = "CUDA"
        prefs.get_devices()
    for dev in prefs.devices:
        dev.use = (dev.type in ("OPTIX", "CUDA"))
    scene.cycles.device = "GPU"

    scene.cycles.samples = samples
    scene.cycles.seed = 0
    scene.cycles.use_denoising = True
    scene.cycles.denoising_input_passes = "RGB_ALBEDO_NORMAL"
    scene.cycles.max_bounces = 12
    scene.cycles.glossy_bounces = 8
    scene.cycles.transmission_bounces = 12
    scene.cycles.transparent_max_bounces = 12
    scene.cycles.volume_bounces = 2
    scene.cycles.filter_glossy = 0.25
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    scene.render.resolution_percentage = 100
    scene.render.fps = 24
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"
    scene.render.film_transparent = False
    scene.render.use_motion_blur = True
    scene.render.motion_blur_shutter = 0.20
    scene.view_settings.view_transform = "AgX"
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = -0.05

def mesh_from(name, vertices, triangles, mat, vertex_normals=None, loop_normals=None, velocity=None):
    mesh = bpy.data.meshes.new(name)
    if not len(vertices) or not len(triangles):
        mesh.materials.append(mat)
        return mesh
    mesh.vertices.add(len(vertices))
    mesh.vertices.foreach_set("co", np.ascontiguousarray(vertices, np.float32).ravel())
    if velocity is not None and len(velocity) == len(vertices):
        mesh.attributes.new("velocity", "FLOAT_VECTOR", "POINT").data.foreach_set(
            "vector", np.ascontiguousarray(velocity, np.float32).ravel()
        )
    mesh.loops.add(triangles.size)
    mesh.loops.foreach_set("vertex_index", np.ascontiguousarray(triangles, np.int32).ravel())
    mesh.polygons.add(len(triangles))
    mesh.polygons.foreach_set("loop_start", np.arange(0, triangles.size, 3, dtype=np.int32))
    mesh.polygons.foreach_set("loop_total", np.full(len(triangles), 3, dtype=np.int32))
    mesh.polygons.foreach_set("use_smooth", np.ones(len(triangles), dtype=np.bool_))
    mesh.update(calc_edges=True)
    if loop_normals is not None and len(loop_normals) == triangles.size:
        mesh.normals_split_custom_set(np.asarray(loop_normals, np.float32).tolist())
    elif vertex_normals is not None and len(vertex_normals) == len(vertices):
        mesh.normals_split_custom_set_from_vertices(np.asarray(vertex_normals, np.float32).tolist())
    mesh.materials.append(mat)
    return mesh

def swap(obj, mesh):
    old = obj.data
    obj.data = mesh
    if old.users == 0:
        bpy.data.meshes.remove(old)

def load_water(f):
    with np.load(surf / f"water_{f:04d}.npz") as z:
        swap(
            water,
            mesh_from(
                f"water_{f:04d}",
                z["vertices"],
                z["triangles"],
                bulk_water_mat,
                vertex_normals=z["normals"],
                velocity=z["velocity"],
            ),
        )
        dv, dt = z["drops_vertices"], z["drops_triangles"]
        dln = z["drops_loop_normals"] if "drops_loop_normals" in z else None
        dvel = z["drops_velocity"] if "drops_velocity" in z else np.zeros_like(dv)
        swap(
            drops,
            mesh_from(
                f"drops_{f:04d}",
                dv,
                dt,
                drop_water_mat,
                loop_normals=dln,
                velocity=dvel,
            ),
        )

hero = load_hero_and_dishes()
build_environment()

bulk_water_mat = water_material(
    "PCVE_ClearWater_Bulk",
    roughness=0.002,
    shadow_min=0.20,
    shadow_max=0.65,
    vol_color=(0.75, 0.92, 0.99, 1.0),
    vol_density=1.6,
)
drop_water_mat = water_material(
    "PCVE_ClearWater_Drops",
    roughness=0.002,
    shadow_min=0.20,
    shadow_max=0.65,
    vol_color=(0.75, 0.92, 0.99, 1.0),
    vol_density=1.2,
)

water = bpy.data.objects.new("SimulatedWater", bpy.data.meshes.new("SimulatedWater"))
bpy.context.scene.collection.objects.link(water)
drops = bpy.data.objects.new("SimulatedDroplets", bpy.data.meshes.new("SimulatedDroplets"))
bpy.context.scene.collection.objects.link(drops)

# Load cup poses
poses = {int(k): v for k, v in json.load(open(surf / "cup_poses.json"))["poses"].items()}
n_frames = max(poses)
bpy.context.scene.frame_start, bpy.context.scene.frame_end = 1, n_frames
for f in range(1, n_frames + 1):
    pose = poses[f]
    hero.location = pose["pos"]
    hero.rotation_quaternion = Quaternion(pose["quat_wxyz"])
    hero.keyframe_insert("location", frame=f)
    hero.keyframe_insert("rotation_quaternion", frame=f)
if hero.animation_data and hero.animation_data.action:
    for curve in hero.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "LINEAR"

# Set AgX neutral tone
bpy.context.scene.view_settings.view_transform = "AgX"
bpy.context.scene.view_settings.look = "None"
bpy.context.scene.view_settings.exposure = 0.0

render_list = frames if frames is not None else list(range(1, n_frames + 1))
print(f"Starting render for {len(render_list)} frames: {render_list[:5]} ...")

for f_idx in render_list:
    target_path = out_dir / f"frame_{f_idx:04d}.png"
    if target_path.exists() and target_path.stat().st_size > 50000:
        print(f"Frame {f_idx:04d} already rendered, skipping.", flush=True)
        continue
    bpy.context.scene.frame_set(f_idx)
    load_water(f_idx)
    bpy.context.scene.render.filepath = str(target_path)
    print(f"Rendering frame {f_idx:04d} -> {target_path} ...", flush=True)
    bpy.ops.render.render(write_still=True)
    print(f"RENDERED {f_idx}", flush=True)

print("All requested frames rendered successfully!")
