"""Material geometry; manufacturing-scale relief is in the physics mesh."""
import numpy as np
import trimesh


def grid_tets(v,shape):
    nx,ny,nz=shape;cells=[]
    for i in range(nx-1):
        for j in range(ny-1):
            for k in range(nz-1):
                a=(i*ny+j)*nz+k;b=a+ny*nz;c=b+nz;d=a+nz
                e=a+1;f=b+1;g=c+1;h=d+1
                cells.extend([(a,b,c,g),(a,c,d,g),(a,d,h,g),(a,h,e,g),(a,e,f,g),(a,f,b,g)])
    t=np.asarray(cells,np.int32)
    delta=np.stack([v[t[:,k]]-v[t[:,0]] for k in [1,2,3]],axis=-1)
    d=np.linalg.det(delta);bad=d<0
    t[bad,0],t[bad,1]=t[bad,1].copy(),t[bad,0].copy()
    if abs(d).min()<1e-14:raise ValueError('Degenerate input tetrahedra')
    return t


def exterior_faces(t):
    f=np.concatenate([t[:,[1,2,3]],t[:,[0,3,2]],t[:,[0,1,3]],t[:,[0,2,1]]])
    _,first,count=np.unique(np.sort(f,axis=1),axis=0,return_index=True,return_counts=True)
    return f[first[count==1]]


def round_xy(x,y,hx,hy,r):
    q=np.stack([x,y],axis=-1);core=np.array([hx-r,hy-r])
    closest=np.clip(q,-core,core);d=q-closest;length=np.linalg.norm(d,axis=-1)
    scale=np.minimum(1,r/np.maximum(length,1e-12))
    return closest+d*scale[...,None]


def quilted_volume(p,q):
    dims=p['solid_dimensions'];nx,ny,nz=q['solid_grid']
    x,y,u=np.meshgrid(np.linspace(-dims[0]/2,dims[0]/2,nx),np.linspace(-dims[1]/2,dims[1]/2,ny),
        np.linspace(0,1,nz),indexing='ij')
    xy=round_xy(x,y,dims[0]/2,dims[1]/2,p['corner_radius']);x,y=xy[...,0],xy[...,1]
    edge=np.minimum(dims[0]/2-abs(x),dims[1]/2-abs(y))
    fade=np.clip(edge/.05,0,1);fade=fade*fade*(3-2*fade)
    # Actual sewn valleys and puffed textile bays, not a shader displacement.
    quilt=np.sin(np.pi*(x+dims[0]/2)/.2333333333)**2*np.sin(np.pi*(y+dims[1]/2)/.2125)**2
    dome=.008*(1-(2*x/dims[0])**2)*(1-(2*y/dims[1])**2)
    top=dims[2]-.018*(1-fade)+p['quilt_height']*quilt*fade+dome
    top+=.0013*np.sin(7*x+1.1)*np.cos(9*y-.4)*fade
    z=.001+u*(top-.001)
    # A stitched soft envelope has gently convex sides instead of vertical box walls.
    edge_inset=.004+.009*np.cos(np.pi*u)**2
    x=x*(1-edge_inset/(dims[0]/2));y=y*(1-edge_inset/(dims[1]/2))
    v=np.stack([x,y,z],axis=-1).reshape(-1,3);t=grid_tets(v,(nx,ny,nz))
    return v,t,np.arange(nx*ny)*nz+(nz-1)


def support_height(p,x,y):
    return p['foundation_height']+.006*np.sin(8*x+.9)*np.cos(11*y-.7)+.0025*np.sin(17*x+6*y)+p.get('foundation_roughness_amplitude',0.)*(np.sin(34*x+.5)*np.cos(29*y-.4)+.43*np.sin(61*x+33*y))


def grass_volume(p):
    w,h=p['cloth_dimensions'];pitch=p['foundation_pitch']
    nx=round((w+.18)/pitch)+1;ny=round((h+.18)/pitch)+1;nz=p.get('foundation_layers',3)
    x,y,u=np.meshgrid(np.linspace(-w/2-.09,w/2+.09,nx),np.linspace(-h/2-.09,h/2+.09,ny),np.linspace(0,1,nz),indexing='ij')
    top=support_height(p,x,y)
    z=.0005+u*(top-.0005)
    v=np.stack([x,y,z],axis=-1).reshape(-1,3);t=grid_tets(v,(nx,ny,nz))
    return v,t,np.arange(nx*ny)*nz+nz-1


def cloth_surface(p):
    w,h=p['cloth_dimensions'];nx=round(w/p['cloth_pitch'])+1;ny=round(h/p['cloth_pitch'])+1
    x,y=np.meshgrid(np.linspace(-w/2,w/2,nx),np.linspace(-h/2,h/2,ny),indexing='ij')
    # A curved, stress-free metric has extra cloth length available to form a basin.
    ax=np.sqrt(4*p['cloth_slack'])/12;ay=np.sqrt(4*p['cloth_slack'])/15
    z=p['foundation_height']+.013+ax+ay+ax*np.sin(12*x+2*y)+ay*np.cos(15*y-3*x)
    z+=.003*np.sin(np.pi*(x/w+.5))*np.sin(np.pi*(y/h+.5))
    v=np.stack([x,y,z],axis=-1).reshape(-1,3)
    f=[]
    for i in range(nx-1):
        for j in range(ny-1):
            a=i*ny+j
            if (i+j)%2:f.extend([(a,a+ny,a+1),(a+1,a+ny,a+ny+1)])
            else:f.extend([(a,a+ny,a+ny+1),(a,a+ny+1,a+1)])
    return v,np.asarray(f,np.int32)


def kettlebell():
    # Union gives a single watertight contact surface matching the render, including the handle opening.
    body=trimesh.creation.icosphere(subdivisions=3,radius=.067)
    xyz=np.asarray(body.vertices).copy();xyz[:,:2]*=(1+.10*xyz[:,2:3]/.067);xyz[:,2]=np.maximum(xyz[:,2],-.056)
    body.vertices=xyz
    handle=trimesh.creation.torus(major_radius=.049,minor_radius=.010,major_sections=40,minor_sections=12)
    handle.apply_transform(trimesh.transformations.rotation_matrix(np.pi/2,[1,0,0]));handle.apply_translation([0,0,.071])
    combined=trimesh.boolean.union([body,handle],engine='manifold')
    if not combined.is_watertight or combined.volume<=0:raise ValueError('Invalid cast-iron geometry')
    return combined


def vertex_masses(v,t,rho):
    volume=abs(np.linalg.det(np.stack([v[t[:,k]]-v[t[:,0]] for k in [1,2,3]],axis=-1)))/6
    m=np.zeros(len(v))
    for k in range(4):np.add.at(m,t[:,k],rho*volume/4)
    return m,volume
