"""Water surface and splash detail of a simulated apple run, reusing the elastic-duck splash stage.

Anisotropic-kernel water surface plus spray, mist and foam, as splash_elastic_fluid_duck.py computes
them (the bowling pool-drop wrapper, scaled down to a kitchen basin). The duck stage was tuned for a
pond: its lengths (spray band, droplet and bubble sizes, landing grid) shrink by SCALE here and its
speed thresholds by sqrt(SCALE), as Froude scaling keeps a smaller splash looking the same. Droplet
and mist counts keep the duck's share of torn-off water volume at the smaller droplet sizes, and the
foam rate keeps its surface coverage at the smaller bubbles. The apple stands in for the duck's
material points (droplets land on it; foam is not left inside it). Below the rim, particles near the
basin wall are mirrored across it so the surface meets the wall instead of rounding off; what the
surface makes of the images, past the wall and under the floor, is moved into the basin's solid.
The simulated counter is flat; <run>/ground.npz (ground_apple_drop_kitchen_basin.py) is the real kitchen under
it. Spilled water that comes to rest over the open sink has fallen in and water under the cutting
board is really lying on the board, so neither is meshed. The ground map reaches beyond the
simulated domain, so droplets land on the counter, the board, into the sink or off the counter's
edge wherever they fly. Water lying on the counter or the board, or running down the basin's outer
wall, is a thin film that 3 mm particles can only draw as beads and lenses; it becomes maps the
render reads in those surfaces' materials (wet_####.npz). On the counter and the board, the puddle's
height: every spilled particle keeps its volume where it came to rest, within LANDING_REACH of its
touchdown (the simulated counter has no contact line to stop it). On the wall, the film running down
now and the streaks where it ran. Droplets stay as beads where they came down on the counter or the
board, or met the things standing there (the soda maker, the peppers, the tap): beads_####.npz, which
the render draws as water, since a bead is a lens.

Writes <run>/aniso/water_####.npz, spray_/mist_/foam_/wet_/beads_####.npz and report_<part>.json.
"""
import argparse
import json
import math
import sys
import time
from pathlib import Path

import numba
import numpy as np
from scipy.ndimage import gaussian_filter, maximum_filter
from scipy.spatial import cKDTree
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO

# The splash stage of elastic_fluid_duck is reused as it is; a change to that module changes this scene too.
DUCK_PHYSICS = REPO / 'scripts/elastic_fluid/elastic_fluid_duck/physics'
sys.path.insert(0, str(DUCK_PHYSICS))
import splash_elastic_fluid_duck as duck  # noqa: E402

DUCK_DX = 0.034722222222222224
SCALE = 0.3               # basin splash lengths / duck pond splash lengths
SPLASH_DROPS = (.001, .0025)  # m; radii of the drops a basin splash throws (log-uniform)
DROP_SCATTER = .06        # drops leave their source with this spread across and along its velocity
MIST_SHARE = 0.           # of the duck's mist (sub-millimetre drizzle a pond splash raises)
LAUNCH_LIMIT = 2.         # drops leave at most this many times the apple's impact speed: at 3 mm the
                          # simulation throws far more water at first contact than the thin sheet it stands for
APPLE_POINTS = 1200
WALL_MIRROR = 3.0         # particles this many smoothing lengths inside the wall are mirrored across it
HEIGHT_CELL = .05 * SCALE  # landing-height grid
WALL_TUCK = .003          # basin water's surface past the inner wall ends this far inside the wall solid
APPLE_GAP = .003          # water surface this near the apple's sphere meets the apple, and goes in to
APPLE_CORE = .015         # this radius, inside the stem and calyx dimples (2 cm from the centre)
FLOOR_CONTACT = .0015     # its surface this close above the floor is the floor contact, which goes
FLOOR_TUCK = .0085        # this far into the 9 mm floor slab: under the drain's funnel too, or the thin
                          # air left between them reflects totally and shows as a dark patch
SPILL_BAND = .012         # spilled water this close to the basin's outer wall runs down it as a film
PROP_HEIGHT = .04         # spilled water under a prop at most this tall (the 3.4 cm cutting board) is inside it
ON_COUNTER = 2            # spilled particles within this many particle sizes of the counter lie on it
WATER_CELL = .001         # counter water height grid (m)
CONTACT_ANGLE = 60        # degrees; a landed droplet's bead meets the sealed stone or oiled wood at this,
PROP_CONTACT_ANGLE = 80   # and the soda maker's paint and glass or the peppers' wax at this
WATER_MIN = 1e-5          # m; water thinner than this is dry
WET_CELL = .001           # outer wall map grid (m)
WALL_BLUR = (.004, .008)  # m; water running down the outer wall is smoothed around and down it,
WET_SHEET = .5            # and wets it fully at this fraction of one particle per dx^2
LANDING_REACH = .01       # m; spilled water stops at most this far from where it first touched down
ESCAPE_BAND = 2           # airborne particles this many particle sizes from the domain's walls or top fly on
STICK_STEPS = 24          # each droplet's path over a frame is checked at this many points for the tall things
PUDDLE_BLUR = .003        # m; the volume of the water lying on the counter is spread over this,
PUDDLE_DEPTH = .004       # m; and water deeper than this spreads further (surface tension holds still
PUDDLE_STEPS = 12         # water on stone to a few millimetres), in this many spreading steps
FILM_EASE = .5            # the wall film moves this far towards each frame's running water


def log_uniform_cube(radius):
    """Mean r^3 of a radius drawn log-uniformly from the range."""
    low, high = radius
    return (high ** 3 - low ** 3) / (3 * math.log(high / low))


def scale_stage():
    """Shrink the duck stage's lengths and speeds to the basin; returns the droplet volume ratios.
    Droplets are not scaled down but set to SPLASH_DROPS: a splash crown's rim breaks up at the
    capillary scale, so a basin splash throws millimetre drops as a pond splash does, only fewer, and
    no mist. They leave the crown more nearly along it than the duck's (DROP_SCATTER)."""
    root = math.sqrt(SCALE)
    volume = {}
    for name, size in (('DROP_RADIUS', SPLASH_DROPS), ('MIST_RADIUS', tuple(v * SCALE for v in duck.MIST_RADIUS))):
        old = getattr(duck, name)
        setattr(duck, name, size)
        volume[name] = log_uniform_cube(old) / log_uniform_cube(size)
    duck.DROP_SPREAD = duck.DROP_STRETCH = DROP_SCATTER
    duck.FOAM_RADIUS = tuple(v * SCALE for v in duck.FOAM_RADIUS)
    for name in ('SPRAY_PIECE', 'SPRAY_MIN_HEIGHT', 'SHED_HEIGHT', 'CULL_MARGIN', 'FOAM_PATCH_SPREAD', 'FOAM_DUCK_GAP'):
        setattr(duck, name, getattr(duck, name) * SCALE)
    duck.SPRAY_BAND = tuple(v * SCALE for v in duck.SPRAY_BAND)
    duck.SPRAY_SPEED = tuple(v * root for v in duck.SPRAY_SPEED)
    duck.FOAM_CHURN = tuple(v * root for v in duck.FOAM_CHURN)
    duck.SHED_MIN_SPEED *= root
    return volume


class Ground:
    """The kitchen under the domain (ground_apple_drop_kitchen_basin.py): counter, cutting board, peppers and the
    open sink, as the first surface from above per 4 mm column; the counter outside the map. Under things
    standing taller than the board (the soda maker, the peppers, the tap), the columns' solid layers are
    those things, which droplets meet on their tops, sides or undersides, and base is the ground below
    them (the counter, or the sink under the tap's spout); names[layer_owner] is the thing of each layer."""

    def __init__(self, path):
        with np.load(path) as data:
            self.lower, self.cell = data['lower'], float(data['cell'])
            self.height, self.counter = data['height'], float(data['counter_z'])
            self.layers, self.layer_owner, self.base = data['layers'], data['layer_owner'], data['base']
            self.owner, self.names = data['owner'], [str(name) for name in data['names']]
        self.tall = self.height > self.counter + PROP_HEIGHT

    def index(self, xy):
        index = np.floor((np.asarray(xy) - self.lower) / self.cell).astype(int)
        shape = np.array(self.height.shape)
        inside = np.all((index >= 0) & (index < shape), axis=-1)
        index = np.clip(index, 0, shape - 1)
        return inside, index[..., 0], index[..., 1]

    def __call__(self, xy):
        inside, i, j = self.index(xy)
        return np.where(inside, self.height[i, j], self.counter)

    def floor(self, xy):
        """Where droplets come down: the ground, but the ground below the tall things, which they meet
        as solids instead (a 1.5 cm landing cell over a thing's edge would take them out in mid-air)."""
        inside, i, j = self.index(xy)
        return np.where(inside, np.where(self.tall[i, j], self.base[i, j], self.height[i, j]), self.counter)

    def solid(self, points):
        """Which points are inside a tall thing (in a solid layer of its columns), and the index in names
        of the thing that layer is."""
        inside, i, j = self.index(points[..., :2])
        layers = self.layers[i, j]
        z = points[..., 2, None]
        within = (z >= layers[..., 0]) & (z <= layers[..., 1])
        layer = within.argmax(axis=-1)[..., None]
        return (inside & self.tall[i, j] & within.any(axis=-1),
                np.take_along_axis(self.layer_owner[i, j], layer, axis=-1)[..., 0])


class Heights:
    """Highest attached-water or apple point per grid column, never below the kitchen, the basin rim or
    the basin floor under it. Water heights spread to neighbouring columns inside the basin only, so
    droplets that fall past the rim reach the counter, the board or the bottom of the sink."""

    def __init__(self, points, lower, upper, basin, ground, size=HEIGHT_CELL):
        self.lower, self.size = np.asarray(lower[:2], dtype=np.float64), size
        self.shape = tuple(np.ceil((np.asarray(upper[:2]) - self.lower) / size).astype(int) + 1)
        height = np.full(self.shape, -np.inf)
        np.maximum.at(height, self.cells(points), points[:, 2])
        centre = self.lower + (np.stack(np.indices(self.shape), -1) + .5) * size
        radius = np.hypot(centre[..., 0] - basin['center_m'][0], centre[..., 1] - basin['center_m'][1])
        inside = radius < basin['outer_radius_m'] + size
        height = np.where(inside, maximum_filter(height, size=3, mode='nearest'), height)
        floor = np.where(radius < basin['inner_radius_m'], basin['bottom_z_m'],
                         np.where(radius < basin['outer_radius_m'], basin['rim_z_m'], ground.floor(centre)))
        self.height = np.maximum(height, floor)

    def cells(self, points):
        index = np.floor((points[:, :2] - self.lower) / self.size).astype(int)
        return np.clip(index[:, 0], 0, self.shape[0] - 1), np.clip(index[:, 1], 0, self.shape[1] - 1)

    def __call__(self, points):
        return self.height[self.cells(points)]


def mirror(points, velocity, basin, band):
    """Images across the basin's inner wall of the points within band inside it, below the rim."""
    cx, cy = basin['center_m']
    wall = basin['inner_radius_m']
    offset = points[:, :2] - (cx, cy)
    radius = np.linalg.norm(offset, axis=1)
    near = (radius > wall - band) & (radius < wall) & (points[:, 2] < basin['rim_z_m'])
    unit = offset[near] / radius[near, None]
    image, speed = points[near].copy(), velocity[near].copy()
    image[:, :2] += 2 * (wall - radius[near])[:, None] * unit
    speed[:, :2] -= 2 * np.einsum('nd,nd->n', speed[:, :2], unit)[:, None] * unit
    return image, speed


class BasinFoam(duck.Foam):
    """Foam on the basin water only. The duck stage seats bubbles at the top of the nearest water, which
    for a droplet landing on the counter is the basin's surface, beside the outer wall."""

    def __init__(self, basin):
        super().__init__()
        self.centre, self.wall = np.asarray(basin['center_m']), basin['inner_radius_m']

    def inside(self, points):
        return np.linalg.norm(np.asarray(points)[:, :2] - self.centre, axis=1) < self.wall

    def spawn(self, points, surface, rng, patch):
        super().spawn(np.asarray(points)[self.inside(points)] if len(points) else points, surface, rng, patch)

    def advance(self, duration, surface, duck_points, lower, upper):
        super().advance(duration, surface, duck_points, lower, upper)
        keep = np.linalg.norm(self.position[:, :2] - self.centre, axis=1) < self.wall - self.radius
        self.position, self.velocity = self.position[keep], self.velocity[keep]
        self.radius, self.age, self.life = self.radius[keep], self.age[keep], self.life[keep]


class Drops(duck.Flying):
    """Spray droplets or mist landing on the kitchen beyond the simulated domain too (where the duck stage
    has a flat deck): on the counter, into the sink, off the counter's edge. Keeps where the droplets
    that landed this frame came down, and their sizes. Droplets that fly into a thing standing taller
    than the board (the soda maker, the peppers, the tap) stick where their path met it: a 1-2.5 mm drop
    beads up on painted metal, glass, glaze or waxy skin and hangs on through the clip. Keeps those
    beads, and the ones resting on the counter or the board, with the thing each one is on and the
    angle it meets it at."""

    def __init__(self, ground, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.ground = ground
        self.before = self.position
        self.stuck = np.zeros((0, 3)), np.zeros(0), np.zeros(0, np.int16), np.zeros(0)

    def rest(self, position, radius, owner, angle):
        """Beads of these sizes from now on, at these points on these things (indices in names)."""
        self.stuck = tuple(np.concatenate([old, new]) for old, new in zip(
            self.stuck, (position, radius, owner, np.full(len(radius), float(angle)))))

    def advance(self, duration):
        self.before = self.position.copy()
        super().advance(duration)

    def stick(self):
        """Droplets whose path over the frame entered a tall thing stop at the last point outside it."""
        before = self.before if len(self.before) == len(self.position) else self.position
        path = before[:, None] + np.linspace(0, 1, STICK_STEPS)[:, None] * (self.position - before)[:, None]
        inside, owner = self.ground.solid(path)
        hit = inside.any(axis=1)
        if hit.any():
            rows = np.flatnonzero(hit)
            first = inside[rows].argmax(axis=1)
            self.rest(path[rows, np.maximum(first - 1, 0)], self.radius[rows], owner[rows, first], PROP_CONTACT_ANGLE)
        return hit

    def save_stuck(self, path):
        position, radius, owner, angle = self.stuck
        np.savez(path, position=position.astype(np.float32), radius=radius.astype(np.float32), owner=owner,
                 angle=angle.astype(np.float32), names=np.array(self.ground.names))

    def beads(self):
        return {self.ground.names[k]: int(n) for k, n in enumerate(np.bincount(self.stuck[2])) if n}

    def add(self, position, velocity, radius):
        """Droplets as they are, not strung out from a source."""
        self.position = np.concatenate([self.position, position])
        self.velocity = np.concatenate([self.velocity, velocity])
        self.radius = np.concatenate([self.radius, np.full(len(position), radius)])
        self.age = np.concatenate([self.age, np.zeros(len(position))])
        self.life = np.concatenate([self.life, np.full(len(position), np.inf)])

    def cull(self, heights, lower, upper):
        hit = self.stick()
        inside = np.all((self.position[:, :2] >= lower[:2]) & (self.position[:, :2] <= upper[:2]), axis=1)
        floor = np.where(inside, heights(self.position), self.ground.floor(self.position[:, :2]))
        landed = ~hit & (self.position[:, 2] < floor + duck.CULL_MARGIN) & (self.velocity[:, 2] < 0)
        self.touched = self.position[landed], self.radius[landed]
        keep = ~hit & ~landed & (self.position[:, 2] > floor) & (self.age < duck.MAX_AGE) & (self.age < self.life)
        self.position, self.velocity = self.position[keep], self.velocity[keep]
        self.radius, self.age, self.life = self.radius[keep], self.age[keep], self.life[keep]
        return self.touched[0]


class CounterWater:
    """Water lying on the counter and the cutting board, as its height above them on a WATER_CELL grid
    over the ground map (wider than the simulation, so droplets that fly further still land on it). The
    puddle: every spilled particle that came down there keeps its volume where it stopped, spread over
    PUDDLE_BLUR, and wherever that is deeper than PUDDLE_DEPTH the excess spreads on outwards. Water stays
    where it landed and nothing dries within the clip, so the map only grows and cannot flicker with the
    particles. The render reads it in the stone's and wood's materials (a clear coat shaped by the
    water's surface): a transparent sheet lying on them traps light between its underside and the stone
    and glows in the stone's colour. A droplet that lands stays as a bead, but a bead is a lens: as a
    coat it can only reflect, and on the bright board it showed as a grey blob. The beads are drawn as
    water (Drops.rest); this only picks the droplets that came to rest here."""

    def __init__(self, ground, basin):
        self.lower = np.asarray(ground.lower, dtype=np.float64)
        self.shape = tuple(np.round(np.array(ground.height.shape) * ground.cell / WATER_CELL).astype(int))
        centre = self.lower + (np.stack(np.indices(self.shape), -1) + .5) * WATER_CELL
        self.level = ground(centre)
        radius = np.hypot(centre[..., 0] - basin['center_m'][0], centre[..., 1] - basin['center_m'][1])
        # Not the basin, the sink or the peppers, and not across the board's edge.
        self.allowed = ((radius > basin['outer_radius_m']) & (self.level > ground.counter - .01)
                        & (self.level < ground.counter + PROP_HEIGHT)
                        & (maximum_filter(self.level, size=3) - self.level < .002))
        self.bead_volume = 0.

    def cells(self, xy):
        index = np.floor((np.asarray(xy)[:, :2] - self.lower) / WATER_CELL).astype(int)
        return np.clip(index[:, 0], 0, self.shape[0] - 1), np.clip(index[:, 1], 0, self.shape[1] - 1)

    def land(self, position, radius):
        """The droplets that came down on the counter or the board, a millimetre above its surface (a fast
        one is culled past it; the render seats beads on the nearest surface, from the side they are on),
        and their sizes."""
        cell = self.cells(position)
        on = self.allowed[cell] & (position[:, 2] < self.level[cell] + .01)
        self.bead_volume += float((4 / 3 * math.pi * radius[on] ** 3).sum())
        rest = position[on].copy()
        rest[:, 2] = self.level[cell[0][on], cell[1][on]] + .001
        return rest, radius[on]

    def depth(self, xy, volume):
        """The puddle's height: of the particles that came down at xy, each holding volume."""
        count = np.zeros(self.shape, np.float32)
        np.add.at(count, self.cells(xy), 1)
        puddle = gaussian_filter(count, PUDDLE_BLUR / WATER_CELL) * volume / WATER_CELL ** 2
        for _ in range(PUDDLE_STEPS):
            excess = np.maximum(puddle - PUDDLE_DEPTH, 0)
            if not excess.any():
                break
            puddle += gaussian_filter(excess, PUDDLE_BLUR / WATER_CELL) - excess
        puddle = np.where(self.allowed, puddle, 0)
        return puddle, {
            'puddle_ml': float(puddle.sum() * WATER_CELL ** 2 * 1e6), 'puddle_max_mm': float(puddle.max() * 1e3),
            'beads_ml': self.bead_volume * 1e6, 'wet_area_m2': float((puddle > WATER_MIN).sum() * WATER_CELL ** 2)}

    def arrays(self, depth):
        return {'water_mm': (depth * 1e3).astype(np.float16), 'lower': self.lower, 'cell': WATER_CELL}


class WallWetMap:
    """Water running down the basin's outer wall, on a WET_CELL grid around it (columns by angle from
    -pi, rows by height from the counter). The film: the depth of the water running there now, spread
    over WALL_BLUR (around, down) and easing towards each frame's by FILM_EASE. Wetness: where the film
    has been, which only grows, so a sheet running down leaves a wet streak. Both are maps the render
    reads in the wall's material: a sheet a fraction of a millimetre off the wall would show its edges."""

    def __init__(self, basin, counter, dx, volume):
        self.centre, self.radius = np.asarray(basin['center_m']), basin['outer_radius_m']
        self.bottom, self.volume = counter, volume
        self.shape = (int(round(2 * math.pi * self.radius / WET_CELL)),
                      int(math.ceil((basin['rim_z_m'] - counter) / WET_CELL)) + 1)
        self.sheet = WET_SHEET * (WET_CELL / dx) ** 2
        self.wet = np.zeros(self.shape, np.float32)
        self.film = np.zeros(self.shape, np.float32)

    def soak(self, points):
        count = np.zeros(self.shape, np.float32)
        if len(points):
            angle = np.arctan2(points[:, 1] - self.centre[1], points[:, 0] - self.centre[0])
            i = np.floor((angle + math.pi) / (2 * math.pi) * self.shape[0]).astype(int) % self.shape[0]
            j = np.clip(np.floor((points[:, 2] - self.bottom) / WET_CELL).astype(int), 0, self.shape[1] - 1)
            np.add.at(count, (i, j), 1)
        spread = gaussian_filter(count, tuple(blur / WET_CELL for blur in WALL_BLUR), mode=('wrap', 'nearest'))
        self.film += FILM_EASE * (spread * self.volume / WET_CELL ** 2 - self.film)
        cover = np.clip(spread / self.sheet, 0, 1)
        self.wet = np.maximum(self.wet, cover * cover * (3 - 2 * cover))

    def stats(self):
        return {'wall_film_ml': float(self.film.sum() * WET_CELL ** 2 * 1e6), 'wall_film_max_mm': float(self.film.max() * 1e3)}

    def arrays(self):
        return {'wall': self.wet.astype(np.float16), 'wall_film_mm': (self.film * 1e3).astype(np.float16),
                'wall_bottom': self.bottom, 'wall_radius': self.radius, 'wall_centre': self.centre}

    def area(self):
        return float(self.wet.sum() * WET_CELL ** 2)


def gone(x, ground, basin, dx):
    """Particles not meshed; which of them came down on the counter or the board; which run down the
    basin's outer wall; which fell into the open sink. The flat simulated counter keeps water the
    kitchen would not: resting where the counter is really the open sink (it fell in) or inside the
    cutting board (in the kitchen it lies on the board). Spilled water lying on the counter or the
    board, or running down within SPILL_BAND of the outer wall, is drawn from maps of it instead: as
    3 mm particles it would show as beads and lenses."""
    level = ground(x[:, :2])
    counter = ground.counter
    sunk = (level < counter - .01) & (x[:, 2] < counter + 2 * dx)
    buried = (level > counter + .003) & (level < counter + PROP_HEIGHT) & (x[:, 2] + dx / 2 < level)
    radius = np.hypot(x[:, 0] - basin['center_m'][0], x[:, 1] - basin['center_m'][1])
    outer = basin['outer_radius_m']
    spilled = radius > .5 * (basin['inner_radius_m'] + outer)
    lying = spilled & ~sunk & ~buried & (x[:, 2] < level + ON_COUNTER * dx) & (level > counter - .01)
    clinging = spilled & ~lying & (radius < outer + SPILL_BAND) & (x[:, 2] < basin['rim_z_m'])
    return sunk | buried | lying | clinging, lying | buried, clinging, sunk


def tuck(vertices, kept, images, basin, apple_centre, apple_radius):
    """The surface of basin water continues through the inner wall (the mirror images, reaching out past
    the outer face too) and under its floor: move those parts into the basin's solid wall and floor
    slab, where the basin hides them. Water outside the basin or above the rim (owned by particles
    there) is left alone; surface drawn round an image always belongs to the basin water."""
    centre = np.asarray(basin['center_m'])
    wall, outer = basin['inner_radius_m'], basin['outer_radius_m']
    sources = np.concatenate([kept, images])
    _, nearest = cKDTree(sources).query(vertices, workers=duck.WORKERS)
    # Water at the wall sits on its inner face (r = wall to float precision); spilled water outside the
    # basin sits at or beyond its outer face.
    owned = (nearest >= len(kept)) | (np.linalg.norm(sources[nearest, :2] - centre, axis=1) < .5 * (wall + outer))
    offset = vertices[:, :2] - centre
    radius = np.linalg.norm(offset, axis=1)
    past = owned & (radius > wall + WALL_TUCK) & (vertices[:, 2] < basin['rim_z_m'])
    vertices[past, :2] = centre + offset[past] / radius[past, None] * (wall + WALL_TUCK)
    floor = owned & (radius < wall + WALL_TUCK) & (vertices[:, 2] < basin['bottom_z_m'] + FLOOR_CONTACT)
    vertices[floor, 2] = np.minimum(vertices[floor, 2], basin['bottom_z_m'] - FLOOR_TUCK)
    # The water keeps clear of the simulated sphere, but the apple is dimpled at the stem and the calyx and
    # meets the water closer than that: the gap would show as air under it and white slivers at the
    # waterline. Water surface this near the sphere goes deep inside it, where the apple's skin hides it,
    # so the water fills the dimples.
    offset = vertices - apple_centre
    distance = np.linalg.norm(offset, axis=1)
    hugging = distance < apple_radius + APPLE_GAP
    vertices[hugging] = apple_centre + offset[hugging] / distance[hugging, None] * APPLE_CORE
    return {'tucked_wall': int(past.sum()), 'tucked_floor': int(floor.sum()), 'tucked_apple': int(hugging.sum())}


def apple_points(center, radius):
    index = np.arange(APPLE_POINTS) + 0.5
    polar = np.arccos(1 - 2 * index / APPLE_POINTS)
    azimuth = math.pi * (1 + 5 ** 0.5) * index
    unit = np.stack([np.cos(azimuth) * np.sin(polar), np.sin(azimuth) * np.sin(polar), np.cos(polar)], 1)
    return np.asarray(center, dtype=np.float64) + radius * unit


def frame_list(text):
    return sorted({frame for part in text.split(',') for frame in range(int(part.split('-')[0]), int(part.split('-')[-1]) + 1)})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('run', type=Path)
    parser.add_argument('--frames', default='1-96', help='Frames whose spray, mist and foam are written.')
    parser.add_argument('--surfaces', help='Frames whose surface this process meshes (default: --frames).')
    parser.add_argument('--write-particles', action='store_true', help='This process writes spray/mist/foam.')
    parser.add_argument('--part', default='0')
    args = parser.parse_args()
    numba.set_num_threads(min(32, numba.config.NUMBA_NUM_THREADS))
    droplet_volume = scale_stage()
    wanted = frame_list(args.frames)
    surfaces = set(frame_list(args.surfaces)) if args.surfaces else set(wanted)
    run = args.run.resolve()
    info = json.loads((run / 'simulation_report.json').read_text())['info']
    dx, basin, apple_radius = info['dx_m'], info['basin'], info['apple']['radius_m']
    h = 2 * dx
    cx, cy = basin['center_m']
    half = info['domain_half_m']
    duck.DECK_Z = info['counter_z_m']
    ground = Ground(run / 'ground.npz')
    lower = np.array([cx - half, cy - half, info['counter_z_m']])
    upper = np.array([cx + half, cy + half, info['domain_top_m']])
    with np.load(run / 'particles' / 'frame_0001.npz') as data:
        still_level = float(np.percentile(data['water_pos'][:, 2], 99.5)) + dx / 2
    mass, area = (dx / DUCK_DX) ** 3, (dx / DUCK_DX) ** 2
    counts_per = {'drops_per_torn': duck.DROPS_PER_TORN * mass * droplet_volume['DROP_RADIUS'],
                  'mist_per_torn': duck.MIST_PER_TORN * mass * droplet_volume['MIST_RADIUS'] * MIST_SHARE,
                  'shed_per_frame': duck.SHED_PER_FRAME * mass * droplet_volume['DROP_RADIUS'],
                  'mist_per_frame': duck.MIST_PER_FRAME * mass * droplet_volume['MIST_RADIUS'] * MIST_SHARE,
                  'foam_rate': duck.FOAM_RATE * area / SCALE ** 2}
    shed_speed = 3 * math.sqrt(SCALE)  # shedding reaches the duck's per-frame rate at this speed
    impact = math.sqrt(-2 * duck.GRAVITY[2] * (info['apple']['start_m'][2] - apple_radius - still_level))

    def launched(velocity):
        speed = np.linalg.norm(velocity, axis=1, keepdims=True)
        return velocity * np.minimum(1, LAUNCH_LIMIT * impact / np.maximum(speed, 1e-9))
    out = run / 'aniso'
    out.mkdir(exist_ok=True)
    report = {'dx_m': dx, 'still_level_m': still_level, 'scale': SCALE, 'scaled_counts': counts_per,
              'scaled_stage': {name: getattr(duck, name) for name in (
                  'DROP_RADIUS', 'MIST_RADIUS', 'FOAM_RADIUS', 'SPRAY_PIECE', 'SPRAY_BAND', 'SPRAY_MIN_HEIGHT',
                  'SHED_HEIGHT', 'CULL_MARGIN', 'FOAM_PATCH_SPREAD', 'FOAM_DUCK_GAP', 'SPRAY_SPEED', 'FOAM_CHURN',
                  'SHED_MIN_SPEED', 'DECK_Z')},
              'duck_stage': str(Path(duck.__file__).resolve()), 'frames': {}}
    report_path = out / f'report_{args.part}.json'
    drops = Drops(ground, dx, duck.DROP_RADIUS)
    mist = Drops(ground, dx, duck.MIST_RADIUS, terminal=duck.MIST_TERMINAL, life=duck.MIST_LIFE)
    foam = BasinFoam(basin)
    counter_water = CounterWater(ground, basin)
    wall = WallWetMap(basin, info['counter_z_m'], dx, info['particle_volume_m3'])
    converted = None
    last = max(max(wanted), max(surfaces))
    for frame in range(1, last + 1):
        tick = time.monotonic()
        with np.load(run / 'particles' / f'frame_{frame:04d}.npz') as data:
            x, v = data['water_pos'].astype(np.float64), data['water_vel'].astype(np.float64)
            apple_centre = data['ball_center']
            apple = apple_points(apple_centre, apple_radius)
        if converted is None:
            converted, escaped, before = np.zeros(len(x), bool), np.zeros(len(x), bool), v
            landing, resting = np.full((len(x), 2), np.nan), np.full((len(x), 2), np.nan)
        tree = cKDTree(x)
        counts = tree.query_ball_point(x, .999 * h, return_length=True, workers=duck.WORKERS) - 1
        lost, soaking, clinging, sunk = gone(x, ground, basin, dx)
        # The simulated domain is a box: water thrown far enough meets its walls (or its top) and runs along them.
        # Water that has not come down on the counter before flies on as a droplet of its own volume, with
        # the velocity it had before it met the wall, and lands on the kitchen wherever that takes it.
        band = ESCAPE_BAND * dx
        at_wall = np.any((x[:, :2] < lower[:2] + band) | (x[:, :2] > upper[:2] - band), axis=1) | (x[:, 2] > upper[2] - band)
        leaving = at_wall & ~escaped & np.isnan(landing[:, 0])
        drops.add(x[leaving], launched(before[leaving]), (3 * info['particle_volume_m3'] / (4 * math.pi)) ** (1 / 3))
        escaped |= leaving
        before = v
        lost, soaking, clinging = lost | escaped, soaking & ~escaped, clinging & ~escaped
        wall.soak(x[clinging])
        # The simulated counter has no friction or contact line, so spilled water slides on as a single
        # layer of particles until the domain's walls stop it. Real water stops within a splat of where
        # it lands: each particle rests where it is until it is LANDING_REACH from its first touchdown,
        # and there for good. The water it holds stays there unless it slid into the sink.
        touching = soaking & np.isnan(landing[:, 0])
        landing[touching] = x[touching, :2]
        moving = np.flatnonzero(soaking & np.isnan(resting[:, 0]))
        slide = x[moving, :2] - landing[moving]
        reach = np.linalg.norm(slide, axis=1)
        stop = landing[moving] + slide * np.minimum(1, LANDING_REACH / np.maximum(reach, 1e-9))[:, None]
        resting[moving[reach >= LANDING_REACH]] = stop[reach >= LANDING_REACH]
        place = resting.copy()
        place[moving] = stop
        puddled = ~np.isnan(place[:, 0]) & ~sunk
        heights = Heights(np.concatenate([x[(counts >= 9) & ~lost], apple]) + [0, 0, dx / 2], lower, upper, basin, ground)
        torn = duck.torn_particles(tree, x, counts, h)
        surface_now = duck.Surface(x[~lost], v[~lost], counts[~lost], still_level, dx)
        rng = np.random.default_rng(duck.SEED + frame)
        if frame > 1:
            drops.advance(1 / duck.FPS)
            mist.advance(1 / duck.FPS)
            foam.advance(1 / duck.FPS, surface_now, apple, lower, upper)
        landed = drops.cull(heights, lower, upper)
        bead, size = counter_water.land(*drops.touched)
        _, i, j = ground.index(bead[:, :2])
        drops.rest(bead, size, ground.owner[i, j], CONTACT_ANGLE)
        mist.cull(heights, lower, upper)
        foam.spawn(landed[rng.uniform(size=len(landed)) < duck.FOAM_FROM_LANDING], surface_now, rng, duck.FOAM_LANDING_PATCH)
        clearance = x[:, 2] - heights(x)
        new = torn & ~converted & ~escaped & (clearance > 0)
        converted = (converted | new) & torn
        speed = np.linalg.norm(v, axis=1)
        energy = np.clip((speed[new] - duck.SPRAY_SPEED[0]) / (duck.SPRAY_SPEED[1] - duck.SPRAY_SPEED[0]), 0, 1) \
            * (clearance[new] > duck.SPRAY_MIN_HEIGHT)
        drops.emit(x[new], launched(v[new]), rng.poisson(counts_per['drops_per_torn'] * energy), rng,
                   duck.DROP_ALONG, duck.DROP_ACROSS, duck.DROP_SPREAD, duck.DROP_STRETCH)
        mist.emit(x[new], v[new], rng.poisson(counts_per['mist_per_torn'] * energy), rng, .5, 1., duck.MIST_SPREAD, .2,
                  duck.MIST_SLOWDOWN)
        shedding = (~converted & ~escaped & (counts >= 1) & (counts <= duck.SHED_NEIGHBOURS) & (speed > duck.SHED_MIN_SPEED)
                    & (x[:, 2] > still_level + duck.SHED_HEIGHT))
        rate = np.clip(speed[shedding] / shed_speed, 0, 1.5)
        drops.emit(x[shedding], launched(v[shedding]), rng.poisson(counts_per['shed_per_frame'] * rate), rng,
                   duck.DROP_ALONG, duck.DROP_ACROSS, duck.DROP_SPREAD, duck.DROP_STRETCH)
        mist.emit(x[shedding], v[shedding], rng.poisson(counts_per['mist_per_frame'] * rate), rng, .5, 1.,
                  duck.MIST_SPREAD, .2, duck.MIST_SLOWDOWN)
        top, _ = surface_now.sample(surface_now.points[:, :2])
        layer = surface_now.points[:, 2] > top - dx / 2 - .02 * SCALE
        points, flow = surface_now.points[layer], surface_now.velocity[layer]
        _, neighbour = cKDTree(points).query(points, k=9, workers=duck.WORKERS)
        churn = np.linalg.norm(flow[neighbour[:, 1:]] - flow[:, None, :], axis=2).mean(axis=1)
        churn = rng.poisson(counts_per['foam_rate'] * np.clip((churn - duck.FOAM_CHURN[0]) / (duck.FOAM_CHURN[1] - duck.FOAM_CHURN[0]), 0, 1))
        foam.spawn(np.repeat(points, churn, axis=0), surface_now, rng, duck.FOAM_PATCH)
        foam.advance(0., surface_now, apple, lower, upper)
        record = {'torn_new': int(new.sum()), 'hidden': int(converted.sum()), 'shedding': int(shedding.sum()),
                  'drops': len(drops.radius), 'mist': len(mist.radius), 'foam': len(foam.radius),
                  'gone': int(lost.sum()), 'escaped': int(escaped.sum()), 'spots_landed': len(size),
                  'beads': drops.beads()}
        if args.write_particles and frame in wanted:
            drops.save(out / f'spray_{frame:04d}.npz')
            drops.save_stuck(out / f'beads_{frame:04d}.npz')
            mist.save(out / f'mist_{frame:04d}.npz')
            foam.save(out / f'foam_{frame:04d}.npz')
            depth, water_stats = counter_water.depth(place[puddled], info['particle_volume_m3'])
            np.savez(out / f'wet_{frame:04d}.npz', **counter_water.arrays(depth), **wall.arrays())
            record.update(wall_wet_area_m2=wall.area(), **water_stats, **wall.stats())
        if frame in surfaces:
            kept, flow = x[~converted & ~lost], v[~converted & ~lost]
            images, image_flow = mirror(kept, flow, basin, WALL_MIRROR * h)
            mesh, stats = duck.surface(np.concatenate([kept, images]), np.concatenate([flow, image_flow]), h, dx, still_level)
            stats['wall_images'] = len(images)
            stats.update(tuck(mesh['vertices'], kept, images, basin, apple_centre, apple_radius))
            np.savez(out / f'water_{frame:04d}.npz', **mesh)
            record['surface'] = stats
        record['seconds'] = time.monotonic() - tick
        report['frames'][str(frame)] = record
        duck.save(report_path, report)
        print('SPLASH', args.part, frame, json.dumps(record), flush=True)


if __name__ == '__main__':
    main()
