"""Restore evaluated polygons and corner normals without runtime booleans."""
import numpy as np

def load_mesh(obj,path):
    mesh=obj.data
    with np.load(path) as data:
        vertices=data['vertices'];ids=data['loop_vertex'];starts=data['loop_start'];totals=data['loop_total']
        smooth=data['smooth'];materials=data['material_index'];normals=data['corner_normals']
    mesh.clear_geometry();mesh.vertices.add(len(vertices));mesh.loops.add(len(ids));mesh.polygons.add(len(starts))
    mesh.vertices.foreach_set('co',vertices.ravel());mesh.loops.foreach_set('vertex_index',ids)
    mesh.polygons.foreach_set('loop_start',starts);mesh.polygons.foreach_set('loop_total',totals)
    mesh.polygons.foreach_set('use_smooth',smooth);mesh.polygons.foreach_set('material_index',materials)
    mesh.update()
    if len(normals):mesh.normals_split_custom_set(normals.tolist())
    return {'vertices':len(vertices),'faces':len(starts)}
