"""Instrumented, guided spring balance: baseline parameters (SI units), derived spring constants and data locations.

DATA and DELIVERY name the accepted native delivery (its frozen data id is steel_ball_silicone_cup);
OUT is where the solver writes and the renderer reads cases/<case>/ (PCVE_SPRING_SCALE_INPUT overrides it);
WORK holds solver work files such as the Numba cache, outside scripts/.
"""
from pathlib import Path
import hashlib, json, math, os
from pcve_assets import asset

HERE=Path(__file__).resolve().parents[1]
REPO=HERE.parents[2]
DATA=REPO/'renders/spring_scale_weight_drop'
DELIVERY=DATA/'delivery/accepted'
OUT=Path(os.environ.get('PCVE_SPRING_SCALE_INPUT', str(DELIVERY)))
WORK=REPO/'renders/spring_scale_weight_drop/work'
ASSET_DIR=asset('scenes/spring_scale_weight_drop')
BASELINE={
 'gravity_m_s2':9.81,
 'weight_mass_kg':.100,
 'weight_present':True,
 'spring_young_modulus_pa':200e9,
 'spring_poisson_ratio':.30,
 'spring_wire_diameter_m':.0011,
 'spring_mean_diameter_m':.035,
 'spring_active_turns':28,
 'spring_density_kg_m3':7850.,
 'spring_initial_tension_n':0.,
 'closed_turn_contact_stiffness_n_m':50000.,
 'spring_internal_segment_damping_ns_m':.40,
 'carriage_mass_kg':.065,
 'guide_damping_ns_m':.30,
 'pad_contact_stiffness_n_m':12000.,
 'pad_compression_damping_ns_m':22.,
 'pan_pad_top_z_m':.550,
 'weight_initial_bottom_z_m':.635,
 'coil_top_z_m':.845,
 'lower_hook_length_m':.025,
 'crosshead_height_m':.014,
 'crosshead_to_pan_m':.237,
 'pan_radius_m':.072,
 'pan_wall_height_m':.015,
 'stop_present':False,
 'stop_travel_m':.080,
 'stop_contact_stiffness_n_m':30000.,
 'stop_compression_damping_ns_m':35.,
 'stop_center_m':[.100,0.,.686309696678137],
 'stop_dimensions_m':[.025,.032,.018],
}

def spring_constants(p):
 G=p['spring_young_modulus_pa']/(2*(1+p['spring_poisson_ratio']))
 d=p['spring_wire_diameter_m'];D=p['spring_mean_diameter_m'];N=p['spring_active_turns']
 length=N*math.hypot(math.pi*D,d)
 return {'shear_modulus_pa':G,'axial_rate_n_m':G*d**4/(8*D**3*N),
         'active_wire_length_m':length,'active_spring_mass_kg':length*math.pi*d*d/4*p['spring_density_kg_m3']}

# Placement of the travel-stop collar (stop_present is False in every case) and the crosshead-to-pan
# distance, both derived from the common initial geometry; they are solver inputs of every case.
_n=BASELINE['spring_active_turns'];_ms=spring_constants(BASELINE)['active_spring_mass_kg']
_rate=spring_constants(BASELINE)['axial_rate_n_m']*_n
_preload_sum=0.
for _i in range(1,_n+1):
 _force=(BASELINE['carriage_mass_kg']+_ms*(_n-_i+.5)/_n)*BASELINE['gravity_m_s2']
 _preload_sum+=(_force-BASELINE['spring_initial_tension_n'])/(_rate if _force>=BASELINE['spring_initial_tension_n'] else BASELINE['closed_turn_contact_stiffness_n_m'])
BASELINE['stop_center_m'][2]=BASELINE['coil_top_z_m']-_n*BASELINE['spring_wire_diameter_m']-_preload_sum-BASELINE['lower_hook_length_m']-BASELINE['crosshead_height_m']-BASELINE['stop_travel_m']-BASELINE['stop_dimensions_m'][2]/2
BASELINE['crosshead_to_pan_m']=BASELINE['coil_top_z_m']-_n*BASELINE['spring_wire_diameter_m']-_preload_sum-BASELINE['lower_hook_length_m']-BASELINE['crosshead_height_m']/2-BASELINE['pan_pad_top_z_m']

def write_spec(folder=None):
 spec={'scene_id':'steel_ball_silicone_cup','case_number':18,'revision':'guided_spring_balance',
 'title_zh':'砝码落入托盘，拉伸弹簧秤',
 'contract':{'width':1280,'height':720,'fps':24,'frames':96,'duration_s':4.},
 'baseline':BASELINE,'derived_baseline':spring_constants(BASELINE),
 'model':'Distributed, massive helical extension spring reduced to 28 axial turn segments; guided rigid carriage and freely falling rigid mass; passive unilateral contacts.',
 'limitations':['Axial symmetry and a visible mechanical guide constrain lateral motion and rotation.',
 'Coil stiffness uses small-helix-angle elastic torsion theory; this is not a full 3D wire FEM or a measured commercial instrument.',
 'Contact pad and viscous losses are declared effective mechanical parameters, not measured material calibration.'],
 'initial_pose_policy':'All existing geometry and initial states identical across the six cases. The baseline pan self-weight pre-extends the low-initial-tension spring. The E edit naturally releases an initially unbalanced material at the same pose; no per-edit retaring or position adjustment.'}
 if folder is not None:
  folder=Path(folder);folder.mkdir(parents=True,exist_ok=True)
  (folder/'scene_spec.json').write_text(json.dumps(spec,ensure_ascii=False,indent=2),encoding='utf-8')
 return spec

def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

if __name__=='__main__':print(json.dumps(write_spec(),ensure_ascii=False,indent=2))
