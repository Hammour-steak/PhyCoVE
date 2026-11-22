"""Fixed geometry of the tabletop press: foam block, platen, ramp, flag and the tetrahedral foam mesh (SI units)."""

import math

import numpy as np

G = 9.81
FOAM_SIZE = np.array([0.032, 0.032, 0.040])
FOAM_BOTTOM = 0.0083
PLATE_BOTTOM = 0.0487
PLATE_MASS = 0.018
BALL_MASS = 0.1347
RADIUS = 0.016
BALL_K = 40000.0
Hinge_X = 0.052
Hinge_Z = 0.0457
EDGE_X = 0.040
FLAG_MASS = 0.003
FLAG_COM = 0.006
FLAG_INERTIA = FLAG_MASS * (0.070**2 / 12 + FLAG_COM**2)
RAMP_ANGLE = math.atan2(0.036, 0.180)
RAMP_LENGTH = math.hypot(0.036, 0.180)
RAMP_ACCEL = (5 / 7) * G * math.sin(RAMP_ANGLE)
EXIT_TIME = math.sqrt(2 * RAMP_LENGTH / RAMP_ACCEL)
EXIT_SPEED = RAMP_ACCEL * EXIT_TIME
RAMP_END = np.array([-0.034, 0.070]) + RADIUS * np.array([math.sin(RAMP_ANGLE), math.cos(RAMP_ANGLE)])


def rolling_state(t):
    length = 0.5 * RAMP_ACCEL * t**2
    tangent = np.array([math.cos(RAMP_ANGLE), -math.sin(RAMP_ANGLE)])
    return RAMP_END - (RAMP_LENGTH - length) * tangent, RAMP_ACCEL * t * tangent


def tetrahedral_box(cells):
    nx, ny, nz = cells
    axes = [np.linspace(-d / 2, d / 2, n + 1) for d, n in zip(FOAM_SIZE, cells)]
    axes[2] += FOAM_BOTTOM + FOAM_SIZE[2] / 2
    vertices = np.array([[x, y, z] for z in axes[2] for y in axes[1] for x in axes[0]])

    def node(i, j, k):
        return k * (ny + 1) * (nx + 1) + j * (nx + 1) + i

    tets = []
    for k in range(nz):
        for j in range(ny):
            for i in range(nx):
                a, b, c, d, e, f, g, h = (
                    node(i, j, k), node(i + 1, j, k), node(i + 1, j + 1, k),
                    node(i, j + 1, k), node(i, j, k + 1), node(i + 1, j, k + 1),
                    node(i + 1, j + 1, k + 1), node(i, j + 1, k + 1),
                )
                tets.extend(((a, b, c, g), (a, c, d, g), (a, d, h, g),
                             (a, h, e, g), (a, e, f, g), (a, f, b, g)))
    tets = np.asarray(tets, np.int32)
    faces = {}
    for a, b, c, d in tets:
        for face in ((a, c, b), (a, b, d), (b, c, d), (c, a, d)):
            key = tuple(sorted(face))
            if key in faces:
                del faces[key]
            else:
                faces[key] = face
    return vertices, tets, np.array(list(faces.values()), np.int32)

# Cup contact friction and steel-on-wood rolling resistance used by the coupled contact model.
FRICTION = 0.20
ROLLING_LENGTH = 0.00015
