"""Edit DSL vocabulary, edit statements and prompts; every edit applies before the simulation starts."""
from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE,CASES,differences,scenario

_ph=BASELINE["physics"]
# Solver fields the DSL bindings address; to_override() maps them onto the configuration.
FLAT={"left_mass":_ph["balls"]["B_left"]["mass_kg"],"pair_restitution":_ph["contacts"]["ball_ball"]["restitution"],
      "right_active":[1],"left_rope_active":[1]}
VOCAB=dsl.Vocabulary(
    objects={"B_left":{"zh":"左侧红球","en":"the left red ball"},
             "B_right":{"zh":"右侧蓝球及其吊绳","en":"the right blue ball and its cord"},
             "B_left_rope":{"zh":"左侧红球的吊绳","en":"the left red ball's cord"}},
    properties={"mass":dsl.PropertySpec("scalar","kg","质量","mass"),
                "restitution":dsl.PropertySpec("scalar","","与右侧蓝球接触的有效恢复系数","effective contact restitution against the right blue ball")},
    sim_bindings={("B_left","mass"):dsl.SimBinding("left_mass"),("B_left","restitution"):dsl.SimBinding("pair_restitution")},
    delete_bindings={"B_right":dsl.DeleteBinding("right_active",0),"B_left_rope":dsl.DeleteBinding("left_rope_active",0)},
    baseline_physics=FLAT,total_frames=round(BASELINE["render"]["fps"]*BASELINE["render"]["duration_sec"]))

# The restitution factor is 0.25/0.90; the ball-ball value is a pair property, bound to the left ball.
STATEMENTS={"edit_heavy_left":"SET B_left.mass TIMES 3",
            "edit_low_restitution":"SET B_left.restitution TIMES 0.27777777777777779",
            "edit_remove_right":"DELETE B_right",
            "edit_remove_left_rope":"DELETE B_left_rope"}

SOURCE_PROMPTS={
    "vague":{"zh":"两个用细绳吊着的小球（左红右蓝）从左右两侧同时由静止释放，在最低点附近迎面相撞后各自回摆，并反复相撞。",
             "en":"A red ball and a blue ball hanging on cords are released from rest on opposite sides at the same time, collide head-on near the bottom, swing back and collide again and again."},
    "quantitative":{"zh":"两个直径 6 cm、质量 120 g 的小球（左红右蓝）各挂在一根细绳下，悬挂点到球心 0.6 m，从左右两侧 35° 处同时由静止释放，在最低点附近迎面相撞（球间恢复系数 0.9）后各自回摆，并反复相撞。",
                    "en":"Two balls, red on the left and blue on the right, each 6 cm in diameter and 120 g, hang on cords 0.6 m from anchor to ball centre. They are released from rest at 35° on opposite sides at the same time, collide head-on near the bottom (ball-ball restitution 0.9), swing back and collide again and again."}}

def to_override(flat):
    physics={}
    if "left_mass" in flat:physics.setdefault("balls",{})["B_left"]={"mass_kg":flat["left_mass"]}
    if "pair_restitution" in flat:physics["contacts"]={"ball_ball":{"restitution":flat["pair_restitution"]}}
    if flat.get("right_active")==[0]:
        physics.setdefault("balls",{})["B_right"]={"present":False};physics.setdefault("ropes",{})["B_right"]={"present":False}
    if flat.get("left_rope_active")==[0]:physics.setdefault("ropes",{})["B_left"]={"present":False}
    return {"physics":physics}

def edit_info(case):
    if case=="source":return {"prompts":SOURCE_PROMPTS}
    statement=STATEMENTS[case];edit=dsl.parse(statement,VOCAB)
    if dsl.starts_at_frame(edit)!=1:raise ValueError("This scene supports edits before simulation only")
    if scenario("source",to_override(dsl.to_physics_override(edit,VOCAB)))!=scenario(case):raise ValueError("DSL and case preset disagree")
    diff=differences(BASELINE,scenario(case))
    return {"edit_dsl":statement,"object_id":edit.object_id,"applies_from_frame":1,"prompts":dsl.make_prompts(edit,VOCAB),
            "physics_override":CASES[case],"physics_diff":{k:{"from":v["before"],"to":v["after"]} for k,v in diff.items()}}
