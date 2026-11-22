"""Reopen the saved Alembic-driven scene and compare all 96 solved frames.

Blender -b scene_genesis_animated.blend --python this.py -- CASE
"""
import json
import sys
from pathlib import Path

import bpy
import numpy as np

case = Path(sys.argv[sys.argv.index("--") + 1]).resolve()
surface = bpy.data.objects["GenesisTeaSurface"]
if not any(m.type == "MESH_SEQUENCE_CACHE" for m in surface.modifiers):
    raise RuntimeError("Saved scene must contain native mesh-sequence playback")
checks = {}
def canonical_oriented_faces(triangles):
    if not len(triangles):
        return triangles
    first = np.argmin(triangles, axis=1)
    rotated = np.take_along_axis(triangles, (first[:, None] + np.arange(3)) % 3, axis=1)
    return rotated[np.lexsort((rotated[:, 2], rotated[:, 1], rotated[:, 0]))]

def canonical_corner_normals(faces, vectors):
    first = np.argmin(faces, axis=1)
    corners = (first[:, None] + np.arange(3)) % 3
    rotated = np.take_along_axis(faces, corners, axis=1)
    values = np.take_along_axis(vectors.reshape(-1,3,3), corners[...,None], axis=1)
    order = np.lexsort((rotated[:,2],rotated[:,1],rotated[:,0]))
    return values[order].reshape(-1,3)

for frame in range(1, 97):
    bpy.context.scene.frame_set(frame)
    bpy.context.view_layer.update()
    mesh = surface.evaluated_get(bpy.context.evaluated_depsgraph_get()).data
    with np.load(case / f"surfaces/frame_{frame:04d}.npz") as data:
        vertices = data["vertices"]
        triangles = data["triangles"]
        triangle_count = len(triangles)
        normals = data["normals"] if "normals" in data.files else None
    if len(mesh.vertices) != len(vertices) or len(mesh.polygons) != triangle_count:
        raise RuntimeError(f"Saved animation topology mismatch at {frame}")
    actual = np.empty(len(vertices) * 3, dtype=np.float32)
    mesh.vertices.foreach_get("co", actual)
    error = float(np.max(np.abs(actual.reshape(-1, 3) - vertices))) if len(vertices) else 0.
    if error > 1e-6:
        raise RuntimeError(f"Saved animation position mismatch at {frame}: {error}")
    loops = np.empty(triangle_count * 3, dtype=np.int32)
    if len(mesh.loops) != len(loops):
        raise RuntimeError(f"Saved animation contains nontriangle faces at {frame}")
    mesh.loops.foreach_get("vertex_index", loops)
    if not np.array_equal(canonical_oriented_faces(loops.reshape(-1, 3)), canonical_oriented_faces(triangles)):
        raise RuntimeError(f"Saved animation oriented connectivity mismatch at {frame}")
    checks[str(frame)] = {"vertices": len(vertices), "triangles": triangle_count,
                          "oriented_connectivity_match": True, "max_position_error_m": error}
    if normals is not None and len(vertices):
        actual_normals = np.empty(len(mesh.corner_normals) * 3, dtype=np.float32)
        mesh.corner_normals.foreach_get("vector", actual_normals)
        errors = np.linalg.norm(actual_normals.reshape(-1, 3) - normals[loops], axis=1)
        checks[str(frame)]["custom_normals_p99_vector_error"] = float(np.percentile(errors, 99))
        checks[str(frame)]["custom_normals_max_vector_error"] = float(errors.max())
        if np.percentile(errors, 99) > .01:
            raise RuntimeError(f"Saved animation shading-normal mismatch at {frame}")
        # Blender encodes custom normals in per-corner normal spaces. A few
        # triangles cannot represent the requested kernel direction exactly.
        # Compare the native cache against the exact same
        # Blender conversion used for the video, not only that raw request.
        reference = bpy.data.meshes.new("NativeNormalReference")
        reference.from_pydata(vertices.tolist(), [], triangles.tolist())
        reference.update()
        reference.polygons.foreach_set("use_smooth",np.ones(len(triangles),dtype=bool))
        reference.normals_split_custom_set_from_vertices(normals.tolist())
        expected = np.empty(len(reference.corner_normals)*3,dtype=np.float32)
        reference.corner_normals.foreach_get("vector",expected)
        delta = np.linalg.norm(canonical_corner_normals(loops.reshape(-1,3),actual_normals)
                               -canonical_corner_normals(triangles,expected),axis=1)
        checks[str(frame)]["native_vs_render_max_normal_vector_error"] = float(delta.max())
        bpy.data.meshes.remove(reference)
        if delta.max() > .005:
            sorted_faces=canonical_oriented_faces(triangles)
            areas=.5*np.linalg.norm(np.cross(vertices[sorted_faces[:,1]]-vertices[sorted_faces[:,0]],vertices[sorted_faces[:,2]]-vertices[sorted_faces[:,0]]),axis=1)
            mismatch=delta.reshape(-1,3).max(1)>.005
            checks[str(frame)]["normal_encoding_difference"]={"faces":int(mismatch.sum()),"all_faces":len(areas),"area_m2":float(areas[mismatch].sum()),"largest_face_m2":float(areas[mismatch].max()),"area_fraction":float(areas[mismatch].sum()/areas.sum())}
        checks[str(frame)]["native_vs_render_p99_normal_vector_error"] = float(np.percentile(delta,99))
        if np.percentile(delta,99) > .01:
            raise RuntimeError(f"Native normals exceed 99th-percentile precision gate at frame {frame}")
result = {"blend": bpy.data.filepath, "passed": True, "all96frames": checks,
          "cache_paths": [c.filepath for c in bpy.data.cache_files],
          "does_not_require_python_handlers": True,
          "normal_verification": "Every corner compared; p99 vector-error gate 0.01. All-corner equality is NOT asserted: per-frame normal-encoding outliers and affected areas are retained. Geometry, topology and timing are exact independently. Selected saved-scene renders require separate pixel comparison."}
(case / "saved_animation_validation.json").write_text(json.dumps(result, indent=2) + "\n")
print("GENESIS_SAVED_ANIMATION_PASS", flush=True)
