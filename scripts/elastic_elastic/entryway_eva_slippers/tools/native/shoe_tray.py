"""One watertight bevelled tray surface shared by collision and rendering."""
import numpy as np


def affine_energy(transform, velocity, mass_data, gravity):
    """Exact native dyadic kinetic energy and OrthoPotential shape energy."""
    matrix = transform[:3, :3]
    linear = velocity[:3, 3]
    gradient = velocity[:3, :3]
    mass = mass_data["mass_kg"]
    first = np.asarray(mass_data["first_mass_moment_kg_m"])
    second = np.asarray(mass_data["second_mass_moment_kg_m2"])
    kinetic = 0.5 * (mass * np.dot(linear, linear)
                     + 2 * linear @ gradient @ first
                     + np.trace(gradient @ second @ gradient.T))
    center = matrix @ (first / mass) + transform[:3, 3]
    potential = mass * gravity * center[2]
    orthogonal_error = np.linalg.norm(matrix.T @ matrix - np.eye(3))
    elastic = mass_data["kappa_pa"] * mass_data["volume_m3"] * orthogonal_error ** 2
    return float(kinetic), float(potential), float(elastic), center, float(orthogonal_error)


def tray_mesh(physics):
    width, length, height = physics["tray_dimensions_m"]
    deck = physics["tray_deck_height_m"]
    rim = physics["tray_rim_width_m"]
    bevel = 0.0025
    radius = 0.022
    rings = [
        (bevel, 0.0), (0.0, bevel), (0.0, height - bevel),
        (bevel, height), (rim - bevel, height), (rim, height - bevel),
        (rim, deck + bevel), (rim + bevel, deck),
    ]
    vertices = []
    for inset, z in rings:
        for sign_x, sign_y, start in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
            for angle in np.deg2rad(np.linspace(start, start + 90, 8)):
                vertices.append([
                    sign_x * (width / 2 - radius) + (radius - inset) * np.cos(angle),
                    sign_y * (length / 2 - radius) + (radius - inset) * np.sin(angle),
                    z,
                ])
    count = 32
    faces = []
    for ring in range(len(rings) - 1):
        for j in range(count):
            a = ring * count + j
            b = ring * count + (j + 1) % count
            faces.extend([(a, b, b + count), (a, b + count, a + count)])
    bottom, top = len(vertices), len(vertices) + 1
    vertices.extend([(0, 0, 0), (0, 0, deck)])
    last = (len(rings) - 1) * count
    for j in range(count):
        k = (j + 1) % count
        faces.extend([(bottom, k, j), (top, last + j, last + k)])
    center = np.array(physics["tray_center_m"])
    center[2] -= height / 2
    return np.array(vertices) + center, np.array(faces, dtype=np.int32)
