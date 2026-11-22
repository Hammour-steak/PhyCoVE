"""Quasistatic ribbon surface frames on the authoritative physical centerlines.

Spatial Bishop transport and endpoint roll follow the material-frame construction
in Bergou et al. (2008). This reconstructs strip orientation; it is not a new
torsion-coupled rod solver. No rigid pose or band centerline is changed.
"""
import math
import numpy as np

def unit(v):
    return np.asarray(v,dtype=float)/max(float(np.linalg.norm(v)),1e-14)

def transport(w,a,b):
    axis=np.cross(a,b);c=float(np.clip(np.dot(a,b),-1,1));s2=float(np.dot(axis,axis))
    if s2>1e-16:
        w=w+np.cross(axis,w)+np.cross(axis,np.cross(axis,w))*(1-c)/s2
    elif c<0:
        # Deterministic 180-degree continuation about the old transverse axis.
        w=w.copy()
    return unit(w-np.dot(w,b)*b)

def rotation(q):
    x,y,z,w=q
    return np.array([[1-2*(y*y+z*z),2*(x*y-z*w),2*(x*z+y*w)],
      [2*(x*y+z*w),1-2*(x*x+z*z),2*(y*z-x*w)],
      [2*(x*z-y*w),2*(y*z+x*w),1-2*(x*x+y*y)]])

def reconstruct(centerlines,pouch_quaternions,config):
    centerlines=np.asarray(centerlines);nframes,nbands,n,_=centerlines.shape
    all_vertices=np.empty((nframes,nbands,n*4,3));directors=np.empty_like(centerlines)
    tangents=np.empty_like(centerlines);previous=[None]*nbands;previous_roll=[None]*nbands
    roll_history=np.zeros((nframes,nbands));attachment_axis_errors=[]
    for frame in range(nframes):
        desired=rotation(pouch_quaternions[frame])@np.array([0.,0.,1.])
        for band in range(nbands):
            center=centerlines[frame,band];edge=np.diff(center,axis=0);length=np.linalg.norm(edge,axis=1)
            edge_unit=edge/np.maximum(length[:,None],1e-14)
            t=np.vstack([edge_unit[0],np.array([unit(edge_unit[i-1]+edge_unit[i])for i in range(1,n-1)]),edge_unit[-1]])
            up=np.array([0.,0.,1.])-t[0,2]*t[0];up_norm=np.linalg.norm(up)
            if previous[band]is None:
                root=unit(up)if up_norm>.1 else unit(np.cross(t[0],[1.,0.,0.]))
            else:
                old_t,old_w=previous[band];continued=transport(old_w,old_t,t[0])
                if up_norm>.1:
                    up=unit(up)
                    if np.dot(up,continued)<0:up=-up
                    alpha=np.clip((up_norm-.1)/.25,0,1);root=unit((1-alpha)*continued+alpha*up)
                else:root=continued
            previous[band]=(t[0].copy(),root.copy())
            bishop=np.empty_like(center);bishop[0]=root
            for i in range(1,n):bishop[i]=transport(bishop[i-1],t[i-1],t[i])
            end=desired-np.dot(desired,t[-1])*t[-1]
            if np.linalg.norm(end)>.05:
                end=unit(end);roll=math.atan2(np.dot(t[-1],np.cross(bishop[-1],end)),np.dot(bishop[-1],end))
                if previous_roll[band]is not None:roll+=2*math.pi*round((previous_roll[band]-roll)/(2*math.pi))
            else:roll=previous_roll[band]if previous_roll[band]is not None else 0.
            previous_roll[band]=roll;roll_history[frame,band]=roll
            arc=np.r_[0,np.cumsum(length)];angle=roll*arc/max(arc[-1],1e-14)
            wide=np.cos(angle[:,None])*bishop+np.sin(angle[:,None])*np.cross(t,bishop)
            normal=np.cross(t,wide);directors[frame,band]=wide;tangents[frame,band]=t
            if np.linalg.norm(end)>.05:attachment_axis_errors.append(abs(float(np.dot(wide[-1],unit(end)))-1))
            station_length=np.r_[length[0],(length[:-1]+length[1:])/2,length[-1]]
            stretch=np.maximum(station_length/(config['band_rest_length_m']/(n-1)),1.)
            width=config['band_width_m']/np.sqrt(stretch);thickness=config['band_thickness_m']/np.sqrt(stretch)
            for k,(a,b)in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
                all_vertices[frame,band,k::4]=center+a*width[:,None]/2*wide+b*thickness[:,None]/2*normal
    assert np.isfinite(all_vertices).all()
    center_error=float(np.linalg.norm(all_vertices.reshape(nframes,nbands,n,4,3).mean(3)-centerlines,axis=3).max())
    return dict(vertices=all_vertices,directors=directors,tangents=tangents,roll_angle_rad=roll_history,
      maximum_centerline_reconstruction_error_m=center_error,
      maximum_pouch_axis_alignment_error=max(attachment_axis_errors,default=0.),
      model='Spatial parallel transport plus continuous quasistatic endpoint roll; physical centerlines and rigid poses unchanged')

def from_cache(cache,config,detail=False,main=False):
    prefix=''if main else('detail_'if detail else'slow_')
    center=cache[prefix+'bands'];wide=cache[prefix+'directors'];nframes,nbands,n,_=center.shape
    vertices=np.empty((nframes,nbands,n*4,3));tangents=np.empty_like(center)
    for f in range(nframes):
        for b in range(nbands):
            edge=np.diff(center[f,b],axis=0);length=np.linalg.norm(edge,axis=1);e=edge/np.maximum(length[:,None],1e-14)
            t=np.vstack([e[0],np.array([unit(e[i-1]+e[i])for i in range(1,n-1)]),e[-1]])
            tangents[f,b]=t;normal=np.cross(t,wide[f,b]);station=np.r_[length[0],(length[:-1]+length[1:])/2,length[-1]]
            stretch=np.maximum(station/(config['band_rest_length_m']/(n-1)),1.)
            w=config['band_width_m']/np.sqrt(stretch);h=config['band_thickness_m']/np.sqrt(stretch)
            for k,(a,c)in enumerate([(-1,-1),(1,-1),(1,1),(-1,1)]):
                vertices[f,b,k::4]=center[f,b]+a*w[:,None]/2*wide[f,b]+c*h[:,None]/2*normal
    names=list(cache['body_names']);pouch_q=cache[prefix+'states'][:,names.index('pouch'),3:]
    errors=[]
    for f,q in enumerate(pouch_q):
        desired=rotation(q)@np.array([0.,0.,1.])
        for b in range(nbands):
            t=tangents[f,b,-1];target=desired-np.dot(desired,t)*t
            if np.linalg.norm(target)>.05:errors.append(abs(abs(np.dot(unit(target),wide[f,b,-1]))-1))
    return dict(vertices=vertices,directors=wide,tangents=tangents,roll_angle_rad=cache[prefix+'roll_angle_rad'],
      maximum_centerline_reconstruction_error_m=float(np.linalg.norm(vertices.reshape(nframes,nbands,n,4,3).mean(3)-center,axis=3).max()),
      maximum_pouch_axis_alignment_error=max(errors,default=0.),
      model='Continuous material directors captured at physical integration steps and used for finite-width contacts; surface is replayed without interpolation or offsets')
