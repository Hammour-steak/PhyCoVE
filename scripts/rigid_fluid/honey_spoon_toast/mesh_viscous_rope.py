"""Surface for the rope + film cache: smooth SDF union, marching cubes.

Each active rope edge is a capsule of its volume-equivalent radius; the lip
meniscus (buffer + material still inside the extrusion segment) is a capsule
from the nozzle to the kinematic node; the puddle is the thin-film height
field. All pieces are blended with a polynomial smooth minimum so the strand,
landed coils and puddle form one closed honey surface. The surface is clipped
just below the toast top, where the opaque toast hides it.
"""
import argparse
import json
import math
from multiprocessing import Pool
from pathlib import Path

import numba
import numpy as np
from scipy.ndimage import gaussian_filter
from skimage.measure import marching_cubes


@numba.njit(cache=True)
def splat_capsules(F, origin, h, a, b, r, k):
    nx, ny, nz = F.shape
    for e in range(a.shape[0]):
        R = r[e]+2*k
        lo0, lo1, lo2 = min(a[e, 0], b[e, 0])-R, min(a[e, 1], b[e, 1])-R, min(a[e, 2], b[e, 2])-R
        hi0, hi1, hi2 = max(a[e, 0], b[e, 0])+R, max(a[e, 1], b[e, 1])+R, max(a[e, 2], b[e, 2])+R
        i0, i1 = max(0, int((lo0-origin[0])/h)), min(nx-1, int((hi0-origin[0])/h)+1)
        j0, j1 = max(0, int((lo1-origin[1])/h)), min(ny-1, int((hi1-origin[1])/h)+1)
        k0, k1 = max(0, int((lo2-origin[2])/h)), min(nz-1, int((hi2-origin[2])/h)+1)
        ab0, ab1, ab2 = b[e, 0]-a[e, 0], b[e, 1]-a[e, 1], b[e, 2]-a[e, 2]
        ll = ab0*ab0+ab1*ab1+ab2*ab2
        for i in range(i0, i1+1):
            px = origin[0]+i*h-a[e, 0]
            for j in range(j0, j1+1):
                py = origin[1]+j*h-a[e, 1]
                for kk in range(k0, k1+1):
                    pz = origin[2]+kk*h-a[e, 2]
                    t = 0.
                    if ll > 0:
                        t = (px*ab0+py*ab1+pz*ab2)/ll
                        t = min(1., max(0., t))
                    dx, dy, dz = px-t*ab0, py-t*ab1, pz-t*ab2
                    d = math.sqrt(dx*dx+dy*dy+dz*dz)-r[e]
                    f = F[i, j, kk]
                    w = max(k-abs(f-d), 0.)/k
                    F[i, j, kk] = min(f, d)-w*w*k*.25


def smooth_radius(radius, on, passes):
    """[1 2 1] passes on cross-section area along each piece; end edges (drops) kept."""
    r2 = radius**2
    n = len(r2)
    for _ in range(passes):
        prev = np.r_[False, on[:-1]] & on
        nxt = np.r_[on[1:], False] & on
        inner = prev & nxt
        s = r2.copy()
        s[inner] = .25*r2[np.flatnonzero(inner)-1]+.5*r2[inner]+.25*r2[np.flatnonzero(inner)+1]
        r2 = s
    return np.sqrt(np.maximum(r2, 0)) if n else radius


def mesh_frame(job):
    path, out, voxel, blend, clip, args_smooth = job
    s = np.load(path)
    x, vol, on = s["x"], s["vol"], s["on"].astype(bool)
    film_h, origin2, cell, z_toast = s["film_h"], s["film_origin"], float(s["film_cell"]), float(s["film_z"])
    nozzle = s["nozzle"]
    meniscus = float(s["pending"])+float(s["buffer"])
    a, b, r = [], [], []
    if len(x) > 1 and on.any():
        e = np.flatnonzero(on)
        L = np.maximum(np.linalg.norm(x[e+1]-x[e], axis=1), 1e-7)
        a.append(x[e]); b.append(x[e+1]); r.append(smooth_radius(s["radius"], on, args_smooth)[e])
    if meniscus > 0 and len(x):
        L = float(np.linalg.norm(x[0]-nozzle))
        # capsule nozzle -> extrusion node holding the whole meniscus volume:
        # solve 4/3 pi r^3 + pi L r^2 = V for r (Newton from the sphere radius)
        rad = (3*meniscus/(4*math.pi))**(1/3)
        for _ in range(20):
            rad -= (4/3*math.pi*rad**3+math.pi*L*rad**2-meniscus)/(4*math.pi*rad**2+2*math.pi*L*rad)
        a.append(nozzle[None]); b.append(x[:1]); r.append(np.array([rad]))
    hs = gaussian_filter(film_h, 1.0)
    wet = hs > 1e-6
    if not a and not wet.any():
        np.savez_compressed(out, vertices=np.zeros((0, 3), np.float32), triangles=np.zeros((0, 3), np.int32))
        return dict(frame=path.name, vertices=0)
    pts = []
    if a:
        a, b, r = np.concatenate(a), np.concatenate(b), np.concatenate(r)
        pts += [a-r[:, None], a+r[:, None], b-r[:, None], b+r[:, None]]
    else:
        a = b = np.zeros((0, 3)); r = np.zeros(0)
    if wet.any():
        ii, jj = np.nonzero(wet)
        lo = origin2+np.array((ii.min(), jj.min()))*cell
        hi = origin2+np.array((ii.max()+1, jj.max()+1))*cell
        pts += [np.array([[lo[0], lo[1], z_toast], [hi[0], hi[1], z_toast+hs.max()]])]
    pts = np.concatenate(pts)
    lo = pts.min(0)-.002
    hi = pts.max(0)+.002
    lo[2] = max(lo[2], z_toast-clip-2*voxel)
    shape = tuple(np.ceil((hi-lo)/voxel).astype(int)+1)
    gx = lo[0]+np.arange(shape[0])*voxel
    gy = lo[1]+np.arange(shape[1])*voxel
    gz = lo[2]+np.arange(shape[2])*voxel
    F = np.ones(shape, np.float64)
    if wet.any():
        # bilinear film height at voxel columns
        fx = np.clip((gx-origin2[0])/cell-.5, 0, film_h.shape[0]-1.001)
        fy = np.clip((gy-origin2[1])/cell-.5, 0, film_h.shape[1]-1.001)
        i0, j0 = fx.astype(int), fy.astype(int)
        tx, ty = (fx-i0)[:, None], (fy-j0)[None, :]
        H = ((1-tx)*(1-ty)*hs[i0][:, j0]+tx*(1-ty)*hs[i0+1][:, j0]
             + (1-tx)*ty*hs[i0][:, j0+1]+tx*ty*hs[i0+1][:, j0+1])
        top = np.where(H > 1e-6, z_toast-.6*clip+H, -1.)
        F = np.where(top[:, :, None] > 0, gz[None, None, :]-top[:, :, None], 1.)
    if len(r):
        splat_capsules(F, lo, voxel, a.astype(np.float64), b.astype(np.float64), r.astype(np.float64), blend)
    F = np.maximum(F, (z_toast-clip)-gz[None, None, :])
    F[[0, -1]] = F[:, [0, -1]] = 1.
    F[:, :, [0, -1]] = 1.
    v, tri, _, _ = marching_cubes(F.astype(np.float32), 0., spacing=(voxel,)*3, gradient_direction="ascent")
    v = v+lo
    local = v-v.mean(0)
    vol_mesh = float(np.einsum('ij,ij->i', local[tri[:, 0]], np.cross(local[tri[:, 1]], local[tri[:, 2]])).sum()/6)
    if vol_mesh < 0:
        tri = tri[:, ::-1]
        vol_mesh = -vol_mesh
    np.savez_compressed(out, vertices=v.astype(np.float32), triangles=tri.astype(np.int32))
    return dict(frame=path.name, vertices=int(len(v)), triangles=int(len(tri)), grid=list(map(int, shape)),
                mesh_volume_ml=vol_mesh*1e6)


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--run", type=Path, required=True)
    p.add_argument("--voxel", type=float, default=.00015)
    p.add_argument("--blend", type=float, default=.0004)
    p.add_argument("--clip", type=float, default=.0004, help="surface is cut this far below the toast top")
    p.add_argument("--workers", type=int, default=12)
    p.add_argument("--radius-smoothing", type=int, default=3,
                   help="[1 2 1] passes over edge radii along the strand (surface only)")
    p.add_argument("--frames", nargs="*", type=int)
    p.add_argument("--mesh-subdir", default="filament_meshes")
    args = p.parse_args()
    out = args.run/args.mesh_subdir
    out.mkdir(exist_ok=True)
    states = sorted((args.run/"rope_states").glob("rope_*.npz"))
    if args.frames:
        states = [s for s in states if int(s.stem.split("_")[1]) in args.frames]
    jobs = [(s, out/f"honey_{s.stem.split('_')[1]}.npz", args.voxel, args.blend, args.clip, args.radius_smoothing)
            for s in states]
    with Pool(args.workers) as pool:
        rows = pool.map(mesh_frame, jobs)
    (args.run/f"meshing_report_{args.mesh_subdir}.json").write_text(json.dumps(
        dict(voxel_m=args.voxel, smooth_min_blend_m=args.blend, clip_below_toast_m=args.clip,
             radius_smoothing_passes=args.radius_smoothing, frames=rows), indent=2)+"\n")
    for row in rows[::8]:
        print(row)


if __name__ == "__main__":
    main()
