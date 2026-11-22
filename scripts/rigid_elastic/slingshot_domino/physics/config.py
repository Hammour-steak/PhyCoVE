from pathlib import Path
import json

CASE_ID='slingshot_domino'
CAT=next(p for p in Path(__file__).resolve().parents if p.name=='rigid_elastic')
DATA=CAT.parents[1]/'renders'/CASE_ID
BASE={
 'young_modulus_pa':1000000.0,'rubber_density_kg_m3':960.0,'rubber_viscosity_pa_s':160.0,
 'band_rest_length_m':0.090,'band_width_m':0.004,'band_thickness_m':0.00018,
 'band_anchor_positions_m':[[0.,-.043,.132],[0.,.043,.132]],
 'pouch_position_m':[-.122,0.,.132], 'pouch_quaternion_xyzw':[0.,0.,0.,1.],
 'pouch_mass_kg':0.00045,'pouch_half_width_m':.013,
 'ball_position_m':[-.113,0.,.132], 'ball_quaternion_xyzw':[0.,0.,0.,1.],
 'ball_radius_m':.0075,'ball_mass_kg':.00185,
 'domino_position_m':[.180,0.,.0375], 'domino_quaternion_xyzw':[0.,0.,0.,1.],
 'domino_size_m':[.012,.035,.075], 'domino_mass_kg':.016,'domino_present':[1],
 'second_domino_present':[0],'second_domino_position_m':[.232,0.,.0375],
 'second_domino_quaternion_xyzw':[0.,0.,0.,1.], 'second_domino_mass_kg':.016,
 'second_domino_size_m':[.012,.035,.075],
 'table_friction':.5,'ball_friction':.25,'domino_friction':.65,
 'release_s':.5, 'duration_s':4., 'fps':24, 'frames':96,
 'gravity_m_s2':[0.,0.,-9.81],
}
EDITS={
 'soft_bands':'SET bands.young_modulus TIMES 0.5',
 'heavy_ball':'SET ball.mass TIMES 3',
 'heavy_domino':'SET domino.mass TIMES 2',
 'heavy_domino_at_frame_12':'SET domino.mass TIMES 10 AT FRAME 12',
 'delete_domino':'DELETE domino',
}
LABELS={'source':'原场景','soft_bands':'橡胶带杨氏模量 ×0.5','heavy_ball':'小球质量 ×3',
 'heavy_domino':'木牌质量 ×2','heavy_domino_at_frame_12':'第12帧木牌质量 ×10','delete_domino':'删除木牌'}

def write_json(p,j):
    p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(j,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
