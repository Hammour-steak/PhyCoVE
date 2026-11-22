"""Newton restitution impulses for a rigid can after IPC's compression solve.

This is a native substep contact law, not an animation correction. Positions are
never changed here. IPC retains separation, compression and persistent contact.
An impact episode is rearmed only after actual separation.
"""
import numpy as np


def skew(x):
    a,b,c=x
    return np.array([[0.,-c,b],[c,0.,-a],[-b,a,0.]])


def angular_velocity(transform, velocity):
    spin=velocity[:3,:3]@np.linalg.inv(transform[:3,:3])
    return np.array([spin[2,1]-spin[1,2],spin[0,2]-spin[2,0],spin[1,0]-spin[0,1]])*.5


def kinetic(v,w,mass,inertia):
    return float(.5*mass*np.dot(v,v)+.5*w@inertia@w)


def restitution_impulse(T,V,V_in,T_in,vertices,mass,inertia_local,coefficient,friction):
    """Resolve one floor witness with angular effective mass and Coulomb friction.

    V is the IPC-compressed state, V_in the incident state including this step's
    gravity impulse. The incoming and outgoing contact velocities determine the
    Newton restitution target. All terms are in SI units.
    """
    R=T[:3,:3];world=vertices@R.T+T[:3,3]
    heights=world[:,2];lowest=heights.min()
    # Average a coplanar witness patch, retaining an edge/point for tilted cans.
    hit=world[heights<=lowest+1e-7].mean(axis=0);r=hit-T[:3,3]
    vin=V_in[:3,3].copy();win=angular_velocity(T_in,V_in)
    uin=vin+np.cross(win,r)
    v=V[:3,3].copy();w=angular_velocity(T,V)
    u=v+np.cross(w,r)
    target=-coefficient*uin[2]
    if uin[2]>=0 or target<=u[2]:return V.copy(),None
    I=R@inertia_local@R.T;inverse=np.linalg.inv(I)
    S=skew(r);K=np.eye(3)/mass-S@inverse@S
    desired=np.array([0.,0.,target])
    impulse=np.linalg.solve(K,desired-u)
    regime='stick'
    if impulse[2]<0 or np.linalg.norm(impulse[:2])>friction*impulse[2]:
        regime='slip';direction=u[:2]/max(np.linalg.norm(u[:2]),1e-15)
        ray=np.array([-friction*direction[0],-friction*direction[1],1.])
        impulse=ray*max(0.,(target-u[2])/(K@ray)[2])
    vo=v+impulse/mass;wo=w+inverse@np.cross(r,impulse)
    result=V.copy();result[:3,3]=vo;result[:3,:3]=skew(wo)@R
    before=kinetic(vin,win,mass,T_in[:3,:3]@inertia_local@T_in[:3,:3].T)
    after=kinetic(vo,wo,mass,I)
    if after>before+max(1e-7,before*1e-5):
        raise ValueError('Floor restitution gained energy: '+str((before,after)))
    info=dict(contact_point_m=hit.tolist(),normal_incident_velocity_m_s=float(uin[2]),
        normal_compressed_velocity_m_s=float(u[2]),normal_outgoing_velocity_m_s=float((vo+np.cross(wo,r))[2]),
        coefficient_of_restitution=coefficient,impulse_N_s=impulse.tolist(),friction_coefficient=friction,
        kinetic_before_J=before,kinetic_after_J=after,friction_regime=regime,
        position_changed=False,angular_velocity_after_rad_s=wo.tolist())
    return result,info
