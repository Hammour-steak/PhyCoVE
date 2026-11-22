"""Passive modal internal force, preserving all rigid motion, plus air drag.

These functions return forces to the native integrator. They never overwrite
native positions or velocities. Damping is constant across the whole recording.
"""
import numpy as np

def internal_force(x,v,mass,rate,dt):
    total=mass.sum();centre=np.einsum('i,ij->j',mass,x)/total
    cm_velocity=np.einsum('i,ij->j',mass,v)/total;r=x-centre
    inertia=np.eye(3)*np.einsum('i,ij,ij->',mass,r,r)-np.einsum('i,ij,ik->jk',mass,r,r)
    momentum=np.einsum('i,ij->j',mass,np.cross(r,v-cm_velocity))
    omega=np.linalg.solve(inertia,momentum)
    relative=v-cm_velocity-np.cross(omega,r)
    force=-(rate/(1.+rate*dt))*mass[:,None]*relative
    power=float(np.sum(force*v));resultant=np.linalg.norm(force.sum(0));torque=np.linalg.norm(np.cross(r,force).sum(0))
    if power>1e-10 or resultant>1e-10 or torque>1e-10:
        raise RuntimeError('Internal damping lost passivity or momentum conservation')
    return force,dict(power_w=power,resultant_force_n=float(resultant),resultant_torque_nm=float(torque))

def air_force(v,normals,area,mass,p,dt):
    normal_speed=np.einsum('ij,ij->i',v,normals);vn=normal_speed[:,None]*normals;vt=v-vn
    normal_coefficient=area*(p['air_linear_normal_kg_m2_s']+.5*p['air_density']*p['air_drag_coefficient']*abs(normal_speed))
    tangent_coefficient=area*(p['air_linear_tangent_kg_m2_s']+.5*p['air_density']*p['air_drag_coefficient']*.03*np.linalg.norm(vt,axis=1))
    # Positive backward-Euler force predictor avoids explicit drag overshoot.
    kn=normal_coefficient/(1.+dt*normal_coefficient/mass)
    kt=tangent_coefficient/(1.+dt*tangent_coefficient/mass)
    force=-kn[:,None]*vn-kt[:,None]*vt
    if np.sum(force*v)>1e-10:raise RuntimeError('Air drag is not passive')
    return force
