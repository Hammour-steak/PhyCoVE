"""Lighting-only comparison against the retained courtyard scene."""
import argparse,json,math,sys,time
from pathlib import Path
import bpy
from mathutils import Vector
here=Path(__file__).resolve().parent
sys.path.insert(0,str(here))
import environment_realism as base

PROFILES={
    'sunny':{'environment_strength':.30,'sun_energy':2.50,'sun_angle_degrees':.65,'exposure':.12},
    'soft':{'environment_strength':.43,'sun_energy':1.95,'sun_angle_degrees':1.60,'exposure':.12},
}
def lighting_state(scene):
    bg=next(n for n in scene.world.node_tree.nodes if n.bl_idname=='ShaderNodeBackground')
    return {'environment_strength':bg.inputs['Strength'].default_value,'look':scene.view_settings.look,
        'exposure':scene.view_settings.exposure,'lights':[
        {'name':o.name,'energy':o.data.energy,'color':list(o.data.color),'rotation':list(o.rotation_euler),
         'angle':o.data.angle if o.data.type=='SUN' else None,'hidden':o.hide_render}
        for o in scene.objects if o.type=='LIGHT']}

def apply_lighting(scene,profile):
    params=PROFILES[profile]
    bg=next(n for n in scene.world.node_tree.nodes if n.bl_idname=='ShaderNodeBackground')
    bg.inputs['Strength'].default_value=params['environment_strength']
    for name in ['PCVE_LargeSoftbox','PCVE_Sun','PCVE_SoftSkyFill']:
        if bpy.data.objects.get(name): bpy.data.objects[name].hide_render=True
    sun=bpy.data.objects['PCVE_RealismSun'];sun.hide_render=False
    sun.data.energy=params['sun_energy'];sun.data.color=(1,.96,.91)
    sun.data.angle=math.radians(params['sun_angle_degrees'])
    elevation=math.radians(45);azimuth=math.radians(-135)
    direction=Vector((math.cos(elevation)*math.cos(azimuth),math.cos(elevation)*math.sin(azimuth),math.sin(elevation)))
    sun.rotation_euler=direction.to_track_quat('Z','Y').to_euler()
    scene.view_settings.look='AgX - Base Contrast';scene.view_settings.exposure=params['exposure']
    return params

def main():
    p=argparse.ArgumentParser();p.add_argument('--out',type=Path,required=True)
    a=p.parse_args(sys.argv[sys.argv.index('--')+1:]);a.out.mkdir(parents=True,exist_ok=True)
    scene=bpy.context.scene;before=lighting_state(scene);geometry=base.environment_signature()
    base.configure_gpu(scene,32);scene.render.resolution_x=1280;scene.render.resolution_y=720
    result={'before':before,'geometry_before':geometry,'profiles':{}}
    for profile in PROFILES:
        apply_lighting(scene,profile);scene.render.filepath=str(a.out/(profile+'.png'));started=time.monotonic()
        bpy.ops.render.render(write_still=True)
        result['profiles'][profile]={'after':lighting_state(scene),'render_seconds':time.monotonic()-started}
        print('LIGHTING_RENDERED',profile,flush=True)
    assert geometry==base.environment_signature()
    result['geometry_after']=base.environment_signature()
    (a.out/'lighting_comparison.json').write_text(json.dumps(result,indent=2))

if __name__=='__main__': main()
