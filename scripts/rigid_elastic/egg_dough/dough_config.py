"""Scene-owned SI inputs: a free, cohesive viscoelastic solid, no fluid."""
from pathlib import Path
import copy,hashlib,json,subprocess
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender, scene_asset
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
ASSETS=scene_asset(HERE, 'assets')
LOOK_FILE=HERE/'appearance/appearance.json'
# Benchmark cases: the source and its four edits (scene-native IDs; the video suite
# publishes them as source, edit_soft_dough_e5, edit_light_egg, edit_heavy_egg, edit_delete_egg).
CASES=('source','soft_dough_e5','light_ball','heavy_ball','delete_egg')
SPEC={
 'scene':'egg_dough','category':'rigid_elastic',
 'units':{'length':'m','mass':'kg','time':'s','stress':'Pa','up':'Z'},
 'physics':{
  'gravity_m_s2':[0.,0.,-9.81],
  'dough':{'present':True,'E_Pa':6000.,'nu':.49,'density_kg_m3':1100.,
   'geometry_xy_scale':1.,'geometry_profile':'domed_pad','equilibrium_shear_fraction':.15,'relaxation_time_s':.006,'shear_viscosity_Pa_s':12.,
   'law':'Finite-strain Hencky standard-linear-solid; multiplicative isochoric Maxwell branch, parallel equilibrium shear spring and elastic bulk',
   'parameter_status':'Phenomenological freshly kneaded unproofed flour-water dough; not a measured recipe fit; no fermentation, fracture, adhesion or fluid'},
  'ball':{'radius_m':.03,'mass_kg':.065,'initial_position_m':[.002,.001,.1855],
   'initial_velocity_m_s':[0.,0.,0.],'initial_angular_velocity_rad_s':[0.,0.,0.]},
  'contact':{'ball_dough_friction':.40,'dough_table_friction':.45,'ball_table_friction':.30,
   'ball_dough_penalty_Pa_per_m':5.e8,'dough_table_penalty_Pa_per_m':2.e9,
   'normal_damping_Pa_s_per_m':20000.,'tangent_damping_Pa_s_per_m':100000.,
   'ball_table_stiffness_N_m':1000000.,'ball_table_damping_N_s_m':160.,
   'ball_table_tangent_damping_N_s_m':80.,'ball_table_rolling_resistance_m':.00035,'ball_table_rolling_damping_N_m_s':.00008,'adhesion':False}},
 'simulation_quality':{'fps':24,'frames':96,'steps_per_frame':2048,'dt_s':1/(24*2048),
  'precision':'f64','integrator':'symplectic Euler','contact_quadrature':'3 reference-area Gauss points per boundary triangle',
  'mesh_spacing_m':.0048,'vertical_layers':7,'settle_min_s':1.,'settle_max_s':4.,
  'settle_max_speed_m_s':.0003},
 'render':{'resolution':[1280,720],'fps':24,'frames':96,'duration_s':4.,'engine':'CYCLES',
  'samples':64,'denoise':True,'motion_blur':False,'color_management':'AgX','video_crf':17},
}
# presets.json holds the single named preset recorded in every accepted configuration
# (its values are the SPEC above); the name is kept so recorded states can be reused and validated.
def preset_names():return tuple(json.loads((HERE/'presets.json').read_text())['presets'])

def config(case,preset=None):
 c=copy.deepcopy(SPEC)
 c['appearance']=json.loads(LOOK_FILE.read_text())
 profiles=json.loads((HERE/'presets.json').read_text());preset=preset or profiles['default'];c['preset']=preset
 for key,value in profiles['presets'][preset]['overrides'].items():
  fields=key.split('.');target=c
  for field in fields[:-1]:target=target[field]
  target[fields[-1]]=copy.deepcopy(value)
 if case=='soft_dough_e5':c['physics']['dough']['E_Pa']/=5
 elif case=='light_ball':c['physics']['ball']['mass_kg']/=2
 elif case=='heavy_ball':c['physics']['ball']['mass_kg']*=2
 elif case=='delete_egg':c['physics']['ball']['present']=False
 elif case!='source':raise ValueError(case)
 import math
 b=c['physics']['ball'];meta=json.loads((ASSETS/'rigid_egg/asset_manifest.json').read_text())
 b['object_type']='whole_intact_brown_egg';b['shape']='mesh_signed_distance';b['radius_m']=meta['bounding_radius_m']
 b['dimensions_m']=meta['source_dimensions_after_uniform_scale_m'];b['effective_density_kg_m3']=b['mass_kg']/meta['homogeneous_effective_volume_m3']
 b['rigid_geometry_asset']='assets/rigid_egg/rigid_geometry.npz';b['rigid_geometry_sha256']=digest(scene_asset(HERE,b['rigid_geometry_asset']))
 b['mass_distribution']='Effective homogeneous intact rigid egg, no internal contents dynamics or shell fracture'
 b['inertia_kg_m2']=[[b['mass_kg']*x for x in row] for row in meta['inertia_per_mass_m2']]
 axis=[.48,.83,.28];norm=sum(x*x for x in axis)**.5;theta=math.radians(32)
 b['initial_rotation_quaternion_wxyz']=[math.cos(theta/2)]+[math.sin(theta/2)*x/norm for x in axis]

 return c
def asset_directory(c):
 assert c['physics']['dough']['geometry_profile']=='domed_pad' and c['physics']['dough']['geometry_xy_scale']==1.
 return ASSETS

def write_json(p,v):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 p.write_text(json.dumps(v,indent=2,ensure_ascii=False)+'\n')
def digest(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def choose_gpu(value='auto'):
 if value!='auto':return str(value)
 rows=subprocess.check_output(['nvidia-smi','--query-gpu=index,utilization.gpu,memory.free','--format=csv,noheader,nounits'],text=True)
 idle=[tuple(map(int,r.split(','))) for r in rows.splitlines()]
 idle=[r for r in idle if r[1]<10 and r[2]>8000]
 if not idle:raise RuntimeError('No idle GPU with 8 GB free')
 return str(sorted(idle,key=lambda r:(r[1],-r[2]))[0][0])
def blender_path():return str(blender())
