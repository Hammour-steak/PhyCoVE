"""Tabletop puddle as a continuous water film. The 1 mm particles land in a radial sheet only one or two particles
thick; at that thickness SPH cannot resolve the capillary rim that holds real water together, so the sheet breaks into
patches. Here the table water (particles near the table, outside the cup, not falling) is turned into a height field:
volumes splatted on a 0.5 mm grid, the wetted region closed over the gaps the torn sheet leaves (up to ~2 cm), the depth
spread over that region by normalized convolution and rescaled per puddle so the volume is the particles' volume, a
rounded edge at a ~60 degree contact angle; `wet` records where the water has been (the wet-oak map). The film is a
closed volume from its top surface down to 0.25 mm inside the (opaque) table, meshed with marching cubes."""
import numpy as np
from scipy import ndimage
from skimage import measure

C = 0.5e-3                       # grid cell
Z_CUT = 6e-3                     # particles below this height are table water unless still falling
FALL_VZ = -0.15                  # m/s: the stream above the table
CLOSE_R = 12e-3                  # gaps narrower than twice this are bridged: the 1-particle sheet tears into channels and
                                 # holes a real film (capillary length 2.7 mm) would not have; 5 mm left them as islands
OUTLINE = 1.5e-3                 # outline wiggles below this scale are rounded off
SPREAD = 12e-3                   # depth is evened out over this scale: gravity and capillarity level a puddle within ~1 cm
EDGE_W = 1.5e-3                  # rounded edge width
H_MIN = 0.12e-3                  # wetted where the splatted depth exceeds this
H_WET = 0.04e-3                  # thinnest water drawn inside the wetted region
DEPTH = 0.25e-3                  # film bottom inside the table


def disk(r):
    k = int(np.ceil(r / C)); y, x = np.mgrid[-k:k + 1, -k:k + 1]
    return x * x + y * y <= (r / C) ** 2


class Film:
    def __init__(self, x0, x1, y0, y1):
        self.x = np.arange(x0, x1 + C, C); self.y = np.arange(y0, y1 + C, C)
        self.wet = np.zeros((len(self.x), len(self.y)), bool)

    def select(self, pos, vel, in_cup):
        """table water: low, outside the cup, not part of the falling stream"""
        return (pos[:, 2] < Z_CUT) & ~in_cup & ~((vel[:, 2] < FALL_VZ) & (pos[:, 2] > 1.5e-3))

    def height(self, pos, vol):
        """depth field (m) on the grid, -1 mm where dry"""
        ix = np.clip(((pos[:, 0] - self.x[0]) / C).astype(int), 0, len(self.x) - 1)
        iy = np.clip(((pos[:, 1] - self.y[0]) / C).astype(int), 0, len(self.y) - 1)
        h = np.zeros(self.wet.shape); np.add.at(h, (ix, iy), vol / C ** 2)
        hs = ndimage.gaussian_filter(h, 1.0e-3 / C)
        m = ndimage.binary_closing(hs > H_MIN, structure=disk(CLOSE_R), iterations=1)
        m = ndimage.binary_fill_holes(m) | (hs > H_MIN)
        lab, n = ndimage.label(m)
        ms = ndimage.gaussian_filter(m.astype(float), OUTLINE / C) > 0.45
        lost = np.setdiff1d(np.arange(1, n + 1), np.unique(lab[ms]))    # droplets smaller than the rounding keep their shape
        m = ms | np.isin(lab, lost)
        s = SPREAD / C
        hf = np.where(m, ndimage.gaussian_filter(hs, s) / np.maximum(ndimage.gaussian_filter(m.astype(float), s), 1e-6), 0.0)
        dist = ndimage.distance_transform_edt(m) * C
        e = 1.0 - (1.0 - np.minimum(dist / EDGE_W, 1.0)) ** 2   # parabolic edge: slope 2 h / EDGE_W
        lab, n = ndimage.label(m)
        if n:
            want = ndimage.sum(h, lab, np.arange(1, n + 1)); got = ndimage.sum(hf * e, lab, np.arange(1, n + 1))
            scale = np.concatenate([[0.0], want / np.maximum(got, 1e-12)])
            hf = hf * e * scale[lab]
        self.wet |= m
        # where the water has been and gone the oak is only wet (renderer's wet map), with no water layer drawn
        out = np.where(m, np.maximum(hf, H_WET), -1e-3)
        return out, m

    def mesh(self, hgt):
        """closed film volume between the top surface and z = -DEPTH; vertices, triangles, outward normals"""
        on = ndimage.binary_dilation(hgt > -1e-3 + 1e-9, iterations=2)
        if not on.any():
            return np.zeros((0, 3), np.float32), np.zeros((0, 3), np.int32), np.zeros((0, 3), np.float32)
        (i0, i1), (j0, j1) = [(np.where(on.any(a))[0][[0, -1]]) for a in (1, 0)]
        i0, j0 = max(i0 - 1, 0), max(j0 - 1, 0); i1, j1 = min(i1 + 2, len(self.x)), min(j1 + 2, len(self.y))
        hh = hgt[i0:i1, j0:j1]
        z = np.concatenate([[-0.35e-3, -0.15e-3], np.arange(0.05e-3, hh.max() + 0.3e-3, 0.2e-3)])
        phi = np.minimum(hh[..., None] - z, z + DEPTH)
        phi[0], phi[-1], phi[:, 0], phi[:, -1] = -1, -1, -1, -1
        v, f, _, _ = measure.marching_cubes(phi.astype(np.float32), 0.0, spacing=(C, C, 1.0), allow_degenerate=False)
        v[:, 0] += self.x[i0]; v[:, 1] += self.y[j0]; v[:, 2] = np.interp(v[:, 2], np.arange(len(z)), z)
        f = f[:, ::-1].copy()
        n = vertex_normals(v, f)
        top = v[:, 2] > 0
        if top.any() and n[top, 2].mean() < 0:
            f = f[:, ::-1].copy(); n = -n
        return v.astype(np.float32), f.astype(np.int32), n.astype(np.float32)


def vertex_normals(v, f):
    fn = np.cross(v[f[:, 1]] - v[f[:, 0]], v[f[:, 2]] - v[f[:, 0]])
    n = np.zeros_like(v)
    for k in range(3):
        np.add.at(n, f[:, k], fn)
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-20)


def depth_at(hgt, film, xy):
    """film top height at points (bilinear), -1 mm outside"""
    from scipy.interpolate import RegularGridInterpolator
    return RegularGridInterpolator((film.x, film.y), hgt, bounds_error=False, fill_value=-1e-3)(xy)
