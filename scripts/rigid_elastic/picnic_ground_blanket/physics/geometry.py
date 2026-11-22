"""Physical geometry in metres. Surface relief belongs to the solver mesh."""
import numpy as np
import trimesh
from pathlib import Path
from pcve_assets import asset
from pcve_fem_geometry import grid_tets,exterior_faces,round_xy,vertex_masses,grass_volume,support_height


def medicine_ball():
    source=asset('scenes/gym_landing_mat/rigid_geometry.npz')
    z=np.load(source);mesh=trimesh.Trimesh(z['vertices'],z['faces'],process=False)
    mesh.merge_vertices()
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:raise ValueError('Invalid closed medicine ball contact mesh')
    return mesh

def mat_volume(p,q):
    w,h,d=p['solid_dimensions'];nx,ny,nz=q['solid_grid']
    # Smoothly grade the centre towards the impact area, keeping the boundary metric.
    def axis(n,half):
        a=np.linspace(-1,1,n);return half*np.sign(a)*abs(a)**1.30
    x,y,u=np.meshgrid(axis(nx,w/2),axis(ny,h/2),np.linspace(0,1,nz),indexing='ij')
    xy=round_xy(x,y,w/2,h/2,p['corner_radius']);x,y=xy[...,0],xy[...,1]
    edge=np.minimum(w/2-abs(x),h/2-abs(y));fade=np.clip(edge/.06,0,1);fade=fade*fade*(3-2*fade)
    top=d-.008*(1-fade)+.0035*(1-(2*x/w)**2)*(1-(2*y/h)**2)
    # Gentle manufactured wrinkles, not periodic pillow quilting.
    top+=.0035*np.sin(30*x+2*y)*np.exp(-((y+h*.40)/.055)**2)*fade
    top+=.0025*np.cos(34*y+3*x)*np.exp(-((x-w*.40)/.065)**2)*fade
    # Manufactured corner puckering is part of the stress-free physical shape.
    # These millimetre-scale ridges belong to both the FEM and contact surface.
    top+=.0025*np.sin(72*x+6*y)*np.exp(-((y+h*.38)/.045)**2)*fade
    top+=.0020*np.sin(64*y-4*x)*np.exp(-((x-w*.39)/.050)**2)*fade
    top+=.0015*np.sin(60*x+45*y)*np.exp(-((x+w*.39)/.11)**2-((y+h*.36)/.080)**2)*fade
    inset=.0035+.0045*np.cos(np.pi*u)**2
    v=np.stack([x*(1-inset/(w/2)),y*(1-inset/(h/2)),.002+u*(top-.002)],axis=-1).reshape(-1,3)
    t=grid_tets(v,(nx,ny,nz));f=exterior_faces(t)
    shellmesh=trimesh.Trimesh(v,f,process=False);shellmesh.fix_normals()
    ids=np.unique(f);lookup=np.full(len(v),-1,np.int32);lookup[ids]=np.arange(len(ids))
    # Separate sealed fabric envelope. No fixed FEM vertices or animated constraints.
    # Clear the lateral manufacturing ease over the steeper corner puckering.
    # This is only an initial bag clearance; gravity prepares the actual fit.
    offset=.00115+.00335*np.clip(v[ids,2]/.10,0,1)
    cv=v[ids]+np.asarray(shellmesh.vertex_normals)[ids]*offset[:,None]
    cv[:,:2]*=1.008
    return v,t,cv,lookup[np.asarray(shellmesh.faces)],ids

def napkin(p):
    w,h=p['cloth_dimensions'];nx=round(w/p['cloth_pitch'])+1;ny=round(h/p['cloth_pitch'])+1
    x,y=np.meshgrid(np.linspace(-w/2,w/2,nx),np.linspace(-h/2,h/2,ny),indexing='ij')
    v=np.stack([x,y,np.full_like(x,p['cloth_height'])],axis=-1).reshape(-1,3)
    f=[]
    for i in range(nx-1):
        for j in range(ny-1):
            a=i*ny+j
            f.extend([(a,a+ny,a+1),(a+1,a+ny,a+ny+1)] if (i+j)%2 else [(a,a+ny,a+ny+1),(a,a+ny+1,a+1)])
    return v,np.asarray(f,np.int32)

def mandarin():
    source=asset('scenes/picnic_ground_blanket/mandarin_geometry.npz')
    z=np.load(source);mesh=trimesh.Trimesh(z['vertices'],z['faces'],process=False)
    mesh.merge_vertices()
    if not mesh.is_watertight or not mesh.is_winding_consistent or mesh.volume<=0:raise ValueError('The orange scan is not a valid closed rigid body')
    return mesh

def path_obstacle(scene_id,p):
    """Closed, origin-centred collision mesh for the dynamic ADD prop."""
    def lathe(profile,sections=64):
        rings=[]
        for radius,z in profile:
            rings.append([[radius*np.cos(2*np.pi*j/sections),radius*np.sin(2*np.pi*j/sections),z] for j in range(sections)])
        vertices=np.asarray(rings,float).reshape(-1,3).tolist()
        bottom=len(vertices);vertices.append([0.,0.,profile[0][1]])
        top=len(vertices);vertices.append([0.,0.,profile[-1][1]])
        faces=[]
        for k in range(len(profile)-1):
            for j in range(sections):
                a=k*sections+j;b=k*sections+(j+1)%sections
                c=(k+1)*sections+(j+1)%sections;d=(k+1)*sections+j
                faces.extend([(a,b,c),(a,c,d)])
        for j in range(sections):
            faces.append((bottom,(j+1)%sections,j))
            a=(len(profile)-1)*sections+j;b=(len(profile)-1)*sections+(j+1)%sections
            faces.append((top,a,b))
        return trimesh.Trimesh(np.asarray(vertices),np.asarray(faces,np.int32),process=True)
    if scene_id=='gym_landing_mat':
        r=p['gym_water_bottle_radius'];h=p['gym_water_bottle_length']/2
        profile=[(r*.88,-h),(r,-h+.006),(r*.96,-h+.014),(r,-h+.023),(r*.97,-.030),(r,.0),(r*.97,.030),(r,h-.030),(r*.82,h-.020),(r*.67,h-.013),(r*.70,h-.006),(r*.70,h)]
        mesh=lathe(profile)
    else:
        # Native collision uses the robust closed cylinder topology.  The
        # render adds manufactured edge rounding and a ceramic microfinish.
        mesh=trimesh.creation.cylinder(radius=p['picnic_cup_radius'],height=p['picnic_cup_height'],sections=32)
    mesh.fix_normals()
    if not mesh.is_watertight or mesh.volume<=0:raise ValueError('Path obstacle is not a closed contact mesh')
    return mesh
