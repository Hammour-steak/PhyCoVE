"""Static precompression and passive release of a McQueen-sized toy car.

The coil's axial stiffness is derived from wire geometry. Its distributed inertia
is reduced to m/3 at the sliding plate. MuJoCo evolves the plate, a free chassis,
four freely rotating wheels, and the free block; no actuator or motion keyframe
exists. The visible helix is reconstructed from the solved axial displacement.
This is an uncalibrated structural surrogate, not measured product ground truth.
The first sample is a zero-velocity static preload configuration. Only its
preparation latch is released at t=0; no launch velocity or impulse is inserted.
"""
from __future__ import annotations

import copy
import hashlib
import json
import math
import os
from pathlib import Path
import time
import xml.etree.ElementTree as ET

os.environ.setdefault("MUJOCO_GL", "disable")
import mujoco
import numpy as np

HERE = Path(__file__).resolve().parent
CASE_DIR = HERE.parent
ASSET_ROOT = Path(os.environ.get("PCVE_ASSETS_DIR", CASE_DIR.parents[2] / "assets"))
DEFAULT_GEOMETRY = ASSET_ROOT / "scenes" / "spring_car_collision" / "canonical_geometry" / "car_geometry.json"
LOADED_PHYSICS_SOURCE = (HERE/"physics_model.py").read_bytes()
LOADED_CLI_SOURCE = (CASE_DIR/"simulate_spring_car_collision.py").read_bytes()
LOADED_SPEC_SOURCE = (CASE_DIR / "scene_spec.json").read_bytes()
SCENE_ID = "spring_car_collision"
EXPECTED_MUJOCO_VERSION = "3.3.7"
WHEEL_NAMES = ("front_left", "front_right", "rear_left", "rear_right")

SPEC = json.loads((CASE_DIR / "scene_spec.json").read_text(encoding="utf-8"))
BASELINE = copy.deepcopy(SPEC["baseline"])
CASE_OVERRIDES = copy.deepcopy(SPEC["cases"])


def json_save(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False, allow_nan=False)+"\n", encoding="utf-8")


def require_mujoco_runtime():
    """Reject solver drift before it can corrupt or destabilize a trajectory."""
    actual = str(mujoco.__version__)
    if actual != EXPECTED_MUJOCO_VERSION:
        raise RuntimeError(
            f"{SCENE_ID} requires mujoco=={EXPECTED_MUJOCO_VERSION}; found {actual}. "
            "Use an isolated environment with the pinned version before simulating."
        )


def spring_geometry(c):
    """Derive coil rate from Young's modulus while keeping coil geometry fixed."""
    d = c["spring_wire_diameter_m"]
    c["spring_shear_modulus_pa"] = c["spring_young_modulus_pa"] / (2 * (1 + c["spring_poisson_ratio"]))
    c["spring_stiffness_n_m"] = (c["spring_shear_modulus_pa"] * d**4
                                  / (8 * c["spring_mean_diameter_m"]**3 * c["spring_active_turns"]))
    turns = c["spring_total_turns"]
    # Two closed end turns have negligible axial pitch; sixteen active turns
    # carry the extension. Active m/3 plus the moving end is a dominant mode.
    active_axial = c["spring_rest_length_m"]-2*d
    active_length = math.hypot(math.pi*c["spring_mean_diameter_m"]*c["spring_active_turns"], active_axial)
    wire_length = active_length+2*math.pi*c["spring_mean_diameter_m"]
    linear_density = math.pi*d*d/4*c["spring_density_kg_m3"]
    mass = wire_length*linear_density
    # Linear mode u(s)=s*q/L gives m_active/3; the upper closed end moves
    # with the plate and the anchored end does not move.
    effective_mass = active_length*linear_density/3+math.pi*c["spring_mean_diameter_m"]*linear_density
    index = c["spring_mean_diameter_m"]/d
    wahl = (4*index-1)/(4*index-4)+0.615/index
    return {
        "spring_wire_diameter_m": d, "spring_wire_length_m": wire_length,
        "spring_coil_mass_kg": mass, "spring_effective_coil_mass_kg": effective_mass,
        "spring_plate_effective_mass_kg": c["spring_plate_mass_kg"]+effective_mass,
        "spring_solid_length_m": turns*d, "spring_index": index,
        "spring_helix_angle_deg": math.degrees(math.atan2(active_axial, math.pi*c["spring_mean_diameter_m"]*c["spring_active_turns"])),
        "spring_wahl_factor": wahl,
        "spring_rest_plate_x_m": c["spring_anchor_x_m"]+c["spring_rest_length_m"],
    }


def params_for_case(case_id="source", overrides=None, geometry_contract=None):
    if case_id not in CASE_OVERRIDES:
        raise ValueError("Unknown case: "+str(case_id))
    c = copy.deepcopy(BASELINE)
    if geometry_contract is None:
        default_geometry = DEFAULT_GEOMETRY
        geometry_contract = default_geometry
    if not Path(geometry_contract).is_file():
        raise FileNotFoundError("Required measured geometry contract: " + str(geometry_contract))
    for filename in ("car_body_points.npz", "car_body_surface.npz", "car_body_surface_parts.json"):
        if not (Path(geometry_contract).parent / filename).is_file():
            raise FileNotFoundError(Path(geometry_contract).parent / filename)
    if geometry_contract:
        geometry_path = Path(geometry_contract).resolve()
        payload = json.loads(geometry_path.read_text(encoding="utf-8"))
        if "body_length_m" in payload:
            c.update(car_length_m=payload["body_length_m"], car_width_m=payload["body_width_m"],
                     car_height_m=payload["total_height_m"], car_root_height_m=payload["chassis_com_above_table_m"],
                     car_wheel_centers_local_m=payload["wheel_centers_local_m"],
                     wheel_radius_m=payload["wheel_radius_m"], wheel_width_m=payload["wheel_width_m"])
            points = geometry_path.parent/"car_body_points.npz"
            if points.exists():
                c["car_collision_points_file"] = str(points)
            surface = geometry_path.parent/"car_body_surface.npz"
            surface_parts = geometry_path.parent/"car_body_surface_parts.json"
            if surface.exists():
                c["car_collision_surface_file"] = str(surface)
            if surface_parts.exists():
                c["car_collision_surface_parts_file"] = str(surface_parts)
            c["car_asset_geometry_contract_file"] = str(geometry_path)
            c["car_asset_geometry_contract_sha256"] = hashlib.sha256(geometry_path.read_bytes()).hexdigest()
        payload = payload.get("physics_overrides", payload)
        # Imported asset measurements may only affect geometry; intervention
        # strength and contact assumptions must remain explicit in this module.
        allowed = {
            "car_length_m", "car_width_m", "car_height_m", "car_root_height_m",
            "car_wheel_centers_local_m", "wheel_radius_m", "wheel_width_m",
            "car_chassis_lower_size_m", "car_chassis_lower_center_m",
            "car_chassis_upper_size_m", "car_chassis_upper_center_m",
            "car_chassis_com_m", "car_chassis_inertia_box_size_m",
        }
        for key, value in payload.items():
            if key in allowed:
                c[key] = value
    c.update(CASE_OVERRIDES[case_id])
    if overrides:
        unexpected = set(overrides)-set(BASELINE)
        if unexpected:
            raise ValueError("Unknown overrides: "+str(sorted(unexpected)))
        c.update(overrides)
    if not overrides or "wheel_ground_rolling_friction_m" not in overrides:
        c["wheel_ground_rolling_friction_m"] = c["wheel_rolling_resistance_coefficient"]*c["wheel_radius_m"]
    c.update(spring_geometry(c))
    if c.get("car_collision_points_file"):
        hull = collision_hull(c["car_collision_points_file"])
        cm = c["car_mass_kg"]-4*c["wheel_mass_kg"]
        c["car_chassis_com_m"] = hull["centroid_m"].tolist()
        c["car_chassis_inertia_kg_m2"] = (cm*hull["inertia_unit_mass_m2"]).tolist()
        c["car_collision_hull_vertex_count"] = int(len(hull["vertices"]))
        c["car_collision_hull_face_count"] = int(len(hull["faces"]))
        c["car_collision_points_sha256"] = hull["source_sha256"]
        c["car_collision_model"] = "convex hull of canonical asset body-only points; wheel arches filled; four separate wheel cylinders"
        c["car_inertia_model"] = "uniform effective mass within body convex hull plus individual wheel cylinder inertias; product mass distribution uncalibrated"
    else:
        c["car_collision_model"] = "development two-box chassis; not final native asset collision model"
    if c.get("car_collision_surface_file"):
        components, component_meta = collision_components(c)
        c["car_collision_model"] = "compound convex hulls of actual face-bearing connected body components; no whole-body spoiler/bumper bridge"
        c["car_collision_surface_sha256"] = hashlib.sha256(Path(c["car_collision_surface_file"]).read_bytes()).hexdigest()
        if c.get("car_collision_surface_parts_file"):
            c["car_collision_surface_parts_sha256"] = hashlib.sha256(Path(c["car_collision_surface_parts_file"]).read_bytes()).hexdigest()
        c["car_collision_component_count"] = len(components)
        c["car_collision_component_metadata"] = component_meta
    c["case_id"] = case_id
    c["scene_id"] = SCENE_ID
    c["block_density_equivalent_kg_m3"] = c["block_mass_kg"]/np.prod(c["block_size_m"])
    c["block_added_ballast_mass_kg"] = max(0., c["block_mass_kg"]-BASELINE["block_mass_kg"])
    c["obstacle_density_kg_m3"] = c["obstacle_mass_kg"]/float(np.prod(c["obstacle_size_m"]))
    c["obstacle_identity"] = "obstacle_block"
    c["obstacle_add_semantics"] = "Genuinely new source-absent free rigid body with dedicated presence, pose, mass and contact slots; present from t=0 only in ADD case"
    c["obstacle_placement_rule"] = "5/6 from source nominal car root to original block center; actual box height is twice the resolved line Z so its nominal bottom is z=0"
    c["wheel_order"] = list(WHEEL_NAMES)
    c["coordinate_system"] = "right-handed: x right, y depth, z up; units SI"
    c["car_transform_origin"] = "canonical car root; collision and asset local coordinates share this root"
    c["spring_deleted_semantics"] = "delete active coil and moving pusher body including elastic/contact/mass; retain fixed backstop and side guides"
    c["spring_geometry_model"] = "guided dominant axial structural mode; closed-end helix reconstructed from solved axial length"
    c["mass_calibration"] = "hypothesized assembly masses; no weighing of the rendered asset"
    c["contact_calibration"] = "uncalibrated compliant contact, bearing and friction coefficients"
    c["rolling_resistance_equivalent_coefficient"] = c["wheel_ground_rolling_friction_m"]/c["wheel_radius_m"]
    c["rolling_resistance_model"] = "declared same-material effective Crr; MuJoCo rolling torque arm b=Crr*measured wheel radius, not a fitted stopping trajectory"
    c["guide_contact_model"] = "bored plate on twin guides represented by ideal axial joint; redundant guide/plate solid collision excluded"
    c["spring_calibration"] = "mechanics-derived nominal steel rate; no measured product force-deflection or hysteresis calibration"
    c["initial_condition"] = "zero-velocity statically held spring precompression; remove only the car latch at t=0"
    c["precompression_parameter_scope"] = "nominal geometric setup; native static soft-contact solve gives the separately recorded actual spring compression"
    c["release_energy_source"] = "initial spring strain energy; no initial kinetic energy or applied launch impulse"
    c["initial_placement_method"] = "exact collision-component triangles clipped to bounded pusher Y/Z rectangle after static gravity support solve"
    validate_params(c)
    return c


def validate_params(c):
    positive = ["car_mass_kg", "wheel_radius_m", "wheel_width_m", "wheel_mass_kg",
                "spring_stiffness_n_m", "spring_rest_length_m", "spring_mean_diameter_m",
                "spring_active_turns", "spring_shear_modulus_pa", "simulation_dt_s", "duration_s"]
    if any(c[k] <= 0 for k in positive):
        raise ValueError("Positive SI parameter required")
    if c["car_speed_m_s"] != 0.0:
        raise ValueError("The car is released from rest; initial car speed must be exactly zero")
    if not 0 < c["spring_initial_compression_m"] < c["spring_max_stroke_m"]:
        raise ValueError("Initial compression must stay strictly within the spring stroke")
    if c["preload_duration_s"] != 0.0:
        raise ValueError("The preload uses a static equilibrium solve, no hidden pre-release trajectory")
    if 4*c["wheel_mass_kg"] >= c["car_mass_kg"]:
        raise ValueError("Wheel mass exceeds total car mass")
    if c["spring_rest_length_m"]-c["spring_max_stroke_m"] <= c["spring_solid_length_m"]:
        raise ValueError("Requested slider stroke enters coil bind")
    if c["contact_time_constant_s"] < 2*c["simulation_dt_s"]:
        raise ValueError("Contact time constant too short for this time step")
    steps_per_frame = 1/(c["fps"]*c["simulation_dt_s"])
    if abs(steps_per_frame-round(steps_per_frame)) > 1e-8:
        raise ValueError("Time step must divide frame interval exactly")
    wheel_outer_y = max(abs(p[1])+c["wheel_width_m"]/2 for p in c["car_wheel_centers_local_m"])
    widest_car_half_width = max(c["car_width_m"]/2, wheel_outer_y)
    if c["spring_guide_y_m"]-c["spring_guide_radius_m"] <= widest_car_half_width:
        raise ValueError("Guides would intersect car")
    if c["obstacle_mass_kg"] <= 0 or np.any(np.asarray(c["obstacle_size_m"]) <= 0):
        raise ValueError("New obstacle requires positive dimensions and mass")
    if abs(np.linalg.norm(c["obstacle_initial_quaternion_wxyz"])-1) > 1e-10:
        raise ValueError("New obstacle quaternion must have unit norm")
    if c["obstacle_present"]:
        position, size = np.asarray(c["obstacle_initial_position_m"]), np.asarray(c["obstacle_size_m"])
        if abs(position[2]-size[2]/2) > 1e-10:
            raise ValueError("This ADD baseline is genuinely floor-seated; do not hide a Z projection")
        old_lo = np.asarray([c["block_initial_x_m"], c["block_initial_y_m"], c["block_size_m"][2]/2])-np.asarray(c["block_size_m"])/2
        old_hi = old_lo+np.asarray(c["block_size_m"])
        if c["block_present"] and np.all(position+size/2 > old_lo) and np.all(position-size/2 < old_hi):
            raise ValueError("ADD initially interpenetrates original block")


def _v(values):
    return " ".join(format(float(x), ".17g") for x in values)


def _box_inertia(mass, sizes):
    a, b, c = sizes
    return mass*np.array([b*b+c*c, a*a+c*c, a*a+b*b])/12


_HULL_CACHE = {}
_COMPONENT_CACHE = {}


def collision_components(c):
    """Use visible connected parts, excluding all unreferenced/loose vertices.

    Flat surface components have no supplied volume. Their collision proxy is a
    declared 20 micron symmetric extrusion, never a millimetre-scale fake wedge.
    Very small detail components are omitted only under the declared100µm size.
    Body mass/inertia are independently declared effective properties.
    """
    from scipy.spatial import ConvexHull, QhullError
    surface_file = Path(c["car_collision_surface_file"]).resolve()
    parts_file = Path(c["car_collision_surface_parts_file"]).resolve() if c.get("car_collision_surface_parts_file") else None
    token = (str(surface_file), surface_file.stat().st_mtime_ns,
             parts_file.stat().st_mtime_ns if parts_file else None,
             c["car_collision_thin_sheet_thickness_m"], c["car_collision_min_component_extent_m"])
    if token in _COMPONENT_CACHE:
        return _COMPONENT_CACHE[token]
    with np.load(surface_file, allow_pickle=False) as payload:
        triangles = payload["triangles"]
        objects, components = payload["source_object_ids"], payload["component_ids"]
    roles = {}
    if parts_file:
        roles = {(r["source_object_id"], r["component_id"]): r["role"]
                 for r in json.loads(parts_file.read_text(encoding="utf-8"))["parts"]}
    keys = np.unique(np.column_stack([objects, components]), axis=0)
    shapes, records = [], []
    for obj, component in keys:
        selected = (objects == obj) & (components == component)
        points = np.unique(triangles[selected].reshape(-1, 3), axis=0)
        extent = float(np.max(np.ptp(points, axis=0)))
        record = {"source_object_id": int(obj), "component_id": int(component),
                  "role": roles.get((int(obj), int(component)), "unknown"),
                  "visible_vertices": len(points), "max_extent_m": extent,
                  "thin_sheet_proxy_thickness_m": 0.0}
        if extent < c["car_collision_min_component_extent_m"]:
            record.update(included=False, reason="visible detail below declared100micron collision tolerance")
            records.append(record)
            continue
        _, singular, basis = np.linalg.svd(points-points.mean(axis=0), full_matrices=False)
        if len(singular) < 2 or singular[1] < 1e-10:
            record.update(included=False, reason="degenerate line/point has no load-bearing surface area")
            records.append(record)
            continue
        normal = np.cross(basis[0], basis[1])
        normal /= np.linalg.norm(normal)
        actual_thickness = float(np.ptp(points@normal))
        if actual_thickness < c["car_collision_thin_sheet_thickness_m"]:
            half = (c["car_collision_thin_sheet_thickness_m"]-actual_thickness)/2
            points = np.concatenate([points+half*normal, points-half*normal])
            record["thin_sheet_proxy_thickness_m"] = c["car_collision_thin_sheet_thickness_m"]
            record["thin_sheet_max_inflation_each_side_m"] = half
        try:
            hull = ConvexHull(points)
        except QhullError:
            raise RuntimeError(f"Could not construct actual component hull object={obj} component={component}")
        vertices = np.unique(hull.simplices)
        remap = np.full(len(points), -1, dtype=np.int64)
        remap[vertices] = np.arange(len(vertices))
        faces = remap[hull.simplices].copy()
        vertices = points[vertices]
        tri = vertices[faces]
        inward = np.einsum("ij,ij->i", np.cross(tri[:, 1]-tri[:, 0], tri[:, 2]-tri[:, 0]), hull.equations[:, :3]) < 0
        faces[inward] = faces[inward][:, [0, 2, 1]]
        name = f"car_chassis_component_{int(obj)}_{int(component)}"
        record.update(included=True, name=name, hull_vertices=len(vertices), hull_faces=len(faces), volume_m3=float(hull.volume))
        shapes.append({"name": name, "vertices": vertices, "faces": faces})
        records.append(record)
    if not shapes:
        raise RuntimeError("No face-bearing car collision components")
    _COMPONENT_CACHE[token] = (shapes, records)
    return shapes, records


def finite_pusher_bearing(c, car_transform):
    """Actual first support of compound hulls in the finite pusher rectangle.

    Calling native GJK distance on far-separated very thin details can return a
    failed zero-distance query. Exact finite-face clipping uses the same native
    component hull faces and has no far-distance or tiny-aspect GJK ambiguity.
    """
    components = collision_components(c)[0]
    local_triangles = np.concatenate([part["vertices"][part["faces"]] for part in components])
    triangles = local_triangles@car_transform[:3, :3].T+car_transform[:3, 3]
    lower = np.array([-c["spring_plate_size_m"][1]/2,
                      c["spring_axis_z_m"]-c["spring_plate_size_m"][2]/2])
    upper = np.array([c["spring_plate_size_m"][1]/2,
                      c["spring_axis_z_m"]+c["spring_plate_size_m"][2]/2])
    lo, hi = triangles[:, :, 1:].min(axis=1), triangles[:, :, 1:].max(axis=1)
    possible = np.all(hi >= lower, axis=1) & np.all(lo <= upper, axis=1)
    inside = possible & np.all(lo >= lower, axis=1) & np.all(hi <= upper, axis=1)
    winner = None
    if np.any(inside):
        candidates = triangles[inside].reshape(-1, 3)
        winner = candidates[np.argmin(candidates[:, 0])].copy()
    for index in np.flatnonzero(possible & ~inside):
        polygon = list(triangles[index].copy())
        for axis in (1, 2):
            for boundary, sign in ((lower[axis-1], 1), (upper[axis-1], -1)):
                clipped = []
                for first, second in zip(polygon, polygon[1:]+polygon[:1]):
                    da, db = sign*(first[axis]-boundary), sign*(second[axis]-boundary)
                    if da >= 0:
                        clipped.append(first)
                    if (da >= 0) != (db >= 0):
                        clipped.append(first+(second-first)*(da/(da-db)))
                polygon = clipped
                if not polygon:
                    break
            if not polygon:
                break
        if polygon:
            candidate = min(polygon, key=lambda v: v[0])
            if winner is None or candidate[0] < winner[0]:
                winner = candidate.copy()
    if winner is None:
        raise RuntimeError("No compound car material in the finite pusher Y/Z rectangle")
    return winner


def collision_hull(points_file):
    from scipy.spatial import ConvexHull
    points_file = Path(points_file).resolve()
    token = (str(points_file), points_file.stat().st_mtime_ns)
    if token in _HULL_CACHE:
        return _HULL_CACHE[token]
    with np.load(points_file, allow_pickle=False) as z:
        points = np.asarray(z["vertices"], np.float64)
    raw = ConvexHull(points)
    selected = np.unique(raw.simplices)
    remap = np.full(len(points), -1, np.int64)
    remap[selected] = np.arange(len(selected))
    vertices = points[selected]
    faces = remap[raw.simplices].copy()
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1]-triangles[:, 0], triangles[:, 2]-triangles[:, 0])
    invert = np.sum(normals*raw.equations[:, :3], axis=1) < 0
    faces[invert] = faces[invert][:, [0, 2, 1]]
    triangles = vertices[faces]
    volumes = np.einsum("fi,fi->f", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2]))/6
    volume = float(volumes.sum())
    centroid = np.sum(volumes[:, None]*triangles.sum(axis=1)/4, axis=0)/volume
    sums = triangles.sum(axis=1)
    second = np.einsum("f,fi,fj->ij", volumes/20, sums, sums)
    second += np.einsum("f,fki,fkj->ij", volumes/20, triangles, triangles)
    second -= volume*np.outer(centroid, centroid)
    inertia = (np.trace(second)*np.eye(3)-second)/volume
    if volume <= 0 or np.linalg.eigvalsh(inertia).min() <= 0:
        raise RuntimeError("Invalid canonical hull inertia")
    result = dict(vertices=vertices, faces=faces, volume_m3=volume,
                  centroid_m=centroid, inertia_unit_mass_m2=inertia,
                  source_sha256=hashlib.sha256(points_file.read_bytes()).hexdigest())
    _HULL_CACHE[token] = result
    return result


def add_obstacle_xml(xml, c):
    """ADD creates one new, dynamically free body; no existing body is edited."""
    if not c["obstacle_present"]:
        return xml
    root = ET.fromstring(xml)
    body = ET.SubElement(root.find("worldbody"), "body", name="obstacle_block",
                         pos=_v(c["obstacle_initial_position_m"]), quat=_v(c["obstacle_initial_quaternion_wxyz"]))
    ET.SubElement(body, "freejoint", name="obstacle_free", align="false")
    ET.SubElement(body, "inertial", mass=str(c["obstacle_mass_kg"]), pos="0 0 0",
                  diaginertia=_v(_box_inertia(c["obstacle_mass_kg"], c["obstacle_size_m"])))
    ET.SubElement(body, "geom", name="obstacle_block_geom", type="box",
                  size=_v(np.asarray(c["obstacle_size_m"])/2),
                  friction=_v([c["obstacle_ground_friction"], .0001, .00001]), rgba="0.45 0.24 0.10 1")
    contact = root.find("contact")
    counterparts = [("table", c["obstacle_ground_friction"])]
    if c["block_present"]:
        counterparts.append(("block_geom", c["obstacle_block_friction"]))
    counterparts += [(geom.get("name"), c["obstacle_car_friction"]) for geom in root.iter("geom")
                     if geom.get("name", "").startswith(("car_chassis", "wheel_geom_"))]
    for name, friction in counterparts:
        ET.SubElement(contact, "pair", geom1=name, geom2="obstacle_block_geom", condim="3",
                      friction=_v([friction, friction, .0001, .00001, .00001]),
                      solref=_v([c["contact_time_constant_s"], c["contact_damping_ratio"]]),
                      solimp=_v([c["contact_impedance"], c["contact_impedance"], .001, .5, 2]))
    ET.indent(root, space="  ")
    return ET.tostring(root, encoding="unicode")+"\n"


def build_xml(c):
    """Construct solver geometry; spring wires are reduced, not collision particles."""
    root = ET.Element("mujoco", model=SCENE_ID)
    ET.SubElement(root, "compiler", angle="radian", autolimits="true", alignfree="false")
    option = ET.SubElement(root, "option", timestep=str(c["simulation_dt_s"]),
                          gravity=_v([0, 0, -c["gravity_m_s2"]]), integrator="implicitfast",
                          cone="elliptic", solver="Newton", iterations=str(c["solver_iterations"]),
                          tolerance=str(c["solver_tolerance"]), noslip_iterations="0")
    ET.SubElement(option, "flag", energy="enable", fwdinv="enable", multiccd="enable", nativeccd="enable")
    default = ET.SubElement(root, "default")
    ET.SubElement(default, "joint", damping="0", frictionloss="0")
    solref = _v([c["contact_time_constant_s"], c["contact_damping_ratio"]])
    solimp = _v([c["contact_impedance"], c["contact_impedance"], 0.001, 0.5, 2])
    ET.SubElement(default, "geom", solref=solref, solimp=solimp,
                  margin="0", gap="0", friction="0.3 0.0001 0.00001", condim="3")
    hull = collision_hull(c["car_collision_points_file"]) if c.get("car_collision_points_file") else None
    components = collision_components(c)[0] if c.get("car_collision_surface_file") else None
    if hull is not None:
        assets = ET.SubElement(root, "asset")
        if components:
            for component in components:
                ET.SubElement(assets, "mesh", name=component["name"]+"_mesh",
                              inertia="shell",
                              vertex=_v(component["vertices"].ravel()),
                              face=" ".join(str(int(i)) for i in component["faces"].ravel()))
        else:
            ET.SubElement(assets, "mesh", name="car_canonical_hull",
                          vertex=_v(hull["vertices"].ravel()), face=" ".join(str(int(i)) for i in hull["faces"].ravel()))
    world = ET.SubElement(root, "worldbody")
    ET.SubElement(world, "body", name="release_latch_frame", mocap="true",
                  pos=_v([c["car_initial_x_m"], c["car_initial_y_m"], c["car_root_height_m"]]))
    ET.SubElement(world, "geom", name="table", type="plane", size="4 3 0.1",
                  friction="0.28 0.0001 0.00001", rgba="0.45 0.3 0.16 1")
    backsize = np.asarray(c["spring_backstop_size_m"])
    ET.SubElement(world, "geom", name="fixed_backstop", type="box",
                  pos=_v([c["spring_anchor_x_m"]-backsize[0]/2, 0, backsize[2]/2]),
                  size=_v(backsize/2), rgba="0.25 0.26 0.28 1")
    for side in (-1, 1):
        ET.SubElement(world, "geom", name="fixed_guide_"+("left" if side > 0 else "right"),
                      type="capsule", size=str(c["spring_guide_radius_m"]),
                      contype="0", conaffinity="0",
                      fromto=_v([c["spring_anchor_x_m"], side*c["spring_guide_y_m"], c["spring_guide_z_m"],
                                 c["spring_rest_plate_x_m"]+0.009, side*c["spring_guide_y_m"], c["spring_guide_z_m"]]),
                      rgba="0.6 0.62 0.65 1")
        # The plate has bored guide holes in the render geometry. These mating
        # surfaces are represented by the ideal slider joint, so collision of
        # a solid plate box with the rods would incorrectly lock the slider.
    if c["spring_present"]:
        plate = ET.SubElement(world, "body", name="spring_plate",
                              pos=_v([c["spring_rest_plate_x_m"], 0, c["spring_axis_z_m"]]))
        ET.SubElement(plate, "joint", name="spring_axial", type="slide", axis="1 0 0",
                      stiffness=str(c["spring_stiffness_n_m"]), springref="0",
                      damping=str(c["spring_damping_n_s_m"]),
                      frictionloss=str(c["spring_guide_friction_loss_n"]), limited="true",
                      range=_v([-c["spring_max_stroke_m"], 0]), solreflimit=solref, solimplimit=solimp)
        pm = c["spring_plate_effective_mass_kg"]
        ET.SubElement(plate, "inertial", pos="0 0 0", mass=str(pm),
                      diaginertia=_v(_box_inertia(pm, c["spring_plate_size_m"])))
        ET.SubElement(plate, "geom", name="spring_plate_geom", type="box",
                      size=_v(np.asarray(c["spring_plate_size_m"])/2), rgba="0.65 0.67 0.70 1")
    car = ET.SubElement(world, "body", name="car",
                        pos=_v([c["car_initial_x_m"], c["car_initial_y_m"], c["car_root_height_m"]]))
    ET.SubElement(car, "freejoint", name="car_free", align="false")
    cm = c["car_mass_kg"]-4*c["wheel_mass_kg"]
    if hull is not None:
        I = np.asarray(c["car_chassis_inertia_kg_m2"])
        ET.SubElement(car, "inertial", pos=_v(c["car_chassis_com_m"]), mass=str(cm),
                      fullinertia=_v([I[0, 0], I[1, 1], I[2, 2], I[0, 1], I[0, 2], I[1, 2]]))
        if components:
            for component in components:
                ET.SubElement(car, "geom", name=component["name"], type="mesh",
                              mesh=component["name"]+"_mesh", rgba="0.75 0.025 0.01 1")
            car_geoms = tuple(component["name"] for component in components)
        else:
            ET.SubElement(car, "geom", name="car_chassis_hull", type="mesh", mesh="car_canonical_hull", rgba="0.75 0.025 0.01 1")
            car_geoms = ("car_chassis_hull",)
    else:
        ET.SubElement(car, "inertial", pos=_v(c["car_chassis_com_m"]), mass=str(cm),
                      diaginertia=_v(_box_inertia(cm, c["car_chassis_inertia_box_size_m"])))
        car_geoms = ("car_chassis_lower", "car_chassis_upper")
        for part in ("lower", "upper"):
            ET.SubElement(car, "geom", name="car_chassis_"+part, type="box",
                          pos=_v(c["car_chassis_"+part+"_center_m"]),
                          size=_v(np.asarray(c["car_chassis_"+part+"_size_m"])/2), rgba="0.65 0.025 0.02 1")
    contact = ET.SubElement(root, "contact")
    for name, pos in zip(WHEEL_NAMES, c["car_wheel_centers_local_m"]):
        wheel = ET.SubElement(car, "body", name="wheel_"+name, pos=_v(pos))
        ET.SubElement(wheel, "joint", name="wheel_hinge_"+name, type="hinge", axis="0 1 0",
                      damping=str(c["wheel_bearing_damping_n_m_s"]),
                      frictionloss=str(c["wheel_bearing_friction_loss_n_m"]))
        wm, wr, ww = c["wheel_mass_kg"], c["wheel_radius_m"], c["wheel_width_m"]
        inertia_axial = 0.5*wm*wr*wr
        inertia_radial = wm*(3*wr*wr+ww*ww)/12
        ET.SubElement(wheel, "inertial", pos="0 0 0", mass=str(wm),
                      diaginertia=_v([inertia_radial, inertia_axial, inertia_radial]))
        ET.SubElement(wheel, "geom", name="wheel_geom_"+name, type="cylinder",
                      euler=_v([math.pi/2, 0, 0]), size=_v([wr, ww/2]),
                      friction=_v([c["wheel_ground_sliding_friction"], c["wheel_ground_torsional_friction_m"], c["wheel_ground_rolling_friction_m"]]),
                      condim="6", rgba="0.02 0.021 0.023 1")
        ET.SubElement(contact, "pair", geom1="table", geom2="wheel_geom_"+name,
                      condim="6", friction=_v([c["wheel_ground_sliding_friction"]]*2+
                                             [c["wheel_ground_torsional_friction_m"]]+
                                             [c["wheel_ground_rolling_friction_m"]]*2), solref=solref, solimp=solimp)
    if c["block_present"]:
        block = ET.SubElement(world, "body", name="block",
                              pos=_v([c["block_initial_x_m"], c["block_initial_y_m"], c["block_size_m"][2]/2]))
        ET.SubElement(block, "freejoint", name="block_free", align="false")
        ET.SubElement(block, "inertial", pos="0 0 0", mass=str(c["block_mass_kg"]),
                      diaginertia=_v(_box_inertia(c["block_mass_kg"], c["block_size_m"])))
        ET.SubElement(block, "geom", name="block_geom", type="box", size=_v(np.asarray(c["block_size_m"])/2),
                      friction=_v([c["block_ground_friction"], 0.0001, 0.00001]), rgba="0.52 0.28 0.12 1")
        ET.SubElement(contact, "pair", geom1="table", geom2="block_geom", condim="3",
                      friction=_v([c["block_ground_friction"]]*2+[0.0001, 0.00001, 0.00001]), solref=solref, solimp=solimp)
        for geom in car_geoms:
            ET.SubElement(contact, "pair", geom1=geom, geom2="block_geom", condim="3",
                          friction=_v([c["car_block_friction"]]*2+[0.0001, 0.00001, 0.00001]), solref=solref, solimp=solimp)
    if c["spring_present"]:
        for geom in car_geoms:
            ET.SubElement(contact, "pair", geom1=geom, geom2="spring_plate_geom", condim="3",
                          friction=_v([c["car_plate_friction"]]*2+[0.0001, 0.00001, 0.00001]), solref=solref, solimp=solimp)
    equality = ET.SubElement(root, "equality")
    ET.SubElement(equality, "weld", name="car_release_latch", body1="car", body2="release_latch_frame",
                  active="false", relpose="0 0 0 1 0 0 0", torquescale="0.1",
                  solref=_v([c["hold_constraint_time_constant_s"], 1.0]),
                  solimp=_v([c["hold_constraint_impedance"], c["hold_constraint_impedance"], .001, .5, 2]))
    if not c.get("car_present", True):
        # DELETE car: no chassis, wheels, car contact pairs, car meshes or car latch.
        car_names = set(car_geoms) | {"wheel_geom_"+name for name in WHEEL_NAMES}
        world.remove(car)
        world.remove(world.find("body[@name='release_latch_frame']"))
        for pair in list(contact):
            if {pair.get("geom1"), pair.get("geom2")} & car_names:
                contact.remove(pair)
        root.remove(equality)
        if hull is not None:
            root.remove(assets)
    ET.indent(root, space="  ")
    return add_obstacle_xml(ET.tostring(root, encoding="unicode")+"\n", c)


def _id(model, kind, name):
    value = mujoco.mj_name2id(model, kind, name)
    if value < 0:
        raise KeyError(name)
    return value


def body_transform(data, body_id):
    T = np.eye(4)
    T[:3, :3] = data.xmat[body_id].reshape(3, 3)
    T[:3, 3] = data.xpos[body_id]
    return T


def body_velocity(model, data, body_id):
    vel = np.zeros(6)
    mujoco.mj_objectVelocity(model, data, mujoco.mjtObj.mjOBJ_XBODY, body_id, vel, 0)
    # XBODY explicitly requests the regular body origin, while BODY requests
    # the inertial COM. Files use world linear then angular at the exported root.
    return np.concatenate([vel[3:], vel[:3]])


class Simulation:
    def __init__(self, c, initial_state=None):
        self.c = c
        self.xml = build_xml(c)
        self.model = mujoco.MjModel.from_xml_string(self.xml)
        self.data = mujoco.MjData(self.model)
        self.car_present = bool(c.get("car_present", True))
        car = self.car_present
        self.car_id = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "car") if car else None
        self.wheel_ids = [_id(self.model, mujoco.mjtObj.mjOBJ_BODY, "wheel_"+n) for n in WHEEL_NAMES] if car else []
        self.wheel_joints = [_id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "wheel_hinge_"+n) for n in WHEEL_NAMES] if car else []
        self.car_joint = _id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "car_free") if car else None
        self.car_placeholder = np.eye(4)
        self.car_placeholder[:3, 3] = [c["car_initial_x_m"], c["car_initial_y_m"], c["car_root_height_m"]]
        self.block_id = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "block") if c["block_present"] else None
        self.block_joint = _id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "block_free") if c["block_present"] else None
        self.obstacle_id = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "obstacle_block") if c["obstacle_present"] else None
        self.obstacle_joint = _id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "obstacle_free") if c["obstacle_present"] else None
        self.spring_joint = _id(self.model, mujoco.mjtObj.mjOBJ_JOINT, "spring_axial") if c["spring_present"] else None
        self.spring_id = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "spring_plate") if c["spring_present"] else None
        self.latch_id = _id(self.model, mujoco.mjtObj.mjOBJ_EQUALITY, "car_release_latch") if car else None
        self.latch_frame_id = _id(self.model, mujoco.mjtObj.mjOBJ_BODY, "release_latch_frame") if car else None
        self.latch_mocap_id = int(self.model.body_mocapid[self.latch_frame_id]) if car else None
        self.block_placeholder = np.eye(4)
        self.block_placeholder[:3, 3] = [c["block_initial_x_m"], c["block_initial_y_m"], c["block_size_m"][2]/2]
        self.obstacle_placeholder = np.eye(4)
        self.obstacle_placeholder[:3, 3] = c["obstacle_initial_position_m"]
        self.obstacle_initial_vertical_rest_residual = None
        self.geom_names = [mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_GEOM, i) for i in range(self.model.ngeom)]
        self.car_geom_ids = [i for i, name in enumerate(self.geom_names) if name.startswith("car_chassis")]
        self.spring_dof = int(self.model.jnt_dofadr[self.spring_joint]) if self.spring_joint is not None else None
        self.spring_qpos = int(self.model.jnt_qposadr[self.spring_joint]) if self.spring_joint is not None else None
        self.wheel_dofs = np.array([self.model.jnt_dofadr[j] for j in self.wheel_joints]) if car else np.zeros(0, int)
        self.wheel_qposes = np.array([self.model.jnt_qposadr[j] for j in self.wheel_joints]) if car else np.zeros(0, int)
        self.initial_state = initial_state
        self.loss_damping_j = 0.0
        self.loss_spring_damping_j = 0.0
        self.loss_bearing_damping_j = 0.0
        self.loss_joint_friction_j = 0.0
        self.loss_contact_friction_j = 0.0
        self.loss_contact_normal_j = 0.0
        self.loss_joint_limit_j = 0.0
        self.max_joint_limit_violation_m = 0.0
        self.contact_records = {}
        self.contact_witnesses = []
        self.max_penetration_m = 0.0
        self.max_forward_inverse_discrepancy = 0.0
        self.max_spring_compression_m = 0.0
        self.max_spring_compression_time_s = 0.0
        self.max_spring_energy_j = 0.0
        self.max_total_energy_j = 0.0
        self.max_wheel_slip_m_s = 0.0
        self.wheel_slip_squared_sum = 0.0
        self.wheel_slip_samples = 0
        self.max_launch_wheel_gap_m = 0.0
        self.first_positive_car_velocity_s = None
        self.max_block_displacement_m = 0.0
        self.peak_block_speed_m_s = 0.0
        self.max_obstacle_displacement_m = 0.0
        self.peak_obstacle_speed_m_s = 0.0
        self.peak_car_speed_m_s = c["car_speed_m_s"]
        self.physical_steps = 0
        if self.model.nu != 0:
            raise RuntimeError("Model must have no actuators")
        self._prepare_initial_state(initial_state)

    def _prepare_initial_state(self, initial_state):
        """Solve a static held configuration without advancing physical time.

        Every trial has identically zero qvel. The source's gravity support pose
        is reused by other cases. The nominal car placement is the first native
        bounded-rectangle/hull contact, not a global bbox/wing support shortcut.
        Only the tiny contact compliance is solved in the spring slider. Opening
        the explicit latch changes eq_active, never qpos or qvel.
        """
        from scipy.optimize import brentq, root

        if not self.car_present:
            return self._prepare_initial_state_without_car(initial_state)
        self.data.qvel[:] = 0.0
        car_qa = int(self.model.jnt_qposadr[self.car_joint])
        car_da = int(self.model.jnt_dofadr[self.car_joint])
        self.data.eq_active[self.latch_id] = 0
        nominal = self.c["spring_initial_compression_m"]
        if self.spring_qpos is not None:
            self.data.qpos[self.spring_qpos] = -nominal
        static_residual = None
        if initial_state is None:
            # Solve vertical support with the car away from the spring. These
            # are static trial positions, not an unrecorded launch/settling run.
            self.data.qpos[car_qa] = 0.0
            base_z = self.c["car_root_height_m"]

            def gravity_trial(values):
                z, roll, pitch = values
                self.data.qpos[car_qa+2] = z
                self.data.qpos[car_qa+3:car_qa+7] = [
                    math.cos(roll/2)*math.cos(pitch/2),
                    math.sin(roll/2)*math.cos(pitch/2),
                    math.cos(roll/2)*math.sin(pitch/2),
                    -math.sin(roll/2)*math.sin(pitch/2)]
                self.data.qacc_warmstart[:] = 0.0
                mujoco.mj_forward(self.model, self.data)
                return self.data.qacc[car_da+np.array([2, 3, 4])].copy()

            def gravity_jac(values):
                h = np.array([1e-9, 1e-7, 1e-7])
                return np.column_stack([(gravity_trial(values+np.eye(3)[i]*h[i])-
                                         gravity_trial(values-np.eye(3)[i]*h[i]))/(2*h[i]) for i in range(3)])

            solved = root(gravity_trial, [base_z-5e-8, 0.0, 0.0], jac=gravity_jac, tol=1e-10)
            static_residual = gravity_trial(solved.x)
            if np.max(np.abs(static_residual)) > 1e-5:
                raise RuntimeError("Static car support did not equilibrate: "+repr(static_residual))
            if self.block_joint is not None:
                block_qa = int(self.model.jnt_qposadr[self.block_joint])
                block_da = int(self.model.jnt_dofadr[self.block_joint])
                def block_force(z):
                    self.data.qpos[block_qa+2] = z
                    self.data.qacc_warmstart[:] = 0.0
                    mujoco.mj_forward(self.model, self.data)
                    return float(self.data.qacc[block_da+2])
                block_z = self.c["block_size_m"][2]/2
                equilibrium_z = brentq(block_force, block_z-1e-4, block_z+1e-7, xtol=1e-15)
                block_force(equilibrium_z)
            # Native geometry distance respects both the actual convex chassis
            # and the pusher's finite y/z rectangle, including a rear spoiler.
            if self.spring_id is None:
                raise ValueError("Build source before deletion cases to share its exact release pose")
            front_x = self.c["spring_rest_plate_x_m"]-nominal+self.c["spring_plate_size_m"][0]/2
            if self.c.get("car_collision_surface_file"):
                mujoco.mj_forward(self.model, self.data)
                witness = finite_pusher_bearing(self.c, body_transform(self.data, self.car_id))
                contact_x = float(front_x-witness[0])
                self.data.qpos[car_qa] = contact_x
                witness[0] += contact_x
                support = np.concatenate([witness, witness])
                exact_gap = float(witness[0]-front_x)
                placement_method = "exact compound-hull triangles clipped to finite pusher Y/Z rectangle"
                mujoco.mj_forward(self.model, self.data)
            else:
                plate_gid = _id(self.model, mujoco.mjtObj.mjOBJ_GEOM, "spring_plate_geom")
                support = np.zeros(6)
                def gap_at_car_x(x):
                    self.data.qpos[car_qa] = x
                    mujoco.mj_forward(self.model, self.data)
                    return float(mujoco.mj_geomDistance(self.model, self.data, self.car_geom_ids[0], plate_gid, 1.0, support))
                approximate = front_x+self.c["car_length_m"]/2
                contact_x = brentq(gap_at_car_x, approximate-.05, approximate+.05, xtol=1e-14)
                exact_gap = gap_at_car_x(contact_x)
                placement_method = "development single convex body native signed distance"
            self.nominal_contact_geometry = {"signed_distance_m": exact_gap,
                "closest_car_point_world_m": support[:3].tolist(),
                "closest_pusher_point_world_m": support[3:].tolist(),
                "native_car_x_m": contact_x,
                "method": placement_method}
        else:
            self.restore_initial_state(initial_state)
            original_nominal = initial_state.get("_nominal_compression_m", BASELINE["spring_initial_compression_m"])
            self.data.qpos[car_qa] -= nominal-original_nominal
            self.nominal_contact_geometry = copy.deepcopy(initial_state.get("_nominal_contact_geometry", {}))
            if "native_car_x_m" in self.nominal_contact_geometry:
                self.nominal_contact_geometry["native_car_x_m"] -= nominal-original_nominal
                for name in ("closest_car_point_world_m", "closest_pusher_point_world_m"):
                    self.nominal_contact_geometry[name][0] -= nominal-original_nominal
        if self.obstacle_joint is not None:
            qa = int(self.model.jnt_qposadr[self.obstacle_joint])
            da = int(self.model.jnt_dofadr[self.obstacle_joint])
            def obstacle_rest_acceleration(z):
                self.data.qpos[qa+2] = z
                self.data.qacc_warmstart[:] = 0.0
                mujoco.mj_forward(self.model, self.data)
                return float(self.data.qacc[da+2])
            nominal_obstacle_z = self.c["obstacle_initial_position_m"][2]
            z = brentq(obstacle_rest_acceleration, nominal_obstacle_z-1e-4,
                       nominal_obstacle_z+1e-7, xtol=1e-15)
            self.obstacle_initial_vertical_rest_residual = obstacle_rest_acceleration(z)
        self.data.qvel[:] = 0.0
        self.data.qacc_warmstart[:] = 0.0
        self.data.time = 0.0
        # An explicit preparation latch carries car translation and moment.
        # No spring-position servo is installed; contact and passive spring
        # must balance by solving their small static soft-contact deformation.
        self.data.mocap_pos[self.latch_mocap_id] = self.data.qpos[car_qa:car_qa+3]
        self.data.mocap_quat[self.latch_mocap_id] = self.data.qpos[car_qa+3:car_qa+7]
        self.data.eq_active[self.latch_id] = 1
        if self.spring_qpos is not None:
            def held_plate_acceleration(q):
                self.data.qpos[self.spring_qpos] = q
                self.data.qacc_warmstart[:] = 0.0
                mujoco.mj_forward(self.model, self.data)
                return float(self.data.qacc[self.spring_dof])
            q_equilibrium = brentq(held_plate_acceleration, -nominal-1e-5,
                                   -nominal+1e-4, xtol=1e-15)
            held_plate_acceleration(q_equilibrium)
        else:
            mujoco.mj_forward(self.model, self.data)

        def contact_snapshot():
            found = []
            for index in range(self.data.ncon):
                con = self.data.contact[index]
                names = [self.geom_names[int(con.geom1)], self.geom_names[int(con.geom2)]]
                if "spring_plate_geom" not in names:
                    continue
                force = np.zeros(6)
                mujoco.mj_contactForce(self.model, self.data, index, force)
                world_force_on_geom2 = con.frame.reshape(3, 3).T@force[:3]
                plate_is_first = names[0] == "spring_plate_geom"
                plate_axial_force = -world_force_on_geom2[0] if plate_is_first else world_force_on_geom2[0]
                found.append({"geoms": names, "point_m": con.pos.tolist(),
                              "normal_force_n": float(force[0]), "signed_distance_m": float(con.dist),
                              "contact_world_force_on_geom2_n": world_force_on_geom2.tolist(),
                              "axial_force_on_pusher_n": float(plate_axial_force)})
            return found

        held_contacts = contact_snapshot()
        held_qacc = self.data.qacc.copy()
        held_spring_passive = float(self.data.qfrc_passive[self.spring_dof]) if self.spring_dof is not None else 0.0
        held_spring_constraint = float(self.data.qfrc_constraint[self.spring_dof]) if self.spring_dof is not None else 0.0
        held_spring_bias = float(self.data.qfrc_bias[self.spring_dof]) if self.spring_dof is not None else 0.0
        jacobian = self.data.efc_J.reshape(self.data.nefc, self.model.nv)
        holding_generalized_force = np.zeros(self.model.nv)
        for i in range(self.data.nefc):
            if self.data.efc_type[i] == mujoco.mjtConstraint.mjCNSTR_EQUALITY:
                holding_generalized_force += jacobian[i]*self.data.efc_force[i]
        held_qpos, held_qvel = self.data.qpos.copy(), self.data.qvel.copy()
        held_mechanical_energy = float(self.data.energy.sum())
        self.data.eq_active[self.latch_id] = 0
        self.data.qacc_warmstart[:] = 0.0
        self.data.qfrc_applied[:] = 0.0
        self.data.xfrc_applied[:] = 0.0
        mujoco.mj_forward(self.model, self.data)
        compression = -float(self.data.qpos[self.spring_qpos]) if self.spring_qpos is not None else 0.0
        self.initial_spring_energy_j = .5*self.c["spring_stiffness_n_m"]*compression**2 if self.spring_qpos is not None else 0.0
        self.initial_mechanical_energy_j = float(self.data.energy.sum())
        self.initial_kinetic_energy_j = float(self.data.energy[1])
        self.initial_available_energy_j = self.initial_kinetic_energy_j+self.initial_spring_energy_j
        self.initial_gravity_and_spring_energy_j = float(self.data.energy[0])
        self.max_total_energy_j = self.initial_mechanical_energy_j
        self.max_spring_compression_m = compression
        self.max_spring_energy_j = self.initial_spring_energy_j
        self.initial_state_audit = {
            "method": "zero-velocity static support and held contact root solves; no pre-release mj_step calls",
            "pre_release_physical_steps": 0, "nominal_compression_m": nominal,
            "obstacle_present": self.obstacle_id is not None,
            "obstacle_identity": "obstacle_block",
            "obstacle_static_rest_acceleration_residual_m_s2": self.obstacle_initial_vertical_rest_residual,
            "obstacle_nominal_initial_position_m": self.c["obstacle_initial_position_m"],
            "obstacle_actual_initial_pose": (self.data.qpos[self.model.jnt_qposadr[self.obstacle_joint]:
                self.model.jnt_qposadr[self.obstacle_joint]+7].tolist() if self.obstacle_joint is not None else None),
            "actual_initial_compression_m": compression,
            "initial_spring_energy_j": self.initial_spring_energy_j,
            "initial_kinetic_energy_j": self.initial_kinetic_energy_j,
            "initial_available_energy_j": self.initial_available_energy_j,
            "static_gravity_rest_residual": static_residual.tolist() if static_residual is not None else None,
            "nominal_contact_geometry": self.nominal_contact_geometry,
            "held_car_generalized_force": holding_generalized_force[car_da:car_da+6].tolist(),
            "held_spring_generalized_acceleration_m_s2": float(held_qacc[self.spring_dof]) if self.spring_dof is not None else None,
            "held_spring_passive_force_n": held_spring_passive,
            "held_spring_constraint_force_n": held_spring_constraint,
            "held_spring_force_balance_residual_n": held_spring_passive+held_spring_constraint-held_spring_bias,
            "held_contact_normal_force_sum_n": sum(x["normal_force_n"] for x in held_contacts),
            "held_contact_axial_force_on_pusher_n": sum(x["axial_force_on_pusher_n"] for x in held_contacts),
            "actual_initial_spring_force_n": self.c["spring_stiffness_n_m"]*compression if self.spring_qpos is not None else 0.0,
            "held_contacts": held_contacts, "released_contacts": contact_snapshot(),
            "released_car_generalized_acceleration": self.data.qacc[car_da:car_da+6].tolist(),
            "released_spring_acceleration_m_s2": float(self.data.qacc[self.spring_dof]) if self.spring_dof is not None else None,
            "all_initial_generalized_velocities_exactly_zero": bool(np.array_equal(self.data.qvel, np.zeros(self.model.nv))),
            "release_preserves_qpos_bitwise": bool(np.array_equal(self.data.qpos, held_qpos)),
            "release_preserves_qvel_bitwise": bool(np.array_equal(self.data.qvel, held_qvel)),
            "release_mechanical_energy_change_j": self.initial_mechanical_energy_j-held_mechanical_energy,
            "active_release_latches": int(np.count_nonzero(self.data.eq_active)),
            "initial_qacc_warmstart_max": float(np.max(np.abs(self.data.qacc_warmstart))),
            "initial_physical_time_s": float(self.data.time),
            "release_external_force_max": float(max(np.max(np.abs(self.data.qfrc_applied)), np.max(np.abs(self.data.xfrc_applied)))),
            "release_actuator_count": int(self.model.nu),
            "static_contact_storage_scope": "native implicit soft contact supports micrometric static penetration; no explicit contact strain energy is included in MuJoCo energy",
            "force_balance_scope": "held plate passive spring/contact/friction balance; after release native contact force changes with coupled car/plate acceleration",
        }
        released_contacts = self.initial_state_audit["released_contacts"]
        compliance_scale = .5*sum(x["normal_force_n"]*max(0.0, -x["signed_distance_m"])
                                  for x in released_contacts)
        self.initial_state_audit["initial_contact_compliance_energy_scale_j"] = compliance_scale
        self.initial_state_audit["initial_contact_compliance_energy_scale_fraction_spring"] = (
            compliance_scale/self.initial_spring_energy_j if self.initial_spring_energy_j > 0 else 0.0)
        self.initial_state_audit["contact_compliance_energy_scale_note"] = (
            "half force times penetration is a local linear scale estimate, not a calibrated physical contact potential or an extra ledger term")
        initial_wheel_loads = {name: 0.0 for name in WHEEL_NAMES}
        for index in range(self.data.ncon):
            con = self.data.contact[index]
            names = [self.geom_names[int(con.geom1)], self.geom_names[int(con.geom2)]]
            if "table" not in names:
                continue
            for name in WHEEL_NAMES:
                if "wheel_geom_"+name in names:
                    force = np.zeros(6)
                    mujoco.mj_contactForce(self.model, self.data, index, force)
                    initial_wheel_loads[name] += float(force[0])
        self.initial_state_audit["released_initial_wheel_normal_loads_n"] = initial_wheel_loads
        self.c["car_initial_x_m"] = float(self.data.qpos[car_qa])
        self.c["actual_initial_spring_compression_m"] = compression
        self.c["initial_spring_energy_j"] = self.initial_spring_energy_j
        self.reference_initial_state = self.capture_initial_state()

    def _prepare_initial_state_without_car(self, initial_state):
        """DELETE car: every remaining body starts from the shared source state with zero velocity.

        The pusher plate keeps the source's held compression; with no car against it nothing holds
        it, so the spring releases at t=0 like the source latch. No pre-release step is taken.
        """
        if initial_state is None:
            raise ValueError("DELETE car starts from the shared source initial state")
        self.data.qvel[:] = 0.0
        self.restore_initial_state(initial_state)
        self.data.qvel[:] = 0.0
        self.data.qacc_warmstart[:] = 0.0
        self.data.time = 0.0
        mujoco.mj_forward(self.model, self.data)
        self.nominal_contact_geometry = {}
        compression = -float(self.data.qpos[self.spring_qpos]) if self.spring_qpos is not None else 0.0
        self.initial_spring_energy_j = .5*self.c["spring_stiffness_n_m"]*compression**2 if self.spring_qpos is not None else 0.0
        self.initial_mechanical_energy_j = float(self.data.energy.sum())
        self.initial_kinetic_energy_j = float(self.data.energy[1])
        self.initial_available_energy_j = self.initial_kinetic_energy_j+self.initial_spring_energy_j
        self.initial_gravity_and_spring_energy_j = float(self.data.energy[0])
        self.max_total_energy_j = self.initial_mechanical_energy_j
        self.max_spring_compression_m = compression
        self.max_spring_energy_j = self.initial_spring_energy_j
        self.initial_state_audit = {
            "method": "car absent (DELETE car); remaining qpos restored from the shared source initial state, zero qvel, no pre-release mj_step calls",
            "car_present": False, "pre_release_physical_steps": 0,
            "nominal_compression_m": self.c["spring_initial_compression_m"],
            "obstacle_present": self.obstacle_id is not None,
            "actual_initial_compression_m": compression,
            "initial_spring_energy_j": self.initial_spring_energy_j,
            "initial_kinetic_energy_j": self.initial_kinetic_energy_j,
            "initial_available_energy_j": self.initial_available_energy_j,
            "released_spring_acceleration_m_s2": float(self.data.qacc[self.spring_dof]) if self.spring_dof is not None else None,
            "all_initial_generalized_velocities_exactly_zero": bool(np.array_equal(self.data.qvel, np.zeros(self.model.nv))),
            "active_release_latches": int(np.count_nonzero(self.data.eq_active)),
            "initial_physical_time_s": float(self.data.time),
            "release_actuator_count": int(self.model.nu),
        }
        self.c["actual_initial_spring_compression_m"] = compression
        self.c["initial_spring_energy_j"] = self.initial_spring_energy_j
        self.reference_initial_state = self.capture_initial_state()

    def capture_initial_state(self):
        state = {}
        for name, joint in [("car", self.car_joint), ("block", self.block_joint), ("spring", self.spring_joint), ("obstacle", self.obstacle_joint)]:
            if joint is None:
                continue
            qa = self.model.jnt_qposadr[joint]
            count = 7 if name in ("car", "block", "obstacle") else 1
            state[name] = self.data.qpos[qa:qa+count].tolist()
        state["wheels"] = self.data.qpos[self.wheel_qposes].tolist()
        state["_nominal_compression_m"] = self.c["spring_initial_compression_m"]
        state["_nominal_contact_geometry"] = copy.deepcopy(self.nominal_contact_geometry)
        return state

    def restore_initial_state(self, state):
        for name, joint in [("car", self.car_joint), ("block", self.block_joint), ("spring", self.spring_joint), ("obstacle", self.obstacle_joint)]:
            if joint is None or name not in state:
                continue
            qa = self.model.jnt_qposadr[joint]
            self.data.qpos[qa:qa+len(state[name])] = state[name]
        if self.car_present:
            self.data.qpos[self.wheel_qposes] = state.get("wheels", [0.0]*4)
        mujoco.mj_forward(self.model, self.data)

    def state(self):
        q = float(self.data.qpos[self.spring_qpos]) if self.spring_qpos is not None else 0.0
        qdot = float(self.data.qvel[self.spring_dof]) if self.spring_dof is not None else 0.0
        compression = -q if self.spring_joint is not None else 0.0
        out = {
            "car_transforms": body_transform(self.data, self.car_id) if self.car_present else self.car_placeholder.copy(),
            "car_velocities": body_velocity(self.model, self.data, self.car_id) if self.car_present else np.zeros(6),
            "wheel_transforms": np.asarray([body_transform(self.data, i) for i in self.wheel_ids]),
            "wheel_angles": self.data.qpos[self.wheel_qposes].copy(),
            "wheel_angular_velocities": self.data.qvel[self.wheel_dofs].copy(),
            "block_transforms": body_transform(self.data, self.block_id) if self.block_id is not None else self.block_placeholder.copy(),
            "block_velocities": body_velocity(self.model, self.data, self.block_id) if self.block_id is not None else np.zeros(6),
            "obstacle_transforms": body_transform(self.data, self.obstacle_id) if self.obstacle_id is not None else self.obstacle_placeholder.copy(),
            "obstacle_velocities": body_velocity(self.model, self.data, self.obstacle_id) if self.obstacle_id is not None else np.zeros(6),
            "spring_plate_transforms": body_transform(self.data, self.spring_id) if self.spring_id is not None else np.eye(4),
            "spring_compression": compression,
            "spring_length": self.c["spring_rest_length_m"]+q,
            "spring_velocity_m_s": qdot,
            "spring_energy_j": 0.5*self.c["spring_stiffness_n_m"]*q*q if self.spring_joint is not None else 0.0,
            "mechanical_energy_j": float(self.data.energy.sum()),
            "kinetic_energy_j": float(self.data.energy[1]),
            "potential_energy_j": float(self.data.energy[0]),
            "damping_loss_j": self.loss_damping_j,
            "spring_damping_loss_j": self.loss_spring_damping_j,
            "bearing_damping_loss_j": self.loss_bearing_damping_j,
            "joint_friction_loss_j": self.loss_joint_friction_j,
            "contact_friction_work_loss_j": self.loss_contact_friction_j,
            "contact_normal_work_loss_j": self.loss_contact_normal_j,
            "guide_endstop_work_loss_j": self.loss_joint_limit_j,
        }
        invalid = [name for name, value in out.items() if not np.isfinite(value).all()]
        if invalid:
            raise RuntimeError(
                "Nonfinite physical state at "
                f"t={float(self.data.time):.9f}s under MuJoCo {mujoco.__version__}; "
                f"invalid fields: {', '.join(invalid)}"
            )
        return out

    def _point_velocity(self, point, body_id):
        jacp = np.zeros((3, self.model.nv))
        mujoco.mj_jac(self.model, self.data, jacp, None, point, int(body_id))
        return jacp@self.data.qvel

    def _contact_telemetry(self):
        dt = self.c["simulation_dt_s"]
        pending_work = []
        # This model uses a dense Jacobian and elliptic contact cones. Native
        # contact rows map generalized velocity to normal, tangential, torsional
        # and rolling relative velocity in the same order as mj_contactForce.
        jacobian = self.data.efc_J.reshape(self.data.nefc, self.model.nv)
        for index in range(self.data.ncon):
            con = self.data.contact[index]
            if con.efc_address < 0:
                continue
            force = np.zeros(6)
            mujoco.mj_contactForce(self.model, self.data, index, force)
            if force[0] <= 1e-9:
                continue
            first, second = int(con.geom1), int(con.geom2)
            names = sorted([self.geom_names[first], self.geom_names[second]])
            if any(name.startswith("car_chassis") for name in names):
                self.contact_witnesses.append([
                    float(self.data.time), first, second, *con.pos.tolist(),
                    float(force[0]), float(con.dist), *body_transform(self.data, self.car_id).ravel().tolist()])
            pair = "::".join(names)
            rec = self.contact_records.setdefault(pair, {"first_contact_s": float(self.data.time),
                "last_contact_s": float(self.data.time), "normal_impulse_n_s": 0.0,
                "peak_normal_force_n": 0.0, "max_penetration_m": 0.0,
                "normal_work_loss_j": 0.0, "friction_work_loss_j": 0.0})
            overlap = max(0., -float(con.dist))
            rec["last_contact_s"] = float(self.data.time)
            rec["normal_impulse_n_s"] += force[0]*dt
            rec["peak_normal_force_n"] = max(rec["peak_normal_force_n"], force[0])
            rec["max_penetration_m"] = max(rec["max_penetration_m"], overlap)
            self.max_penetration_m = max(self.max_penetration_m, overlap)
            address, dimension = int(con.efc_address), int(con.dim)
            pending_work.append((rec, force[:dimension].copy(), jacobian[address:address+dimension].copy()))
        return pending_work

    def advance(self):
        dt = self.c["simulation_dt_s"]
        if np.any(self.data.eq_active) or np.any(self.data.qfrc_applied) or np.any(self.data.xfrc_applied):
            raise RuntimeError("Release trajectory must have no active hold or applied force")
        old_velocity = self.data.qvel.copy()
        old_damping_power = float(np.dot(self.model.dof_damping, old_velocity*old_velocity))
        spring_old_power = (self.c["spring_damping_n_s_m"]*old_velocity[self.spring_dof]**2
                            if self.spring_dof is not None else 0.0)
        bearing_old_power = float(np.sum(self.c["wheel_bearing_damping_n_m_s"]*old_velocity[self.wheel_dofs]**2))
        # mj_step1 leaves physical positions unchanged while evaluating current
        # forces/contact. mj_step2 advances without a user force or control input.
        mujoco.mj_step1(self.model, self.data)
        contact_work = self._contact_telemetry()
        joint_friction_work = []
        joint_limit_work = []
        jacobian = self.data.efc_J.reshape(self.data.nefc, self.model.nv)
        for i in range(self.data.nefc):
            if self.data.efc_type[i] == mujoco.mjtConstraint.mjCNSTR_FRICTION_DOF:
                joint_friction_work.append((float(self.data.efc_force[i]), jacobian[i].copy()))
            elif self.data.efc_type[i] == mujoco.mjtConstraint.mjCNSTR_LIMIT_JOINT:
                joint_limit_work.append((float(self.data.efc_force[i]), jacobian[i].copy()))
                self.max_joint_limit_violation_m = max(self.max_joint_limit_violation_m, -float(self.data.efc_pos[i]))
        mujoco.mj_step2(self.model, self.data)
        midpoint_velocity = .5*(old_velocity+self.data.qvel)
        for rec, contact_force, contact_jacobian in contact_work:
            relative_velocity = contact_jacobian@midpoint_velocity
            normal_loss = -float(contact_force[0]*relative_velocity[0])*dt
            friction_loss = -float(np.dot(contact_force[1:], relative_velocity[1:]))*dt
            rec["normal_work_loss_j"] += normal_loss
            rec["friction_work_loss_j"] += friction_loss
            self.loss_contact_normal_j += normal_loss
            self.loss_contact_friction_j += friction_loss
        self.loss_joint_friction_j += sum(-force*float(row@midpoint_velocity)*dt
                                             for force, row in joint_friction_work)
        self.loss_joint_limit_j += sum(-force*float(row@midpoint_velocity)*dt
                                          for force, row in joint_limit_work)
        # Forward updates transform/velocity/energy to the new native state;
        # it cannot alter qpos or qvel and is necessary for exact cache replay.
        mujoco.mj_forward(self.model, self.data)
        new_power = float(np.dot(self.model.dof_damping, self.data.qvel*self.data.qvel))
        spring_new_power = (self.c["spring_damping_n_s_m"]*self.data.qvel[self.spring_dof]**2
                            if self.spring_dof is not None else 0.0)
        bearing_new_power = float(np.sum(self.c["wheel_bearing_damping_n_m_s"]*self.data.qvel[self.wheel_dofs]**2))
        self.loss_damping_j += 0.5*(old_damping_power+new_power)*dt
        self.loss_spring_damping_j += 0.5*(spring_old_power+spring_new_power)*dt
        self.loss_bearing_damping_j += 0.5*(bearing_old_power+bearing_new_power)*dt
        self.max_forward_inverse_discrepancy = max(self.max_forward_inverse_discrepancy, float(np.max(self.data.solver_fwdinv)))
        if self.spring_qpos is not None:
            compression = -float(self.data.qpos[self.spring_qpos])
            if compression > self.max_spring_compression_m:
                self.max_spring_compression_m = compression
                self.max_spring_compression_time_s = float(self.data.time)
            self.max_spring_energy_j = max(self.max_spring_energy_j, .5*self.c["spring_stiffness_n_m"]*compression**2)
            if compression > .001:
                for wheel_id in self.wheel_ids:
                    wheel_axis_z = float(self.data.xmat[wheel_id].reshape(3, 3)[2, 1])
                    lowest_z = (self.data.xpos[wheel_id, 2]
                        -self.c["wheel_radius_m"]*math.sqrt(max(0.0, 1.0-wheel_axis_z**2))
                        -self.c["wheel_width_m"]/2*abs(wheel_axis_z))
                    self.max_launch_wheel_gap_m = max(self.max_launch_wheel_gap_m, float(lowest_z))
        car_v = body_velocity(self.model, self.data, self.car_id) if self.car_present else np.zeros(6)
        self.peak_car_speed_m_s = max(self.peak_car_speed_m_s, float(np.linalg.norm(car_v[:3])))
        if self.first_positive_car_velocity_s is None and car_v[0] > .02:
            self.first_positive_car_velocity_s = float(self.data.time)
        if self.block_id is not None:
            displacement = np.linalg.norm(self.data.xpos[self.block_id]-self.block_placeholder[:3, 3])
            self.max_block_displacement_m = max(self.max_block_displacement_m, float(displacement))
            self.peak_block_speed_m_s = max(self.peak_block_speed_m_s, float(np.linalg.norm(body_velocity(self.model, self.data, self.block_id)[:3])))
        if self.obstacle_id is not None:
            displacement = np.linalg.norm(self.data.xpos[self.obstacle_id]-self.obstacle_placeholder[:3, 3])
            self.max_obstacle_displacement_m = max(self.max_obstacle_displacement_m, float(displacement))
            self.peak_obstacle_speed_m_s = max(self.peak_obstacle_speed_m_s, float(np.linalg.norm(body_velocity(self.model, self.data, self.obstacle_id)[:3])))
        self.max_total_energy_j = max(self.max_total_energy_j, float(self.data.energy.sum()))
        # Rolling constraint residual at each wheel's bottom point. Contact is
        # allowed to slip during bumper impact; omega is never forced to v/R.
        wr = self.c["wheel_radius_m"]
        for bid in self.wheel_ids:
            center = self.data.xpos[bid]
            if center[2] < wr+0.001:
                vel = body_velocity(self.model, self.data, bid)
                bottom_v = vel[:3]+np.cross(vel[3:], [0., 0., -wr])
                slip = float(np.linalg.norm(bottom_v[:2]))
                self.max_wheel_slip_m_s = max(self.max_wheel_slip_m_s, slip)
                self.wheel_slip_squared_sum += slip*slip
                self.wheel_slip_samples += 1
        self.physical_steps += 1

    def summary(self):
        final = self.state()
        mechanical_drop = self.initial_mechanical_energy_j-float(final["mechanical_energy_j"])
        work = (self.loss_damping_j+self.loss_joint_friction_j+self.loss_contact_friction_j
                +self.loss_contact_normal_j+self.loss_joint_limit_j)
        compression = self.max_spring_compression_m
        force = self.c["spring_stiffness_n_m"]*compression
        shear_stress = self.c["spring_wahl_factor"]*8*force*self.c["spring_mean_diameter_m"]/(math.pi*self.c["spring_wire_diameter_m"]**3)
        active_contact = {key: val for key, val in self.contact_records.items() if val["normal_impulse_n_s"] > 1e-7}
        spring_times = [v["first_contact_s"] for k, v in active_contact.items() if "spring_plate_geom" in k and "car_chassis" in k]
        block_times = [v["first_contact_s"] for k, v in active_contact.items() if "block_geom" in k.split("::") and "car_chassis" in k]
        obstacle_times = [v["first_contact_s"] for k, v in active_contact.items() if "obstacle_block_geom" in k.split("::") and "car_chassis" in k]
        obstacle_block_times = [v["first_contact_s"] for k, v in active_contact.items() if set(k.split("::")) == {"block_geom", "obstacle_block_geom"}]
        backstop_times = [v["first_contact_s"] for k, v in active_contact.items() if "fixed_backstop" in k and "car_chassis" in k]
        return {
            "scene_id": SCENE_ID, "case_id": self.c["case_id"],
            "solver": "MuJoCo "+mujoco.__version__, "integrator": "implicitfast",
            "simulation_dt_s": self.c["simulation_dt_s"], "physical_steps": self.physical_steps,
            "actuator_count": int(self.model.nu), "applied_force_max": float(np.max(np.abs(self.data.qfrc_applied))),
            "hand_authored_motion": False, "hand_authored_bounce": False,
            "hand_authored_deformation": False,
            "coil_visualization": "mechanical axial reduced coordinates; not a full wire strain field",
            "material_calibrated": False, "accepted_benchmark_gt": False,
            "status": "UNCALIBRATED_PHYSICAL_SURROGATE",
            "first_spring_contact_s": min(spring_times) if spring_times else None,
            "first_block_contact_s": min(block_times) if block_times else None,
            "first_obstacle_contact_s": min(obstacle_times) if obstacle_times else None,
            "first_obstacle_original_block_contact_s": min(obstacle_block_times) if obstacle_block_times else None,
            "obstacle_present": self.c["obstacle_present"],
            "first_backstop_contact_s": min(backstop_times) if backstop_times else None,
            "first_rightward_car_velocity_s": self.first_positive_car_velocity_s,
            "peak_spring_compression_m": compression,
            "peak_spring_compression_time_s": self.max_spring_compression_time_s,
            "peak_spring_energy_j": self.max_spring_energy_j,
            "peak_spring_force_n": force, "peak_nominal_corrected_wire_shear_stress_pa": shear_stress,
            "minimum_coil_length_m": self.c["spring_rest_length_m"]-compression,
            "coil_bind_clearance_m": self.c["spring_rest_length_m"]-compression-self.c["spring_solid_length_m"],
            "stroke_limit_clearance_m": self.c["spring_max_stroke_m"]-compression,
            "initial_kinetic_energy_j": self.initial_kinetic_energy_j,
            "initial_spring_energy_j": self.initial_spring_energy_j,
            "initial_available_energy_j": self.initial_available_energy_j,
            "actual_initial_spring_compression_m": self.initial_state_audit["actual_initial_compression_m"],
            "initial_state_audit": self.initial_state_audit,
            "initial_mechanical_energy_j": self.initial_mechanical_energy_j,
            "final_mechanical_energy_j": float(final["mechanical_energy_j"]),
            "mechanical_energy_drop_j": mechanical_drop,
            "maximum_mechanical_energy_gain_j": max(0.0, self.max_total_energy_j-self.initial_mechanical_energy_j),
            "explicit_damping_loss_j": self.loss_damping_j,
            "spring_damping_loss_j": self.loss_spring_damping_j,
            "bearing_damping_loss_j": self.loss_bearing_damping_j,
            "joint_dry_friction_work_loss_j": self.loss_joint_friction_j,
            "guide_endstop_work_loss_j": self.loss_joint_limit_j,
            "max_guide_endstop_soft_violation_m": self.max_joint_limit_violation_m,
            "contact_tangential_and_rolling_work_loss_j": self.loss_contact_friction_j,
            "signed_contact_normal_work_loss_j": self.loss_contact_normal_j,
            "work_energy_residual_j": mechanical_drop-work,
            "work_energy_residual_fraction_initial_available": ((mechanical_drop-work)/self.initial_available_energy_j
                                                               if self.initial_available_energy_j > 0 else None),
            "work_energy_residual_fraction_initial_kinetic": None,
            "energy_scope": "all multibody kinetic and gravity, plus guided spring elastic energy; contact implicit deformation is not stored in MuJoCo energy",
            "contact_work_scope": "native pre-step contact and joint-limit Jacobian times same-step midpoint generalized velocity, dotted with native force/torque; signed work not clipped",
            "max_contact_penetration_m": self.max_penetration_m,
            "max_wheel_bottom_slip_m_s": self.max_wheel_slip_m_s,
            "rms_wheel_bottom_slip_m_s": math.sqrt(self.wheel_slip_squared_sum/max(1, self.wheel_slip_samples)),
            "max_launch_wheel_surface_gap_m": self.max_launch_wheel_gap_m,
            "peak_car_speed_m_s": self.peak_car_speed_m_s,
            "peak_block_speed_m_s": self.peak_block_speed_m_s,
            "max_block_displacement_m": self.max_block_displacement_m,
            "max_obstacle_displacement_m": self.max_obstacle_displacement_m,
            "peak_obstacle_speed_m_s": self.peak_obstacle_speed_m_s,
            "final_car_position_m": final["car_transforms"][:3, 3].tolist(),
            "final_car_velocity_m_s": final["car_velocities"][:3].tolist(),
            "final_block_position_m": final["block_transforms"][:3, 3].tolist(),
            "final_block_velocity_m_s": final["block_velocities"][:3].tolist(),
            "final_obstacle_position_m": final["obstacle_transforms"][:3, 3].tolist(),
            "final_obstacle_velocity_m_s": final["obstacle_velocities"][:3].tolist(),
            "max_forward_inverse_discrepancy": self.max_forward_inverse_discrepancy,
            "warning_counts": {str(i): int(w.number) for i, w in enumerate(self.data.warning) if w.number},
            "contact_pairs": active_contact,
            "solver_geometry_names": self.geom_names,
            "solver_body_names": [mujoco.mj_id2name(self.model, mujoco.mjtObj.mjOBJ_BODY, i) for i in range(self.model.nbody)],
        }


def run_case(c, out=None, initial_state=None):
    require_mujoco_runtime()
    start = time.monotonic()
    source_snapshot = LOADED_PHYSICS_SOURCE
    cli_snapshot = LOADED_CLI_SOURCE
    if ((HERE/"physics_model.py").read_bytes() != source_snapshot
            or (CASE_DIR/"simulate_spring_car_collision.py").read_bytes() != cli_snapshot
            or (CASE_DIR/"scene_spec.json").read_bytes() != LOADED_SPEC_SOURCE):
        raise RuntimeError("Physics or CLI source changed after import; restart the simulation with frozen code")
    asset_snapshots = {}
    for parameter, output_name, expected_hash_parameter in [
        ("car_asset_geometry_contract_file", "native_input_car_geometry.json", "car_asset_geometry_contract_sha256"),
        ("car_collision_points_file", "native_input_car_body_points.npz", "car_collision_points_sha256"),
        ("car_collision_surface_file", "native_input_car_body_surface.npz", "car_collision_surface_sha256"),
        ("car_collision_surface_parts_file", "native_input_car_body_surface_parts.json", "car_collision_surface_parts_sha256"),
        ("source_initial_state_input_file", "native_input_source_initial_state.json", "source_initial_state_input_sha256"),
    ]:
        if c.get(parameter):
            content = Path(c[parameter]).read_bytes()
            digest = hashlib.sha256(content).hexdigest()
            if digest != c[expected_hash_parameter]:
                raise RuntimeError("Asset input changed after parameters were prepared: "+parameter)
            asset_snapshots[output_name] = content
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        (out/"source_scene_spec.json").write_bytes(LOADED_SPEC_SOURCE)
        for filename, content in asset_snapshots.items():
            (out/filename).write_bytes(content)
    sim = Simulation(c, initial_state)
    sample = round(1/(c["fps"]*c["simulation_dt_s"]))
    steps = round(c["duration_s"]/c["simulation_dt_s"])
    expected_frames = round(c["duration_s"]*c["fps"])
    states, times = [sim.state()], [0.0]
    # A four-second clip at 24 fps has exactly 96 samples on [0, 4 s).
    # Integrate to just before the exclusive endpoint and never append t=4 s.
    for step in range(1, steps):
        sim.advance()
        if step % max(1, round(1/c["simulation_dt_s"])) == 0:
            print(json.dumps({"native_case_progress": c["case_id"], "physical_time_s": step*c["simulation_dt_s"],
                              "wall_elapsed_s": time.monotonic()-start}), flush=True)
        if step % sample == 0:
            states.append(sim.state())
            times.append(step*c["simulation_dt_s"])
    if len(times) != expected_frames:
        raise RuntimeError(f"Expected {expected_frames} half-open video samples, got {len(times)}")
    arrays = {key: np.asarray([s[key] for s in states]) for key in states[0]}
    arrays.update(times=np.asarray(times), spring_present=np.asarray(c["spring_present"]),
                  car_present=np.asarray(bool(c.get("car_present", True))), block_present=np.asarray(c["block_present"]),
                  obstacle_present=np.asarray(c["obstacle_present"]),
                  wheel_order=np.asarray(WHEEL_NAMES),
                  spring_anchor=np.asarray([c["spring_anchor_x_m"], 0., c["spring_axis_z_m"]]),
                  spring_rest_length_m=np.asarray(c["spring_rest_length_m"]),
                  spring_wire_diameter_m=np.asarray(c["spring_wire_diameter_m"]),
                  wheel_radius_m=np.asarray(c["wheel_radius_m"]),
                  wheel_centers_local_m=np.asarray(c["car_wheel_centers_local_m"]))
    summary = sim.summary()
    summary["elapsed_s"] = time.monotonic()-start
    summary["frame_count"] = len(times)
    summary["endpoint_policy"] = "half-open [0,duration): exactly fps*duration samples; no duplicate endpoint frame"
    if ((HERE/"physics_model.py").read_bytes() != source_snapshot
            or (CASE_DIR/"simulate_spring_car_collision.py").read_bytes() != cli_snapshot
            or (CASE_DIR/"scene_spec.json").read_bytes() != LOADED_SPEC_SOURCE):
        raise RuntimeError("Source changed during simulation; candidate native outputs are not frozen")
    if out is not None:
        out = Path(out)
        out.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(out/"trajectory.npz", **arrays)
        witnesses = np.asarray(sim.contact_witnesses, np.float64).reshape(-1, 24)
        np.savez_compressed(out/"contact_witnesses.npz", times_s=witnesses[:, 0],
                            geometry_ids=witnesses[:, 1:3].astype(np.int32), points_world_m=witnesses[:, 3:6],
                            normal_force_n=witnesses[:, 6], signed_contact_distance_m=witnesses[:, 7],
                            car_transforms=witnesses[:, 8:].reshape(-1, 4, 4), geometry_names=np.asarray(sim.geom_names))
        json_save(out/"scene_params.json", c)
        json_save(out/"physics_telemetry.json", summary)
        json_save(out/"initial_state.json", sim.reference_initial_state)
        json_save(out/"initial_state_audit.json", sim.initial_state_audit)
        (out/"physics_model.xml").write_bytes(sim.xml.encode("utf-8"))
        source = HERE/"physics_model.py"
        json_save(out/"physics_provenance.json", {
            "python_source": str(source),
            "scene_spec_snapshot": "source_scene_spec.json",
            "scene_spec_sha256": hashlib.sha256(LOADED_SPEC_SOURCE).hexdigest(),
            "model_xml_sha256": hashlib.sha256(sim.xml.encode("utf-8")).hexdigest(),
            "engine_version": mujoco.__version__, "numpy_version": np.__version__,
            "native_solver_cache": True, "actuators": 0, "controls": 0,
            "source_shared_initial_state": initial_state is not None,
            "initial_condition": ("stationary precompressed spring and car; explicit latch removed at t=0" if c.get("car_present", True)
                                  else "car absent (DELETE car); stationary precompressed spring released at t=0"),
            "pre_release_physical_steps": 0,
            "initial_kinetic_energy_j": sim.initial_kinetic_energy_j,
            "initial_spring_energy_j": sim.initial_spring_energy_j,
            "trajectory_sha256": hashlib.sha256((out/"trajectory.npz").read_bytes()).hexdigest(),
            "contact_witnesses_sha256": hashlib.sha256((out/"contact_witnesses.npz").read_bytes()).hexdigest(),
            "scene_params_sha256": hashlib.sha256((out/"scene_params.json").read_bytes()).hexdigest(),
            "asset_input_snapshot_sha256": {name: hashlib.sha256(content).hexdigest() for name, content in asset_snapshots.items()},
            "render_interpolation": "sampled solver states; must not patch collision position or spring trajectory",
        })
    return arrays, summary, sim.reference_initial_state
