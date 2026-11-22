"""Source parameters and the five independent edits of the tabletop press, in SI units."""

import math
from pathlib import Path
import sys

H = Path(__file__).resolve().parent
ROOT = H.parents[3]
SCENE = "silicone_block_chain"
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(H))

import pcve_edit_dsl as dsl
from pcve_edit_policy import audit_scenario_override
from rig import BALL_MASS, FOAM_BOTTOM, FOAM_SIZE, FRICTION, PLATE_BOTTOM, PLATE_MASS, RADIUS, ROLLING_LENGTH

PLATEN_STOP_Z = PLATE_BOTTOM - .023
BALLAST_MASS = .04
BALLAST_DENSITY = 7850.
BALLAST_INNER = .0311
BALLAST_OUTER = .0340
BALLAST_HEIGHT = BALLAST_MASS / (BALLAST_DENSITY * math.pi * (BALLAST_OUTER**2 - BALLAST_INNER**2))

CASE_DSL = {
    "source": None,
    "stiff_foam": "SET foam_block.young_modulus TIMES 4",
    "light_ball": "SET steel_ball.mass TIMES 0.5",
    "viscous_foam": "SET foam_block.viscosity TIMES 4",
    "remove_foam": "DELETE foam_block",
}
# Timed edits (AT FRAME k): physics.py runs the source parameters up to t = (k-1)/24 and switches to the edited value
# there, in the same solve, so frames 1..k-1 are exactly those of a source solve on the same host.
TIMED_DSL = {
    "light_ball_at_frame_8": "SET steel_ball.mass TIMES 0.5 AT FRAME 8",
}
LABELS = {
    "light_ball_at_frame_8": "第 8 帧起钢球质量 ×0.5",
    "source": "基准",
    "stiff_foam": "海绵杨氏模量 ×4",
    "light_ball": "钢球质量 ×0.5",
    "viscous_foam": "海绵黏度 ×4",
    "remove_foam": "移除海绵",
}

BASELINE = {
    "foam_present": [1],
    "foam_young_modulus_pa": 3000.,
    "foam_shear_viscosity_pa_s": 35.,
    "foam_bulk_viscosity_pa_s": 70.,
    "foam_poisson_ratio": .08,
    "foam_density_kg_m3": 48.,
    "initial_foam_dimensions_m": FOAM_SIZE.tolist(),
    "initial_foam_bottom_m": FOAM_BOTTOM,
    "initial_platen_bottom_m": PLATE_BOTTOM,
    "platen_mass_kg": PLATE_MASS,
    "ball_mass_kg": BALL_MASS,
    "ball_radius_m": RADIUS,
    "cup_contact_friction": FRICTION,
    "cup_normal_stiffness_n_m": 160000.,
    "cup_normal_damping_n_s_m": 55.,
    "rolling_resistance_length_m": ROLLING_LENGTH,
    "ballast_present": [0],
    "ballast_initial_center_m": [0., 0., PLATE_BOTTOM + .004 + BALLAST_HEIGHT / 2],
    "ballast_mass_kg": BALLAST_MASS,
    "ballast_inner_radius_m": BALLAST_INNER,
    "ballast_outer_radius_m": BALLAST_OUTER,
    "ballast_height_m": BALLAST_HEIGHT,
}
COLLAR_FIELDS = tuple(key for key in BASELINE if key.startswith("ballast_") and key != "ballast_present")
COLLAR_SLOTS = (dsl.SimBinding("ballast_present", 0), *(dsl.SimBinding(key) for key in COLLAR_FIELDS))

VOCAB = dsl.Vocabulary(
    objects={
        "foam_block": {"zh": "海绵块", "en": "the foam block"},
        "steel_ball": {"zh": "钢球", "en": "the steel ball"},
        "ballast_ring": {"zh": "钢制配重环", "en": "a steel ballast ring"},
    },
    properties={
        "young_modulus": dsl.PropertySpec("scalar", "Pa", "杨氏模量", "Young's modulus",
                                        physical_quantity="young_modulus"),
        "mass": dsl.PropertySpec("scalar", "kg", "质量", "mass", physical_quantity="mass"),
        "viscosity": dsl.PropertySpec("scalar", "Pa*s", "黏度", "viscosity",
                                     physical_quantity="viscosity"),
    },
    sim_bindings={
        ("foam_block", "young_modulus"): dsl.SimBinding("foam_young_modulus_pa"),
        ("steel_ball", "mass"): dsl.SimBinding("ball_mass_kg"),
        ("foam_block", "viscosity"): dsl.CompoundBinding((
            dsl.SimBinding("foam_shear_viscosity_pa_s"), dsl.SimBinding("foam_bulk_viscosity_pa_s"),
        )),
    },
    delete_bindings={"foam_block": dsl.DeleteBinding("foam_present", 0),
                     "steel_ball": dsl.DeleteBinding("ball_present", 0)},
    add_bindings={"ballast_ring": dsl.AddBinding("ballast_present", 0, "ballast_initial_center_m",
                                               owned_parameters=COLLAR_SLOTS)},
    add_presets={("ballast_ring", "cup_collar"): dsl.AddPreset(
        tuple((key, BASELINE[key]) for key in COLLAR_FIELDS),
        "在接球杯外圈套上一个 40 g 的钢制配重环",
        "fit a 40 g steel ballast ring around the outside of the receiving cup",
    )},
    object_parameters={"ballast_ring": COLLAR_SLOTS},
    # ball_present lives only in the vocabulary baseline (the solver reads it with default [1]),
    # so the physics of the published cases is unchanged.
    baseline_physics={**BASELINE, "ball_present": [1]},
    total_frames=96,
)


def timed_schedule(case):
    """(frame, edited values) of a timed case, audited by the edit policy like the whole-clip edits."""
    edit = dsl.parse(TIMED_DSL[case], VOCAB)
    schedule = dsl.to_scenario_override(edit, VOCAB)
    audit_scenario_override(edit, VOCAB, schedule, BASELINE)
    (entry,) = schedule[dsl.TIMED_EDITS_KEY]
    return int(entry["frame"]), dict(entry["params"])


def parameters(case):
    if case in TIMED_DSL:
        return dict(BASELINE)            # in effect at frame 1; timed_schedule gives the change
    params = dict(BASELINE)
    text = CASE_DSL[case]
    if text is not None:
        edit = dsl.parse(text, VOCAB)
        params.update(dsl.to_physics_override(edit, VOCAB))
        audit_scenario_override(edit, VOCAB, params, BASELINE)
    return params
