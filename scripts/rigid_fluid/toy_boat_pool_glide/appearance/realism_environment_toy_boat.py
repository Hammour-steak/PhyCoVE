"""Second backyard look: measured props, textured cedar, varied turf, softer PVC highlights."""
import importlib.util
import math
from pathlib import Path

import bpy
from mathutils import Matrix, Vector


def load_previous():
    spec = importlib.util.spec_from_file_location("toy_boat_backyard", (Path(__file__).parents[1] / "appearance/garden_environment_toy_boat.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def varied_lawn():
    base = bpy.data.objects["PCVE_LawnHair"]
    settings = base.particle_systems[0].settings
    settings.length_random = 0.70
    settings.roughness_1 = 0.007
    settings.roughness_2 = 0.009
    settings.roughness_endpoint = 0.003
    mat = base.data.materials[0]
    n, l = mat.node_tree.nodes, mat.node_tree.links
    bsdf = n.get("Principled BSDF")
    bsdf.inputs["Roughness"].default_value = 0.70
    geo = n.new("ShaderNodeNewGeometry")
    noise = n.new("ShaderNodeTexNoise")
    noise.inputs["Scale"].default_value = 2.3
    noise.inputs["Detail"].default_value = 2.5
    l.new(geo.outputs["Position"], noise.inputs["Vector"])
    hair = next(x for x in n if x.type == "HAIR_INFO")
    variation = n.new("ShaderNodeMath")
    variation.operation = "MULTIPLY_ADD"
    variation.inputs[1].default_value = 0.36
    l.new(hair.outputs["Random"], variation.inputs[0])
    l.new(noise.outputs["Fac"], variation.inputs[2])
    ramp = n.new("ShaderNodeValToRGB")
    ramp.color_ramp.elements[0].position = 0.15
    ramp.color_ramp.elements[0].color = (0.022, 0.055, 0.007, 1)
    ramp.color_ramp.elements[1].position = 0.95
    ramp.color_ramp.elements[1].color = (0.24, 0.30, 0.072, 1)
    ramp.color_ramp.elements.new(0.62).color = (0.075, 0.145, 0.016, 1)
    l.new(variation.outputs[0], ramp.inputs["Fac"])
    l.new(ramp.outputs["Color"], bsdf.inputs["Base Color"])
    for node in n:
        if node.type == "BSDF_TRANSLUCENT":
            l.new(ramp.outputs["Color"], node.inputs["Color"])
    # Broken patches of flattened grass around the pool's footprint, rather than a perfect carpet.
    group = base.vertex_groups.get("density")
    for i, vert in enumerate(base.data.vertices):
        x, y, _ = vert.co
        radius = math.hypot(x, y)
        if 0.94 < radius < 1.30:
            patch = 0.65 + 0.18 * math.sin(x * 17 + y * 9) + 0.12 * math.sin(y * 29)
            group.add([i], max(0.22, patch), "REPLACE")
    return {"blade_length_variation":0.70, "patch_scale_m":0.43, "palette":"olive, green, dry tips"}


def textured_fence(renderer):
    path = renderer.ASSETS / "blenderkit/wood_board_cc0/wood_board.blend"
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.materials = ["Wood Board"]
    material = target.materials[0]
    material.name = "Backyard_photographic_wood"
    n, l = material.node_tree.nodes, material.node_tree.links
    bsdf = next(x for x in n if x.type == "BSDF_PRINCIPLED")
    # Keep the image grain, but weather it toward a quiet grey-brown.
    socket = bsdf.inputs["Base Color"]
    if socket.links:
        original = socket.links[0].from_socket
        hue = n.new("ShaderNodeHueSaturation")
        hue.inputs["Saturation"].default_value = 0.72
        hue.inputs["Value"].default_value = 0.80
        l.new(original, hue.inputs["Color"])
        tint = n.new("ShaderNodeMixRGB")
        tint.blend_type = "MULTIPLY"
        tint.inputs[0].default_value = 0.35
        tint.inputs[2].default_value = (0.70, 0.60, 0.45, 1)
        l.new(hue.outputs["Color"], tint.inputs[1])
        l.new(tint.outputs["Color"], socket)
    for node in n:
        if node.type == "NORMAL_MAP":
            node.inputs["Strength"].default_value = 0.28
        if node.type == "MAPPING":
            node.inputs["Scale"].default_value.x *= 2.6
        if node.type == "DISPLACEMENT":
            node.inputs["Scale"].default_value = 0.0
    for obj in bpy.data.objects:
        if obj.name.startswith("Garden_fence_"):
            obj.data.materials.clear()
            obj.data.materials.append(material)
    return {"source":str(path.relative_to(renderer.ROOT)),"license":"CC0, source manifest retained"}


def import_blend_objects(path, names, collection_name):
    with bpy.data.libraries.load(str(path), link=False) as (source, target):
        target.objects = names
    collection = bpy.data.collections.new(collection_name)
    bpy.context.scene.collection.children.link(collection)
    for obj in target.objects:
        collection.objects.link(obj)
    return target.objects


def normalize(objects, position, height=None, length=None, rotation=0):
    bpy.context.view_layer.update()
    points = [o.matrix_world @ Vector(v) for o in objects if o.type == "MESH" for v in o.bound_box]
    low = Vector([min(p[i] for p in points) for i in range(3)])
    high = Vector([max(p[i] for p in points) for i in range(3)])
    scale = height / (high.z-low.z) if height else length / max(high-low)
    transform = (Matrix.Translation(position) @ Matrix.Rotation(rotation,4,"Z")
                 @ Matrix.Diagonal((scale,scale,scale,1))
                 @ Matrix.Translation((-(low.x+high.x)/2,-(low.y+high.y)/2,-low.z)))
    # Freeze world matrices before unparenting to avoid applying group transforms twice.
    matrices = [(o,o.matrix_world.copy()) for o in objects]
    for obj, world in matrices:
        obj.parent = None
        obj.matrix_world = transform @ world


def hose(renderer):
    material = bpy.data.materials.new("Garden_hose_sage_rubber")
    material.diffuse_color = (0.075,0.13,0.065,1)
    material.use_nodes = True
    bsdf=material.node_tree.nodes.get("Principled BSDF")
    bsdf.inputs["Base Color"].default_value=(0.075,0.13,0.065,1)
    bsdf.inputs["Roughness"].default_value=0.62
    curve=bpy.data.curves.new("Garden_hose_coil","CURVE")
    curve.dimensions="3D"
    curve.bevel_depth=0.008
    curve.bevel_resolution=3
    spline=curve.splines.new("POLY")
    points=[]
    for i in range(150):
        t=i/149
        a=t*math.pi*4.3
        r=0.20+0.045*t
        points.append((1.20+math.cos(a)*r,0.45+math.sin(a)*r,0.012+0.004*math.sin(a)))
    # An uncoiled length leads toward the spray nozzle.
    end=Vector(points[-1])
    target=Vector((1.00,0.95,0.014))
    for i in range(1,25):
        t=i/24
        p=end.lerp(target,t)
        p.x+=0.06*math.sin(math.pi*t)
        points.append(tuple(p))
    spline.points.add(len(points)-1)
    for p,co in zip(spline.points,points): p.co=(*co,1)
    obj=bpy.data.objects.new("Garden_hose",curve)
    bpy.context.scene.collection.objects.link(obj)
    obj.data.materials.append(material)
    asset=renderer.ASSETS/"blenderkit/garden_hose_spray_nozzle/garden_hose_spray_nozzle.blend"
    objects=import_blend_objects(asset,["Garden Hose Spray Nozzle","FAUCET"],"Garden_nozzle_asset")
    normalize(objects,(1.00,1.01,0.008),length=0.15,rotation=1.2)
    return {"hose_diameter_m":0.016,"nozzle_long_edge_m":0.15,"nozzle_source":str(asset.relative_to(renderer.ROOT))}


def soften_pvc():
    # Only shader changes: the original visual mesh and collision dimensions stay fixed.
    pool=bpy.data.objects.get("PCVE_Pool")
    mats={slot.material for obj in pool.children_recursive if obj.type=="MESH" for slot in obj.material_slots if slot.material}
    for mat in mats:
        n,l=mat.node_tree.nodes,mat.node_tree.links
        bsdf=next((node for node in n if node.type=="BSDF_PRINCIPLED"),None)
        if not bsdf: continue
        bsdf.inputs["Coat Weight"].default_value=0.16
        bsdf.inputs["Coat Roughness"].default_value=0.24
        coord=n.new("ShaderNodeNewGeometry")
        noise=n.new("ShaderNodeTexNoise")
        noise.inputs["Scale"].default_value=620
        noise.inputs["Detail"].default_value=2
        l.new(coord.outputs["Position"],noise.inputs["Vector"])
        rough=n.new("ShaderNodeMapRange")
        rough.inputs["To Min"].default_value=0.24
        rough.inputs["To Max"].default_value=0.36
        l.new(noise.outputs["Fac"],rough.inputs["Value"])
        l.new(rough.outputs["Result"],bsdf.inputs["Roughness"])
        bump=n.new("ShaderNodeBump")
        bump.inputs["Strength"].default_value=0.14
        bump.inputs["Distance"].default_value=0.000045
        if bsdf.inputs["Normal"].links:
            l.new(bsdf.inputs["Normal"].links[0].from_socket,bump.inputs["Normal"])
        l.new(noise.outputs["Fac"],bump.inputs["Height"])
        l.new(bump.outputs["Normal"],bsdf.inputs["Normal"])
        color=bsdf.inputs["Base Color"]
        if color.links:
            original=color.links[0].from_socket
            hue=n.new("ShaderNodeHueSaturation")
            hue.inputs["Saturation"].default_value=0.93
            hue.inputs["Value"].default_value=0.90
            l.new(original,hue.inputs["Color"])
            l.new(hue.outputs["Color"],color)
    return {"roughness":[0.24,0.36],"coat_weight":0.16,"saturation":0.93,"micro_bump_m":0.000045}


def build(scene,renderer):
    previous=load_previous()
    record=previous.build(scene,renderer)
    record["lawn_detail"]=varied_lawn()
    record["fence_material"]=textured_fence(renderer)
    record["garden_hose"]=hose(renderer)
    path=renderer.ASSETS/"blenderkit/summer_garden/summer_garden.blend"
    trees=import_blend_objects(path,["tree.040"],"Garden_shade_tree")
    normalize(trees,(-3.4,3.9,0),height=4.2,rotation=0.55)
    record["shade_tree"]={"source":str(path.relative_to(renderer.ROOT)),"height_m":4.2,"position_m":[-3.4,3.9,0]}
    renderer.CAMERAS["kneeling_rim"]=((0.23,-1.30,0.72),(0,0.055,0.185),28)
    record["version"]="backyard_realism"
    record["camera"]="Slightly wider framing, unchanged 28 mm perspective; more grass at pool edge"
    return record
