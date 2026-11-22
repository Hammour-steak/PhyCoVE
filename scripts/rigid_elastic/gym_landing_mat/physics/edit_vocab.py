from pathlib import Path
import sys,json
HERE=Path(__file__).resolve().parent;sys.path.insert(0,str(HERE.parents[2]))
import pcve_edit_dsl as dsl
SPECS=json.loads((HERE/'scene_specs.json').read_text(encoding='utf-8'))

def vocabulary(scene_id):
    s=SPECS[scene_id];gym=scene_id=='gym_landing_mat';actor=s['actor_id'];elastic=s['elastic_id']
    objects={actor:{'zh':'实心球' if gym else '野餐布上滚动的橘子','en':'the medicine ball' if gym else 'the mandarin orange rolling on the picnic blanket'},elastic:{'zh':'落地垫' if gym else '自由铺放的柔软棉质野餐布','en':'the landing mat' if gym else 'the freely laid soft cotton picnic blanket'}}
    if gym:
        objects['gym_water_bottle']={'zh':'运动水壶','en':'a sports water bottle'}
    bindings={(actor,'mass'):dsl.SimBinding('body_mass'),(actor,'initial_velocity'):dsl.SimBinding('body_initial_speed'),(elastic,'young_modulus'):dsl.SimBinding('solid_young_modulus' if gym else 'cloth_young_modulus'),(elastic,'bending_stiffness'):dsl.SimBinding('cover_bending_stiffness' if gym else 'cloth_bending_stiffness'),(actor,'friction'):dsl.SimBinding('friction')}
    if not gym:
        objects['grass_thatch']={'zh':'野餐布下的可压缩草层','en':'the compressible grass layer under the picnic blanket'}
        bindings[('grass_thatch','young_modulus')]=dsl.SimBinding('solid_young_modulus')
    geometry={actor:dsl.GeometryAnchor('body_initial_location','body_radius')}
    if gym:
        geometry['gym_water_bottle']=dsl.GeometryAnchor('gym_water_bottle_location','gym_water_bottle_radius')
    object_parameters={}
    if gym:
        object_parameters['gym_water_bottle']=(dsl.SimBinding('gym_water_bottle_active',0),dsl.SimBinding('gym_water_bottle_location'),dsl.SimBinding('gym_water_bottle_radius'),dsl.SimBinding('gym_water_bottle_length'),dsl.SimBinding('gym_water_bottle_mass'),dsl.SimBinding('gym_water_bottle_surface_friction'),dsl.SimBinding('gym_water_bottle_ball_friction'),dsl.SimBinding('gym_water_bottle_contact_resistance'))
    add_bindings={}
    add_presets={}
    if gym:
        add_bindings['gym_water_bottle']=dsl.AddBinding('gym_water_bottle_active',0,'gym_water_bottle_location',owned_parameters=object_parameters['gym_water_bottle'])
        add_presets[('gym_water_bottle','roll_path')]=dsl.AddPreset((('gym_water_bottle_location',s['physics']['gym_water_bottle_location']),('gym_water_bottle_radius',s['physics']['gym_water_bottle_radius']),('gym_water_bottle_length',s['physics']['gym_water_bottle_length']),('gym_water_bottle_mass',s['physics']['gym_water_bottle_mass']),('gym_water_bottle_surface_friction',s['physics']['gym_water_bottle_surface_friction']),('gym_water_bottle_ball_friction',s['physics']['gym_water_bottle_ball_friction']),('gym_water_bottle_contact_resistance',s['physics']['gym_water_bottle_contact_resistance'])), '落地垫上、实心球的右下方横放','lying on its side on the landing mat, below and to the right of the medicine ball')
    return dsl.Vocabulary(objects=objects,
        properties={'mass':dsl.PropertySpec('scalar','kg','质量','mass'),'initial_velocity':dsl.PropertySpec('scalar','m/s','初速度大小','initial speed'),'young_modulus':dsl.PropertySpec('scalar','Pa','杨氏模量',"Young's modulus"),'bending_stiffness':dsl.PropertySpec('scalar','N*m','包布弯曲刚度','cover bending stiffness',physical_quantity='bending_rigidity'),'friction':dsl.PropertySpec('scalar','','接触摩擦系数','contact friction coefficient')},
        sim_bindings=bindings,
        delete_bindings={actor:dsl.DeleteBinding('active',index=0),elastic:dsl.DeleteBinding('active',index=1)},baseline_physics=s['physics'],geometry=geometry,add_bindings=add_bindings,add_presets=add_presets,object_parameters=object_parameters,total_frames=round(s['simulation']['duration']*s['simulation']['fps']))

def edit_info(scene_id,text):
    if not text:return {}
    v=vocabulary(scene_id);e=dsl.parse(text,v)
    if dsl.starts_at_frame(e)!=1:raise ValueError('Only whole-clip edits in this suite')
    return dict(edit_dsl=text,applies_from_frame=1,prompts=dsl.make_prompts(e,v),override=dsl.to_physics_override(e,v))

def cases(scene_id):
    s=SPECS[scene_id];a=s['actor_id'];e=s['elastic_id']
    speed=3 if scene_id=='gym_landing_mat'else 2
    if scene_id=='gym_landing_mat':
        return {'source':None,'mass_double':f'SET {a}.mass TIMES 2','faster':f'SET {a}.initial_velocity TIMES {speed}','young_modulus_rebound':f'SET {e}.young_modulus TIMES 10','rebound_probe_x10':f'SET {e}.young_modulus TIMES 10','young_modulus_soft':f'SET {e}.young_modulus TIMES 0.25','add_path_obstacle':'ADD gym_water_bottle AT PRESET roll_path','delete_actor':f'DELETE {a}'}
    return {'source':None,'mass_double':f'SET {a}.mass TIMES 2','faster':f'SET {a}.initial_velocity TIMES {speed}','stiffer':'SET grass_thatch.young_modulus TIMES 10','add_path_obstacle':'ADD picnic_cup AT PRESET roll_path','delete_actor':f'DELETE {a}'}
