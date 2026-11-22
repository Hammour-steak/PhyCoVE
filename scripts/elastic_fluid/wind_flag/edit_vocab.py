"""One DSL declaration generates wind-flag prompts, overrides and timing."""
from __future__ import annotations
import copy
import sys
from wind_flag_config import ROOT, SPEC, SOURCE_ID, CASE_MAP
sys.path.insert(0, str(ROOT / "scripts"))
import pcve_edit_dsl as dsl

BASELINE_PHYSICS = copy.deepcopy(SPEC["physics"])
VOCAB = dsl.Vocabulary(
    objects={"flag":{"zh":"旗帜","en":"the flag"}, "wind":{"zh":"风场","en":"the wind field"}},
    properties={"young_modulus":dsl.PropertySpec("scalar","Pa","杨氏模量","Young modulus"),
                "speed":dsl.PropertySpec("scalar","m/s","参考风速","reference wind speed")},
    sim_bindings={("flag","young_modulus"):dsl.SimBinding("young_modulus_pa"),
                  ("wind","speed"):dsl.SimBinding("wind_reference_speed_m_s")},
    delete_bindings={}, baseline_physics=BASELINE_PHYSICS, total_frames=96)
EDIT_CASES = (
    {"case_id":"edit_wind_6mps","edit_dsl":"SET wind.speed TIMES 3",
     "edit_summary":"Increase the reference wind speed from 2 to 6 m/s; flag material and all other inputs stay fixed."},
    {"case_id":"edit_young_modulus_100mpa","edit_dsl":"SET flag.young_modulus TIMES 100",
     "edit_summary":"Increase E from 1 to 100 MPa, with derived membrane and bending coefficients; visibly stiffer but still bending and moving."},
    {"case_id":"edit_wind_drop_at_2s","edit_dsl":"SET wind.speed TIMES 0.25 AT FRAME 49",
     "edit_summary":"At t=2 s, reduce reference wind from 2 to 0.5 m/s; continue the complete native state without resetting or splicing motion."},
    {"case_id":"edit_wind_0p5mps","edit_dsl":"SET wind.speed TIMES 0.25",
     "edit_summary":"From t=0, reduce reference wind from 2 to 0.5 m/s; retain the source initial positions and velocities, material and all other inputs."},
    {"case_id":"edit_wind_0mps","edit_dsl":"SET wind.speed TIMES 0",
     "edit_summary":"From t=0, set prescribed ambient wind to zero everywhere; retain source momentum, gravity and relative-air drag. This does not freeze the flag."})


def plans():
    source_prompts = {"vague":{"zh":"屋顶上的旗帜随风飘动。","en":"A rooftop flag flutters in the wind."},
        "quantitative":{"zh":"参考风速为 2 m/s，旗帜杨氏模量为 1 MPa，旗面在 4 秒内随风弯曲和飘动。",
                        "en":"Over 4 seconds, a 1 MPa flag bends and flutters under a 2 m/s reference wind field."}}
    result = [{"case_id":SOURCE_ID,"native_case":"source","kind":"source","edit_dsl":None,
               "physics_override":{},"prompts":source_prompts,"applies_from_frame":1,"physics_diff":{}}]
    for case in EDIT_CASES:
        edit = dsl.parse(case["edit_dsl"], VOCAB)
        # Zero wind reads "leave the wind field at rest": the air, not the flag, becomes still.
        prompts = dsl.make_prompts(edit,VOCAB)
        result.append({**case,"native_case":CASE_MAP[case["case_id"]],"kind":"edit","source_case_id":SOURCE_ID,
            "physics_override":dsl.to_scenario_override(edit,VOCAB),"applies_from_frame":dsl.starts_at_frame(edit),
            "physics_diff":{f"{edit.property_name} ({edit.object_id})":{"from":dsl.baseline_value_for(edit,VOCAB),"to":dsl.resolved_to_value(edit,VOCAB)},"timing":dsl.timing_diff(edit,VOCAB)},
            "prompts":prompts})
    return result
