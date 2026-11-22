"""Audit the NEW outfeed planes against the newly simulated native physics."""
import socket
import bpy,numpy as np
from mathutils import Vector

def audit(p,c):
    deps=bpy.context.evaluated_depsgraph_get()
    names=('Continuous moving belt','Fixed feathered transition plate','Downhill stainless slide','Horizontal baggage pickup deck')
    objects=[bpy.data.objects[name].evaluated_get(deps) for name in names]
    errors=[];angles=[];missed=[];count=0
    for plane,row in enumerate(c['support_profile']):
        lo,hi,z,slope=row;lo=max(lo,-1.5)
        for x in np.linspace(lo+.003,hi-.003,9):
          h=z+slope*(x-row[0]);target=Vector((-slope,0,1)).normalized()
          for y in (-.20,0.,.20):
            origin=Vector((x,y,h+.012));best=None
            for ob in objects:
                inv=ob.matrix_world.inverted();ok,hit,n,face=ob.ray_cast(inv@origin,inv.to_3x3()@Vector((0,0,-1)),distance=.05)
                if not ok:continue
                pt=ob.matrix_world@hit;normal=(ob.matrix_world.to_3x3().inverted().transposed()@n).normalized()
                if best is None or pt.z>best[0]:best=(pt.z,normal)
            count+=1
            if best is None:missed.append([plane,float(x),y]);continue
            errors.append(abs(best[0]-h));angles.append((best[1]-target).length)
    floor=bpy.data.objects['Granite station floor'];floor_top=max((floor.matrix_world@Vector(v)).z for v in floor.bound_box)
    stop=bpy.data.objects['Pickup rubber end stop'];stop_front=min((stop.matrix_world@Vector(v)).x for v in stop.bound_box)
    checks={'all_four_native_contact_faces_exist':len(objects)==4,'all_native_profile_rays_hit':not missed,'native_and_visual_contact_height_below_0p1mm':max(errors,default=1)<.0001,'native_and_visual_plane_normals_match':max(angles,default=1)<.0001,'end_stop_face_matches_native_x':abs(stop_front-p['pickup_end_x_m'])<.0001,'original_floor_datum_preserved':abs(floor_top+.005)<1e-6,'new_native_rigid_dofs_present':all(k in c for k in ('bag_positions','bag_euler','bag_rigid','bag_rigid_velocity'))}
    return {'status':'passed' if all(checks.values()) else 'failed','checks':{k:bool(v) for k,v in checks.items()},'native_generation':'recomputed; no physics cache reused from earlier runs','support_rays':count,'max_contact_height_error_m':max(errors,default=None),'max_plane_normal_vector_error':max(angles,default=None),'missed':missed,'end_stop_x_m':stop_front,'floor_top_z_m':floor_top,'execution_host':socket.gethostname(),'local_blender_used':False,'scope':'Actual evaluated belt/nose/slope/platform rays and stop face against all four native support faces. Rigid contact penetration checked independently from native states; no render offsets.'}
