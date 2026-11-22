"""Formal edit vocabulary and edit cases for the curling scene.

The stone line is ordered along X.  The green stone is an off-at-baseline slot
used by ADD.  DELETE cases rebuild the ordered solver arrays without the target
stone, while mass edits change exactly one entry of ``mass_kg``.
"""
from __future__ import annotations
import pcve_edit_dsl as dsl
from scene_config import BASELINE, scenario

_ph = BASELINE["physics"]
_y,_z = _ph["track_y_m"],_ph["com_height_m"]
_red,_blue,_yellow = _ph["initial_x_m"]
TOTAL_FRAMES = BASELINE["render"]["total_frames"]
GREEN_HANDLE_RGB = [0.018,0.27,0.05]

BASELINE_PHYSICS = {
    "stone_radius":_ph["radius_m"],
    "mass_kg":list(_ph["mass_kg"]),
    "red_location":[_red,_y,_z],
    "blue_location":[_blue,_y,_z],
    "yellow_location":[_yellow,_y,_z],
    "green_location":[0.0,_y,_z],
    # Slots ordered red, blue, green, yellow.
    "stone_active":[1,1,0,1],
}
OBJECTS = {
    "red_stone":{"zh":"红把手冰壶","en":"the red-handled stone"},
    "blue_stone":{"zh":"蓝把手冰壶","en":"the blue-handled stone"},
    "yellow_stone":{"zh":"黄把手冰壶","en":"the yellow-handled stone"},
    "green_stone":{"zh":"绿把手冰壶","en":"a green-handled stone"},
}
VOCAB = dsl.Vocabulary(
    objects=OBJECTS,
    properties={"mass":dsl.PropertySpec("scalar","kg","质量","mass")},
    sim_bindings={
        ("red_stone","mass"):dsl.SimBinding("mass_kg",0),
        ("blue_stone","mass"):dsl.SimBinding("mass_kg",1),
        ("yellow_stone","mass"):dsl.SimBinding("mass_kg",2),
    },
    delete_bindings={
        "red_stone":dsl.DeleteBinding("stone_active",0,0),
        "blue_stone":dsl.DeleteBinding("stone_active",1,0),
        "yellow_stone":dsl.DeleteBinding("stone_active",3,0),
    },
    baseline_physics=BASELINE_PHYSICS,
    geometry={
        "red_stone":dsl.GeometryAnchor("red_location","stone_radius"),
        "blue_stone":dsl.GeometryAnchor("blue_location","stone_radius"),
        "yellow_stone":dsl.GeometryAnchor("yellow_location","stone_radius"),
        "green_stone":dsl.GeometryAnchor("green_location","stone_radius"),
    },
    add_bindings={"green_stone":dsl.AddBinding("stone_active",2,"green_location")},
    total_frames=TOTAL_FRAMES,
)
EDIT_CASES = {
    "edit_add_green_stone_midpoint":{"seed":9109,"dsl":"ADD green_stone BETWEEN blue_stone AND yellow_stone AT MIDPOINT"},
    "edit_delete_yellow_stone":{"seed":9110,"dsl":"DELETE yellow_stone"},
    "edit_delete_blue_stone":{"seed":9111,"dsl":"DELETE blue_stone"},
    "edit_blue_mass_x3":{"seed":9112,"dsl":"SET blue_stone.mass TIMES 3"},
    "edit_red_mass_x1p1":{"seed":9113,"dsl":"SET red_stone.mass TIMES 1.1"},
}

_SOURCE_IDS = list(_ph["object_ids"])
_SOURCE_MASSES = list(_ph["mass_kg"])
_SOURCE_X = list(_ph["initial_x_m"])
_SOURCE_V = list(_ph["initial_velocity_m_per_s"])
_SOURCE_COLORS = list(BASELINE["appearance"]["handle_colors_rgb"])
_SOURCE_INDEX = {"red_stone":0,"blue_stone":1,"yellow_stone":2}


def edit_record(case_id):
    """DSL-derived prompts, physics difference and the solver configuration of one case."""
    case = EDIT_CASES[case_id]
    parsed = dsl.parse(case["dsl"],VOCAB)
    binding_override = dsl.to_scenario_override(parsed,VOCAB)
    appearance_override = None

    if isinstance(parsed,dsl.AddEdit):
        active = binding_override["stone_active"]
        if active!=[1,1,1,1]:
            raise ValueError(active)
        x,y,z = binding_override["green_location"]
        if (y,z)!=(_y,_z):
            raise ValueError("The added stone must stand on the solved track")
        physics_override = {
            "object_ids":["R01","B01","G01","Y01"],
            "mass_kg":[_ph["mass_kg"][0]]*4,
            "initial_x_m":[_red,_blue,x,_yellow],
            "initial_velocity_m_per_s":[_ph["initial_velocity_m_per_s"][0],0.0,0.0,0.0],
        }
        appearance_override = {"handle_colors_rgb":[_SOURCE_COLORS[0],_SOURCE_COLORS[1],GREEN_HANDLE_RGB,_SOURCE_COLORS[2]]}
        physics_diff = {
            parsed.object_id:{"from":"absent","to":"present","position":dsl.add_position_diff(parsed,VOCAB)},
            "timing":dsl.timing_diff(parsed,VOCAB),
        }
    elif isinstance(parsed,dsl.DeleteEdit):
        removed = _SOURCE_INDEX[parsed.object_id]
        kept = [i for i in range(3) if i!=removed]
        physics_override = {
            "object_ids":[_SOURCE_IDS[i] for i in kept],
            "mass_kg":[_SOURCE_MASSES[i] for i in kept],
            "initial_x_m":[_SOURCE_X[i] for i in kept],
            "initial_velocity_m_per_s":[_SOURCE_V[i] for i in kept],
        }
        appearance_override = {"handle_colors_rgb":[_SOURCE_COLORS[i] for i in kept]}
        physics_diff = {
            f"presence ({parsed.object_id})":{"from":"present","to":"absent"},
            "timing":dsl.timing_diff(parsed,VOCAB),
        }
    else:
        physics_override = dsl.to_physics_override(parsed,VOCAB)
        physics_diff = {
            f"{parsed.property_name} ({parsed.object_id})":{
                "from":dsl.baseline_value_for(parsed,VOCAB),
                "to":dsl.resolved_to_value(parsed,VOCAB),
                "factor":parsed.factor,
            },
            "timing":dsl.timing_diff(parsed,VOCAB),
        }

    override = {"physics":physics_override}
    if appearance_override is not None:
        override["appearance"] = appearance_override
    configuration = scenario(override)
    return {"edit_dsl":case["dsl"],"seed":case["seed"],"applies_from_frame":dsl.starts_at_frame(parsed),
        "prompts":dsl.make_prompts(parsed,VOCAB),"scenario_override":physics_override,
        "binding_override":binding_override,"physics_diff":physics_diff,
        "configuration":configuration}


def edit_summary(result):
    """Outcome text, read from the solved run rather than written by hand."""
    contacts = ", ".join(f"{e['object_ids'][0]} into {e['object_ids'][1]} at {e['time_sec']:.3f} s" for e in result["contact_events"])
    final = result["final_state"]["bodies"]
    positions = ", ".join(f"{name} x={body['location'][0]:+.3f} m, {body['linear_velocity'][0]:.3f} m/s" for name,body in final.items())
    return f"Solved contacts: {contacts}. At 4 s: {positions}."
