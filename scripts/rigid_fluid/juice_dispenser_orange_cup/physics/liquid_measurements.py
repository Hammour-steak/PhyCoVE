"""Volume diagnostics measured from baked, closed liquid surfaces."""
import numpy as np


def volume_below(triangles, zcut):
    """Signed closed-mesh volume below a horizontal plane, in mesh units^3."""
    triangles = np.asarray(triangles, dtype=np.float64)
    below = triangles[:, :, 2] <= zcut
    full = triangles[below.all(axis=1)]
    total = 0.0
    if len(full):
        cross_z = np.cross(full[:, 1]-full[:, 0], full[:, 2]-full[:, 0])[:, 2]
        total = float(np.sum((full[:, :, 2].mean(axis=1)-zcut)*cross_z/2.0))
    for tri in triangles[below.any(axis=1) & ~below.all(axis=1)]:
        polygon = []
        for i in range(3):
            a, b = tri[i], tri[(i+1) % 3]
            ina, inb = a[2] <= zcut, b[2] <= zcut
            if ina:
                polygon.append(a)
            if ina != inb:
                polygon.append(a+(b-a)*((zcut-a[2])/(b[2]-a[2])))
        for i in range(1, len(polygon)-1):
            a, b, c = polygon[0], polygon[i], polygon[i+1]
            total += ((a[2]+b[2]+c[2])/3.0-zcut)*np.cross(b-a, c-a)[2]/2.0
    return float(total)


def measure_surface(obj, *, bottom_z, lip_z, outlet_z, glass_center_xy, glass_radius):
    mesh = obj.data
    mesh.calc_loop_triangles()
    vertices = np.empty(len(mesh.vertices)*3, dtype=np.float64)
    mesh.vertices.foreach_get('co', vertices)
    vertices = vertices.reshape(-1, 3)
    mat = np.asarray(obj.matrix_world)
    vertices = vertices@mat[:3, :3].T+mat[:3, 3]
    indices = np.empty(len(mesh.loop_triangles)*3, dtype=np.int32)
    mesh.loop_triangles.foreach_get('vertices', indices)
    indices = indices.reshape(-1, 3)
    if not np.isfinite(vertices).all():
        raise RuntimeError('Nonfinite coordinates in the baked liquid surface')
    if not len(indices):
        return {'all_liquid_mesh_volume_ml': 0.0, 'retained_volume_ml': 0.0,
                'delivered_below_outlet_volume_ml': 0.0, 'triangles': 0,
                'cup_band_vertices_outside_glass': 0}
    tri = vertices[indices]
    edges = np.sort(np.concatenate((indices[:, [0, 1]], indices[:, [1, 2]], indices[:, [2, 0]])), axis=1)
    _, edge_counts = np.unique(edges, axis=0, return_counts=True)
    nonmanifold_edges = int(np.count_nonzero(edge_counts != 2))
    if nonmanifold_edges:
        raise RuntimeError(f'Volume integration requires a closed surface; found {nonmanifold_edges} open/nonmanifold edges')
    signed = float(np.einsum('ij,ij->i', tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum()/6)
    sign = 1 if signed >= 0 else -1
    cup = (volume_below(tri, lip_z)-volume_below(tri, bottom_z))*sign*1e6
    delivered = volume_below(tri, outlet_z)*sign*1e6
    in_band = (vertices[:, 2] >= bottom_z) & (vertices[:, 2] <= lip_z)
    outside = np.linalg.norm(vertices[:, :2]-np.asarray(glass_center_xy), axis=1) > glass_radius
    return {'all_liquid_mesh_volume_ml': abs(signed)*1e6,
            'retained_volume_ml': max(0.0, cup),
            'delivered_below_outlet_volume_ml': max(0.0, delivered),
            'triangles': len(indices),
            'open_or_nonmanifold_edges': nonmanifold_edges,
            'cup_band_vertices_outside_glass': int((in_band & outside).sum())}
