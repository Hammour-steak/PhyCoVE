"""Selective: chairs/turf/rails, original dark panel and white print.

No import of earlier passes, no geometry/camera/light changes, no actual pixel/image edits.
All literal assignments explicitly detach an old socket link. CPU tests may
import this module and test assignment using small fake node sockets, not bpy.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


PARAMETERS = {"chair_palette": [[.010,.035,.061,1], [.025,.080,.132,1], [.053,.125,.183,1]],
    "chair_roughness": [.31,.52], "leaf_roughness": [.30,.58], "leaf_macro_gain": [.90,1.08],
    "canopy_macro_gain": [.93,1.07], "optional_panel_charcoal_linear_rgba": [.035,.065,.075,1],
    "sun_and_fill_and_exposure_change": False, "actual_grass_photo_tile_m": 2.51,
    "concrete_and_print_materials_unchanged": True}


def literal(tree, socket, value):
    """No ineffective default_value write behind an existing driver link."""
    removed = len(socket.links)
    for edge in tuple(socket.links):
        tree.links.remove(edge)
    socket.default_value = value
    return removed


def wire(tree, value, socket):
    if hasattr(value, "node"):
        for edge in tuple(socket.links):
            tree.links.remove(edge)
        tree.links.new(value,socket)
    else:
        literal(tree,socket,value)


def value(socket):
    if socket.is_linked:
        return socket.links[0].from_socket
    original = socket.default_value
    return original[:] if hasattr(original,"__len__") else original


def node(tree, kind, **properties):
    result=tree.nodes.new(kind)
    for name,data in properties.items():setattr(result,name,data)
    return result


def scalar(tree, op, a, b=None):
    result=node(tree,"ShaderNodeMath",operation=op)
    wire(tree,a,result.inputs[0])
    if b is not None:wire(tree,b,result.inputs[1])
    return result.outputs[0]


def mix(tree,a,b,factor,mode="MIX"):
    result=node(tree,"ShaderNodeMixRGB",blend_type=mode)
    for index,data in enumerate((factor,a,b)):wire(tree,data,result.inputs[index])
    return result.outputs[0]


def noise(tree,pos,frequency,detail=2):
    result=node(tree,"ShaderNodeTexNoise")
    wire(tree,pos,result.inputs["Vector"])
    for name,data in (("Scale",frequency),("Detail",detail),("Roughness",.62)):literal(tree,result.inputs[name],data)
    return result.outputs["Fac"]


def ranged(tree,fac,low,high):return scalar(tree,"ADD",low,scalar(tree,"MULTIPLY",fac,high-low))


def kind_for(name,panel_mode):
    for prefix,kind in (("moulded polypropylene chairs |","chairs"),
                        ("living grass leaves |","leaves"),
                        ("continuous living canopy substrate |","canopy"),
                        ("maintained metal coating | galvanized guardrails","rails")):
        if name.startswith(prefix):return kind
    if panel_mode=="warm_charcoal" and name.startswith("maintained printed pitchside panel |"):
        return "panel"
    return None


def _signature(mat):
    tree=mat.node_tree
    record={"nodes":[{"name":n.name,"type":n.bl_idname,
        "inputs":[(s.identifier,str(s.default_value)) for s in n.inputs if hasattr(s,"default_value")]}
        for n in tree.nodes],"links":[(l.from_node.name,l.from_socket.identifier,l.to_node.name,l.to_socket.identifier) for l in tree.links]}
    return hashlib.sha256(json.dumps(record,sort_keys=True).encode()).hexdigest()


def replace_references(bpy,mapping):
    """Unlike the old helper, include DATA slots on FONT/CURVE objects."""
    uses=[]
    for collection in (bpy.data.meshes,bpy.data.curves):
        for data in collection:
            for index,mat in enumerate(data.materials):
                if mat in mapping:
                    data.materials[index]=mapping[mat]
                    uses.append({"data":data.name,"slot":index,"material":mapping[mat].name})
    for obj in bpy.data.objects:
        for slot in obj.material_slots:
            if slot.link=="OBJECT" and slot.material in mapping:
                slot.material=mapping[slot.material]
    for group in bpy.data.node_groups:
        for n in group.nodes:
            for socket in n.inputs:
                if socket.type=="MATERIAL" and socket.default_value in mapping:
                    literal(group,socket,mapping[socket.default_value])
    return uses


def _revise(original,kind):
    result=original.copy();result.name=kind+" | "+original.name;result["selective_common_surface"]=True
    tree=result.node_tree
    surfaces=[n for n in tree.nodes if n.bl_idname=="ShaderNodeBsdfPrincipled"]
    if len(surfaces)!=1:raise RuntimeError("Unknown actual material surface chain: "+original.name)
    surface=surfaces[0]
    geo=node(tree,"ShaderNodeNewGeometry");pos=geo.outputs["Position"]
    old=value(surface.inputs["Base Color"])
    if kind=="chairs":
        attr=node(tree,"ShaderNodeAttribute",attribute_name="component_tone")
        palette=node(tree,"ShaderNodeValToRGB")
        palette.color_ramp.elements[0].color=PARAMETERS["chair_palette"][0]
        palette.color_ramp.elements[1].color=PARAMETERS["chair_palette"][2]
        palette.color_ramp.elements.new(.5).color=PARAMETERS["chair_palette"][1]
        wire(tree,attr.outputs["Fac"],palette.inputs[0])
        normal=node(tree,"ShaderNodeSeparateXYZ");wire(tree,geo.outputs["Normal"],normal.inputs[0])
        dust=scalar(tree,"MULTIPLY",scalar(tree,"POWER",scalar(tree,"MAXIMUM",0,normal.outputs["Z"]),3),
                    ranged(tree,noise(tree,pos,.2,3),.018,.07))
        wire(tree,mix(tree,palette.outputs["Color"],(.13,.15,.14,1),dust),surface.inputs["Base Color"])
        wire(tree,ranged(tree,noise(tree,pos,2.),*PARAMETERS["chair_roughness"]),surface.inputs["Roughness"])
        literal(tree,surface.inputs["Coat Weight"],.018);literal(tree,surface.inputs["IOR"],1.49)
    elif kind in {"leaves","canopy"}:
        bounds=PARAMETERS["leaf_macro_gain" if kind=="leaves" else "canopy_macro_gain"]
        pigment=mix(tree,old,ranged(tree,noise(tree,pos,.27,3),*bounds),1,"MULTIPLY")
        wire(tree,pigment,surface.inputs["Base Color"])
        if kind=="leaves":
            wire(tree,ranged(tree,noise(tree,pos,64),*PARAMETERS["leaf_roughness"]),surface.inputs["Roughness"])
            literal(tree,surface.inputs["Sheen Weight"],.045)
            for n in tree.nodes:
                if n.bl_idname=="ShaderNodeBsdfTranslucent":wire(tree,pigment,n.inputs[0])
    elif kind=="rails":
        wire(tree,ranged(tree,noise(tree,pos,75),.29,.43),surface.inputs["Roughness"])
        literal(tree,surface.inputs["Metallic"],.85)
        # No unverified anisotropy socket; an earlier pass failed on that Blender API.
    elif kind=="panel":
        literal(tree,surface.inputs["Base Color"],PARAMETERS["optional_panel_charcoal_linear_rgba"])
    return result,{"original":original.name,"new":result.name,"kind":kind,
        "old_image_and_normal_nodes_preserved":True,"literal_assignment_unlinks_prior_input":True,
        "actual_base_color_linked_after":surface.inputs["Base Color"].is_linked,
        "actual_base_color_default_after":list(surface.inputs["Base Color"].default_value),
        "true_displacement_or_geometry_change":False}


def apply_common_surfaces(*,look,expect_net_present,panel_mode="unchanged"):
    if panel_mode not in {"unchanged","warm_charcoal"}:raise ValueError("Explicit shared panel mode required")
    import bpy
    if any(m.get("selective_common_surface") for m in bpy.data.materials):raise RuntimeError("Do not apply twice")
    before=look.protected_state()
    panels={m:_signature(m) for m in bpy.data.materials if m.name.startswith((
        "maintained printed pitchside panel |","daylight non-emissive white print","restrained turquoise print accent"))}
    nets=[o for o in bpy.context.scene.objects if o.name.startswith("visible net =") and not o.hide_render]
    if len(nets)!=int(expect_net_present):raise RuntimeError("Actual cache/net presence mismatch")
    net_before=look.evaluated_net_digest(nets[0]) if nets else None
    mapping,records,seen={},[],set()
    for mat in list(bpy.data.materials):
        kind=kind_for(mat.name,panel_mode)
        if kind:
            mapping[mat],record=_revise(mat,kind);records.append(record);seen.add(kind)
    required={"chairs","leaves","canopy","rails"}|({"panel"} if panel_mode=="warm_charcoal" else set())
    if seen!=required:raise RuntimeError("Missing actual material kinds: "+str(required-seen))
    uses=replace_references(bpy,mapping);bpy.context.view_layer.update()
    after=look.protected_state()
    net_after=look.evaluated_net_digest(nets[0]) if nets else None
    if before!=after or net_before!=net_after:raise RuntimeError("changed actor/fixture geometry, animation, camera, light or net envelope")
    if any(_signature(mat)!=digest for mat,digest in panels.items()):raise RuntimeError("Original board/print node data were overwritten")
    return {"parameters":PARAMETERS,"panel_mode":panel_mode,"materials":records,"material_uses":uses,
        "protected_before_sha256":hashlib.sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
        "protected_after_sha256":hashlib.sha256(json.dumps(after,sort_keys=True).encode()).hexdigest(),
        "net_evaluated_before_sha256":net_before,"net_evaluated_after_sha256":net_after,
        "original_panel_and_white_font_data_unmodified":True,"geometry_camera_light_unchanged":True,
        "real_pbr_nodes_preserved_no_image_pixel_edits":True,"all_cases_same_recipe_required":True,
        "movie_grade_material_calibration_or_visual_pass":False}
