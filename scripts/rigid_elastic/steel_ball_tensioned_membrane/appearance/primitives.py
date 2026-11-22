"""Mesh helpers of the laboratory workcell used by render_native.py: torus, beam and the animated drop sphere."""
import bpy
from mathutils import Matrix,Vector
from geometry import cylinder

def torus(name,loc,major,minor,material):
    bpy.ops.mesh.primitive_torus_add(major_radius=major,minor_radius=minor,major_segments=128,minor_segments=20,location=loc);o=bpy.context.object;o.name=name;o.data.materials.append(material);return o

def beam(name,a,b,radius,material):
    a=Vector(a);b=Vector(b);v=b-a;o=cylinder(name,(a+b)/2,radius,v.length,material,24);o.rotation_euler=v.to_track_quat('Z','Y').to_euler();return o

def animate_ball(z,p,material,markmat,transforms_key='ball_transforms',radius_key='ball_radius_m',object_name='304 stainless drop sphere'):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=128,ring_count=64,radius=p[radius_key]);ball=bpy.context.object;ball.name=object_name;ball.data.materials.append(material);ball.rotation_mode='QUATERNION'
    for f,T in enumerate(z[transforms_key],1):
        M=Matrix(T.tolist());ball.location=M.to_translation();ball.rotation_quaternion=M.to_quaternion();ball.keyframe_insert('location',frame=f);ball.keyframe_insert('rotation_quaternion',frame=f)
    return ball
