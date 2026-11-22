"""Build the accepted PCVE rigid-fluid sink scene from its frozen template.

Run with Blender 4.3.2.  This stage validates the accepted scene, redirects
Mantaflow to an isolated work cache, and writes ``work/scene.blend``.  It does
not bake, render, or place cache data in the delivery output directory.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import bmesh
import bpy
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import asset


HERE = Path(__file__).resolve().parents[1]
ACCEPTED_TEMPLATE = asset("scenes/faucet_sink/scene_template.blend")


def default_template() -> Path:
    local_template = HERE / "assets" / "scene_template.blend"
    return local_template if local_template.is_file() else ACCEPTED_TEMPLATE


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--template", type=Path, default=default_template())
    parser.add_argument(
        "--case-id",
        choices=("source", "edit_low_flow", "edit_high_flow", "edit_high_viscosity", "edit_stop_flow_at_2s"),
        default="source",
    )
    parser.add_argument(
        "--high-viscosity-m2-s",
        type=float,
        default=2.0e-2,
        help="Explicit SI kinematic viscosity for edit_high_viscosity probes.",
    )
    parser.add_argument(
        "--flow-subframes",
        type=int,
        default=2,
        help="Temporal sampling of the continuous nozzle inlet.",
    )
    parser.add_argument(
        "--inlet-depth-m",
        type=float,
        default=None,
        help="Override nozzle-source depth; the accepted default is a planar outlet source.",
    )
    parser.add_argument(
        "--inlet-surface-distance",
        type=float,
        default=None,
        help="Override Mantaflow source dilation in voxel units for isolated probes.",
    )
    parser.add_argument("--work-dir", type=Path)
    argv = sys.argv[sys.argv.index("--") + 1 :] if "--" in sys.argv else []
    return parser.parse_args(argv)


def fluid_domain():
    domain = bpy.data.objects.get("LiquidDomain")
    if domain is None:
        raise RuntimeError("Missing LiquidDomain")
    modifiers = [
        modifier
        for modifier in domain.modifiers
        if modifier.type == "FLUID" and modifier.fluid_type == "DOMAIN"
    ]
    if len(modifiers) != 1 or modifiers[0].domain_settings is None:
        raise RuntimeError("Expected exactly one configured liquid domain")
    return domain, modifiers[0].domain_settings


def replace_with_planar_inlet(
    velocity: float,
    radius: float,
    surface_distance: float,
    subframes: int,
    inlet_depth_m: float,
):
    """Create a calibrated nozzle source at the measured outlet bore."""
    old = bpy.data.objects.get("FaucetWaterInflow")
    if old is not None:
        bpy.data.objects.remove(old, do_unlink=True)
    if inlet_depth_m > 0.0:
        bpy.ops.mesh.primitive_cylinder_add(
            vertices=64,
            radius=radius,
            depth=inlet_depth_m,
            location=(0.242, 0.785, 0.995 - inlet_depth_m / 2.0),
        )
    else:
        bpy.ops.mesh.primitive_circle_add(
            vertices=64,
            radius=radius,
            fill_type="NGON",
            location=(0.242, 0.785, 0.995),
        )
    emitter = bpy.context.object
    emitter.name = "FaucetWaterInflow"
    emitter.hide_render = True
    modifier = emitter.modifiers.new("Nozzle Liquid Inflow", "FLUID")
    modifier.fluid_type = "FLOW"
    flow = modifier.flow_settings
    flow.flow_type = "LIQUID"
    flow.flow_behavior = "INFLOW"
    flow.use_plane_init = inlet_depth_m <= 0.0
    flow.surface_distance = surface_distance
    flow.subframes = subframes
    flow.use_inflow = True
    flow.use_initial_velocity = True
    flow.velocity_coord = (0.0, 0.0, -velocity)
    return emitter, flow


def repair_basin_collision_center() -> dict[str, float | int | str]:
    """Remove the high-valence pole below the blocked drain.

    The accepted proxy closes the bowl with 96 narrow triangles meeting at a
    single top-center vertex.  That sub-voxel fan is harmless for water, but
    the dedicated high-viscosity solve can accumulate pressure at the pole and
    become unstable.  Preserve the existing first ring and replace only the
    fan by a flat n-gon; the visible basin mesh is not modified.
    """
    bowl = bpy.data.objects.get("BasinProxy_CurvedBowl")
    if bowl is None or bowl.type != "MESH":
        raise RuntimeError("Missing BasinProxy_CurvedBowl")

    center_x, center_y = 0.302, 0.785
    bm = bmesh.new()
    try:
        bm.from_mesh(bowl.data)
        center_vertices = [
            vertex
            for vertex in bm.verts
            if math.hypot(vertex.co.x - center_x, vertex.co.y - center_y) < 1.0e-6
        ]
        if len(center_vertices) != 2:
            raise RuntimeError(
                f"Expected two basin center pole vertices, found {len(center_vertices)}"
            )
        top_pole = max(center_vertices, key=lambda vertex: vertex.co.z)
        ring = [edge.other_vert(top_pole) for edge in top_pole.link_edges]
        if len(ring) != 96 or len(top_pole.link_faces) != 96:
            raise RuntimeError(
                "Unexpected basin center topology: expected a 96-edge/96-face top pole"
            )

        original_z = float(top_pole.co.z)
        cap_z = sum(vertex.co.z for vertex in ring) / len(ring)
        max_surface_delta = max(
            abs(float(vertex.co.z) - cap_z) for vertex in ring
        )
        if abs(original_z - cap_z) > 1.0e-3 or max_surface_delta > 1.0e-3:
            raise RuntimeError(
                "Refusing collision repair larger than 1 mm: "
                f"pole={abs(original_z - cap_z):.9f} m, "
                f"ring={max_surface_delta:.9f} m"
            )

        for vertex in ring:
            vertex.co.z = cap_z
        ring.sort(
            key=lambda vertex: math.atan2(
                vertex.co.y - center_y, vertex.co.x - center_x
            )
        )
        bmesh.ops.delete(bm, geom=[top_pole], context="VERTS")
        cap = bm.faces.new(ring)
        cap.material_index = 0
        bm.normal_update()
        bm.to_mesh(bowl.data)
    finally:
        bm.free()
    bowl.data.update()
    return {
        "object": bowl.name,
        "removed_pole_valence": 96,
        "cap_z_m": float(cap_z),
        "max_surface_delta_m": max(
            abs(original_z - cap_z), max_surface_delta
        ),
    }


def stop_inflow_at_2s(scene, emitter, flow) -> list[dict]:
    """Stop the source at t=(49-1)/24, retaining the simulated liquid.

    Initial velocity does not govern Mantaflow's source volume. Disable the
    inlet as well, so zero velocity means zero injection, not water created
    at rest. Constant keys preserve the baseline up to the event boundary.
    """
    for frame, enabled, speed in ((1, True, -0.6), (49, False, 0.0), (96, False, 0.0)):
        flow.velocity_coord = (0.0, 0.0, speed)
        flow.use_inflow = enabled
        flow.keyframe_insert(data_path="velocity_coord", frame=frame, group="Timed inlet")
        flow.keyframe_insert(data_path="use_inflow", frame=frame, group="Timed inlet")
    for curve in emitter.animation_data.action.fcurves:
        for key in curve.keyframe_points:
            key.interpolation = "CONSTANT"
    evaluated = []
    for frame, subframe in ((1, 0.0), (48, 0.0), (48, 0.999), (49, 0.0), (50, 0.0), (96, 0.0)):
        scene.frame_set(frame, subframe=subframe)
        enabled = frame < 49
        expected = -0.6 if enabled else 0.0
        if flow.use_inflow != enabled or abs(flow.velocity_coord.z - expected) > 1.0e-6:
            raise RuntimeError(f"Incorrect inlet schedule at frame {frame}+{subframe}")
        evaluated.append({"frame": frame + subframe, "time_s": (frame + subframe - 1) / 24,
                          "velocity_m_s": list(flow.velocity_coord), "use_inflow": flow.use_inflow})
    scene.frame_set(1)
    return evaluated


def main() -> None:
    args = parse_args()
    if not 1 <= args.flow_subframes <= 10:
        raise ValueError("flow-subframes must be between 1 and 10")
    if args.inlet_depth_m is not None and args.inlet_depth_m < 0.0:
        raise ValueError("inlet-depth-m must be non-negative")
    if args.inlet_surface_distance is not None and args.inlet_surface_distance < 0.0:
        raise ValueError("inlet-surface-distance must be non-negative")
    template = args.template.expanduser().resolve()
    work = (args.work_dir or (HERE / "cases" / args.case_id / "work")).expanduser().resolve()
    if not template.is_file():
        raise FileNotFoundError(template)
    work.mkdir(parents=True, exist_ok=True)
    if (work / "scene.blend").exists():
        raise FileExistsError(f"Refusing to overwrite a prepared scene: {work}")

    bpy.ops.wm.open_mainfile(filepath=str(template))
    scene = bpy.context.scene
    domain, settings = fluid_domain()
    # Redirect before geometry, flow or animation edits can invalidate the
    # template's absolute Mantaflow cache. A copied blend is not isolation.
    cache = (work / "fluid_cache").resolve()
    template_cache = Path(bpy.path.abspath(settings.cache_directory)).resolve()
    if cache == template_cache or cache in template_cache.parents or template_cache in cache.parents:
        raise RuntimeError(f"Runtime cache overlaps the reference cache: {cache}")
    if cache.exists() and any(cache.iterdir()):
        raise FileExistsError(f"Refusing a populated runtime cache: {cache}")
    settings.cache_directory = str(cache)
    flows = [
        obj.name
        for obj in scene.objects
        if any(mod.type == "FLUID" and mod.fluid_type == "FLOW" for mod in obj.modifiers)
    ]
    if flows != ["FaucetWaterInflow"]:
        raise RuntimeError(f"Unexpected liquid flows: {flows}")
    if any(bpy.data.objects.get(name) for name in ("SinkDrainOutflow", "AccumulatedBasinWater", "BasinVolumeInflow")):
        raise RuntimeError("Rejected outflow or synthetic pool object is present")
    if (scene.frame_start, scene.frame_end, scene.render.fps) != (1, 96, 24):
        raise RuntimeError("Expected the accepted 96-frame, 24 fps scene")
    if settings.domain_type != "LIQUID" or settings.resolution_max != 144:
        raise RuntimeError("Unexpected Mantaflow liquid configuration")

    emitter = bpy.data.objects["FaucetWaterInflow"]
    flow_modifier = next(
        mod for mod in emitter.modifiers if mod.type == "FLUID" and mod.fluid_type == "FLOW"
    )
    flow = flow_modifier.flow_settings
    if tuple(round(value, 6) for value in flow.velocity_coord) != (0.0, 0.0, -0.6):
        raise RuntimeError(f"Unexpected baseline inflow velocity: {tuple(flow.velocity_coord)}")
    if not settings.use_diffusion or settings.use_viscosity:
        raise RuntimeError("Expected the accepted diffusion-based water viscosity path")
    if abs(settings.viscosity_base - 1.0) > 1e-6 or settings.viscosity_exponent != 6:
        raise RuntimeError("Unexpected baseline kinematic viscosity")

    before = {
        "inflow_velocity_m_s": [0.0, 0.0, -0.6],
        "kinematic_viscosity_m2_s": 1.0e-6,
    }
    after = dict(before)
    emitter_radius = 0.0033
    surface_distance = 1.5
    inlet_depth_m = 0.0 if args.inlet_depth_m is None else args.inlet_depth_m
    # Keep the hidden collision geometry identical across source and edits.
    # The repair is safe for the water baseline and required for the dedicated
    # high-viscosity solve, so apply it before branching on physical edits.
    collision_repair = repair_basin_collision_center()
    if args.inlet_surface_distance is not None:
        surface_distance = args.inlet_surface_distance
    if args.case_id == "edit_low_flow":
        after["inflow_velocity_m_s"] = [0.0, 0.0, -0.2]
        # Mantaflow's Initial Velocity controls momentum, while Inflow fills
        # its voxelized source independently. This hidden-source calibration
        # preserves the visible outlet diameter while making the accumulated
        # liquid amount respond clearly to the lower velocity.
        emitter_radius = 0.0025
        surface_distance = 0.0
    elif args.case_id == "edit_high_flow":
        after["inflow_velocity_m_s"] = [0.0, 0.0, -1.5]
    elif args.case_id == "edit_high_viscosity":
        # SI kinematic viscosity through Blender's diffusion path:
        # Follow the accepted coffee-scene routing for explicit SI viscosities
        # above 1e-2 m^2/s: use Blender's dedicated high-viscosity solver and
        # tighten time integration instead of forcing the diffusion path.
        settings.use_diffusion = False
        settings.use_viscosity = True
        settings.viscosity_base = 1.0
        settings.viscosity_exponent = 1
        if args.high_viscosity_m2_s < 1.0e-2:
            raise ValueError("Dedicated high-viscosity probes require at least 1e-2 m^2/s")
        settings.viscosity_value = args.high_viscosity_m2_s
        # The accepted sink-specific probe uses a planar 6.6 mm outlet with
        # zero source dilation.  A 192-cell domain, denser particle sampling,
        # a 50/50 PIC-FLIP blend, and strict adaptive stepping keep the
        # dedicated high-viscosity solve continuous without the late pressure
        # blow-ups that a 256-cell domain with a volumetric source produces.
        settings.resolution_max = 192
        settings.particle_number = 4
        settings.mesh_particle_radius = 1.0
        settings.flip_ratio = 0.5
        settings.cfl_condition = 1.0
        settings.timesteps_min = 4
        settings.timesteps_max = 20
        settings.use_fractions = True
        if args.inlet_depth_m is None:
            inlet_depth_m = 0.0
        if args.inlet_surface_distance is None:
            surface_distance = 0.0
        after["kinematic_viscosity_m2_s"] = args.high_viscosity_m2_s
    emitter, flow = replace_with_planar_inlet(
        velocity=abs(after["inflow_velocity_m_s"][2]),
        radius=emitter_radius,
        surface_distance=surface_distance,
        subframes=args.flow_subframes,
        inlet_depth_m=inlet_depth_m,
    )
    if args.case_id == "edit_stop_flow_at_2s":
        before["timed_edits"] = []
        after["timed_edits"] = [{"at_frame": 49, "at_time_s": 2.0,
                                  "inflow_velocity_m_s": [0.0, 0.0, 0.0], "use_inflow": False}]
        evaluated = stop_inflow_at_2s(scene, emitter, flow)
        scene["pcve_edit_dsl"] = "SET faucet.inflow_velocity TIMES 0 AT FRAME 49"
        scene["pcve_inflow_stop_frame"] = 49
        scene["pcve_inflow_stop_time_s"] = 2.0
        scene["pcve_timed_edits"] = json.dumps(after["timed_edits"])
        (work / "inflow_schedule.json").write_text(json.dumps({
            "edit_dsl": scene["pcve_edit_dsl"],
            "time_convention": "t=(frame-1)/24; frame 49 is 2 seconds",
            "before": before, "after": after, "evaluated": evaluated,
            "existing_liquid": "retained and continues under the active liquid solver",
        }, ensure_ascii=False, indent=2) + "\n")
    scene["pcve_case_id"] = args.case_id
    scene["pcve_physics_before"] = str(before)
    scene["pcve_physics_after"] = str(after)
    scene["pcve_inlet_model"] = "planar_nozzle_flux_calibration"
    scene["pcve_emitter_radius_m"] = emitter_radius
    scene["pcve_emission_surface_distance_voxels"] = surface_distance
    scene["pcve_flow_subframes"] = args.flow_subframes
    scene["pcve_inlet_depth_m"] = inlet_depth_m
    target_flow_ratios = {
        "edit_low_flow": 1.0 / 3.0,
        "edit_high_flow": 2.5,
        "edit_stop_flow_at_2s": 0.5,
    }
    scene["pcve_target_volume_flow_ratio"] = target_flow_ratios.get(args.case_id, 1.0)
    scene["pcve_high_viscosity_solver"] = bool(settings.use_viscosity)
    scene["pcve_high_viscosity_value"] = (
        float(settings.viscosity_value) if settings.use_viscosity else -1.0
    )
    if args.case_id == "edit_high_viscosity":
        scene["pcve_high_viscosity_resolution"] = settings.resolution_max
        scene["pcve_high_viscosity_particle_number"] = settings.particle_number
        scene["pcve_high_viscosity_mesh_particle_radius"] = (
            settings.mesh_particle_radius
        )
        scene["pcve_high_viscosity_flip_ratio"] = settings.flip_ratio
        scene["pcve_high_viscosity_cfl"] = settings.cfl_condition
        scene["pcve_high_viscosity_timesteps_min"] = settings.timesteps_min
        scene["pcve_high_viscosity_timesteps_max"] = settings.timesteps_max
    scene["pcve_collision_repair"] = (
        "BasinProxy_CurvedBowl central 96-way top pole replaced by "
        "flat first-ring n-gon"
    )
    scene["pcve_collision_repair_cap_z_m"] = collision_repair["cap_z_m"]
    scene["pcve_collision_repair_max_delta_m"] = collision_repair[
        "max_surface_delta_m"
    ]

    settings.cache_type = "ALL"
    settings.cache_frame_start = 1
    settings.cache_frame_end = 96
    scene.frame_set(1)
    bpy.ops.wm.save_as_mainfile(filepath=str(work / "scene.blend"))
    print(f"PCVE_SCENE={work / 'scene.blend'}", flush=True)
    print(f"PCVE_RUNTIME_CACHE={cache}", flush=True)
    print(f"PCVE_CASE_ID={args.case_id}", flush=True)
    print(f"PCVE_PHYSICS_BEFORE={before}", flush=True)
    print(f"PCVE_PHYSICS_AFTER={after}", flush=True)
    print(
        f"PCVE_INLET_CALIBRATION=radius:{emitter_radius},surface_distance:{surface_distance}",
        flush=True,
    )
    print(f"PCVE_COLLISION_REPAIR={collision_repair}", flush=True)


if __name__ == "__main__":
    main()
