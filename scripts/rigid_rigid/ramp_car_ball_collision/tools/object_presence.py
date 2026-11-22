"""Whole-frame visual presence for native object-deletion interventions."""
CAR_ROOTS=('car_body','wheel_0','wheel_1','wheel_2','wheel_3')

def car_present(configuration,frame):
    car=configuration['physics']['car']
    time=(frame-1)/configuration['render']['fps']
    return car.get('present',True) and (car.get('remove_at_sec') is None or time<car['remove_at_sec'])

def remove_roots(roots,names):
    import bpy
    for name in names:
        root=roots.pop(name,None) or bpy.data.objects.get(name)
        if root is None:continue
        for obj in list(root.children_recursive):bpy.data.objects.remove(obj,do_unlink=True)
        bpy.data.objects.remove(root,do_unlink=True)

def keyframe_presence(roots,configuration):
    car=configuration['physics']['car'];time=car.get('remove_at_sec')
    if time is None:return
    frame=1+time*configuration['render']['fps']
    for name in CAR_ROOTS:
        root=roots.get(name)
        if root is None:continue
        for obj in [root]+list(root.children_recursive):
            for f,hidden in [(1,False),(frame-1e-4,False),(frame,True)]:
                obj.hide_render=hidden;obj.hide_viewport=hidden
                obj.keyframe_insert(data_path='hide_render',frame=f)
                obj.keyframe_insert(data_path='hide_viewport',frame=f)
            for curve in obj.animation_data.action.fcurves:
                if curve.data_path in {'hide_render','hide_viewport'}:
                    for point in curve.keyframe_points:point.interpolation='CONSTANT'

def active_roots(roots,configuration,frame):
    return {name:root for name,root in roots.items() if name not in CAR_ROOTS or car_present(configuration,frame)}

def apply_frame_presence(roots,configuration,frame):
    # Hard removal before Cycles builds its scene also removes shadow/reflection
    # geometry throughout the whole shutter interval of the first absent frame.
    if not car_present(configuration,frame):remove_roots(roots,CAR_ROOTS)
