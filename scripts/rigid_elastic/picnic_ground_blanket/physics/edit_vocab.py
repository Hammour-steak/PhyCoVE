from pathlib import Path
import sys,json
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[2]))
import pcve_edit_dsl as dsl
SPECS=json.loads((HERE/'scene_specs.json').read_text(encoding='utf-8'))

def vocabulary(scene_id):
    s=SPECS[scene_id];gym=scene_id=='gym_landing_mat';actor=s['actor_id'];elastic=s['elastic_id']
    objects={actor:{'zh':'训练实心球' if gym else '滚动的橘子','en':'the weighted medicine ball' if gym else 'the rolling orange'},elastic:{'zh':'体操落地垫的泡棉内芯' if gym else '野餐布','en':'the landing mat foam core' if gym else 'the picnic blanket'}}
    bindings={(actor,'mass'):dsl.SimBinding('body_mass'),(actor,'initial_velocity'):dsl.SimBinding('body_initial_speed'),(elastic,'young_modulus'):dsl.SimBinding('solid_young_modulus' if gym else 'cloth_young_modulus'),(elastic,'bending_stiffness'):dsl.SimBinding('cover_bending_stiffness' if gym else 'cloth_bending_stiffness'),(actor,'friction'):dsl.SimBinding('friction')}
    if not gym:
        objects['grass_thatch']={'zh':'草地','en':'the lawn'}
        bindings[('grass_thatch','young_modulus')]=dsl.SimBinding('solid_young_modulus')
    geometry={actor:dsl.GeometryAnchor('body_initial_location','body_radius')}
    object_parameters={};add_bindings={};add_presets={}
    return dsl.Vocabulary(objects=objects,
        properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),'initial_velocity':dsl.PropertySpec('scalar','m/s','初速度大小','initial speed'),'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),'bending_stiffness':dsl.PropertySpec('scalar','N*m','薄壳弯曲刚度','shell bending rigidity',physical_quantity='bending_rigidity'),'friction':dsl.PropertySpec('scalar','','接触摩擦系数','contact friction coefficient')},
        sim_bindings=bindings,
        delete_bindings={actor:dsl.DeleteBinding('active',index=0),elastic:dsl.DeleteBinding('active',index=1)},baseline_physics=s['physics'],geometry=geometry,add_bindings=add_bindings,add_presets=add_presets,object_parameters=object_parameters,total_frames=round(s['simulation']['duration']*s['simulation']['fps']))

def edit_info(scene_id,text):
    if not text:return {}
    v=vocabulary(scene_id);e=dsl.parse(text,v)
    # A timed edit (AT FRAME k) carries the edited values; simulate.py applies them from frame k on,
    # continuing from the accepted source state (--source-cache).
    return dict(edit_dsl=text,applies_from_frame=dsl.starts_at_frame(e),prompts=dsl.make_prompts(e,v),override=dsl.to_physics_override(e,v))

def timed_cases(scene_id):
    """Timed edits: solved from the accepted source state of their frame (simulate.py --source-cache)."""
    if scene_id=='picnic_ground_blanket':
        return {'mass_double_at_frame_12':f"SET {SPECS[scene_id]['actor_id']}.mass TIMES 2 AT FRAME 12"}
    return {}

def cases(scene_id):
    s=SPECS[scene_id];a=s['actor_id'];e=s['elastic_id']
    stiffness=f'SET {e}.young_modulus TIMES 10'if scene_id=='gym_landing_mat'else'SET grass_thatch.young_modulus TIMES 10'
    speed=3 if scene_id=='gym_landing_mat'else 2
    if scene_id=='gym_landing_mat':
        return {'source':None,'mass_double':f'SET {a}.mass TIMES 2','faster':f'SET {a}.initial_velocity TIMES {speed}','stiffer':stiffness,'young_modulus_soft':f'SET {e}.young_modulus TIMES 0.25','add_path_obstacle':'ADD gym_water_bottle AT PRESET roll_path','delete_actor':f'DELETE {a}'}
    return {'source':None,'mass_double':f'SET {a}.mass TIMES 2','faster':f'SET {a}.initial_velocity TIMES {speed}','stiffer':stiffness,'delete_actor':f'DELETE {a}'}
