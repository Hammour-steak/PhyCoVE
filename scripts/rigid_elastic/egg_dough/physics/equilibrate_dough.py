"""Force-balanced, fully relaxed gravity initial state for a cohesive SLS solid.

Minimizes the equilibrium Hencky energy plus the identical unilateral floor
penalty and gravity potential. It prepares both geometry and Maxwell metric;
the released simulation then continues without fixed nodes or projections.
"""
import time
import numpy as np
from scipy.optimize import minimize,root

def equilibrate(solid,c,d):
    started=time.monotonic();rest=d['rest_vertices'];tet=d['tetrahedra'];inv=d['inverse_dm'];vol=d['volumes']
    qids=d['quadrature_nodes'];qw=d['quadrature_weights'];qa=d['quadrature_area'];mass=solid.mass.to_numpy()
    mu=solid.mu*solid.ginf;bulk=solid.bulk;kn=solid.kt;gravity=9.81
    gn=np.concatenate((-inv.sum(axis=1)[:,None,:],inv),axis=1)
    diagonal=np.zeros_like(rest)
    for j in range(4):np.add.at(diagonal,tet[:,j],(vol*(2*mu+bulk)*(gn[:,j]**2).sum(1))[:,None]*np.ones((1,3)))
    contact=(rest[qids]*qw[:,:,None]).sum(1)[:,2]<1e-10
    for j in range(3):np.add.at(diagonal[:,2],qids[contact,j],kn*qa[contact]*qw[contact,j]**2)
    scale=1/np.sqrt(np.maximum(diagonal,1e-8));last={};calls=0
    def energy(y):
        nonlocal calls
        x=rest+y.reshape(rest.shape)*scale
        ds=np.stack([x[tet[:,j]]-x[tet[:,0]] for j in (1,2,3)],axis=-1);F=ds@inv;J=np.linalg.det(F)
        if J.min()<=0:return 1e12+float(np.linalg.norm(y)**2),2*y
        U,s,Vh=np.linalg.svd(F);e=np.log(s);tr=e.sum(1);dev=e-tr[:,None]/3
        tau=2*mu*dev+bulk*tr[:,None];P=(U*(tau/s)[:,None,:])@Vh
        G=vol[:,None,None]*(P@inv.transpose(0,2,1));gradient=np.zeros_like(rest)
        for j in range(3):np.add.at(gradient,tet[:,j+1],G[:,:,j])
        np.add.at(gradient,tet[:,0],-G.sum(2));gradient[:,2]+=mass*gravity
        points=(x[qids]*qw[:,:,None]).sum(1);gap=np.minimum(points[:,2],0.)
        for j in range(3):np.add.at(gradient[:,2],qids[:,j],kn*qa*gap*qw[:,j])
        val=float(np.sum(vol*(mu*(dev*dev).sum(1)+.5*bulk*tr*tr))+np.sum(mass*gravity*x[:,2])+.5*kn*np.sum(qa*gap*gap))
        last.update(x=x,F=F,U=U,s=s,Vh=Vh,gradient=gradient,energy=val,J=J)
        calls+=1
        return val,(gradient*scale).ravel()
    result=minimize(energy,np.zeros(rest.size),jac=True,method='L-BFGS-B',options={'maxiter':2500,'maxls':40,'ftol':1e-15,'gtol':2e-11,'maxcor':30})
    refined=root(lambda y:energy(y)[1],result.x,method='krylov',options={'maxiter':12,'fatol':1e-11})
    energy(refined.x)
    x=last['x'];gradient=last['gradient'];acceleration=np.linalg.norm(gradient/mass[:,None],axis=1)
    max_acceleration=float(acceleration.max());net=float(np.linalg.norm(gradient.sum(0)))
    # Keep the existing first pass and acceptance tolerances. Very soft
    # candidates may need extra Krylov iterations to reach the same equilibrium.
    # This fallback does not affect cases that already pass the original solve.
    refinement_extra_iterations=0
    for extra_budget in (24,48):
        if max_acceleration<=.01 and net<=1e-5:break
        refined=root(lambda y:energy(y)[1],refined.x,method='krylov',options={'maxiter':extra_budget,'fatol':1e-11})
        refinement_extra_iterations+=int(refined.nit)
        energy(refined.x)
        x=last['x'];gradient=last['gradient'];acceleration=np.linalg.norm(gradient/mass[:,None],axis=1)
        max_acceleration=float(acceleration.max());net=float(np.linalg.norm(gradient.sum(0)))
    if max_acceleration>.01 or net>1e-5:raise RuntimeError(('Static equilibrium force residual too large',max_acceleration,net,str(result.message)))
    # Fv^-1 = V diag(J^(1/3)/s_i) V^T, so Fe is a pure dilation/rotation
    # and the Maxwell shear stress is fully relaxed. det(Fv)=1.
    V=last['Vh'].transpose(0,2,1);Jthird=np.exp(np.log(last['s']).mean(1))
    fvi=(V*(Jthird[:,None]/last['s'])[:,None,:])@last['Vh']
    solid.x.from_numpy(x);solid.v.fill(0);solid.fvi.from_numpy(fvi)
    magnitude=np.sqrt(2/3)*np.linalg.norm(np.log(np.linalg.svd(fvi,compute_uv=False)),axis=1)
    solid.ev.from_numpy(magnitude)
    return {'method':'fully_relaxed_static_force_balance','maximum_force_residual_N':float(np.linalg.norm(gradient,axis=1).max()),
      'maximum_residual_acceleration_m_s2':max_acceleration,'net_force_residual_N':net,
      'minimum_detF_initial':float(last['J'].min()),'force_refinement_extra_iterations':refinement_extra_iterations,'optimizer_iterations':int(result.nit),'energy_evaluations':calls,
      'optimizer_message':str(result.message),'force_refinement_message':str(refined.message),'static_wall_seconds':time.monotonic()-started,
      'maxwell_metric_isochoric_error':float(np.abs(np.linalg.det(fvi)-1).max()),
      'initial_history':'Fully relaxed Maxwell shear metric under gravity; nonzero equilibrium spring stress. No constraints retained during dynamics.'}
