"""Splash detail for render_elastic_fluid_duck.py, computed from the existing particle caches.

The simulation is not re-run and its parameters are unchanged. Two render-side changes:
1. Anisotropic-kernel water surface (Yu & Turk 2013): near the free surface each particle's kernel
   follows the shape of its neighbourhood, so the 1-2 particle thick crown and its filaments mesh as
   continuous sheets and ligaments instead of separate 4 cm beads.
2. Secondary particles (after Ihmsen et al. 2012): fast airborne particles that have torn off (clusters
   of at most 3) are hidden from the surface and replaced by millimetre droplets strung along their
   path, and fast thin sheets shed droplets. Droplets fly with gravity and air drag until they reach the
   water, the duck or the deck. The same sources throw off fine whitish mist that fades in under a
   second, and white foam rides the surface where it churns and where droplets land, fading in 1-2.5 s.

Writes runs/source/aniso/water_####.npz (surface mesh, normals, vertex velocity, spray weight),
spray_####.npz, mist_####.npz and foam_####.npz (positions, radii, velocities, fade) and report.json.
"""
import argparse
import json
import math
import time
from pathlib import Path

import numba
import numpy as np
from scipy.ndimage import maximum_filter
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from scipy.spatial import cKDTree
from skimage.measure import marching_cubes

FPS = 24
GRAVITY = np.array([0., 0., -9.81])
WORKERS = 16
# Anisotropic surface
COVARIANCE_RADIUS = 1.5   # neighbourhood for the shape estimate, in kernel radii h
SURFACE_NEIGHBOURS = 20   # sparse splash particles (fewer neighbours within h; open water 20-27, deep 42)
                          # get anisotropic kernels; the main surface keeps the default isotropic kernel
MIN_NEIGHBOURS = 4        # fewer neighbours in the shape neighbourhood -> isotropic kernel
MAX_STRETCH = 4.          # longest / shortest kernel axis (k_r)
AXIS_RANGE = (.5, 2.)     # longest kernel axis, in h
CENTRE_SMOOTHING = .5     # anisotropic kernel centres move this far towards the neighbourhood mean
SMOOTHING_DENSITY = (12, 20)  # mesh smoothing weight ramps 0 -> 1 over this local neighbour count
SMOOTHING_ITERATIONS = 25  # weighted Laplacian mesh smoothing passes, as the default surface
NORMAL_ITERATIONS = 10    # vertex normal smoothing passes, as the default surface
ISO = .6
CELL = .8                 # marching-cubes cell, in particle radii (as the default surface)
SPRAY_BAND = (.04, .10)   # metres above the still surface where the material blends to clear spray
SPRAY_PIECE = .15         # separate surface pieces smaller than this are clear spray
# Secondary spray
TORN_CLUSTER = 3          # airborne clusters up to this size are hidden from the surface and become droplets
# Changing only the droplet settings below reuses the surface meshes; the droplets are recomputed.
SPRAY_SETTINGS = ('DROPS_PER_TORN', 'SPRAY_SPEED', 'SPRAY_MIN_HEIGHT', 'SHED_NEIGHBOURS', 'SHED_PER_FRAME',
                  'SHED_MIN_SPEED', 'SHED_HEIGHT', 'DROP_RADIUS', 'DROP_ALONG', 'DROP_ACROSS', 'DROP_SPREAD',
                  'DROP_STRETCH', 'CULL_MARGIN', 'SUBSTEPS', 'MAX_AGE', 'DECK_Z', 'SEED',
                  'MIST_PER_TORN', 'MIST_PER_FRAME', 'MIST_RADIUS', 'MIST_SPREAD', 'MIST_SLOWDOWN',
                  'MIST_TERMINAL', 'MIST_LIFE', 'FOAM_CHURN', 'FOAM_RATE', 'FOAM_PATCH', 'FOAM_PATCH_SPREAD',
                  'FOAM_FROM_LANDING', 'FOAM_LANDING_PATCH', 'FOAM_RADIUS', 'FOAM_LIFE', 'FOAM_DUCK_GAP')
DROPS_PER_TORN = 60       # droplets replacing one fast torn-off particle (33.5 g of water)
SPRAY_SPEED = (.8, 2.5)   # torn particles slower than the first speed make no droplets; full count from the second
SPRAY_MIN_HEIGHT = .03    # nor do torn particles closer than this to the water under them
SHED_NEIGHBOURS = 14      # crown rim and filaments (at most this many neighbours within h) shed droplets,
SHED_PER_FRAME = 4.       # on average this many per frame at 3 m/s,
SHED_MIN_SPEED = 1.5      # when moving at least this fast
SHED_HEIGHT = .05         # and at least this far above the still water
DROP_RADIUS = (.0015, .008)
DROP_ALONG = 1.           # droplets start strung along the source's path over this many frames of travel,
DROP_ACROSS = .3          # within this many particle spacings across it (a ligament, not a ball)
DROP_SPREAD = .12         # velocity spread across the path, as a fraction of the source speed
DROP_STRETCH = .12        # speed spread along the path, so the ligament keeps stretching into a streak
CULL_MARGIN = .02         # falling droplets this close above the water have landed
SUBSTEPS = 4
MAX_AGE = 2.
DECK_Z = 0.               # approximate deck height outside the pool
SEED = 20261018
# Mist: fine aerated droplets sheared off the same sources, slow, whitish and short-lived.
MIST_PER_TORN = 40        # per fast torn-off particle (scaled like DROPS_PER_TORN)
MIST_PER_FRAME = 10.      # per frame from a shedding particle at 3 m/s
MIST_RADIUS = (.0006, .0018)
MIST_SPREAD = .35
MIST_SLOWDOWN = (.3, .9)  # mist leaves at this fraction of its source speed
MIST_TERMINAL = 1.5       # m/s; fine mist hangs in the air
MIST_LIFE = (.3, .7)      # seconds until it has faded
# Foam: white bubbles riding the surface where it churns and where droplets land, fading out.
FOAM_CHURN = (.4, 1.)     # m/s; surface water moving this differently from its neighbours traps air and foams
                          # (impact zone p90 .56-.95; the outgoing ring wave stays under .35), full rate from the second
FOAM_RATE = .12           # foam patches per frame per churning surface particle at full rate
FOAM_PATCH = (5, 12)      # bubbles per patch: foam clumps into small lacy patches, not single dots
FOAM_PATCH_SPREAD = .008  # m; a patch's bubbles lie this close together
FOAM_FROM_LANDING = .15   # chance that a landing droplet leaves a small patch
FOAM_LANDING_PATCH = (2, 5)
FOAM_RADIUS = (.0015, .004)
FOAM_LIFE = (.6, 1.6)     # clean pool water does not hold foam for long
FOAM_DUCK_GAP = .015      # foam closer than this to the duck's material points is under or inside it


def save(path, value):
    path = Path(path)
    temporary = path.with_name(path.name+'.tmp')
    temporary.write_text(json.dumps(value, indent=2), encoding='utf8')
    temporary.replace(path)


def cubic(q):
    """Genesis' cubic spline profile with compact support q < 1 (unnormalised)."""
    return np.where(q <= .5, 6*q**3-6*q**2+1, np.where(q < 1, 2*(1-q)**3, 0.))


def random_in_ball(count, rng):
    direction = rng.standard_normal((count, 3))
    direction /= np.linalg.norm(direction, axis=1, keepdims=True)
    return direction*rng.uniform(0, 1, (count, 1))**(1/3)


class Heights:
    """Highest attached-water or duck point per 5 cm column: where droplets land, what is airborne."""

    def __init__(self, points, lower, upper, default, size=.05):
        self.lower, self.size = np.asarray(lower[:2], dtype=np.float64), size
        self.shape = tuple(np.ceil((np.asarray(upper[:2])-self.lower)/size).astype(int)+1)
        height = np.full(self.shape, -np.inf)
        np.maximum.at(height, self.cells(points), points[:, 2])
        height = maximum_filter(height, size=3, mode='nearest')
        height[~np.isfinite(height)] = default
        self.height = height

    def cells(self, points):
        index = np.floor((points[:, :2]-self.lower)/self.size).astype(int)
        return np.clip(index[:, 0], 0, self.shape[0]-1), np.clip(index[:, 1], 0, self.shape[1]-1)

    def __call__(self, points):
        return self.height[self.cells(points)]


class Flying:
    """Airborne droplets (spray or mist) carried from frame to frame, with an optional fade-out time."""

    def __init__(self, dx, radius, terminal=None, life=None):
        self.dx, self.radius_range, self.terminal, self.life_range = dx, radius, terminal, life
        self.position, self.velocity = np.zeros((0, 3)), np.zeros((0, 3))
        self.radius, self.age, self.life = np.zeros(0), np.zeros(0), np.zeros(0)

    def emit(self, origins, velocities, counts, rng, along, across, spread, stretch, slowdown=(1., 1.)):
        """Droplets strung along each source's path (a ligament) that keeps stretching into a streak."""
        total = int(counts.sum())
        if not total:
            return
        base = np.repeat(velocities, counts, axis=0)*rng.uniform(*slowdown, (total, 1))
        speed = np.linalg.norm(base, axis=1, keepdims=True)
        direction = base/np.maximum(speed, 1e-6)
        sideways = rng.standard_normal((total, 3))
        sideways -= np.einsum('nd,nd->n', sideways, direction)[:, None]*direction
        sideways /= np.maximum(np.linalg.norm(sideways, axis=1, keepdims=True), 1e-12)
        position = (np.repeat(origins, counts, axis=0)
                    + direction*rng.uniform(-.5, .5, (total, 1))*along*speed/FPS
                    + sideways*np.sqrt(rng.uniform(0, 1, (total, 1)))*across*self.dx)
        velocity = base*(1+stretch*rng.standard_normal((total, 1)))+sideways*rng.normal(0, spread, (total, 1))*speed
        radius = np.exp(rng.uniform(*np.log(self.radius_range), total))
        life = rng.uniform(*self.life_range, total) if self.life_range else np.full(total, np.inf)
        self.position = np.concatenate([self.position, position])
        self.velocity = np.concatenate([self.velocity, velocity])
        self.radius = np.concatenate([self.radius, radius])
        self.age = np.concatenate([self.age, np.zeros(total)])
        self.life = np.concatenate([self.life, life])

    def advance(self, duration):
        """Gravity and quadratic air drag, scaled so each droplet reaches its terminal speed
        (raindrop terminal speeds by size unless a fixed one is set)."""
        terminal = (np.full(len(self.radius), self.terminal) if self.terminal else
                    np.maximum(.5, 9.65-10.3*np.exp(-.6*2000*self.radius)))[:, None]
        dt = duration/SUBSTEPS
        for _ in range(SUBSTEPS):
            speed = np.linalg.norm(self.velocity, axis=1, keepdims=True)
            self.velocity += (GRAVITY-9.81*speed*self.velocity/terminal**2)*dt
            self.position += self.velocity*dt
        self.age += duration

    def cull(self, heights, lower, upper):
        """Drop droplets that landed, left or faded; return where droplets landed on the pool water."""
        inside = np.all((self.position[:, :2] >= lower[:2]) & (self.position[:, :2] <= upper[:2]), axis=1)
        floor = np.where(inside, heights(self.position), DECK_Z)
        landed = (self.position[:, 2] < floor+CULL_MARGIN) & (self.velocity[:, 2] < 0)
        touchdown = self.position[landed & inside]
        keep = ~landed & (self.position[:, 2] > floor) & (self.age < MAX_AGE) & (self.age < self.life)
        self.position, self.velocity = self.position[keep], self.velocity[keep]
        self.radius, self.age, self.life = self.radius[keep], self.age[keep], self.life[keep]
        return touchdown

    def save(self, path):
        np.savez(path, position=self.position.astype(np.float32), radius=self.radius.astype(np.float32),
                 velocity=self.velocity.astype(np.float32),
                 fade=np.clip(1-self.age/self.life, 0, 1).astype(np.float32))


class Surface:
    """Local free-surface height and flow from the attached water near the surface."""

    def __init__(self, x, v, counts, still_level, dx):
        near = (counts >= 9) & (x[:, 2] > still_level-.3)
        self.points, self.velocity, self.dx = x[near], v[near], dx
        self.tree = cKDTree(self.points[:, :2])

    def sample(self, xy):
        """Surface height (top of the highest nearby particles) and horizontal flow of the top layer."""
        _, index = self.tree.query(xy, k=8, workers=WORKERS)
        z = self.points[index, 2]
        top = np.argsort(-z, axis=1)[:, :3]
        flow = np.take_along_axis(self.velocity[index][:, :, :2], top[:, :, None], axis=1).mean(axis=1)
        return z.max(axis=1)+self.dx/2, flow


class Foam:
    """White bubbles riding the free surface, fading out over their lifetime."""

    def __init__(self):
        self.position, self.velocity = np.zeros((0, 3)), np.zeros((0, 3))
        self.radius, self.age, self.life = np.zeros(0), np.zeros(0), np.zeros(0)

    def spawn(self, points, surface, rng, patch):
        """A patch of patch[0]..patch[1] bubbles packed around each point."""
        if not len(points):
            return
        size = rng.integers(patch[0], patch[1]+1, len(points))
        position = np.repeat(np.asarray(points, dtype=np.float64), size, axis=0)
        total = len(position)
        position[:, :2] += rng.normal(0, FOAM_PATCH_SPREAD, (total, 2))
        radius = np.exp(rng.uniform(*np.log(FOAM_RADIUS), total))
        top, _ = surface.sample(position[:, :2])
        position[:, 2] = top-.3*radius
        self.position = np.concatenate([self.position, position])
        self.velocity = np.concatenate([self.velocity, np.zeros((total, 3))])
        self.radius = np.concatenate([self.radius, radius])
        self.age = np.concatenate([self.age, np.zeros(total)])
        self.life = np.concatenate([self.life, rng.uniform(*FOAM_LIFE, total)])

    def advance(self, duration, surface, duck, lower, upper):
        """Drift with the surface flow and stay on the surface; fade, and leave the duck's footprint."""
        if not len(self.radius):
            return
        _, flow = surface.sample(self.position[:, :2])
        self.velocity = np.column_stack([flow, np.zeros(len(flow))])
        self.position[:, :2] += flow*duration
        top, _ = surface.sample(self.position[:, :2])
        self.position[:, 2] = top-.3*self.radius
        self.age += duration
        inside = np.all((self.position[:, :2] > lower[:2]) & (self.position[:, :2] < upper[:2]), axis=1)
        clear = cKDTree(duck).query(self.position, workers=WORKERS)[0] > FOAM_DUCK_GAP if len(duck) else True
        keep = inside & clear & (self.age < self.life)
        self.position, self.velocity = self.position[keep], self.velocity[keep]
        self.radius, self.age, self.life = self.radius[keep], self.age[keep], self.life[keep]

    def save(self, path):
        np.savez(path, position=self.position.astype(np.float32), radius=self.radius.astype(np.float32),
                 velocity=self.velocity.astype(np.float32),
                 fade=np.clip(1-self.age/self.life, 0, 1).astype(np.float32))


def torn_particles(tree, x, counts, h):
    """Particles in clusters of at most TORN_CLUSTER particles (linked by neighbours within h)."""
    torn = np.zeros(len(x), bool)
    candidates = np.flatnonzero(counts < TORN_CLUSTER)
    if not len(candidates):
        return torn
    slot = np.full(len(x), -1)
    slot[candidates] = np.arange(len(candidates))
    rows, cols = [], []
    attached = np.zeros(len(candidates), bool)
    for k, group in enumerate(tree.query_ball_point(x[candidates], .999*h, workers=WORKERS)):
        for p in group:
            if p == candidates[k]:
                continue
            if slot[p] < 0:
                attached[k] = True
            else:
                rows.append(k)
                cols.append(slot[p])
    graph = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(len(candidates),)*2)
    count, labels = connected_components(graph, directed=False)
    reaches_out = np.zeros(count, bool)
    np.logical_or.at(reaches_out, labels, attached)
    size = np.bincount(labels, minlength=count)
    torn[candidates[~reaches_out[labels] & (size[labels] <= TORN_CLUSTER)]] = True
    return torn


def lattice_variance(dx, radius):
    """Weighted per-axis position variance of a full bulk neighbourhood (normalises the shape)."""
    n = int(radius/dx)+1
    grid = np.stack(np.meshgrid(*[np.arange(-n, n+1)]*3, indexing='ij'), -1).reshape(-1, 3)*dx
    distance = np.linalg.norm(grid, axis=1)
    grid, distance = grid[distance < radius], distance[distance < radius]
    weight = 1-(distance/radius)**3
    return float((weight[:, None]*grid**2).sum(0).mean()/weight.sum())


def kernel_shapes(x, tree, counts, h, dx):
    """Kernel centre, principal axes (rotation) and axis lengths in h for every particle."""
    centres = x.copy()
    axes = np.ones((len(x), 3))
    rotation = np.tile(np.eye(3), (len(x), 1, 1))
    radius = COVARIANCE_RADIUS*h
    reference = lattice_variance(dx, radius)
    surface = np.flatnonzero(counts < SURFACE_NEIGHBOURS)
    for chunk in np.array_split(surface, max(1, len(surface)//20000)):
        distance, index = tree.query(x[chunk], k=128, distance_upper_bound=radius, workers=WORKERS)
        valid = np.isfinite(distance)
        weight = np.where(valid, 1-(np.minimum(distance, radius)/radius)**3, 0.)
        neighbours = x[np.where(valid, index, 0)]
        total = weight.sum(1)
        mean = np.einsum('nk,nkd->nd', weight, neighbours)/total[:, None]
        offset = neighbours-mean[:, None, :]
        covariance = np.einsum('nk,nka,nkb->nab', weight, offset, offset)/total[:, None, None]
        values, vectors = np.linalg.eigh(covariance)
        values, vectors = values[:, ::-1]/reference, vectors[:, :, ::-1]
        first = np.clip(values[:, 0], *AXIS_RANGE)
        shaped = np.stack([first, np.clip(values[:, 1], first/MAX_STRETCH, first),
                           np.clip(values[:, 2], first/MAX_STRETCH, first)], axis=1)
        few = valid.sum(1) < MIN_NEIGHBOURS
        shaped[few], vectors[few] = 1., np.eye(3)
        axes[chunk], rotation[chunk] = shaped, vectors
        centres[chunk] = (1-CENTRE_SMOOTHING)*x[chunk]+CENTRE_SMOOTHING*mean
    return centres, rotation, axes


@numba.njit(parallel=True, fastmath=True, cache=True)
def splat(phi, origin, cell, centres, G, weight, extent, order, starts, blocks):
    """Add every particle's anisotropic kernel to the grid; blocks of one colour never overlap."""
    nx, ny, nz = phi.shape
    for b in numba.prange(blocks.size):
        block = blocks[b]
        for k in range(starts[block], starts[block+1]):
            p = order[k]
            cx, cy, cz = centres[p, 0], centres[p, 1], centres[p, 2]
            i0 = max(int(math.ceil((cx-extent[p, 0]-origin[0])/cell)), 0)
            i1 = min(int(math.floor((cx+extent[p, 0]-origin[0])/cell)), nx-1)
            j0 = max(int(math.ceil((cy-extent[p, 1]-origin[1])/cell)), 0)
            j1 = min(int(math.floor((cy+extent[p, 1]-origin[1])/cell)), ny-1)
            l0 = max(int(math.ceil((cz-extent[p, 2]-origin[2])/cell)), 0)
            l1 = min(int(math.floor((cz+extent[p, 2]-origin[2])/cell)), nz-1)
            w = weight[p]
            for i in range(i0, i1+1):
                rx = origin[0]+i*cell-cx
                for j in range(j0, j1+1):
                    ry = origin[1]+j*cell-cy
                    a0 = G[p, 0, 0]*rx+G[p, 0, 1]*ry
                    b0 = G[p, 1, 0]*rx+G[p, 1, 1]*ry
                    c0 = G[p, 2, 0]*rx+G[p, 2, 1]*ry
                    for l in range(l0, l1+1):
                        rz = origin[2]+l*cell-cz
                        a = a0+G[p, 0, 2]*rz
                        b2 = b0+G[p, 1, 2]*rz
                        c = c0+G[p, 2, 2]*rz
                        q2 = a*a+b2*b2+c*c
                        if q2 < 1.:
                            q = math.sqrt(q2)
                            if q <= .5:
                                f = 6.*q2*q-6.*q2+1.
                            else:
                                t = 1.-q
                                f = 2.*t*t*t
                            phi[i, j, l] += w*f


def vertex_adjacency(triangles, count):
    rows = np.concatenate([triangles[:, 0], triangles[:, 1], triangles[:, 2]])
    cols = np.concatenate([triangles[:, 1], triangles[:, 2], triangles[:, 0]])
    adjacency = coo_matrix((np.ones(len(rows)), (rows, cols)), shape=(count, count)).tocsr()
    adjacency = (adjacency+adjacency.T).tocsr()
    adjacency.data[:] = 1.
    return adjacency, np.maximum(np.asarray(adjacency.sum(axis=1)).ravel(), 1)[:, None]


def smooth(vertices, adjacency, degree, weight):
    """Weighted Laplacian smoothing as in the default surface: dense water is smoothed, sparse splash kept."""
    for _ in range(SMOOTHING_ITERATIONS):
        vertices = vertices+weight*(adjacency@vertices/degree-vertices)
    return vertices


def surface(x, v, h, dx, still_level):
    """Anisotropic-kernel water surface with outward normals, vertex velocities and spray weights."""
    tree = cKDTree(x)
    counts = tree.query_ball_point(x, .999*h, return_length=True, workers=WORKERS)-1
    volume = np.empty(len(x))
    for chunk in np.array_split(np.arange(len(x)), max(1, len(x)//100000)):
        distance, _ = tree.query(x[chunk], k=64, distance_upper_bound=h, workers=WORKERS)
        volume[chunk] = 1/((8/np.pi/h**3)*cubic(np.where(np.isfinite(distance), distance/h, 1.))).sum(1)
    centres, rotation, axes = kernel_shapes(x, tree, counts, h, dx)
    G = np.einsum('nik,nk,njk->nij', rotation, 1/(h*axes), rotation)
    weight = volume*(8/np.pi)/(h**3*axes.prod(axis=1))
    extent = h*np.sqrt(np.einsum('nak,nk->na', rotation**2, axes**2))
    cell = CELL*dx/2
    margin = h*AXIS_RANGE[1]+2*cell
    origin = centres.min(axis=0)-margin
    shape = np.ceil((centres.max(axis=0)+margin-origin)/cell).astype(int)+1
    phi = np.zeros(shape, np.float32)
    block = 2*extent[:, :2].max()+2*cell
    nbx, nby = int(np.ceil(shape[0]*cell/block)), int(np.ceil(shape[1]*cell/block))
    bx = np.clip(((centres[:, 0]-origin[0])/block).astype(int), 0, nbx-1)
    by = np.clip(((centres[:, 1]-origin[1])/block).astype(int), 0, nby-1)
    block_id = bx*nby+by
    order = np.argsort(block_id, kind='stable')
    starts = np.searchsorted(block_id[order], np.arange(nbx*nby+1))
    for px, py in ((0, 0), (0, 1), (1, 0), (1, 1)):
        blocks = np.array([i*nby+j for i in range(px, nbx, 2) for j in range(py, nby, 2)], dtype=np.int64)
        splat(phi, origin, cell, centres, G, weight, extent, order, starts, blocks)
    vertices, triangles, _, _ = marching_cubes(phi, ISO, spacing=(cell,)*3, allow_degenerate=False)
    vertices = vertices+origin
    adjacency, degree = vertex_adjacency(triangles, len(vertices))
    distance, index = tree.query(vertices, k=8, workers=WORKERS)
    falloff = np.clip(1-distance/h, 0, None)**3
    falloff[:, 0] += 1e-9
    falloff /= falloff.sum(axis=1, keepdims=True)
    velocity = np.einsum('vk,vkd->vd', falloff, v[index])
    ramp = np.clip(((falloff*counts[index]).sum(axis=1)-SMOOTHING_DENSITY[0])/
                   (SMOOTHING_DENSITY[1]-SMOOTHING_DENSITY[0]), 0, 1)
    vertices = smooth(vertices, adjacency, degree, (ramp*ramp*(3-2*ramp))[:, None])
    corners = vertices[triangles]
    face_volume = np.einsum('ij,ij->i', corners[:, 0], np.cross(corners[:, 1], corners[:, 2]))/6
    if face_volume.sum() < 0:
        triangles, face_volume = triangles[:, ::-1], -face_volume
        corners = vertices[triangles]
    normals = np.zeros_like(vertices)
    face = np.cross(corners[:, 1]-corners[:, 0], corners[:, 2]-corners[:, 0])
    for k in range(3):
        np.add.at(normals, triangles[:, k], face)
    for _ in range(NORMAL_ITERATIONS+1):
        normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        normals = normals+adjacency@normals
    normals /= np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
    count, labels = connected_components(adjacency, directed=False)
    # Closed pieces with negative volume are air pockets between flattened surface kernels: fill them.
    voids = np.bincount(labels[triangles[:, 0]], weights=face_volume, minlength=count) <= 0
    triangles = triangles[~voids[labels[triangles[:, 0]]]]
    used = np.unique(triangles)
    remap = np.full(len(vertices), -1)
    remap[used] = np.arange(len(used))
    vertices, triangles, labels = vertices[used], remap[triangles], labels[used]
    normals, velocity = normals[used], velocity[used]
    # Separate small pieces and everything well above the still water use the clear spray material.
    low, high = np.full((count, 3), np.inf), np.full((count, 3), -np.inf)
    np.minimum.at(low, labels, vertices)
    np.maximum.at(high, labels, vertices)
    small = ((high-low).max(axis=1) < SPRAY_PIECE) & ~voids
    rise = np.clip((vertices[:, 2]-still_level-SPRAY_BAND[0])/(SPRAY_BAND[1]-SPRAY_BAND[0]), 0, 1)
    spray = np.maximum(rise*rise*(3-2*rise), small[labels])
    mesh = {'vertices':vertices.astype(np.float32), 'triangles':triangles.astype(np.int32),
            'normals':normals.astype(np.float32), 'velocity':velocity.astype(np.float32),
            'spray':spray.astype(np.float32)}
    stats = {'vertices':len(vertices), 'triangles':len(triangles), 'pieces':int((~voids).sum()),
             'small_pieces':int(small.sum()), 'voids_filled':int(voids.sum()),
             'anisotropic_particles':int((counts < SURFACE_NEIGHBOURS).sum()),
             'grid':shape.tolist()}
    return mesh, stats


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--case-dir', type=Path, required=True)
    parser.add_argument('--frames', default='1-96',
                        help='Frames to write, e.g. 9-32 or 1,13,60 (spray is always simulated from frame 1).')
    args = parser.parse_args()
    wanted = sorted({frame for part in args.frames.split(',')
                     for frame in range(int(part.split('-')[0]), int(part.split('-')[-1])+1)})
    assert wanted and 1 <= wanted[0] and wanted[-1] <= 96
    numba.set_num_threads(min(32, numba.config.NUMBA_NUM_THREADS))
    case = args.case_dir.resolve()
    run = case/'runs/source'
    spec = json.loads((case/'mpm_sph_experiment.json').read_text())
    assert spec['physics'].get('water_presence', [1]) == [1], 'No water in this case: nothing splashes.'
    q = spec['simulation_quality']
    dx = q['sph_particle_size_m']
    h = 2*dx
    lower, upper = np.asarray(q['sph_lower_bound_m']), np.asarray(q['sph_upper_bound_m'])
    with np.load(run/'initial_particles.npz') as data:
        still_level = float(np.percentile(data['water_rest'][:, 2], 99.5))+dx/2
    out = run/'aniso'
    out.mkdir(exist_ok=True)
    names = [name for name in globals() if name.isupper() and name not in ('GRAVITY', 'SPRAY_SETTINGS')]
    settings = json.loads(json.dumps({
        'surface':{name:globals()[name] for name in names if name not in SPRAY_SETTINGS},
        'spray':{name:globals()[name] for name in SPRAY_SETTINGS}}))
    report_path = out/'report.json'
    report = json.loads(report_path.read_text()) if report_path.exists() else {'settings':settings, 'frames':{}}
    assert report['settings'].get('surface') == settings['surface'], \
        'Surface settings changed: delete runs/source/aniso first.'
    report['settings'] = settings
    drops = Flying(dx, DROP_RADIUS)
    mist = Flying(dx, MIST_RADIUS, terminal=MIST_TERMINAL, life=MIST_LIFE)
    foam = Foam()
    converted = None
    previous = None
    for frame in range(1, wanted[-1]+1):
        tick = time.monotonic()
        with np.load(run/'particles'/f'frame_{frame:04d}.npz') as data:
            x, v = data['water_pos'].astype(np.float64), data['water_vel'].astype(np.float64)
            duck = data['duck_pos'].astype(np.float64)
        if previous is not None:  # Particle order must be stable for the torn-particle bookkeeping.
            assert np.median(np.linalg.norm(x-previous, axis=1)) < dx
        previous = x
        converted = np.zeros(len(x), bool) if converted is None else converted
        tree = cKDTree(x)
        counts = tree.query_ball_point(x, .999*h, return_length=True, workers=WORKERS)-1
        heights = Heights(np.concatenate([x[counts >= 9], duck])+[0, 0, dx/2], lower, upper, still_level)
        torn = torn_particles(tree, x, counts, h)
        surface_now = Surface(x, v, counts, still_level, dx)
        rng = np.random.default_rng(SEED+frame)
        if frame > 1:
            drops.advance(1/FPS)
            mist.advance(1/FPS)
            foam.advance(1/FPS, surface_now, duck, lower, upper)
        landed = drops.cull(heights, lower, upper)
        mist.cull(heights, lower, upper)
        foam.spawn(landed[rng.uniform(size=len(landed)) < FOAM_FROM_LANDING], surface_now, rng, FOAM_LANDING_PATCH)
        clearance = x[:, 2]-heights(x)
        new = torn & ~converted & (clearance > 0)
        converted = (converted | new) & torn  # Particles that rejoin the water show again.
        speed = np.linalg.norm(v, axis=1)
        # Only energetic ejecta break up into spray; a slow piece just above the water simply rejoins it.
        energy = np.clip((speed[new]-SPRAY_SPEED[0])/(SPRAY_SPEED[1]-SPRAY_SPEED[0]), 0, 1)*(clearance[new] > SPRAY_MIN_HEIGHT)
        drops.emit(x[new], v[new], np.round(DROPS_PER_TORN*energy).astype(int), rng,
                   DROP_ALONG, DROP_ACROSS, DROP_SPREAD, DROP_STRETCH)
        mist.emit(x[new], v[new], np.round(MIST_PER_TORN*energy).astype(int), rng, .5, 1., MIST_SPREAD, .2, MIST_SLOWDOWN)
        shedding = (~converted & (counts >= 1) & (counts <= SHED_NEIGHBOURS) & (speed > SHED_MIN_SPEED)
                    & (x[:, 2] > still_level+SHED_HEIGHT))
        rate = np.clip(speed[shedding]/3, 0, 1.5)
        drops.emit(x[shedding], v[shedding], rng.poisson(SHED_PER_FRAME*rate), rng,
                   DROP_ALONG, DROP_ACROSS, DROP_SPREAD, DROP_STRETCH)
        mist.emit(x[shedding], v[shedding], rng.poisson(MIST_PER_FRAME*rate), rng, .5, 1., MIST_SPREAD, .2, MIST_SLOWDOWN)
        # Foam where the surface churns (Ihmsen's trapped-air idea): top-layer water moving differently
        # from its neighbours, as in the impact zone, unlike a wave that travels as one piece.
        top, _ = surface_now.sample(surface_now.points[:, :2])
        layer = surface_now.points[:, 2] > top-dx/2-.02
        points, flow = surface_now.points[layer], surface_now.velocity[layer]
        _, neighbour = cKDTree(points).query(points, k=9, workers=WORKERS)
        churn = np.linalg.norm(flow[neighbour[:, 1:]]-flow[:, None, :], axis=2).mean(axis=1)
        churn = rng.poisson(FOAM_RATE*np.clip((churn-FOAM_CHURN[0])/(FOAM_CHURN[1]-FOAM_CHURN[0]), 0, 1))
        foam.spawn(np.repeat(points, churn, axis=0), surface_now, rng, FOAM_PATCH)
        foam.advance(0., surface_now, duck, lower, upper)  # New foam may not start under the duck.
        record = {'torn_new':int(new.sum()), 'hidden':int(converted.sum()), 'shedding':int(shedding.sum()),
                  'drops':len(drops.radius), 'mist':len(mist.radius), 'foam':len(foam.radius)}
        if frame in wanted:
            drops.save(out/f'spray_{frame:04d}.npz')
            mist.save(out/f'mist_{frame:04d}.npz')
            foam.save(out/f'foam_{frame:04d}.npz')
            if not ((out/f'water_{frame:04d}.npz').exists() and 'surface' in report['frames'].get(str(frame), {})):
                visible = ~converted
                mesh, stats = surface(x[visible], v[visible], h, dx, still_level)
                np.savez(out/f'water_{frame:04d}.npz', **mesh)
                record['surface'] = stats
            else:
                record['surface'] = report['frames'][str(frame)]['surface']
        elif 'surface' in report['frames'].get(str(frame), {}):
            record['surface'] = report['frames'][str(frame)]['surface']  # Keep the record of a mesh written earlier.
        record['seconds'] = time.monotonic()-tick
        report['frames'][str(frame)] = record
        save(report_path, report)
        print('SPLASH_DETAIL', frame, json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
