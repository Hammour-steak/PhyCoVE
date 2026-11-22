"""Eight requested counterfactuals using the shared PCVE edit DSL."""
from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE

STATEMENTS = {
    "edit_high_restitution": "SET B01.restitution TO 1",
    "edit_low_restitution": "SET B01.restitution TIMES 0.5",
    "edit_fast_initial_velocity": "SET B01.initial_velocity TIMES 1.2",
    "edit_slow_initial_velocity": "SET B01.initial_velocity TIMES 0.8",
    "edit_high_ball_friction": "SET B01.lateral_friction TIMES 2.5",
    "edit_high_football_friction": "SET B02.lateral_friction TIMES 2",
    "edit_remove_football": "DELETE B02",
    "edit_remove_football_at_2s": "DELETE B02 AT FRAME 49",
}


def vocabulary(cfg):
    ph = cfg["physics"]
    return dsl.Vocabulary(
        objects={"B01": {"zh": "星星玩具球", "en": "the star-patterned toy ball"},
                 "B02": {"zh": "足球", "en": "the football"},
                 "C01": {"zh": "白色玩具箱", "en": "the white toy chest"}},
        properties={
            "restitution": dsl.PropertySpec("scalar", "", "恢复系数", "coefficient of restitution"),
            "initial_velocity": dsl.PropertySpec("vector", "m/s", "初速度", "initial velocity"),
            "lateral_friction": dsl.PropertySpec("scalar", "", "接触摩擦系数", "lateral friction coefficient"),
        },
        sim_bindings={
            ("B01", "restitution"): dsl.SimBinding("ball_restitution"),
            ("B01", "initial_velocity"): dsl.SimBinding("ball_initial_velocity"),
            ("B01", "lateral_friction"): dsl.SimBinding("ball_lateral_friction"),
            ("B02", "lateral_friction"): dsl.SimBinding("football_lateral_friction"),
        },
        delete_bindings={"B02": dsl.DeleteBinding("football_present", 0),
                         "B01": dsl.DeleteBinding("ball_present", 0),
                         "C01": dsl.DeleteBinding("box_present", 0)},
        baseline_physics={
            "ball_restitution": ph["ball"]["restitution"],
            "ball_initial_velocity": tuple(ph["ball"]["initial_velocity_m_per_s"]),
            "ball_lateral_friction": ph["ball"]["lateral_friction"],
            "football_lateral_friction": ph["football"]["lateral_friction"],
            "football_present": [1],
            "ball_present": [1],
            "box_present": [1],
        }, total_frames=cfg["render"]["total_frames"],
    )


def edit_info(case, source_cfg=None):
    cfg = source_cfg or BASELINE
    vocab = vocabulary(cfg)
    statement = STATEMENTS[case]
    edit = dsl.parse(statement, vocab)
    flat = dsl.to_physics_override(edit, vocab)
    frame = dsl.starts_at_frame(edit)
    at = (frame - 1) / cfg["render"]["fps"]
    prompts = dsl.make_prompts(edit, vocab)
    ph, changes = cfg["physics"], {}
    if case.startswith("edit_remove_"):
        assert flat["football_present"] == [0]
        target, values = "football", {"remove_at_sec": at}
        changes["physics.football.remove_at_sec"] = {"from": ph["football"]["remove_at_sec"], "to": at}
        application = "Do not create B02 at initialization." if frame == 1 else "Remove B02 in the same running world exactly at solver step 3840, after integrating to t=2 and before sampling frame 49; no reset or new impulse."
    elif "initial_velocity" in case:
        target = "ball"
        velocity = list(flat["ball_initial_velocity"])
        factor = 1.2 if "fast" in case else .8
        spin = [v * factor for v in ph["ball"]["initial_angular_velocity_rad_per_s"]]
        values = {"initial_velocity_m_per_s": velocity, "initial_angular_velocity_rad_per_s": spin}
        for field, value in values.items():
            changes["physics.ball." + field] = {"from": ph["ball"][field], "to": value}
        application = "One rolling launch-speed edit: linear velocity and its derived no-slip angular velocity are initialized once, with no later actuation."
    else:
        target = "football" if "football_friction" in case else "ball"
        field = "restitution" if "restitution" in case else "lateral_friction"
        value = flat[target + "_" + field]
        values = {field: value}
        changes[f"physics.{target}.{field}"] = {"from": ph[target][field], "to": value}
        application = "Set one actual PyBullet contact parameter once, then solve all resulting motion independently."
    return {"edit_dsl": statement, "object_id": "B02" if target == "football" else "B01",
            "target_fields": list(changes), "applies_from_frame": frame, "applies_at_time_sec": at,
            "physics_override": {"physics": {target: values}}, "physics_diff": changes,
            "timing": dsl.timing_diff(edit, vocab), "prompts": prompts, "application": application,
            "framing_policy": "Keep the source camera; edited bodies may naturally leave the frame, as requested by the user."}
