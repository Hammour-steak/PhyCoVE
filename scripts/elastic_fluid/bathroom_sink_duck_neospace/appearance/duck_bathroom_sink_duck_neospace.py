"""Duck geometry for the Genesis run, taken from the built scene.

Writes, in world coordinates:
  duck_solid_world.obj  voxel-remeshed closed copy of the undeformed visible duck (MPM fills it with particles);
  duck_shell_world.obj  the solid's inner 5 mm shell (SPH ghost boundary particles; water sees them within one
                        kernel radius, so particles deeper inside would only cost time);
  duck_rest.npz         the visible duck's rest vertices (the surface step skins the MPM motion back onto them).
    blender -b work/scene.blend --python duck_bathroom_sink_duck_neospace.py -- --out-dir DIR
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import bmesh
import bpy
import numpy as np

SOLID_VOXEL_M = 0.0015
SHELL_THICKNESS_M = 0.005


def parse_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, required=True)
    return parser.parse_args(sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else [])


def evaluated_world_bmesh(obj):
    evaluated = obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
    bm = bmesh.new()
    bm.from_mesh(evaluated.to_mesh())
    bm.transform(obj.matrix_world)
    evaluated.to_mesh_clear()
    if any(not edge.is_manifold for edge in bm.edges):
        raise RuntimeError(f"{obj.name} is not closed")
    return bm


def write_obj(bm, path):
    with path.open("w") as stream:
        for vertex in bm.verts:
            stream.write("v %.6f %.6f %.6f\n" % tuple(vertex.co))
        for face in bm.faces:
            stream.write("f " + " ".join(str(v.index + 1) for v in face.verts) + "\n")


def main():
    args = parse_args()
    out = args.out_dir.expanduser().resolve()
    out.mkdir(parents=True, exist_ok=True)
    duck = bpy.data.objects["ElasticRubberDuck"]
    rest = np.array([duck.matrix_world @ v.co for v in duck.data.vertices], dtype=np.float64)

    solid = bpy.data.objects.new("DuckSolid", duck.data.copy())    # the bare mesh, without the scene's modifiers
    bpy.context.scene.collection.objects.link(solid)
    solid.matrix_world = duck.matrix_world
    remesh = solid.modifiers.new("Close", "REMESH")
    remesh.mode = "VOXEL"
    remesh.voxel_size = SOLID_VOXEL_M
    solid_bm = evaluated_world_bmesh(solid)
    write_obj(solid_bm, out / "duck_solid_world.obj")

    shell = bpy.data.objects.new("DuckShell", bpy.data.meshes.new("DuckShell"))
    solid_bm.to_mesh(shell.data)                                   # already in world coordinates
    bpy.context.scene.collection.objects.link(shell)
    solidify = shell.modifiers.new("Shell", "SOLIDIFY")
    solidify.thickness = SHELL_THICKNESS_M
    solidify.offset = -1.0
    solidify.use_even_offset = True
    solidify.use_quality_normals = True
    shell_bm = evaluated_world_bmesh(shell)
    write_obj(shell_bm, out / "duck_shell_world.obj")

    np.savez_compressed(out / "duck_rest.npz", rest_vertices=rest, duck_matrix=np.array(duck.matrix_world))
    report = {"solid_volume_m3": abs(solid_bm.calc_volume(signed=True)), "shell_volume_m3": abs(shell_bm.calc_volume(signed=True)),
              "visible_vertices": int(len(rest)), "solid_voxel_m": SOLID_VOXEL_M, "shell_thickness_m": SHELL_THICKNESS_M}
    solid_bm.free()
    shell_bm.free()
    (out / "duck_prepare_report.json").write_text(json.dumps(report, indent=2) + "\n")
    print("PCVE_GENESIS_DUCK " + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
