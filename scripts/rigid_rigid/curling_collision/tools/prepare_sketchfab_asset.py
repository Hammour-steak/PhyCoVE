"""Normalize the user-downloaded Sketchfab GLB, preserving its embedded PBR maps."""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import bpy
from mathutils import Matrix, Vector

COLLECTION_NAME = "Curling stone / FilinMX / normalized SI"
SOURCE_SHA256 = "4395792301a6b11ef9e5c27a7aea85d489cb84335f87155324cd19d1818e4112"

def bounds(objects):
    points = [o.matrix_world@Vector(v) for o in objects for v in o.bound_box]
    lower = [min(p[i] for p in points) for i in range(3)]
    upper = [max(p[i] for p in points) for i in range(3)]
    return lower,upper

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input",type=Path,required=True)
    parser.add_argument("--out",type=Path,required=True)
    parser.add_argument("--diameter",type=float,default=.29)
    parser.add_argument("--yaw-degrees",type=float,default=0)
    args = parser.parse_args(sys.argv[sys.argv.index("--")+1:])
    digest = hashlib.sha256(args.input.read_bytes()).hexdigest()
    if digest!=SOURCE_SHA256:
        raise ValueError("Unexpected source GLB; inspect and register its provenance before use")
    bpy.ops.wm.read_factory_settings(use_empty=True)
    bpy.ops.import_scene.gltf(filepath=str(args.input.resolve()))
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    meshes = [o for o in scene.objects if o.type=="MESH"]
    source_bounds = bounds(meshes)
    source_dimensions = [b-a for a,b in zip(*source_bounds)]
    scale = args.diameter/max(source_dimensions[:2])
    center = [(a+b)/2 for a,b in zip(*source_bounds)]
    # Bake the imported parent hierarchy once, in measured Blender world coordinates.
    normalize = (Matrix.Rotation(math.radians(args.yaw_degrees),4,"Z")
        @Matrix.Scale(scale,4)
        @Matrix.Translation((-center[0],-center[1],-source_bounds[0][2])))
    world_matrices = {obj:obj.matrix_world.copy() for obj in meshes}
    for obj in meshes:
        obj.data = obj.data.copy()
        obj.data.transform(normalize@world_matrices[obj])
        obj.parent = None
        obj.matrix_world = Matrix.Identity(4)
        obj.name = "Imported curling stone geometry"
        obj.data.name = "FilinMX curling stone / original UV mesh / SI"
        for poly in obj.data.polygons:
            poly.use_smooth = True
        obj["source_author"] = "FilinMX"
        obj["source_model_uid"] = "436c3ebc3eb14cdb92c83adb9190b34e"
        obj["source_license"] = "CC BY-NC 4.0"
        obj["pcve_component_role"] = "complete rigid visual stone, including handle"
    for obj in list(scene.objects):
        if obj not in meshes:
            bpy.data.objects.remove(obj,do_unlink=True)
    collection = bpy.data.collections.new(COLLECTION_NAME)
    scene.collection.children.link(collection)
    for obj in meshes:
        for old in list(obj.users_collection):
            old.objects.unlink(obj)
        collection.objects.link(obj)
    bpy.context.view_layer.update()
    normalized_bounds = bounds(meshes)
    normalized_dimensions = [b-a for a,b in zip(*normalized_bounds)]
    details = {"source_glb_sha256":digest,"author":"FilinMX","license":"CC BY-NC 4.0",
        "source_page":"https://sketchfab.com/3d-models/curling-stone-436c3ebc3eb14cdb92c83adb9190b34e",
        "source_world_bounds":source_bounds,"source_world_dimensions":source_dimensions,
        "uniform_scale":scale,"fixed_asset_yaw_degrees":args.yaw_degrees,
        "normalized_world_bounds_m":normalized_bounds,"normalized_dimensions_m":normalized_dimensions,
        "collection_name":COLLECTION_NAME,"mesh_objects":len(meshes),
        "mesh_vertices":sum(len(o.data.vertices) for o in meshes),"mesh_faces":sum(len(o.data.polygons) for o in meshes),
        "images":[{"name":i.name,"size_px":list(i.size),"colorspace":i.colorspace_settings.name,"packed":bool(i.packed_file)} for i in bpy.data.images],
        "materials":[{"name":m.name,"nodes":[{"name":n.name,"type":n.type} for n in m.node_tree.nodes]} for m in bpy.data.materials if m.use_nodes],
        "blender_version":bpy.app.version_string,
        "method":"Original GLB mesh, UVs and embedded maps; imported world hierarchy baked, uniformly scaled to measured 29 cm maximum horizontal diameter, centered in XY and grounded at Z=0. No procedural replacement geometry."}
    if abs(normalized_dimensions[0]-.29)>.001 or abs(normalized_dimensions[1]-.29)>.001:
        raise ValueError("The imported footprint is not the expected circular 29 cm stone")
    args.out.parent.mkdir(parents=True,exist_ok=True)
    bpy.ops.file.pack_all()
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=str(args.out.resolve()))
    args.out.with_suffix(".normalization.json").write_text(json.dumps(details,indent=2)+"\n")
    print(json.dumps(details,indent=2))

if __name__ == "__main__":
    main()
