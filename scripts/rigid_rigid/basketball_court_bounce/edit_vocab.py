"""Single-property object, mass and restitution edits using the shared PCVE DSL."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
VOCAB=dsl.Vocabulary(
    objects={"B01":{"zh":"橙色篮球","en":"the orange basketball"}},
    properties={"restitution":dsl.PropertySpec("scalar","","恢复系数","coefficient of restitution"),
                "mass":dsl.PropertySpec("scalar","kg","质量","mass")},
    sim_bindings={("B01","restitution"):dsl.SimBinding("ball_restitution"),
                  ("B01","mass"):dsl.SimBinding("ball_mass_kg")},
    delete_bindings={"B01":dsl.DeleteBinding("ball_present",0)},
    baseline_physics={"ball_restitution":.76,"ball_mass_kg":.625,"ball_present":[1]},
    total_frames=96)
STATEMENTS={
    "low_restitution":"SET B01.restitution TIMES 0.5",
    "high_restitution":"SET B01.restitution TIMES 1.25",
    "remove_ball":"DELETE B01",
    "heavy_ball":"SET B01.mass TIMES 2",
    "restitution_at_1s":"SET B01.restitution TIMES 1.25 AT FRAME 25",
}
def edit_info(case):
    statement=STATEMENTS[case]
    edit=dsl.parse(statement,VOCAB)
    flat=dsl.to_physics_override(edit,VOCAB)
    timed=dsl.to_scenario_override(edit,VOCAB)
    frame=dsl.starts_at_frame(edit)
    prompts=dsl.make_prompts(edit,VOCAB)
    if case=="remove_ball":
        target,before,after="physics.ball.present",True,False
        override={"physics":{"ball":{"present":False}}}
        application="Do not create B01 in the independent physics world; remove its visual mesh before rendering."
    elif case=="heavy_ball":
        target,before,after="physics.ball.mass_kg",.625,flat["ball_mass_kg"]
        override={"physics":{"ball":{"mass_kg":after}}}
        application="Set actual body mass and the corresponding hollow-sphere inertia, then independently solve. In this fixed-floor model, trajectories stay invariant while collision impulses double."
    else:
        target,before,after="physics.ball.restitution",.76,flat["ball_restitution"]
        override={"physics":timed} if frame>1 else {"physics":{"ball":{"restitution":after}}}
        application="Change actual solver restitution at t=1 s without resetting pose or velocity; continue the same world." if frame>1 else "Set restitution at initialization and independently solve free rigid contacts."
    return {"edit_dsl":statement,"object_id":"B01","target_field":target,
            "before_value":before,"after_value":after,"applies_from_frame":frame,
            "applies_at_time_sec":(frame-1)/24,"prompts":prompts,"physics_override":override,
            "physics_diff":{target:{"from":before,"to":after},"timing":dsl.timing_diff(edit,VOCAB)},
            "application":application}
