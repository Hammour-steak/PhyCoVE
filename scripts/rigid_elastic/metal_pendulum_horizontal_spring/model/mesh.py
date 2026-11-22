"""Smooth visual tube over solved wire samples; no force or state modification."""

import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np


def tube(centerline, radius, radial=16, subdiv=3):
    p = np.asarray(centerline, dtype=float)
    if len(p) == 0:
        return np.empty((0, 3)), np.empty((0, 4), dtype=int)
    padded = np.vstack([2 * p[0] - p[1], p, 2 * p[-1] - p[-2]])
    samples = []
    for i in range(len(p) - 1):
        a, b, c, d = padded[i : i + 4]
        v0 = (c - a) / 2
        v1 = (d - b) / 2
        for t in np.arange(subdiv) / subdiv:
            samples.append(
                (2 * t**3 - 3 * t**2 + 1) * b
                + (t**3 - 2 * t**2 + t) * v0
                + (-2 * t**3 + 3 * t**2) * c
                + (t**3 - t**2) * v1
            )
    samples = np.vstack([samples, p[-1]])
    tang = np.gradient(samples, axis=0)
    tang /= np.linalg.norm(tang, axis=1)[:, None]
    ref = (
        np.array([0.0, 0.0, 1.0])
        if abs(tang[0, 2]) < 0.9
        else np.array([1.0, 0.0, 0.0])
    )
    normal = np.cross(tang[0], ref)
    normal /= np.linalg.norm(normal)
    verts = []
    for point, tan in zip(samples, tang):
        normal -= tan * np.dot(tan, normal)
        normal /= np.linalg.norm(normal)
        bi = np.cross(tan, normal)
        for angle in np.arange(radial) * 2 * np.pi / radial:
            verts.append(point + radius * (normal * np.cos(angle) + bi * np.sin(angle)))
    faces = []
    for i in range(len(samples) - 1):
        for j in range(radial):
            faces.append(
                (
                    i * radial + j,
                    i * radial + (j + 1) % radial,
                    (i + 1) * radial + (j + 1) % radial,
                    (i + 1) * radial + j,
                )
            )
    # All quads, including degenerate quad fans at the two small end caps.
    for j in range(1, radial - 1):
        faces.append((0, j + 1, j, j))
    end = (len(samples) - 1) * radial
    for j in range(1, radial - 1):
        faces.append((end, end + j, end + j + 1, end + j + 1))
    return np.asarray(verts), np.asarray(faces, dtype=int)
