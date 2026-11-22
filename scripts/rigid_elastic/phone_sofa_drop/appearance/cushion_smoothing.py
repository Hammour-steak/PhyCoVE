"""Blender (numpy): render-side corrections of the cushion's shape keys around the phone. Physics untouched.

The rendered cushion is the original high-resolution sculpt carried by the solver's linear
tetrahedra (grid about 2.2 cm). Where the phone presses a dent several centimetres deep, the
surface between the pressed and the free part bends inside one coarse element, so the
high-resolution render surface shows a straight sharp crease (dihedral up to ~50 deg in the
source case; folds of more than 90 deg in the heavy-phone pit) right at the phone's end: under the
raking sunlight it reads as a thin fabric flap. In addition the sculpt lies a few millimetres
above the solver's boundary, so at contact the render surface reaches into the phone body.

Two render-only passes, applied to every shape key (solver state k) after the animation rebuild:
  smooth()              Laplacian low-pass of the displacement from state 0 (the settled
                        equilibrium, unchanged), only within `radius_m` of the phone's outline in
                        the phone's frame at that state (smooth falloff). Removes the crease; the
                        dent keeps its size and position (depth changes reported).
  contact_projection()  render vertices inside the phone body (or just over its outline) are moved
                        along the phone's -z axis to just under its bottom face, spread to the
                        surrounding fabric with a per-ring decay.
The solver caches and the ground truth are not touched; scene_report.json records how far the
rendered surface moved, the dent depth before/after and the crease angles before/after.
"""
import numpy as np


def _edges(mesh):
    e = np.empty(len(mesh.edges) * 2, dtype=np.int64)
    mesh.edges.foreach_get("vertices", e)
    return e.reshape(-1, 2)


def _faces(mesh):
    tris = []
    for p in mesh.polygons:
        v = list(p.vertices)
        for i in range(1, len(v) - 1):
            tris.append((v[0], v[i], v[i + 1]))
    return np.asarray(tris, dtype=np.int64)


def _normals(co, tris):
    n = np.cross(co[tris[:, 1]] - co[tris[:, 0]], co[tris[:, 2]] - co[tris[:, 0]])
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


class _Mesh:
    """Edge adjacency (for averaging) and face pairs (for crease angles) of the cushion mesh."""

    def __init__(self, obj):
        self.obj = obj
        self.blocks = obj.data.shape_keys.key_blocks
        self.n = len(obj.data.vertices)
        self.mw = np.asarray(obj.matrix_world, dtype=np.float64)
        self.inv_mw = np.linalg.inv(self.mw)
        edges = _edges(obj.data)
        both = np.concatenate([edges, edges[:, ::-1]])
        order = np.argsort(both[:, 0], kind="stable")
        self.src, self.dst = both[order, 0], both[order, 1]
        self.rows, self.starts, self.counts = np.unique(self.src, return_index=True, return_counts=True)
        tris = _faces(obj.data)
        fe = np.sort(np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]]), axis=1)
        fid = np.tile(np.arange(len(tris)), 3)
        key = fe[:, 0] * self.n + fe[:, 1]
        o = np.argsort(key)
        key, fid, fe = key[o], fid[o], fe[o]
        same = key[1:] == key[:-1]
        self.tris = tris
        self.pairs = np.stack([fid[:-1][same], fid[1:][same]], 1)
        self.pair_vertex = fe[:-1][same][:, 0]

    def world(self, k):
        co = np.empty(self.n * 3, dtype=np.float32)
        self.blocks[k + 1].data.foreach_get("co", co)
        return co.reshape(-1, 3).astype(np.float64) @ self.mw[:3, :3].T + self.mw[:3, 3]

    def store(self, k, world):
        local = world @ self.inv_mw[:3, :3].T + self.inv_mw[:3, 3]
        self.blocks[k + 1].data.foreach_set("co", local.astype(np.float32).ravel())

    def mean(self, values):
        out = np.zeros_like(values)
        out[self.rows] = np.add.reduceat(values[self.dst], self.starts, axis=0) / self.counts.reshape((-1,) + (1,) * (values.ndim - 1))
        return out

    def crease(self, world, select):
        normal = _normals(world, self.tris)
        c = np.einsum("ij,ij->i", normal[self.pairs[select, 0]], normal[self.pairs[select, 1]])
        return np.degrees(np.arccos(np.clip(c, -1.0, 1.0)))


def _phone_local(world, T):
    Ti = np.linalg.inv(np.asarray(T, dtype=np.float64))
    return world @ Ti[:3, :3].T + Ti[:3, 3]


def _outline_distance(loc, body_x, body_y):
    dx = np.maximum(np.maximum(body_x[0] - loc[:, 0], loc[:, 0] - body_x[1]), 0.0)
    dy = np.maximum(np.maximum(body_y[0] - loc[:, 1], loc[:, 1] - body_y[1]), 0.0)
    return np.hypot(dx, dy)


def smooth(mesh, phone_T, cfg):
    rest = mesh.world(0)
    report = {"method": "Laplacian low-pass of the displacement from state 0 within radius_m of the phone outline",
              "parameters": cfg, "states_changed": 0, "max_render_change_m": 0.0, "max_render_change_state": None,
              "max_crease_deg_before": 0.0, "max_crease_deg_after": 0.0, "worst_crease_state": None,
              "max_dent_depth_m_before": 0.0, "max_dent_depth_m_after": 0.0, "max_dent_depth_change_m": 0.0}
    R, lam = cfg["radius_m"], cfg["lambda"]
    for k in range(1, len(mesh.blocks) - 1):
        world = mesh.world(k)
        dist = _outline_distance(_phone_local(world, phone_T[k]), cfg["body_x"], cfg["body_y"])
        w = np.clip((R - dist) / (cfg["falloff_fraction"] * R), 0.0, 1.0)
        w = w * w * (3.0 - 2.0 * w)
        if not w.any():
            continue
        d = world - rest
        wr = w[mesh.rows][:, None]
        for _ in range(cfg["iterations"]):
            m = mesh.mean(d)
            d[mesh.rows] += lam * wr * (m[mesh.rows] - d[mesh.rows])
        new = rest + d
        select = w[mesh.pair_vertex] > 0
        before = mesh.crease(world, select)
        after = mesh.crease(new, select)
        near = w > 0
        depth_before = float(-(world[near, 2] - rest[near, 2]).min())
        depth_after = float(-(new[near, 2] - rest[near, 2]).min())
        change = float(np.linalg.norm(new - world, axis=1).max())
        mesh.store(k, new)
        report["states_changed"] += 1
        if before.size and before.max() > report["max_crease_deg_before"]:
            report["max_crease_deg_before"], report["worst_crease_state"] = float(before.max()), k
        report["max_crease_deg_after"] = max(report["max_crease_deg_after"], float(after.max()) if after.size else 0.0)
        report["max_dent_depth_m_before"] = max(report["max_dent_depth_m_before"], depth_before)
        report["max_dent_depth_m_after"] = max(report["max_dent_depth_m_after"], depth_after)
        report["max_dent_depth_change_m"] = max(report["max_dent_depth_change_m"], abs(depth_after - depth_before))
        if change > report["max_render_change_m"]:
            report["max_render_change_m"], report["max_render_change_state"] = change, k
    return report


def contact_projection(mesh, phone_T, cfg):
    (x0, x1), (y0, y1), bottom = cfg["body_x"], cfg["body_y"], cfg["bottom_z"]
    m, target = cfg["margin_m"], cfg["bottom_z"] - cfg["clearance_m"]
    reach = cfg["top_z"] + cfg["overhang_m"]
    report = {"method": "render vertices inside the phone body or just over its outline pushed below its bottom face",
              "parameters": cfg, "states_corrected": 0, "max_penetration_before_m": 0.0,
              "max_push_m": 0.0, "max_penetration_after_m": 0.0, "worst_state": None}
    for k in range(len(mesh.blocks) - 1):
        world = mesh.world(k)
        T = np.asarray(phone_T[k], dtype=np.float64)
        loc = _phone_local(world, T)
        foot = (loc[:, 0] > x0 - m) & (loc[:, 0] < x1 + m) & (loc[:, 1] > y0 - m) & (loc[:, 1] < y1 + m)
        need = np.where(foot & (loc[:, 2] > target) & (loc[:, 2] < reach), loc[:, 2] - target, 0.0)
        if not need.any():
            continue
        pen = float((loc[foot & (loc[:, 2] < reach), 2] - bottom).max())
        # Fabric standing higher over the phone's outline than `reach` (the walls of the deep pit
        # around the heavy phone) is the solver's own shape and is left where it is.
        free = ~(foot & (loc[:, 2] >= reach))
        push = need.copy()
        for _ in range(cfg["spread_rings"]):
            push = np.maximum(need, cfg["ring_decay"] * mesh.mean(push)) * free
        world = world - push[:, None] * T[:3, 2][None, :]
        after_loc = _phone_local(world, T)
        inside = foot & (after_loc[:, 2] < reach) & free
        after = float((after_loc[inside, 2] - bottom).max())
        mesh.store(k, world)
        report["states_corrected"] += 1
        if pen > report["max_penetration_before_m"]:
            report["max_penetration_before_m"], report["worst_state"] = pen, k
        report["max_push_m"] = max(report["max_push_m"], float(push.max()))
        report["max_penetration_after_m"] = max(report["max_penetration_after_m"], after)
    return report


def apply(obj, phone_T, smoothing, contact):
    mesh = _Mesh(obj)
    report = {}
    if smoothing.get("enabled"):
        report["smoothing"] = smooth(mesh, phone_T, smoothing)
    if contact.get("enabled"):
        report["contact"] = contact_projection(mesh, phone_T, contact)
    obj.data.update()
    return report
