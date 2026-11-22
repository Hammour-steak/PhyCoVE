"""Shared SI geometry for the rendered spoon and Genesis collision boundary."""
import math
import numpy as np

SPOON_CENTER = np.array((0.060, 0.0, 0.910))
BOWL_RX = 0.039
BOWL_RY = 0.025
BOWL_DEPTH = 0.012
BOWL_THICKNESS = 0.0025
INITIAL_TILT = 15.0
FINAL_TILT = INITIAL_TILT


def rotation_y(degrees):
    a = math.radians(degrees)
    return np.array(((math.cos(a), 0, math.sin(a)), (0, 1, 0),
                     (-math.sin(a), 0, math.cos(a))), dtype=float)


def tilt_at(playback_s):
    return INITIAL_TILT


def bowl_mesh(rings=16, sides=96):
    verts, faces = [], []
    for shell in (0, 1):
        base = len(verts)
        verts.append((0, 0, -BOWL_DEPTH - shell*BOWL_THICKNESS))
        for i in range(1, rings+1):
            r = i/rings
            for j in range(sides):
                a = 2*math.pi*j/sides
                verts.append((BOWL_RX*r*math.cos(a), BOWL_RY*r*math.sin(a),
                              -BOWL_DEPTH*(1-r*r)-shell*BOWL_THICKNESS))
        for j in range(sides):
            tri = (base, base+1+j, base+1+(j+1)%sides)
            faces.append(tri if shell == 0 else tri[::-1])
        for i in range(rings-1):
            for j in range(sides):
                a = base+1+i*sides+j
                b = base+1+i*sides+(j+1)%sides
                c = base+1+(i+1)*sides+(j+1)%sides
                d = base+1+(i+1)*sides+j
                quads = ((a,d,c), (a,c,b))
                faces.extend(quads if shell == 0 else [q[::-1] for q in quads])
    layer = 1+rings*sides
    rim = 1+(rings-1)*sides
    for j in range(sides):
        a, b = rim+j, rim+(j+1)%sides
        faces.extend(((a,b,b+layer), (a,b+layer,a+layer)))
    return np.asarray(verts), np.asarray(faces, dtype=np.int32)


def initial_reservoir(dx, clearance=0.0022):
    # A slightly domed spoonful within the bowl footprint. The 5 mm central
    # meniscus provides a natural full-spoon initial condition at a fixed tilt.
    # Every particle begins at rest over the bowl; there is no falling strand.
    dome_height = 0.005
    axes = [np.arange(-BOWL_RX, BOWL_RX+dx/2, dx),
            np.arange(-BOWL_RY, BOWL_RY+dx/2, dx),
            np.arange(-BOWL_DEPTH+clearance, dome_height+dx/2, dx)]
    p = np.stack(np.meshgrid(*axes, indexing="ij"), axis=-1).reshape(-1,3)
    r2 = (p[:,0]/BOWL_RX)**2 + (p[:,1]/BOWL_RY)**2
    floor = -BOWL_DEPTH*(1-r2)
    world = p @ rotation_y(INITIAL_TILT).T + SPOON_CENTER
    keep = ((r2 < 0.94**2) & (p[:,2] >= floor+clearance) &
            (p[:,2] <= dome_height*(1-r2)-0.0008))
    return world[keep].astype(np.float32)
