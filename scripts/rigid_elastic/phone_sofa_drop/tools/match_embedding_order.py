"""Blender: re-order a cushion embedding to the vertex order of one packed scene.

Run as  blender -b assets/scenes/phone_sofa_drop/packed/CASE/scene.blend --disable-autoexec
        --python tools/match_embedding_order.py -- EMBEDDING.npz REFERENCE_DENSE_CACHE.npz OUT.npz

The FEM embedding (vertex_ids, weights: fixed linear tetrahedral shape functions of the sculpted
cushion) is the same for every case, but the two packed scenes that were rebuilt separately (soft_e_div2,
added_pillow) store the cushion vertices in another order. This finds that order by matching the
packed scene's first shape key (the state at t = 0) to the embedding's prediction from the
accepted 0-3 s reference cache, then requires every one of the 721 stored reference shape keys to agree after the
re-ordering (1e-6 m), and writes the re-ordered embedding (all per-vertex arrays permuted, plus
the permutation as `packed_vertex_order`). Nothing is fitted: weights and ids are only re-ordered.
"""
import json
import sys

import bpy
import numpy as np
from mathutils import kdtree

CUSHION = "Dynamic_Original_Middle_Seat"


def main():
    emb_path, cache_path, out_path = sys.argv[sys.argv.index("--") + 1:][:3]
    obj = bpy.data.objects[CUSHION]
    blocks = obj.data.shape_keys.key_blocks
    n = len(obj.data.vertices)

    def key(i):
        co = np.empty(n * 3, dtype=np.float32)
        blocks[i].data.foreach_get("co", co)
        return co.reshape(-1, 3).astype(np.float64)

    e = np.load(emb_path, allow_pickle=False)
    ids, w = e["vertex_ids"].astype(np.int64), e["weights"]
    solid = np.load(cache_path, allow_pickle=False)["solid_positions"]
    inv = np.linalg.inv(np.asarray(obj.matrix_world))

    def predicted(k):
        world = np.einsum("nv,nvc->nc", w, solid[k][ids])
        return world @ inv[:3, :3].T + inv[:3, 3]

    first = predicted(0)
    tree = kdtree.KDTree(n)
    for i, p in enumerate(first):
        tree.insert(p, i)
    tree.balance()
    order = np.empty(n, dtype=np.int64)
    gap = 0.0
    for j, p in enumerate(key(1)):
        _, i, d = tree.find(p)
        order[j], gap = i, max(gap, d)
    worst = max(float(np.abs(key(k + 1) - predicted(k)[order]).max()) for k in range(len(blocks) - 1))
    direct = float(np.abs(key(1) - first).max())
    if worst > 1e-6:
        raise ValueError(f"No vertex re-ordering reproduces the packed shape keys (worst {worst} m)")
    arrays = {k: e[k] for k in e.files}
    for k, v in arrays.items():
        if v.ndim and v.shape[0] == n:
            arrays[k] = v[order]
    arrays["packed_vertex_order"] = order.astype(np.int32)
    np.savez_compressed(out_path, **arrays)
    print("EMBEDDING_ORDER", json.dumps({"vertices": n, "keys_checked": len(blocks) - 1,
                                         "before_max_abs_m": direct, "after_max_abs_m": worst,
                                         "matching_max_distance_m": gap,
                                         "distinct_targets": int(len(np.unique(order)))}))


if __name__ == "__main__":
    main()
