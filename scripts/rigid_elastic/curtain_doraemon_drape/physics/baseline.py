"""Shared baseline geometry and SI physical specification of every case. Does not import bpy.

The curtain is already released at the first frame and falls onto the figurine (the porcelain vase) standing
on a window-side desk; each edit changes only its DSL-bound parameter. The cup parameters describe an optional
rigid tumbler the solver and the renderer still support (cup_active stays 0 in every published case).
"""
from pathlib import Path
import hashlib, json, sys

CASE = 'curtain_doraemon_drape'
HERE = Path(__file__).resolve().parent
SCENE = HERE.parent
REPO = HERE.parents[3]
sys.path.insert(0, str(HERE.parents[2]))
from pcve_assets import asset

ASSETS = asset('scenes/curtain_doraemon_drape')
RUNTIME = REPO / '.runtime' / CASE
# The figurine body is a scanned porcelain vase (Poly Haven antique_ceramic_vase_01, CC0), prepared by
# tools/prepare_vase.py.
FIGURE_ASSET = ASSETS / 'porcelain_vase'
# Identifier of this baseline, written into every simulation_config.json and required by appearance/render.py.
BASELINE_REVISION = 'porcelain_vase'

PHYSICS = dict(cloth_young_modulus=2e6, cloth_density=360., cloth_thickness=.00025,
    cloth_friction=.55, cloth_poisson_ratio=.3, figure_mass=.75,
    figure_active=[1], cup_active=[0], cup_location=[.19,-.015,.0755],
    cup_radius=.042, cup_height=.15, cup_mass=.28,
    figure_location=[0.,0.,.0005], figure_radius=.111,
    gravity=[0.,0.,-9.81], air_density=1.225, air_drag_coefficient=1.15,
    cloth_deformation_damping_s_inv=8., air_linear_normal_kg_m2_s=.15,
    air_linear_tangent_kg_m2_s=.015, cloth_initial_velocity_m_s=[0.,0.,-.16])
LAYOUT = dict(cloth_width=.68, cloth_height=.50, cloth_bottom=.55,
    pleat_amplitude=.024, pleat_period=.113333333333, cloth_y=-.035,
    table_dimensions=[1.36,.83,.036], table_center=[-.06,-.055,-.018],
    notebook_location=[-.405,-.225,.002], pen_holder_location=[-.44,.055,.002],
    camera_location=[.88,-1.52,.96], camera_target=[-.025,.015,.405], camera_lens=41.)


def save(path, obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf8')

def sha(path): return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def curtain(pitch=.009):
    import numpy as np
    w,h=LAYOUT['cloth_width'],LAYOUT['cloth_height']
    nx,nz=round(w/pitch)+1,round(h/pitch)+1
    u,v=np.meshgrid(np.linspace(0,1,nx),np.linspace(0,1,nz),indexing='ij')
    x=w*(u-.5)
    # Vertical manufacturing pleats; a small smooth common asymmetry avoids a
    # perfectly symmetric unstable balance on the crown. No edited placement.
    y=LAYOUT['cloth_y']+LAYOUT['pleat_amplitude']*np.sin(2*np.pi*(u*6+.12))
    y+=.005*np.sin(2*np.pi*u)*v+.004*v
    z=LAYOUT['cloth_bottom']+h*v
    vertices=np.stack([x,y,z],axis=-1).reshape(-1,3);faces=[]
    for i in range(nx-1):
        for j in range(nz-1):
            a=i*nz+j;b=a+nz
            faces.extend([(a,b,b+1),(a,b+1,a+1)]if(i+j)%2 else[(a,b,a+1),(a+1,b,b+1)])
    return vertices,np.asarray(faces,np.int32),np.stack([u,v],axis=-1).reshape(-1,2)

def figure_mesh():
    """Watertight collision surface of the figurine (asset collision.npz, figurine-local metres)."""
    import numpy as np,trimesh
    z=np.load(FIGURE_ASSET/'collision.npz')
    m=trimesh.Trimesh(z['vertices'],z['faces'],process=False)
    assert m.is_watertight and m.volume>0
    return m

def cup_mesh():
    import numpy as np,trimesh
    n=64;r=PHYSICS['cup_radius'];h=PHYSICS['cup_height'];wall=.003
    theta=np.arange(n)*2*np.pi/n
    rings=[(r*.89,-h/2),(r,h/2),(r-wall,h/2),(r*.89-wall,-h/2+.006)]
    vs=np.concatenate([np.stack([rr*np.cos(theta),rr*np.sin(theta),np.full(n,z)],axis=1)for rr,z in rings])
    vs=np.concatenate([vs,[[0,0,-h/2],[0,0,-h/2+.006]]]);fs=[]
    for k in range(3):
        for i in range(n):
            j=(i+1)%n;a=k*n+i;b=k*n+j;c=(k+1)*n+j;d=(k+1)*n+i
            fs.extend([(a,b,c),(a,c,d)])
    for i in range(n):
        j=(i+1)%n;fs.extend([(4*n,j,i),(4*n+1,3*n+i,3*n+j)])
    m=trimesh.Trimesh(vs,np.asarray(fs,np.int32),process=True);m.fix_normals()
    assert m.is_watertight and m.volume>0
    return m
