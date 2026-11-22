"""Geometry loaders reused from the accepted Genesis renderer."""
import bpy
import numpy as np
from pathlib import Path

def load_state(run: Path, frame: int, mesh_dir_name: str):
    with np.load(run / "particles" / f"frame_{frame:04d}.npz") as src:
        car_pos = src["car_pos"].astype(float)
        car_quat = src["car_quat_wxyz"].astype(float)
        water_pos = src["water_pos"].astype(float)
        water_vel = src["water_vel"].astype(float)
    with np.load(run / mesh_dir_name / f"water_{frame:04d}.npz") as src:
        vertices = src["vertices"].astype(float)
        triangles = src["triangles"].astype(int)
    return car_pos, car_quat, water_pos, water_vel, vertices, triangles

def replace_water_geometry(obj, vertices, triangles, in_place=False):
    old = obj.data
    materials = [material for material in old.materials if material]
    mesh = old if in_place else bpy.data.meshes.new(f"PCVE_GenesisWaterMesh_{bpy.context.scene.frame_current:04d}")
    if in_place:mesh.clear_geometry()
    mesh.from_pydata(vertices.tolist(), [], triangles.tolist())
    mesh.update()
    if not in_place:
        for material in materials:mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.data = mesh
    if not in_place and old and old.users == 0:
        bpy.data.meshes.remove(old)

def replace_spray_geometry(obj, points, radius, in_place=False):
    """Render solver particles above the sheet as compact octahedral droplets."""
    old = obj.data
    materials = [material for material in old.materials if material]
    vertices = []
    triangles = []
    offsets = ((1, 0, 0), (-1, 0, 0), (0, 1, 0),
               (0, -1, 0), (0, 0, 1), (0, 0, -1))
    faces = ((0, 2, 4), (2, 1, 4), (1, 3, 4), (3, 0, 4),
             (2, 0, 5), (1, 2, 5), (3, 1, 5), (0, 3, 5))
    radii = np.broadcast_to(np.asarray(radius, dtype=float), (len(points),))
    for point, particle_radius in zip(points, radii):
        base = len(vertices)
        vertices.extend(tuple(point + np.asarray(offset) * particle_radius) for offset in offsets)
        triangles.extend(tuple(base + i for i in face) for face in faces)
    mesh = old if in_place else bpy.data.meshes.new(f"PCVE_GenesisSprayMesh_{bpy.context.scene.frame_current:04d}")
    if in_place:mesh.clear_geometry()
    mesh.from_pydata(vertices, [], triangles)
    mesh.update()
    if not in_place:
        for material in materials:mesh.materials.append(material)
    for polygon in mesh.polygons:
        polygon.use_smooth = True
    obj.data = mesh
    if not in_place and old and old.users == 0:
        bpy.data.meshes.remove(old)

def load_secondary(run, directory, frame, kind):
    with np.load(run / directory / f"{kind}_{frame:04d}.npz") as data:
        return data["position"].astype(float), data["radius"].astype(float)

