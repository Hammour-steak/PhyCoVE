"""Existing PCVE DSL with scalar, vector and compound nested-config adapters."""
from __future__ import annotations
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
import pcve_edit_dsl as dsl
from scene_config import BASELINE, CASES, INITIAL_VELOCITY_CASES, FRICTION_CASES, COMBINED_FRICTION_CASES

VOCAB=dsl.Vocabulary(
    objects={"B01":{"zh":"彩色玩具皮球","en":"the colorful toy ball"}},
    properties={"restitution":dsl.PropertySpec("scalar","","恢复系数","coefficient of restitution"),
                "initial_velocity":dsl.PropertySpec("vector","m/s","初始速度","initial velocity"),
                "lateral_friction":dsl.PropertySpec("scalar","","滑动摩擦系数","lateral friction coefficient"),
                "rolling_friction":dsl.PropertySpec("scalar","","滚动摩擦参数","rolling friction parameter"),
                "friction":dsl.PropertySpec("scalar","","摩擦（滑动和滚动同时）","friction (lateral and rolling together)")},
    sim_bindings={("B01","restitution"):dsl.SimBinding("ball_restitution"),
                  ("B01","initial_velocity"):dsl.SimBinding("ball_initial_velocity"),
                  ("B01","lateral_friction"):dsl.SimBinding("ball_lateral_friction"),
                  ("B01","rolling_friction"):dsl.SimBinding("ball_rolling_friction"),
                  ("B01","friction"):dsl.CompoundBinding((dsl.SimBinding("ball_lateral_friction"),dsl.SimBinding("ball_rolling_friction")))},
    delete_bindings={},
    baseline_physics={"ball_restitution":BASELINE["physics"]["ball"]["restitution"],
                      "ball_initial_velocity":tuple(BASELINE["physics"]["ball"]["initial_velocity_m_per_s"]),
                      "ball_lateral_friction":BASELINE["physics"]["ball"]["lateral_friction"],
                      "ball_rolling_friction":BASELINE["physics"]["ball"]["rolling_friction"]},
    total_frames=round(BASELINE["render"]["fps"]*BASELINE["render"]["duration_sec"]))

STATEMENTS={case:f"SET B01.restitution TIMES {value/BASELINE['physics']['ball']['restitution']:.15g}"
            for case,value in CASES.items() if value is not None}
# A vector TO statement would put a coordinate triple into the prompts; the same velocity is written as a factor.
STATEMENTS.update({case:f"SET B01.initial_velocity TIMES {value/BASELINE['physics']['ball']['initial_velocity_m_per_s'][0]:.17g}"
                   for case,value in INITIAL_VELOCITY_CASES.items()})
STATEMENTS.update({case:f"SET B01.{edit['field']} TO {edit['value']:g}"
                   for case,edit in FRICTION_CASES.items()})
STATEMENTS.update({case:f"SET B01.friction TIMES {factor:g}"
                   for case,factor in COMBINED_FRICTION_CASES.items()})

def edit_info(case):
    statement=STATEMENTS[case];edit=dsl.parse(statement,VOCAB)
    if case in COMBINED_FRICTION_CASES:
        flat=dsl.to_physics_override(edit,VOCAB)
        values={field:flat['ball_'+field] for field in ['lateral_friction','rolling_friction']}
        before=BASELINE['physics']['ball']
        prompts=dsl.make_prompts(edit,VOCAB)
        return {'edit_dsl':statement,'object_id':'B01','target_property':'friction',
                'target_fields':['physics.ball.'+field for field in values],
                'edit_kind':'user_requested_coupled_friction','applies_from_frame':1,
                'application':'One atomic friction edit initializes lateral and rolling coefficients together; free solver-driven motion thereafter.',
                'prompts':prompts,'physics_override':{'physics':{'ball':values}},
                'physics_diff':{**{field+' (B01)':{'from':before[field],'to':value} for field,value in values.items()},'timing':dsl.timing_diff(edit,VOCAB)}}
    if case in FRICTION_CASES:
        field=FRICTION_CASES[case]['field'];before=BASELINE['physics']['ball'][field]
        scalar=dsl.to_physics_override(edit,VOCAB)['ball_'+field]
        prompts=dsl.make_prompts(edit,VOCAB)
        return {'edit_dsl':statement,'object_id':'B01','target_field':'physics.ball.'+field,
                'applies_from_frame':1,'application':'Set one contact coefficient once at initialization; free solver-driven motion thereafter.',
                'prompts':prompts,'physics_override':{'physics':{'ball':{field:scalar}}},
                'physics_diff':{field+' (B01)':{'from':before,'to':scalar},'timing':dsl.timing_diff(edit,VOCAB)}}
    if case in INITIAL_VELOCITY_CASES:
        velocity=list(dsl.to_physics_override(edit,VOCAB)["ball_initial_velocity"])
        prompts=dsl.make_prompts(edit,VOCAB)
        return {"edit_dsl":statement,"object_id":"B01","target_field":"physics.ball.initial_velocity_m_per_s",
                "applies_from_frame":1,"application":"Initialize once at t=0; no subsequent actuation or velocity maintenance.",
                "prompts":prompts,
                "physics_override":{"physics":{"ball":{"initial_velocity_m_per_s":velocity}}},
                "physics_diff":{"initial velocity (B01)":{"from":BASELINE["physics"]["ball"]["initial_velocity_m_per_s"],"to":velocity},
                                "timing":dsl.timing_diff(edit,VOCAB)}}
    scalar=dsl.to_physics_override(edit,VOCAB)["ball_restitution"]
    return {"edit_dsl":statement,"object_id":"B01","target_field":"physics.ball.restitution",
            "applies_from_frame":1,"prompts":dsl.make_prompts(edit,VOCAB),
            "physics_override":{"physics":{"ball":{"restitution":scalar}}},
            "physics_diff":{"restitution (B01)":{"from":BASELINE["physics"]["ball"]["restitution"],"to":scalar},
                            "timing":dsl.timing_diff(edit,VOCAB)}}
