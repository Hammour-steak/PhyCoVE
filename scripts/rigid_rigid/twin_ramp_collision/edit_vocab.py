import math
import importlib.util
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
# The benchmark consolidator imports several vocabularies in one process.
# Keep this scene's config separate from another scene's cached scene_config.
_spec=importlib.util.spec_from_file_location("_pcve_twin_ramp_config",Path(__file__).with_name("scene_config.py"))
_config=importlib.util.module_from_spec(_spec);_spec.loader.exec_module(_config)
BASELINE,CASES,differences,scenario=_config.BASELINE,_config.CASES,_config.differences,_config.scenario

FLAT={"left_mass":.075,"pair_restitution":.9604,"right_active":[1],"left_active":[1]}
VOCAB=dsl.Vocabulary(
    objects={"B_left":{"zh":"左侧红球","en":"the left red ball"},
             "B_right":{"zh":"右侧蓝球","en":"the right blue ball"}},
    properties={"mass":dsl.PropertySpec("scalar","kg","质量","mass"),
        "restitution":dsl.PropertySpec("scalar","","与右侧蓝球接触的有效恢复系数","effective contact restitution against the right blue ball")},
    sim_bindings={("B_left","mass"):dsl.SimBinding("left_mass"),("B_left","restitution"):dsl.SimBinding("pair_restitution")},
    delete_bindings={"B_right":dsl.DeleteBinding("right_active",0),"B_left":dsl.DeleteBinding("left_active",0)},baseline_physics=FLAT,
    total_frames=round(BASELINE["render"]["fps"]*BASELINE["render"]["duration_sec"]))
STATEMENTS={"edit_heavy_left":"SET B_left.mass TIMES 1.5",
    "edit_low_restitution":f"SET B_left.restitution TIMES {.3025/.9604:.17g}","edit_remove_right":"DELETE B_right"}

def compile_edit(statement):
    edit=dsl.parse(statement,VOCAB)
    if dsl.starts_at_frame(edit)!=1:raise ValueError("Only pre-simulation edits are supported")
    flat=dsl.to_physics_override(edit,VOCAB);balls={}
    if "left_mass" in flat:balls["B_left"]={"mass_kg":round(flat["left_mass"],15)}
    if "pair_restitution" in flat:
        e=flat["pair_restitution"]
        if not 0<=e<=1:raise ValueError("Effective restitution must be within [0,1]")
        balls={name:{"restitution":round(math.sqrt(e),15)} for name in ["B_left","B_right"]}
    if "right_active" in flat:balls["B_right"]={"present":bool(flat["right_active"][0])}
    if "left_active" in flat:balls["B_left"]={"present":bool(flat["left_active"][0])}
    return edit,{"physics":{"balls":balls}}

SOURCE_PROMPTS={
    "vague":{"zh":"红球和蓝球同时下坡，在中央碰撞、返回原坡并再次滚回。",
             "en":"The red and blue balls roll down together, collide in the center, rebound up their own ramps and roll back."},
    "quantitative":{"zh":"直径各 5 cm、质量各 75 g 的红球和蓝球从对称双斜坡上同时静止释放，在中央 20 cm 水平段迎面碰撞，反弹爬回原坡后再次滚回。初始线速度和自转均为零。",
                    "en":"The red and blue balls, each 5 cm in diameter and 75 g, start simultaneously from rest on symmetric ramps, collide on the 20 cm central flat, rebound up their original ramps and roll back. Initial linear and angular velocities are zero."}}

def edit_info(case):
    """Source prompts as published; edit prompts generated from the DSL by pcve_edit_dsl.make_prompts."""
    if case=="source":return {"physics_override":CASES[case],"application_time_sec":0.,"prompts":SOURCE_PROMPTS}
    edit,override=compile_edit(STATEMENTS[case]);assert override==CASES[case],(override,CASES[case])
    result={"physics_override":CASES[case],"application_time_sec":0.,"prompts":dsl.make_prompts(edit,VOCAB)}
    diff=differences(BASELINE,scenario(case))
    result.update({"edit_dsl":STATEMENTS[case],"object_id":edit.object_id,"applies_from_frame":1,
        "physics_diff":{k:{"from":v["before"],"to":v["after"]} for k,v in diff.items()},"configuration_diff":diff})
    if case=="edit_low_restitution":
        result["physics_diff"]={"effective_ball_ball_restitution":{"from":.9604,"to":.3025},**result["physics_diff"]}
        result["contact_parameter_scope"]={"target_pair":["B_left","B_right"],"dsl_property_semantics":"Effective pair restitution against B_right, parameterized on B_left; both body values set to sqrt(effective)","effective_before":.9604,"effective_after":.3025,"ball_ramp_effective":0.}
    return result
