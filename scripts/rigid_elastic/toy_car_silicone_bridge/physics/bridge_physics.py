"""SI rigid car + finite-thickness elastic shell, solved together by MuJoCo."""
from __future__ import annotations
import copy
import hashlib
import json
from pathlib import Path

CASES = ('source', 'soft_bridge', 'stiff_bridge', 'heavy_car', 'delete_bridge')
# Cases outside the published catalog; the driver kept in the staged suite's inputs/edit_<case>/ solves them.
STAGED_CASES = ('delete_car',)

# Appearance inputs (camera, optics, materials, room, light) live in appearance/appearance.json;
# they are part of every solved configuration, so a change there is an appearance revision.
APPEARANCE = json.loads((Path(__file__).resolve().parents[1] / 'appearance/appearance.json').read_text())


def baseline():
    return {
        'schema_version': 1,
        'scene': 'toy_car_silicone_bridge', 'category': 'rigid_elastic',
        'physics': {
            'units': {'length':'m','mass':'kg','time':'s','up':'Z'},
            'gravity': [0,0,-9.81],
            'bridge': {'present':True, 'young_pa':900000., 'poisson':.47,
                       'density_kg_m3':1100., 'length_m':.32, 'free_span_m':.28,
                       'width_m':.12, 'thickness_m':.006, 'top_z_m':.065,
                       'rayleigh_damping_s':.02},
            'car': {'mass_kg':.15,'chassis_mass_fraction':.7647058823529411,
                    'length_m':.11,'width_m':.078,'wheelbase_m':.075,
                    'track_m':.068,'wheel_radius_m':.014,'wheel_width_m':.009,
                    'chassis_size_m':[.105,.052,.030], 'chassis_com_z_m':.014,
                    'start_x_m':-.29,'push_time_s':.25, 'initial_speed_m_s':.65,
                    'axle_frictionloss_Nm':.00009,'axle_damping_Nms':0.},
            'contact': {'friction':[.75,.002,.00001], 'timeconst_s':.0015,
                        'solimp':[.97,.999,.0001]},
            'road': {'left_extent_m':-.56,'right_extent_m':1.15,'width_m':.16,
                     'height_m':.065},
        },
        'simulation_quality': {'solver':'MuJoCo 3.17.0', 'integrator':'discrete',
            'timestep_s':1/4800, 'grid':[33,13], 'preroll_s':4.,
            'constraint_solver':'Newton','iterations':600,'tolerance':1e-8,'cone':'elliptic',
            'jacobian':'sparse','self_collision':False},
        'appearance': copy.deepcopy(APPEARANCE),
        'render': {'width':1280,'height':720,'fps':24,'frames':96,
            'duration_s':4.,'engine':'CYCLES','samples':256,'denoise':True,
            'denoiser':'OpenImageDenoise','color_management':'AgX','motion_blur':True,
            'motion_blur_shutter_frames':.25,'persistent_data':False},
    }

def config_for(case, base=None):
    if case not in CASES + STAGED_CASES: raise ValueError(case)
    cfg=copy.deepcopy(base or baseline())
    if case=='soft_bridge': cfg['physics']['bridge']['young_pa']/=3
    if case=='stiff_bridge': cfg['physics']['bridge']['young_pa']*=3
    if case=='heavy_car': cfg['physics']['car']['mass_kg']*=2
    if case=='delete_bridge': cfg['physics']['bridge']['present']=False
    # DELETE car: the published configurations carry no car presence key (absent means present).
    if case=='delete_car': cfg['physics']['car']['present']=False
    return cfg

def differences(a,b,path=''):
    if isinstance(a,dict) and isinstance(b,dict):
        out=[]
        for key in sorted(a.keys()|b.keys()):
            out+=differences(a.get(key),b.get(key),f'{path}.{key}' if path else key)
        return out
    return [] if a==b else [{'path':path,'before':a,'after':b}]

def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True).encode()).hexdigest()

def save_json(path, value):
    Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False)+'\n')

def car_properties(cfg):
    c=cfg['physics']['car']; m=c['mass_kg']*c['chassis_mass_fraction']
    l,w,h=c['chassis_size_m']; r=c['wheel_radius_m']; width=c['wheel_width_m']
    mw=(c['mass_kg']-m)/4
    return {'chassis_mass_kg':m, 'wheel_mass_kg':mw,
        'chassis_inertia_kg_m2':[m*(w*w+h*h)/12,m*(l*l+h*h)/12,m*(l*l+w*w)/12],
        'wheel_inertia_kg_m2':[mw*(3*r*r+width*width)/12,mw*r*r/2,mw*(3*r*r+width*width)/12]}

def model_xml(cfg, car=True):
    p=cfg['physics']; b=p['bridge']; c=p['car']; s=cfg['simulation_quality']; con=p['contact']
    friction=' '.join(map(str,con['friction'])); imp=' '.join(map(str,con['solimp']))
    fmt=lambda xs:' '.join(f'{v:.12g}' for v in xs)
    parts=[f'''<mujoco model="toy_car_silicone_bridge">
      <compiler angle="radian"/>
      <option timestep="{s['timestep_s']}" gravity="{fmt(p['gravity'])}" integrator="{s['integrator']}"
        solver="{s['constraint_solver']}" jacobian="sparse" cone="elliptic" iterations="{s['iterations']}" tolerance="{s['tolerance']}"/>
      <size memory="128M"/>
      <default><geom friction="{friction}" solref="{con['timeconst_s']} 1" solimp="{imp}"/>
        <joint damping="0"/></default><worldbody>
      <geom name="floor" type="plane" size="2 2 .01" rgba=".55 .42 .28 1"/>
    ''']
    road=p['road']; half=b['free_span_m']/2; z=road['height_m']
    for name,x1,x2 in [('left',road['left_extent_m'],-half),('right',half,road['right_extent_m'])]:
        parts.append(f'<geom name="road_{name}" type="box" pos="{(x1+x2)/2} 0 {z/2}" size="{(x2-x1)/2} {road["width_m"]/2} {z/2}" rgba=".75 .55 .32 1"/>')
    if b['present']:
        nx,ny=s['grid']; dx=b['length_m']/(nx-1); dy=b['width_m']/(ny-1)
        pinned=[i*ny+j for i in range(nx) for j in range(ny) if abs(-b['length_m']/2+i*dx)>=half-1e-8]
        mass=b['density_kg_m3']*b['length_m']*b['width_m']*b['thickness_m']
        parts.append(f'''<flexcomp name="silicone" type="grid" dim="2" count="{nx} {ny} 1"
            spacing="{dx} {dy} .01" pos="0 0 {b['top_z_m']-b['thickness_m']/2}" radius="{b['thickness_m']/2}" mass="{mass}">
          <contact condim="3" friction="{friction}" solref="{con['timeconst_s']} 1" solimp="{imp}" selfcollide="none"/>
          <elasticity young="{b['young_pa']}" poisson="{b['poisson']}" thickness="{b['thickness_m']}" elastic2d="both" damping="{b['rayleigh_damping_s']}"/>
          <pin id="{' '.join(map(str,pinned))}"/>
        </flexcomp>''')
    if car:
        cp=car_properties(cfg); axle_z=z+c['wheel_radius_m']+.0001
        parts.append(f'''<body name="chassis" pos="{c['start_x_m']} 0 {axle_z}"><freejoint name="car_free"/>
          <inertial mass="{cp['chassis_mass_kg']}" pos="0 0 {c['chassis_com_z_m']}" diaginertia="{fmt(cp['chassis_inertia_kg_m2'])}"/>
          <geom name="chassis_base" type="box" pos="0 0 .012" size=".0525 .026 .009" rgba=".9 .32 .08 1"/>
          <geom name="chassis_roof" type="box" pos="-.008 0 .031" size=".026 .024 .010" rgba=".9 .32 .08 1"/>''')
        for i,(x,y) in enumerate([(x,y) for x in [-c['wheelbase_m']/2,c['wheelbase_m']/2] for y in [-c['track_m']/2,c['track_m']/2]]):
            parts.append(f'''<body name="wheel_{i}" pos="{x} {y} 0">
              <joint name="axle_{i}" type="hinge" axis="0 1 0" damping="{c['axle_damping_Nms']}" frictionloss="{c['axle_frictionloss_Nm']}"/>
              <inertial mass="{cp['wheel_mass_kg']}" pos="0 0 0" diaginertia="{fmt(cp['wheel_inertia_kg_m2'])}"/>
              <geom name="tire_{i}" type="cylinder" size="{c['wheel_radius_m']} {c['wheel_width_m']/2}" quat=".707106781187 .707106781187 0 0" rgba=".045 .045 .05 1"/>
            </body>''')
        parts.append('</body>')
    parts.append('</worldbody></mujoco>')
    return '\n'.join(parts)
