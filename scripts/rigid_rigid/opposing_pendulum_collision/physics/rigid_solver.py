"""3D free-sphere impulse dynamics with unilateral, inextensible endpoint ropes.

No pendulum angle coordinates, planar joints, motion guides or prescribed paths.
Rope: |x+R*a-A| <= L, tensile impulse lambda >= 0. Nonlinear endpoint
constraint is solved by projected impulses together with actual sphere/box
contacts. Each body retains all six velocity DOFs and a unit quaternion.
Pair contact materials are explicit; e is used directly (no body multiplication).
No Baumgarte contact velocity bias, energy clamp, pose correction or spring.
"""
from __future__ import annotations
import math
import numpy as np

SOLVER_VERSION="pcve_free_sphere_unilateral_passive_bend_2"

def cross(a,b):
    return np.array([a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]])

def skew(v):
    x,y,z=v
    return np.array([[0.,-z,y],[z,0.,-x],[-y,x,0.]])

def rotate(q,v):
    t=2*cross(q[:3],v)
    return v+q[3]*t+cross(q[:3],t)

def advance_quaternion(q,w,dt):
    # Exponential of world angular velocity; spheres have isotropic inertia.
    angle=float(np.linalg.norm(w))*dt
    if angle<1.e-14:
        xyz=.5*dt*w;cw=1.
    else:
        xyz=w*(math.sin(angle/2)*dt/angle);cw=math.cos(angle/2)
    v=cw*q[:3]+q[3]*xyz+cross(xyz,q[:3])
    s=cw*q[3]-float(xyz@q[:3]);out=np.r_[v,s]
    return out/np.linalg.norm(out)

class Body:
    def __init__(self,name,spec,position,quaternion,rope=None):
        self.name=name;self.spec=spec;self.mass=spec["mass_kg"];self.inv_mass=1/self.mass
        self.radius=spec["radius_m"];self.inertia=spec["inertia_factor"]*self.mass*self.radius**2
        self.inv_inertia=1/self.inertia
        self.p=np.array(position,dtype=float);self.q=np.array(quaternion,dtype=float)
        self.v=np.array(spec["initial_linear_velocity"],dtype=float)
        self.w=np.array(spec["initial_angular_velocity"],dtype=float)
        self.rope=rope if rope and rope["present"] else None
        self.anchor=np.array(rope["anchor_m"]) if rope else None
        self.attach=np.array(rope["attachment_local_m"]) if rope else None
        self.rope_impulse=0.;self.rope_work=0.
        self.bend_impulse=np.zeros(3);self.bend_relative_angular_velocity=np.zeros(3)
        self.bend_coefficient=0.;self.bend_dissipation=0.

    def velocity_at(self,r):return self.v+cross(self.w,r)

    def impulse(self,imp,r):
        self.v+=imp*self.inv_mass;self.w+=cross(r,imp)*self.inv_inertia

    def kinetic(self):return .5*self.mass*float(self.v@self.v)+.5*self.inertia*float(self.w@self.w)

    def energy(self,g,reference_z):return self.kinetic()-self.mass*float(g@np.array([self.p[0],self.p[1],self.p[2]-reference_z]))

    def endpoint(self):return self.p+rotate(self.q,self.attach)

class CordBendDamper:
    """Passive, zero-stiffness loss at the textile/eyelet connection.

    nu = P_n*w - Omega_cord = Jv*v + Jw*w. Apply both -Jv.T*lambda
    and -Jw.T*lambda; a torque alone would omit the reaction and could add
    energy. The implicit constitutive law is nu = lambda/(c*dt).
    P_n leaves spin about the cord free. No position or angle target exists.
    c = rate / mean_nonzero_eigenvalue(K), K=J*M^-1*J.T, so rate has
    units 1/s and equal geometry retains mass-independent free swing.
    """
    def __init__(self,body,dt):
        self.body=body;self.impulse=np.zeros(3)
        r=rotate(body.q,body.attach);d=body.anchor-body.p-r;length=float(np.linalg.norm(d));n=d/length
        self.Jv=skew(n)/length
        self.Jw=np.eye(3)-np.outer(n,n)-self.Jv@skew(r)
        self.K=body.inv_mass*(self.Jv@self.Jv.T)+body.inv_inertia*(self.Jw@self.Jw.T)
        self.c=body.rope['bend_damping_rate_per_s']/(.5*float(np.trace(self.K)))
        self.alpha=1/(self.c*dt)
        self.inverse=np.linalg.inv(self.K+self.alpha*np.eye(3))

    def relative(self):
        b=self.body;return self.Jv@b.v+self.Jw@b.w

    def solve(self):
        enabled=self.body.rope_impulse>1.e-14
        new=self.inverse@(self.relative()+self.K@self.impulse) if enabled else np.zeros(3)
        delta=new-self.impulse;self.impulse=new
        self.body.v-=self.body.inv_mass*(self.Jv.T@delta)
        self.body.w-=self.body.inv_inertia*(self.Jw.T@delta)
        return float(np.linalg.norm(delta))

class Contact:
    def __init__(self,a,b,normal,ra,rb,gap,mat,label):
        self.a=a;self.b=b;self.n=normal;self.ra=ra;self.rb=rb;self.gap=gap
        self.e=mat["restitution"];self.mu=mat["friction"];self.label=label
        self.normal_impulse=0.;self.tangent_impulse=np.zeros(3)
        self.pre_velocity=self.relative();self.pre_vn=float(self.n@self.pre_velocity)
        self.target_vn=0.;self.fresh=False

    def relative(self):
        return self.a.velocity_at(self.ra)-(self.b.velocity_at(self.rb) if self.b else 0.)

    def effective(self,direction):
        r=cross(self.ra,direction);value=self.a.inv_mass+self.a.inv_inertia*float(r@r)
        if self.b:
            r=cross(self.rb,direction);value+=self.b.inv_mass+self.b.inv_inertia*float(r@r)
        return value

    def apply(self,imp):
        self.a.impulse(imp,self.ra)
        if self.b:self.b.impulse(-imp,self.rb)

    def solve(self):
        vn=float(self.n@self.relative())
        new=max(0.,self.normal_impulse+(self.target_vn-vn)/self.effective(self.n))
        delta=new-self.normal_impulse;self.normal_impulse=new;self.apply(delta*self.n)
        vt=self.relative();vt-=float(vt@self.n)*self.n;speed=float(np.linalg.norm(vt))
        if speed>1.e-12:
            direction=vt/speed;candidate=self.tangent_impulse-direction*speed/self.effective(direction)
            norm=float(np.linalg.norm(candidate));bound=self.mu*self.normal_impulse
            if norm>bound:candidate*=bound/norm
            self.apply(candidate-self.tangent_impulse);self.tangent_impulse=candidate
        return abs(delta)

def sphere_box(body,box,material):
    center=np.asarray(box["center"]);half=np.asarray(box["dimensions"])/2
    local=body.p-center;closest=np.minimum(np.maximum(local,-half),half)
    d=local-closest;length=float(np.linalg.norm(d))
    if length>1.e-14:n=d/length;gap=length-body.radius
    else:
        clearance=half-np.abs(local);axis=int(np.argmin(clearance));n=np.zeros(3)
        n[axis]=1. if local[axis]>=0 else -1.;gap=-float(clearance[axis])-body.radius
    return Contact(body,None,n,-body.radius*n,None,gap,material,body.name+":"+box["id"])

class World:
    def __init__(self,bodies,boxes,physics,quality,dt):
        self.bodies=bodies;self.boxes=boxes;self.physics=physics;self.quality=quality
        self.g=np.asarray(physics["gravity"]);self.dt=dt;self.active=set();self.time=0.
        self.max_penetration=0.;self.max_rope_extension=0.;self.max_positive_rope_work=0.
        self.total_rope_work=0.;self.max_solver_iterations=0;self.contact_steps=0
        self.bend_dissipated=0.;self.max_positive_bend_work=0.;self.max_bend_constitutive_error=0.

    def contacts(self):
        out=[]
        if len(self.bodies)==2:
            a,b=self.bodies;d=a.p-b.p;dist=float(np.linalg.norm(d));n=d/dist
            gap=dist-a.radius-b.radius
            if gap<=self.quality["contact_activation_gap_m"]:
                out.append(Contact(a,b,n,-a.radius*n,b.radius*n,gap,self.physics["contacts"]["ball_ball"],"B_left:B_right"))
        for body in self.bodies:
            for box in self.boxes:
                # Broad phase preserves finite table/base edges and all box faces.
                if np.any(np.abs(body.p-np.asarray(box["center"]))>np.asarray(box["dimensions"])/2+body.radius):continue
                mat=self.physics["contacts"]["ball_table" if box["material"]=="table" else "ball_fixture"]
                c=sphere_box(body,box,mat)
                if c.gap<=self.quality["contact_activation_gap_m"]:out.append(c)
        return out

    def rope_solve(self,b,pold,qold):
        if b.rope is None:return 0.
        dt=self.dt;qp=advance_quaternion(qold,b.w,dt);ra=rotate(qp,b.attach)
        d=pold+dt*b.v+ra-b.anchor;dist=float(np.linalg.norm(d));n=d/dist
        residual=(dist-b.rope["length_m"])/dt
        arm=cross(ra,n);effective=b.inv_mass+b.inv_inertia*float(arm@arm)
        new=max(0.,b.rope_impulse+residual/effective);delta=new-b.rope_impulse
        b.rope_impulse=new;b.impulse(-delta*n,ra)
        return abs(delta)

    def step(self):
        dt=self.dt;previous=[];kin_before={}
        for b in self.bodies:
            previous.append((b.p.copy(),b.q.copy()))
            b.v+=dt*self.g;b.v*=math.exp(-b.spec["linear_drag_per_s"]*dt)
            b.w*=math.exp(-b.spec["angular_drag_per_s"]*dt)
            b.rope_impulse=0.;b.bend_impulse=np.zeros(3);b.bend_relative_angular_velocity=np.zeros(3)
            b.bend_coefficient=0.;b.bend_dissipation=0.;kin_before[b.name]=b.kinetic()
        dampers=[CordBendDamper(b,dt) for b in self.bodies if b.rope and b.rope.get('bend_damping_rate_per_s',0.)>0]
        contacts=self.contacts();active={c.label for c in contacts}
        for c in contacts:
            c.fresh=c.label not in self.active
            c.target_vn=-c.e*c.pre_vn if c.fresh and c.pre_vn<-self.quality["restitution_velocity_threshold_m_per_s"] else 0.
            self.max_penetration=max(self.max_penetration,-c.gap)
        for iteration in range(self.quality["solver_iterations"]):
            largest=0.
            for b,(pold,qold) in zip(self.bodies,previous):largest=max(largest,self.rope_solve(b,pold,qold))
            for damper in dampers:largest=max(largest,damper.solve())
            for c in contacts:largest=max(largest,c.solve())
            if largest<self.quality["impulse_tolerance_Ns"]:break
        self.max_solver_iterations=max(self.max_solver_iterations,iteration+1)
        for damper in dampers:
            b=damper.body;nu=damper.relative();work=-float(damper.impulse@nu)
            b.bend_impulse=damper.impulse.copy();b.bend_relative_angular_velocity=nu
            b.bend_coefficient=damper.c;b.bend_dissipation=-work
            self.bend_dissipated-=work;self.max_positive_bend_work=max(self.max_positive_bend_work,work)
            self.max_bend_constitutive_error=max(self.max_bend_constitutive_error,float(np.linalg.norm(nu-damper.alpha*damper.impulse)) if b.rope_impulse>1.e-14 else float(np.linalg.norm(damper.impulse)))
        events=[]
        for c in contacts:
            if c.fresh and c.normal_impulse>1.e-9:
                events.append({"time_sec":self.time,"objects":[c.a.name,c.b.name if c.b else c.label.split(":")[1]],
                    "kind":"ball_ball" if c.b else "ball_static", "contact_point_m":(c.a.p+c.ra).tolist(),
                    "normal_toward_first":c.n.tolist(),"gap_m":c.gap,"pre_normal_velocity_m_per_s":c.pre_vn,
                    "post_normal_velocity_m_per_s":float(c.n@c.relative()),
                    "configured_restitution":c.e,
                    "applied_restitution":c.target_vn/(-c.pre_vn) if c.pre_vn<-1.e-10 else 0.,
                    "measured_normal_restitution":float(c.n@c.relative())/(-c.pre_vn) if c.pre_vn<-1.e-10 else None,
                    "normal_impulse_Ns":c.normal_impulse,"tangent_impulse_Ns":c.tangent_impulse.tolist(),
                    "pre_contact_relative_velocity":c.pre_velocity.tolist(),
                    "post_linear_velocities":{b.name:b.v.tolist() for b in self.bodies},
                    "post_angular_velocities":{b.name:b.w.tolist() for b in self.bodies}})
        # Integration only: these are solved free rigid-body velocities, no projection.
        for b,(pold,qold) in zip(self.bodies,previous):
            if not contacts:
                work=b.kinetic()-kin_before[b.name];self.total_rope_work+=work
                self.max_positive_rope_work=max(self.max_positive_rope_work,work)
            b.p=pold+dt*b.v;b.q=advance_quaternion(qold,b.w,dt)
            if b.rope:
                self.max_rope_extension=max(self.max_rope_extension,float(np.linalg.norm(b.endpoint()-b.anchor))-b.rope["length_m"])
        self.active=active;self.time+=dt
        if contacts:self.contact_steps+=1
        return events
