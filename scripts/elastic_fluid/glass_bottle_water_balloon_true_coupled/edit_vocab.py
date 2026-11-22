"""Three edits; the membrane hardness edit uses a uniform relative elastic scale."""
from __future__ import annotations
import copy
import sys
from balloon_config import ROOT, BASELINE_PHYSICS, TOTAL_FRAMES, SOURCE_CASE_ID
sys.path.insert(0,str(ROOT / "scripts"))
import pcve_edit_dsl as dsl


VOCAB = dsl.Vocabulary(
    objects={
        "tap": {"zh": "厨房水龙头", "en": "the kitchen tap"},
        "balloon": {"zh": "蓝色气球", "en": "the blue balloon"},
    },
    properties={
        "flow_rate": dsl.PropertySpec("scalar", "L/min", "出水流量", "flow rate"),
        "stiffness": dsl.PropertySpec("scalar", "N/m", "弹性刚度", "elastic stiffness"),
        "young_modulus_scale":dsl.PropertySpec("scalar","","相对弹性模量","relative elastic modulus"),
    },
    sim_bindings={
        ("tap", "flow_rate"): dsl.SimBinding("flow_l_min"),
        ("balloon", "stiffness"): dsl.SimBinding("edge_stiffness"),
        ("balloon","young_modulus_scale"):dsl.SimBinding("elastic_modulus_scale"),
    },
    # DELETE balloon: the simulator's --without-balloon (the tap fills the open jar). balloon_present is a
    # presence slot of this vocabulary only; the plans' solver parameters stay BASELINE_PHYSICS.
    delete_bindings={"balloon": dsl.DeleteBinding("balloon_present", 0)},
    baseline_physics={**BASELINE_PHYSICS, "balloon_present": [1]},
    total_frames=TOTAL_FRAMES,
)


EDIT_CASES = (
    {"case_id":"edit_high_flow","edit_dsl":"SET tap.flow_rate TIMES 2",
     "edit_summary":"Double the outlet speed at the unchanged aerator area. Input becomes 9 L/min; all water is retained and inflation continues with idealized retention pressure. No overflow."},
    {"case_id":"edit_tap_off_from_start","edit_dsl":"SET tap.flow_rate TO 0",
     "edit_summary":"Keep the tap off from the beginning. No stream or incoming water; the balloon stays empty instead of inflating and sagging under the water load."},
    {"case_id":"edit_hard_balloon","edit_dsl":"SET balloon.young_modulus_scale TIMES 5",
     "edit_summary":"Uniformly multiply all elastic spring energies by five: stretch/shear-network edge springs 25 to 125 N/m and bending springs 6 to 30 N/m. Water input is unchanged and all retained. Inflation, sag and shape may differ; the same final retained water does not guarantee a smaller final volume. Relative discrete-model modulus, not calibrated absolute E in Pa."},
)


def make_plans():
    plans = [{"case_id": SOURCE_CASE_ID, "kind": "source", "edit_dsl": None,
              "physics": copy.deepcopy(BASELINE_PHYSICS), "timed_edits": [], "prompts": None}]
    for edit in EDIT_CASES:
        parsed = dsl.parse(edit["edit_dsl"], VOCAB)
        override = dsl.to_scenario_override(parsed, VOCAB)
        physics = copy.deepcopy(BASELINE_PHYSICS)
        timed = override.get("timed_edits", [])
        if not timed:
            unknown = set(override) - set(BASELINE_PHYSICS)
            if unknown:
                raise ValueError(f"{edit['case_id']}: override touches unknown parameters {sorted(unknown)}")
            physics.update(override)
        plans.append({
            **edit, "kind": "edit", "source_case_id": SOURCE_CASE_ID, "physics": physics,
            "timed_edits": timed, "scenario_override": override,
            "applies_from_frame": dsl.starts_at_frame(parsed),
            "prompts": dsl.make_prompts(parsed, VOCAB),
            "physics_diff": {
                f"{parsed.property_name} ({parsed.object_id})": {
                    "from": dsl.baseline_value_for(parsed, VOCAB), "to": parsed.to_value},
                "timing": dsl.timing_diff(parsed, VOCAB),
            },
        })
    return plans
