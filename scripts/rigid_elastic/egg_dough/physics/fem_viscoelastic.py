"""Free 3-D tetrahedral finite-strain viscoelastic solid and six-DOF mesh-SDF rigid egg, SI/f64.

All contact forces are unilateral. A contact quadrature force acts at the same
world point on both bodies, conserving its linear and angular impulse exactly.
No pins, shape restoration, prescribed indentation, or post-step projection.
"""
import numpy as np
import taichi as ti
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import scene_asset

@ti.data_oriented
class DoughBall:
 def __init__(self,c,d):
  p=c['physics'];s=p['dough'];b=p['ball'];k=p['contact'];q=c['simulation_quality']
  self.n=len(d['rest_vertices']);self.ne=len(d['tetrahedra']);self.nq=len(d['quadrature_area'])
  self.present=s['present'];self.dt=q['dt_s'];self.M=b['mass_kg'];self.R=b['radius_m'];self.I=np.array(b['inertia_kg_m2'],dtype=float)
  from pathlib import Path
  shape=dict(np.load(scene_asset(Path(__file__).parents[1],b['rigid_geometry_asset'])))
  self.sdf=ti.field(ti.f64,shape['sdf'].shape);self.sdf.from_numpy(shape['sdf'].astype(np.float64))
  self.sdf_lo=tuple(shape['sdf_min']);self.sdf_dx=tuple(shape['sdf_spacing']);self.grid_n=shape['sdf'].shape[0]
  self.rigid_vertices=shape['vertices'];self.rigid_faces=shape['faces']
  self.rv=ti.Vector.field(3,ti.f64,len(self.rigid_vertices));self.rv.from_numpy(self.rigid_vertices)
  self.body_I=ti.Matrix.field(3,3,ti.f64,());self.body_invI=ti.Matrix.field(3,3,ti.f64,())
  self.body_I[None]=self.I;self.body_invI[None]=np.linalg.inv(self.I)
  self.bl=ti.Vector.field(3,ti.f64,());self.bl[None]=[0.,0.,0.]
  self.floor_gap=ti.field(ti.f64,());self.floor_arm=ti.Vector.field(3,ti.f64,());self.floor_count=ti.field(ti.i32,())
  # Optional finite pastry board under the egg (contact.board_support): board top z=0 inside its footprint,
  # worktop top board_support['worktop_z_m'] outside it. Absent (every published case): the z=0 plane.
  self.board=k.get('board_support');self.has_board=self.board is not None
  if self.has_board:
   self.board_c=tuple(float(x) for x in self.board['center_xy_m']);self.board_h=tuple(.5*float(x) for x in self.board['size_xy_m']);self.board_z=float(self.board['worktop_z_m'])
  self.mu=s['E_Pa']/(2*(1+s['nu']));self.bulk=s['E_Pa']/(3*(1-2*s['nu']));self.ginf=s['equilibrium_shear_fraction'];self.tau=s['relaxation_time_s'];self.eta=s['shear_viscosity_Pa_s'];self.decay=float(np.exp(-self.dt/self.tau))
  self.kn=k['ball_dough_penalty_Pa_per_m'];self.kt=k['dough_table_penalty_Pa_per_m'];self.cn=k['normal_damping_Pa_s_per_m'];self.ct=k['tangent_damping_Pa_s_per_m'];self.mub=k['ball_dough_friction'];self.mut=k['dough_table_friction'];self.mubt=k['ball_table_friction'];self.kbt=k['ball_table_stiffness_N_m'];self.cbt=k['ball_table_damping_N_s_m'];self.ctbt=k['ball_table_tangent_damping_N_s_m'];self.rr=k['ball_table_rolling_resistance_m'];self.crr=k['ball_table_rolling_damping_N_m_s']
  self.x=ti.Vector.field(3,ti.f64,self.n);self.v=ti.Vector.field(3,ti.f64,self.n);self.f=ti.Vector.field(3,ti.f64,self.n);self.mass=ti.field(ti.f64,self.n)
  self.tet=ti.Vector.field(4,ti.i32,self.ne);self.inv=ti.Matrix.field(3,3,ti.f64,self.ne);self.vol=ti.field(ti.f64,self.ne)
  self.fvi=ti.Matrix.field(3,3,ti.f64,self.ne);self.ev=ti.field(ti.f64,self.ne);self.detf=ti.field(ti.f64,self.ne);self.stress=ti.field(ti.f64,self.ne)
  self.kirchhoff=ti.Matrix.field(3,3,ti.f64,self.ne)
  self.qids=ti.Vector.field(3,ti.i32,self.nq);self.qw=ti.Vector.field(3,ti.f64,self.nq);self.qa=ti.field(ti.f64,self.nq)
  self.bp=ti.Vector.field(3,ti.f64,());self.bv=ti.Vector.field(3,ti.f64,());self.bw=ti.Vector.field(3,ti.f64,());self.bq=ti.Vector.field(4,ti.f64,())
  self.bf=ti.Vector.field(3,ti.f64,());self.bt=ti.Vector.field(3,ti.f64,());self.extP=ti.Vector.field(3,ti.f64,());self.extL=ti.Vector.field(3,ti.f64,())
  self.cP=ti.Vector.field(3,ti.f64,());self.cL=ti.Vector.field(3,ti.f64,());self.peak_force=ti.field(ti.f64,());self.first_contact=ti.field(ti.f64,())
  self.minJ=ti.field(ti.f64,());self.max_pen=ti.field(ti.f64,());self.max_table_pen=ti.field(ti.f64,());self.relaxation_work=ti.field(ti.f64,());self.visc_work=ti.field(ti.f64,());self.contact_work=ti.field(ti.f64,());self.contactN=ti.field(ti.f64,());self.rolling_work=ti.field(ti.f64,())
  self.instant_gap=ti.field(ti.f64,());self.table_force=ti.Vector.field(3,ti.f64,());self.current_energy=ti.field(ti.f64,())
  self.x.from_numpy(d['rest_vertices']);self.v.fill(0);self.tet.from_numpy(d['tetrahedra']);self.inv.from_numpy(d['inverse_dm']);self.vol.from_numpy(d['volumes'])
  mass=np.zeros(self.n)
  for j in range(4):np.add.at(mass,d['tetrahedra'][:,j],d['volumes']*s['density_kg_m3']/4)
  self.mass.from_numpy(mass);self.qids.from_numpy(d['quadrature_nodes']);self.qw.from_numpy(d['quadrature_weights']);self.qa.from_numpy(d['quadrature_area'])
  self.fvi.from_numpy(np.repeat(np.eye(3)[None],self.ne,axis=0));self.ev.fill(0);self.detf.fill(1)
  self.bp[None]=b['initial_position_m'];self.bv[None]=b['initial_velocity_m_s'];self.bw[None]=b['initial_angular_velocity_rad_s'];self.bq[None]=b['initial_rotation_quaternion_wxyz']
  Q=pose([0.,0.,0.],b['initial_rotation_quaternion_wxyz'])[:3,:3];self.bl[None]=Q@self.I@Q.T@np.array(b['initial_angular_velocity_rad_s'])
  self.minJ[None]=1.;self.first_contact[None]=-1.

 @ti.func
 def rotation(self):
  q=self.bq[None];w,x,y,z=q[0],q[1],q[2],q[3]
  return ti.Matrix([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],[2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

 @ti.func
 def mesh_gap(self,p):
  dist=p.norm();normal=p/ti.max(dist,1e-20);gap=dist-self.R
  if dist<self.R+.001:
   q=(p-ti.Vector(self.sdf_lo))/ti.Vector(self.sdf_dx)
   if (q>=0).all() and (q<self.grid_n-1).all():
    cell=ti.cast(ti.floor(q),ti.i32);f=q-ti.cast(cell,ti.f64)
    weights=ti.Matrix([[1-f[0],f[0]],[1-f[1],f[1]],[1-f[2],f[2]]])
    gap=0.;grad=ti.Vector.zero(ti.f64,3)
    for i,j,k in ti.static(ti.ndrange(2,2,2)):
     v=self.sdf[cell[0]+i,cell[1]+j,cell[2]+k]
     wx,wy,wz=weights[0,i],weights[1,j],weights[2,k]
     gap+=v*wx*wy*wz
     grad[0]+=v*(2*i-1)*wy*wz/self.sdf_dx[0]
     grad[1]+=v*wx*(2*j-1)*wz/self.sdf_dx[1]
     grad[2]+=v*wx*wy*(2*k-1)/self.sdf_dx[2]
    normal=grad/ti.max(grad.norm(),1e-20)
   else:gap=.003
  return gap,normal

 @ti.kernel
 def probe_mesh_gaps(self,points:ti.types.ndarray(dtype=ti.f64,ndim=2),out:ti.types.ndarray(dtype=ti.f64,ndim=2)):
  for i in range(points.shape[0]):
   gap,n=self.mesh_gap(ti.Vector([points[i,0],points[i,1],points[i,2]]))
   out[i,0]=gap
   for j in ti.static(range(3)):out[i,j+1]=n[j]

 @ti.func
 def support(self,p):
  h=0.
  if ti.static(self.has_board):
   if ti.abs(p[0]-self.board_c[0])>self.board_h[0] or ti.abs(p[1]-self.board_c[1])>self.board_h[1]:h=self.board_z
  return h

 def rigid_angular_momentum(self):
  return np.array(self.bl[None])

 @ti.func
 def external(self,point,force):
  dp=force*self.dt;dl=point.cross(dp)
  for j in ti.static(range(3)):
   ti.atomic_add(self.extP[None][j],dp[j]);ti.atomic_add(self.extL[None][j],dl[j])

 @ti.kernel
 def reset_accounting(self):
  self.extP[None]=ti.Vector.zero(ti.f64,3);self.extL[None]=ti.Vector.zero(ti.f64,3)
  self.cP[None]=ti.Vector.zero(ti.f64,3);self.cL[None]=ti.Vector.zero(ti.f64,3)
  self.minJ[None]=1.;self.max_pen[None]=0.;self.max_table_pen[None]=0.;self.first_contact[None]=-1.
  self.rolling_work[None]=0.;self.relaxation_work[None]=0.;self.visc_work[None]=0.;self.contact_work[None]=0.;self.peak_force[None]=0.

 @ti.kernel
 def step(self,use_ball:ti.i32,time:ti.f64):
  self.bf[None]=ti.Vector([0.,0.,-9.81*self.M]);self.bt[None]=ti.Vector.zero(ti.f64,3);self.instant_gap[None]=1.;self.table_force[None]=ti.Vector.zero(ti.f64,3);self.current_energy[None]=0.;self.contactN[None]=0.
  self.floor_gap[None]=1.;self.floor_arm[None]=ti.Vector.zero(ti.f64,3);self.floor_count[None]=0
  Q=self.rotation()
  for i in self.rv:
   arm=Q@self.rv[i];ti.atomic_min(self.floor_gap[None],self.bp[None][2]+arm[2]-self.support(self.bp[None]+arm))
  for i in self.rv:
   arm=Q@self.rv[i]
   if self.bp[None][2]+arm[2]-self.support(self.bp[None]+arm)<=self.floor_gap[None]+1e-10:
    for j in ti.static(range(3)):ti.atomic_add(self.floor_arm[None][j],arm[j])
    ti.atomic_add(self.floor_count[None],1)
  if ti.static(self.present):
   for i in self.x:
    gravity=self.mass[i]*ti.Vector([0.,0.,-9.81]);self.f[i]=gravity
    self.external(self.x[i],gravity)
   for e in self.tet:
    ids=self.tet[e];Ds=ti.Matrix.cols([self.x[ids[1]]-self.x[ids[0]],self.x[ids[2]]-self.x[ids[0]],self.x[ids[3]]-self.x[ids[0]]]);F=Ds@self.inv[e];J=F.determinant();self.detf[e]=J
    ti.atomic_min(self.minJ[None],J)
    # Equilibrium Hencky spring: objective spatial Kirchhoff stress.
    U0,S0,V0=ti.svd(F,ti.f64)
    e0=ti.Vector([ti.log(ti.max(S0[0,0],1e-12)),ti.log(ti.max(S0[1,1],1e-12)),ti.log(ti.max(S0[2,2],1e-12))])
    tr0=e0.sum();dev0=e0-ti.Vector([tr0/3,tr0/3,tr0/3]);A0=ti.Matrix.zero(ti.f64,3,3)
    for j in ti.static(range(3)):A0[j,j]=2*self.mu*self.ginf*dev0[j]+self.bulk*tr0
    # Multiplicative Maxwell branch. At fixed F its deviatoric logarithmic
    # elastic strain decays exactly by exp(-dt/tau). The viscous metric stays
    # isochoric and unchanged by superposed rigid rotations.
    Fe=F@self.fvi[e];U,S,V=ti.svd(Fe,ti.f64)
    ev=ti.Vector([ti.log(ti.max(S[0,0],1e-12)),ti.log(ti.max(S[1,1],1e-12)),ti.log(ti.max(S[2,2],1e-12))])
    tr=ev.sum();trial=ev-ti.Vector([tr/3,tr/3,tr/3]);dev=self.decay*trial
    corr=ti.Matrix.zero(ti.f64,3,3);A1=ti.Matrix.zero(ti.f64,3,3)
    for j in ti.static(range(3)):
     corr[j,j]=ti.exp(dev[j]+tr/3);A1[j,j]=2*self.mu*(1-self.ginf)*dev[j]
    self.fvi[e]=F.inverse()@U@corr@V.transpose()
    self.ev[e]+=ti.sqrt(2./3.)*(trial-dev).norm()
    ti.atomic_add(self.relaxation_work[None],self.vol[e]*self.mu*(1-self.ginf)*(trial.dot(trial)-dev.dot(dev)))
    tau=U0@A0@U0.transpose()+U@A1@U.transpose();self.kirchhoff[e]=tau;FiT=F.inverse().transpose();P=tau@FiT
    dv=ti.Matrix.cols([self.v[ids[1]]-self.v[ids[0]],self.v[ids[2]]-self.v[ids[0]],self.v[ids[3]]-self.v[ids[0]]]);L=dv@self.inv[e]@F.inverse();D=(L+L.transpose())*.5;devD=D-ti.Matrix.identity(ti.f64,3)*D.trace()/3
    P+=2*self.eta*J*devD@FiT
    H=-self.vol[e]*P@self.inv[e].transpose()
    for j in ti.static(range(3)):
     for k in ti.static(range(3)):
      ti.atomic_add(self.f[ids[j+1]][k],H[k,j]);ti.atomic_add(self.f[ids[0]][k],-H[k,j])
    deviator=tau-ti.Matrix.identity(ti.f64,3)*tau.trace()/3
    self.stress[e]=ti.sqrt(1.5*(deviator@deviator).trace())
    ti.atomic_add(self.current_energy[None],self.vol[e]*(self.mu*self.ginf*dev0.dot(dev0)+self.mu*(1-self.ginf)*dev.dot(dev)+.5*self.bulk*tr0*tr0))
    ti.atomic_add(self.visc_work[None],self.dt*self.vol[e]*2*self.eta*J*(devD@devD).trace())
   for a in self.qa:
    ids=self.qids[a];w=self.qw[a];point=ti.Vector.zero(ti.f64,3);vel=ti.Vector.zero(ti.f64,3)
    for j in ti.static(range(3)):point+=w[j]*self.x[ids[j]];vel+=w[j]*self.v[ids[j]]
    force=ti.Vector.zero(ti.f64,3);area=self.qa[a]
    if point[2]<0.:
     elastic=-self.kt*area*point[2];normal=ti.max(0.,elastic-self.cn*area*vel[2]);ft=ti.Vector([-vel[0],-vel[1],0.]);speed=ft.norm();ft*=ti.min(self.mut*normal,self.ct*area*speed)/ti.max(speed,1e-20)
     tf=ft+ti.Vector([0.,0.,normal]);force+=tf;self.external(point,tf)
     for k in ti.static(range(3)):ti.atomic_add(self.table_force[None][k],tf[k])
     ti.atomic_max(self.max_table_pen[None],-point[2]);ti.atomic_add(self.contact_work[None],self.dt*(-ft.dot(vel)+(normal-elastic)*(-vel[2])))
    if use_ball==1:
     arm=point-self.bp[None];gap,nlocal=self.mesh_gap(Q.transpose()@arm);n=Q@nlocal;ti.atomic_min(self.instant_gap[None],gap)
     if gap<0.:
      rel=vel-self.bv[None]-self.bw[None].cross(arm);vn=rel.dot(n);vt=rel-vn*n
      elastic=-self.kn*area*gap;normal=ti.max(0.,elastic-self.cn*area*vn)
      ft=-vt*ti.min(self.mub*normal,self.ct*area*vt.norm())/ti.max(vt.norm(),1e-20);cf=normal*n+ft;force+=cf;torque=arm.cross(-cf)
      for k in ti.static(range(3)):
       ti.atomic_add(self.bf[None][k],-cf[k]);ti.atomic_add(self.bt[None][k],torque[k]);ti.atomic_add(self.cP[None][k],-cf[k]*self.dt);ti.atomic_add(self.cL[None][k],point.cross(-cf)[k]*self.dt)
      ti.atomic_max(self.max_pen[None],-gap);ti.atomic_add(self.contactN[None],normal)
      ti.atomic_add(self.contact_work[None],self.dt*(-ft.dot(rel)+(normal-elastic)*(-vn)))
    for j in ti.static(range(3)):
     for k in ti.static(range(3)):ti.atomic_add(self.f[ids[j]][k],w[j]*force[k])
  if use_ball==1:
   self.external(self.bp[None],ti.Vector([0.,0.,-9.81*self.M]))
   gap=self.floor_gap[None]
   if gap<0.:
    arm=self.floor_arm[None]/ti.max(self.floor_count[None],1);point=self.bp[None]+arm;vel=self.bv[None]+self.bw[None].cross(arm);elastic=-self.kbt*gap;fn=ti.max(0.,elastic-self.cbt*vel[2]);vt=ti.Vector([vel[0],vel[1],0.]);ft=-vt*ti.min(self.mubt*fn,self.ctbt*vt.norm())/ti.max(vt.norm(),1e-20);force=ti.Vector([0.,0.,fn])+ft
    self.bf[None]+=force;self.bt[None]+=arm.cross(force);self.external(point,force);ti.atomic_max(self.max_table_pen[None],-gap)
    # Dissipative rolling resistance of the wooden ball on the floured board.
    # A smooth viscous torque is bounded by N*b (rolling resistance length).
    # It acts only under compressive contact, and its external angular impulse
    # is included in the conservation ledger. No pose or velocity is prescribed.
    wt=ti.Vector([self.bw[None][0],self.bw[None][1],0.]);speed=wt.norm();rr=-wt*ti.min(self.rr*fn,self.crr*speed)/ti.max(speed,1e-20)
    self.bt[None]+=rr;self.extL[None]+=self.dt*rr;self.rolling_work[None]+=self.dt*(-rr.dot(wt))
   if self.contactN[None]>0. and self.first_contact[None]<0.:self.first_contact[None]=time
   self.peak_force[None]=ti.max(self.peak_force[None],self.contactN[None])
   self.bv[None]+=self.dt*self.bf[None]/self.M;self.bp[None]+=self.dt*self.bv[None];self.bl[None]+=self.dt*self.bt[None];self.bw[None]=Q@self.body_invI[None]@Q.transpose()@self.bl[None]
   w=self.bw[None];qq=self.bq[None];vec=ti.Vector([qq[1],qq[2],qq[3]]);dv=.5*(qq[0]*w+w.cross(vec));dq=ti.Vector([-.5*w.dot(vec),dv[0],dv[1],dv[2]])
   qq+=self.dt*dq;self.bq[None]=qq/qq.norm()
   Qnew=self.rotation();self.bw[None]=Qnew@self.body_invI[None]@Qnew.transpose()@self.bl[None]
  if ti.static(self.present):
   for i in self.x:self.v[i]+=self.dt*self.f[i]/self.mass[i];self.x[i]+=self.dt*self.v[i]

 def state(self):
  return self.x.to_numpy(),self.v.to_numpy(),np.array(self.bp[None]),np.array(self.bv[None]),np.array(self.bw[None]),np.array(self.bq[None])

def pose(pos,q):
 w,x,y,z=q;T=np.eye(4)
 T[:3,:3]=[[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
  [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],[2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]]
 T[:3,3]=pos;return T
