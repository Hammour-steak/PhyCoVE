"""PCVE DSL with individual B01/P01/P02/P03 bindings; initial-state edits only."""
from __future__ import annotations
import copy
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE,differences,scenario

FLAT={"ball_mass":BASELINE["physics"]["ball"]["mass_kg"],"pin_active":[1,1,1],"ball_active":[1]}
for i in range(3):
    FLAT[f"P{i+1:02}_mass"]=BASELINE["physics"]["pins"]["masses_kg"][i]
    FLAT[f"P{i+1:02}_friction"]=BASELINE["physics"]["pins"]["frictions"][i]

VOCAB=dsl.Vocabulary(
 objects={"B01":{"zh":"深蓝色保龄球","en":"the deep-blue bowling ball"},
  "P01":{"zh":"前排中央球瓶","en":"the front-center pin"},
  "P02":{"zh":"后排左侧球瓶","en":"the rear-left pin"},
  "P03":{"zh":"后排右侧球瓶","en":"the rear-right pin"}},
 properties={"mass":dsl.PropertySpec("scalar","kg","质量","mass"),"friction":dsl.PropertySpec("scalar","","摩擦系数","friction coefficient")},
 sim_bindings={("B01","mass"):dsl.SimBinding("ball_mass"),**{(f"P{i+1:02}",prop):dsl.SimBinding(f"P{i+1:02}_{prop}") for i in range(3) for prop in ["mass","friction"]}},
 delete_bindings={"B01":dsl.DeleteBinding("ball_active",0),**{f"P{i+1:02}":dsl.DeleteBinding("pin_active",i) for i in range(3)}},
 baseline_physics=FLAT,total_frames=round(BASELINE["render"]["fps"]*BASELINE["render"]["duration_sec"]))

STATEMENTS={"edit_light_ball":"SET B01.mass TIMES 0.01","edit_heavy_P01":"SET P01.mass TIMES 100","edit_remove_P01":"DELETE P01","edit_grippy_P01":"SET P01.friction TIMES 6.944444444444445"}

def compile_edit(statement):
    edit=dsl.parse(statement,VOCAB)
    if dsl.starts_at_frame(edit)!=1:raise ValueError("This scene supports edits before simulation only")
    flat=dsl.to_physics_override(edit,VOCAB);physics={}
    if "ball_mass" in flat:physics["ball"]={"mass_kg":flat["ball_mass"]}
    pins={}
    for prop,key in [("mass","masses_kg"),("friction","frictions")]:
        values=copy.deepcopy(BASELINE["physics"]["pins"][key]);changed=False
        for i in range(3):
            field=f"P{i+1:02}_{prop}"
            if field in flat:values[i]=flat[field];changed=True
        if changed:pins[key]=values
    if "pin_active" in flat:pins["active"]=flat["pin_active"]
    # The ball has no presence field in the baseline; physics.ball.active=0 is read by the simulator and renderer.
    if "ball_active" in flat:physics["ball"]={**physics.get("ball",{}),"active":flat["ball_active"][0]}
    if pins:physics["pins"]=pins
    return edit,{"physics":physics}

def edit_info(case):
    statement=STATEMENTS[case];edit,override=compile_edit(statement);expected=scenario(case=case)
    assert scenario(override)==expected,"DSL and case preset disagree"
    diff=differences(BASELINE,expected)
    return {"edit_dsl":statement,"object_id":edit.object_id,"applies_from_frame":1,
      "physics_override":override,"configuration_diff":diff,"physics_diff":{k:{"from":v["before"],"to":v["after"]} for k,v in diff.items()},"prompts":dsl.make_prompts(edit,VOCAB),
      "outcome_policy":"Describe only measured simulation outcomes; prompts do not prescribe pin motion"}
