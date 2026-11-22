"""Volume-preserving geometry and clean split-normal generation for sub-grid and landed droplets."""
import numpy as np
import trimesh
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree


def particle_components(points, radius):
    """Sparse local connectivity graph assigning every particle to a connected component."""
    points = np.asarray(points)
    n = len(points)
    if n == 0:
        return np.empty(0, np.int32), np.empty(0, np.int64)
    k = min(10, n)
    distances, columns = cKDTree(points).query(points, k=k, distance_upper_bound=radius)
    distances, columns = distances.reshape(n, k), columns.reshape(n, k)
    rows = np.broadcast_to(np.arange(n)[:, None], columns.shape)
    valid = np.isfinite(distances) & (columns != rows)
    graph = coo_matrix((np.ones(valid.sum(), np.uint8), (rows[valid], columns[valid])), shape=(n, n)).tocsr()
    count, labels = connected_components(graph, directed=False)
    return labels, np.bincount(labels, minlength=count)


def airborne_droplets(points, velocities, particle_volume, particle_size):
    """Represent tiny detached airborne clusters (< 8 particles) as volume-preserving icospheres."""
    labels, counts = particle_components(points, 1.45 * particle_size)
    small = counts[labels] < 8
    template = trimesh.creation.icosphere(subdivisions=2)
    template.vertices /= abs(template.volume) ** (1.0 / 3.0)
    vertices, triangles, normals, motion = [], [], [], []
    offset = 0
    for label in np.flatnonzero(counts < 8):
        indices = np.flatnonzero(labels == label)
        radius = (3.0 * len(indices) * particle_volume / (4.0 * np.pi)) ** (1.0 / 3.0)
        compact = np.linalg.norm(np.ptp(points[indices], axis=0)) <= 2.8 * radius
        groups = [indices] if compact else [[i] for i in indices]
        for group in groups:
            center = points[group].mean(axis=0)
            speed = velocities[group].mean(axis=0)
            v = template.vertices * (len(group) * particle_volume) ** (1.0 / 3.0) + center
            vertices.append(v)
            triangles.append(template.faces + offset)
            normals.append(template.vertex_normals)
            motion.append(np.broadcast_to(speed, v.shape))
            offset += len(v)

    def stack(parts, dtype):
        return np.concatenate(parts).astype(dtype) if parts else np.empty((0, 3), dtype)

    return (
        ~small,
        stack(vertices, np.float32),
        stack(triangles, np.int32),
        stack(normals, np.float32),
        stack(motion, np.float32),
        int(small.sum()),
    )


def _split_cap_loop_normals(vertices, top_faces, bot_faces):
    """Compute per-loop normals with smooth dome shading on top and crisp sharp crease at the flat base."""
    top_mesh = trimesh.Trimesh(vertices, top_faces, process=False)
    bot_mesh = trimesh.Trimesh(vertices, bot_faces, process=False)
    top_ln = top_mesh.vertex_normals[top_faces].reshape(-1, 3)
    bot_ln = bot_mesh.vertex_normals[bot_faces].reshape(-1, 3)
    return np.vstack([top_ln, bot_ln]).astype(np.float32)


def wetting_cap(center, volume, angle_deg, support_z, rings=8, segments=32):
    """Finite-volume spherical sessile drop cap with split top/bottom loop normals."""
    if not 0 < angle_deg <= 90 or volume <= 0:
        raise ValueError("positive volume and contact angle in (0, 90] degrees required")
    theta = np.radians(angle_deg)
    h_over_a = np.tan(theta / 2.0)
    a = (6.0 * volume / (np.pi * h_over_a * (3.0 + h_over_a ** 2))) ** (1.0 / 3.0)
    radius = a / np.sin(theta)
    xy = [np.asarray(center)]
    rr = [0.0]
    for ring in range(1, rings + 1):
        for j in range(segments):
            rho, az = a * ring / rings, 2.0 * np.pi * j / segments
            xy.append(center + rho * np.array([np.cos(az), np.sin(az)]))
            rr.append(rho)
    xy = np.asarray(xy)
    height = np.sqrt(np.maximum(radius ** 2 - np.asarray(rr) ** 2, 0.0)) - radius * np.cos(theta)
    base_z = support_z(xy)
    vertices = np.column_stack([xy, base_z + height])
    top_faces = [[0, 1 + j, 1 + (j + 1) % segments] for j in range(segments)]
    for ring in range(rings - 1):
        lower, upper = 1 + ring * segments, 1 + (ring + 1) * segments
        for j in range(segments):
            k = (j + 1) % segments
            top_faces.extend([[lower + j, upper + j, upper + k], [lower + j, upper + k, lower + k]])
    top_count, rim_start = len(vertices), len(vertices) - segments
    bottom_map = np.arange(top_count)
    bottom_map[:rim_start] += top_count
    vertices = np.vstack([vertices, np.column_stack([xy[:rim_start], base_z[:rim_start]])])
    top_faces = np.asarray(top_faces, np.int32)
    bot_faces = bottom_map[top_faces[:, ::-1]].astype(np.int32)
    faces = np.vstack([top_faces, bot_faces])
    mesh_volume = abs(trimesh.Trimesh(vertices, faces, process=False).volume)
    if mesh_volume <= 0:
        raise ValueError("degenerate wetting cap")
    vertices[:top_count, 2] = base_z + height * (volume / mesh_volume)
    # Embed contact rim and bottom cap slightly into solid support to avoid coplanar water-air TIR
    vertices[rim_start:top_count, 2] = base_z[rim_start:top_count] - 0.00003
    vertices[top_count:, 2] = base_z[:rim_start] - 0.00025
    loop_normals = _split_cap_loop_normals(vertices, top_faces, bot_faces)
    return vertices, faces, loop_normals


def wetting_film(points, particle_volume, particle_size, support_z):
    """Watertight height-field film over a spread puddle footprint with smoothed rim and split loop normals."""
    step, radius = 0.45 * particle_size, 2.25 * particle_size
    low = np.floor((points[:, :2].min(0) - radius - 2.0 * step) / step) * step
    high = np.ceil((points[:, :2].max(0) + radius + 2.0 * step) / step) * step
    xs, ys = [low[i] + np.arange(int(round((high[i] - low[i]) / step)) + 1) * step for i in range(2)]
    x, y = np.meshgrid(xs, ys)
    xy = np.column_stack([x.ravel(), y.ravel()])
    distances = cKDTree(xy).sparse_distance_matrix(cKDTree(points[:, :2]), radius, output_type="coo_matrix")
    weights = np.maximum(1.0 - (distances.data / radius) ** 2, 0.0) ** 3
    h_grid = (np.bincount(distances.row, weights=weights, minlength=len(xy)) * particle_volume / step ** 2).reshape(
        len(ys), len(xs)
    )
    for _ in range(3):
        p = np.pad(h_grid, 1, mode="constant")
        h_grid = (
            4.0 * p[1:-1, 1:-1]
            + 2.0 * (p[:-2, 1:-1] + p[2:, 1:-1] + p[1:-1, :-2] + p[1:-1, 2:])
            + (p[:-2, :-2] + p[:-2, 2:] + p[2:, :-2] + p[2:, 2:])
        ) / 16.0
    height = h_grid.ravel()
    cutoff = max(height.max() * 0.035, 1e-6)
    height = np.maximum(height - cutoff, 0.0)
    grid = np.arange(len(xy)).reshape(len(ys), len(xs))
    a = grid[:-1, :-1].ravel()
    b, c, d = a + 1, a + len(xs), a + len(xs) + 1
    faces = np.vstack([np.column_stack([a, b, d]), np.column_stack([a, d, c])])
    faces = faces[np.any(height[faces] > 0.0, axis=1)]
    used, inverse = np.unique(faces, return_inverse=True)
    top_faces = inverse.reshape(-1, 3).astype(np.int32)
    xy, height = xy[used].copy(), height[used]
    # Smooth zero-height rim contour XY to remove square-grid stair-stepping
    rim_mask = height == 0.0
    if rim_mask.any():
        edges = np.vstack([top_faces[:, [0, 1]], top_faces[:, [1, 2]], top_faces[:, [2, 0]]])
        rim_edges = edges[rim_mask[edges[:, 0]] & rim_mask[edges[:, 1]]]
        if len(rim_edges):
            for _ in range(3):
                acc = np.zeros_like(xy)
                cnt = np.zeros(len(xy))
                np.add.at(acc, rim_edges[:, 0], xy[rim_edges[:, 1]])
                np.add.at(acc, rim_edges[:, 1], xy[rim_edges[:, 0]])
                np.add.at(cnt, rim_edges[:, 0], 1.0)
                np.add.at(cnt, rim_edges[:, 1], 1.0)
                upd = rim_mask & (cnt > 0)
                xy[upd] = 0.5 * xy[upd] + 0.5 * (acc[upd] / cnt[upd, None])
    base_z = support_z(xy)
    vertices = np.column_stack([xy, base_z + height])
    positive = height > 0.0
    bottom = np.arange(len(xy))
    bottom[positive] = len(xy) + np.arange(positive.sum())
    vertices = np.vstack([vertices, np.column_stack([xy[positive], base_z[positive]])])
    bot_faces = bottom[top_faces[:, ::-1]].astype(np.int32)
    faces = np.vstack([top_faces, bot_faces])
    mesh_volume = abs(trimesh.Trimesh(vertices, faces, process=False).volume)
    if mesh_volume <= 0:
        raise ValueError("degenerate wetting film")
    vertices[: len(xy), 2] = base_z + height * (len(points) * particle_volume / mesh_volume)
    vertices[np.flatnonzero(rim_mask), 2] = base_z[rim_mask] - 0.00003
    vertices[len(xy) :, 2] = base_z[positive] - 0.00025
    loop_normals = _split_cap_loop_normals(vertices, top_faces, bot_faces)
    return vertices, faces, loop_normals


def landed_droplets(points, velocities, particle_volume, particle_size, angle_deg, support_z):
    """Build watertight sessile caps or spread films with split loop normals and sliding velocities."""
    if not len(points):
        return (
            np.empty((0, 3), np.float32),
            np.empty((0, 3), np.int32),
            np.empty((0, 3), np.float32),
            np.empty((0, 3), np.float32),
            0,
        )
    # Coalesce neighbouring specks into coherent drops/puddles (avoids a gritty "sand" look on dark wood)
    labels, sizes = particle_components(points, 3.2 * particle_size)
    tiny = np.flatnonzero(sizes <= 4)
    if len(tiny) and (sizes > 4).any():
        big_mask = sizes[labels] > 4
        big_idx = np.flatnonzero(big_mask)
        tree = cKDTree(points[big_idx, :2])
        for label in tiny:
            members = np.flatnonzero(labels == label)
            dist, nn = tree.query(points[members, :2].mean(0), k=1, distance_upper_bound=8.0 * particle_size)
            if np.isfinite(dist):
                labels[members] = labels[big_idx[nn]]
        _, labels = np.unique(labels, return_inverse=True)
        sizes = np.bincount(labels)
    vertices, triangles, loop_normals, motion = [], [], [], []
    offset = 0
    for label, size in enumerate(sizes):
        mask = labels == label
        cluster = points[mask]
        cvel = velocities[mask]
        center = cluster[:, :2].mean(0)
        volume = int(size) * particle_volume
        # Authentic wetting puddle film (angle_deg=22.0)
        drop_angle = angle_deg
        tangent = np.tan(np.radians(drop_angle) / 2.0)
        cap_radius = (6.0 * volume / (np.pi * tangent * (3.0 + tangent ** 2))) ** (1.0 / 3.0)
        if size <= 6 or np.linalg.norm(cluster[:, :2] - center, axis=1).max() <= 1.25 * cap_radius:
            v, t, ln = wetting_cap(center, volume, drop_angle, support_z)
            mean_v = np.array([cvel[:, 0].mean(), cvel[:, 1].mean(), 0.0], dtype=np.float32)
            mv = np.broadcast_to(mean_v, v.shape).copy()
        else:
            v, t, ln = wetting_film(cluster, particle_volume, particle_size, support_z)
            k = min(4, len(cluster))
            dists, idx = cKDTree(cluster[:, :2]).query(v[:, :2], k=k)
            dists = np.asarray(dists).reshape(len(v), k)
            idx = np.asarray(idx).reshape(len(v), k)
            w = 1.0 / np.maximum(dists, 1e-5)
            w /= w.sum(1, keepdims=True)
            mv = (cvel[idx] * w[..., None]).sum(1).astype(np.float32)
            mv[:, 2] = 0.0
        vertices.append(v)
        triangles.append(t + offset)
        loop_normals.append(ln)
        motion.append(mv)
        offset += len(v)
    return (
        np.concatenate(vertices).astype(np.float32),
        np.concatenate(triangles).astype(np.int32),
        np.concatenate(loop_normals).astype(np.float32),
        np.concatenate(motion).astype(np.float32),
        len(sizes),
    )
