from pathlib import Path
import sys
root=next((p for p in Path(__file__).resolve().parents if (p/"scripts/pcve_edit_dsl.py").is_file()),None)
sys.path.insert(0,str(root/"scripts") if root else str(Path(__file__).resolve().parent.parent))
from pcve_edit_dsl import Vocabulary,PropertySpec,SimBinding,DeleteBinding,AddBinding,AddPreset
import json
from pcve_assets import asset
# The accepted physics configs record their inputs as paths inside the restored worker
# kit (see scene_paths.py); KIT is that kit's case-data directory, not a repository location.
KIT=json.loads((asset('scenes/book_pillow_bedroom')/'kit/kit_layout.json').read_text(encoding='utf-8'))['case_data']
baseline={'geometry_mode': 'asset', 'cushion_asset_path': KIT+'/assets/quilt/mattress_volume.npz', 'static_collision_path': KIT+'/assets/bed_scene/no_extra_colliders.npz', 'cushion_dimensions_m': [1.02, 1.02, 0.074], 'cushion_bottom_z_m': 0.4, 'cushion_center_xy_m': [0.0, 0.3], 'cushion_reference_scale_xyz': [1.0, 1.0, 1.0], 'cushion_reference_translation_xy_m': [0.0, 0.0], 'cushion_initial_lift_m': 0.0, 'seat_deck_present': True, 'seat_deck_top_z_m': 0.399, 'simulation_grid': [19, 19, 4], 'phone_release_xy_m': [0.025, 0.3], 'phone_initial_euler_deg': [4.0, -5.0, -9.0], 'phone_initial_velocity_m_s': [0.0, 0.0, 0.0], 'drop_height_m': 0.4947338860034942, 'cushion_young_modulus_pa': 120000.0, 'cushion_poisson_ratio': 0.2, 'cushion_density_kg_m3': 60.0, 'cushion_shear_viscosity_pa_s': 50.0, 'cushion_bulk_viscosity_pa_s': 100.0, 'preload_duration_s': 0.35, 'simulation_dt_s': 0.0016666666666666668, 'phone_collision_path': KIT+'/assets/bed_scene/book_collision.npz', 'phone_dimensions_m': [0.24, 0.17, 0.036], 'phone_mass_kg': 0.5, 'phone_present': True, 'cushion_present': True, 'phone_contact_friction': 0.55, 'upholstery_thickness_m': 0.00065, 'upholstery_density_kg_m3': 320.0, 'upholstery_stretch_modulus_pa': 200000.0, 'upholstery_shear_modulus_pa': 50000.0, 'upholstery_bending_stiffness_nm': 2e-05, 'upholstery_shear_viscosity_n_s_m': 0.25, 'upholstery_bulk_viscosity_n_s_m': 0.5, 'phone_initial_angular_velocity_rad_s': [0.0, 0.0, 0.0], 'seat_deck_dimensions_m': [1.65, 2.02, 0.18], 'native_velocity_tolerance_m_s': 5e-05, 'native_linear_tolerance': 1e-06, 'contact_resistance': 10000000000.0, 'phone_affine_stiffness_pa': 10000000000.0, 'contact_kappa_policy': 'explicit_fixed', 'contact_fixed_kappa': 10000000000.0, 'contact_d_hat_m': 0.0004, 'simulation_fps': 24, 'dense_fps': 24, 'constitutive_viscosity_enabled': True, 'actual_cushion_reference_bounds_m': [[-0.48, -0.12, 0.4], [0.48, 0.72, 0.45126611399650574]], 'actual_cushion_reference_geometry_vertices': 3198, 'cushion_viscosity_scale': 1.0, 'added_book_present': False, 'added_book_dimensions_m': [0.22, 0.18, 0.02], 'added_book_mass_kg': 0.4, 'added_book_center_m': [0.0, -0.18, 0.5], 'added_book_euler_deg': [0.0, 0.0, 0.0], 'added_book_contact_friction': 0.5, 'added_book_affine_stiffness_pa': 10000000000.0, 'viscosity_transfer': 'native_coupled_increment_energy', 'pillow_present': True, 'pillow_asset_id': 'BlenderKit_53ae1732_Grey_pillow_with_border', 'pillow_reference_path': KIT+'/assets/bedding/pillow_volume.npz', 'pillow_render_mapping_path': KIT+'/assets/boundary_render_mapping.npz', 'pillow_center_m': [0.0, 0.3, 0.635], 'pillow_orientation_quaternion_wxyz': [1.0, 0.0, 0.0, 0.0], 'pillow_young_modulus_pa': 400.0, 'pillow_poisson_ratio': 0.22, 'pillow_density_kg_m3': 18.0, 'pillow_shear_viscosity_pa_s': 18.0, 'pillow_bulk_viscosity_pa_s': 36.0, 'pillow_contact_friction': 0.55, 'pillow_self_collision_enabled': 0, 'pillow_preroll_max_s': 2.0, 'pillow_preroll_speed_threshold_m_s': 0.001, 'pillow_preroll_hold_s': 0.2, 'accent_book_present': False, 'accent_book_dimensions_m': [0.26, 0.19, 0.03], 'accent_book_mass_kg': 0.65, 'accent_book_center_m': [0.025, 0.3, 0.89], 'accent_book_euler_deg': [0.0, 0.0, -9.0], 'accent_book_contact_friction': 0.55, 'accent_book_affine_stiffness_pa': 10000000000.0, 'duvet_young_modulus_pa': 1800.0, 'duvet_poisson_ratio': 0.4, 'duvet_density_kg_m3': 24.0, 'duvet_shear_viscosity_pa_s': 24.0, 'duvet_bulk_viscosity_pa_s': 125.0, 'added_book_release': 'pre_settled_on_landing_point', 'duvet_contact_friction': 0.55, 'bedding_material_revision': 'cotton'}
reserved=['accent_book_center_m','accent_book_dimensions_m','accent_book_mass_kg','accent_book_euler_deg','accent_book_contact_friction','accent_book_affine_stiffness_pa']
VOCAB=Vocabulary(scene_id='book_pillow_bedroom',
    # Display names as the objects read on screen (prompts use the same words, see the builder catalog).
    objects={'book':{'zh':'蓝色书','en':'the blue book'},'pillow':{'zh':'枕头','en':'the pillow'},
             'extra_book':{'zh':'棕色精装本','en':'a brown book'},'duvet':{'zh':'被子','en':'the duvet'},
             'mattress':{'zh':'床垫','en':'the mattress'}},
    properties={'mass':PropertySpec('scalar','kg','质量','mass'),'young_modulus':PropertySpec('scalar','Pa','杨氏模量',"Young's modulus")},
    sim_bindings={('book','mass'):SimBinding('phone_mass_kg'),('pillow','young_modulus'):SimBinding('pillow_young_modulus_pa')},
    delete_bindings={'pillow':DeleteBinding('pillow_present',0,0),'book':DeleteBinding('book_present',0,0)},
    baseline_physics=dict(baseline,pillow_present=[1],accent_book_present=[0],book_present=[1]),
    add_bindings={'extra_book':AddBinding('accent_book_present',0,'accent_book_center_m',owned_parameters=tuple(SimBinding(k) for k in reserved))},
    add_presets={('extra_book','landing_point'):AddPreset(tuple((k,baseline[k]) for k in reserved),'在蓝色书落点处的枕头上平放一本书','a book lying flat on the pillow where the blue book lands')},
    object_parameters={'book':tuple(SimBinding(k) for k in ['phone_mass_kg','phone_dimensions_m','phone_release_xy_m','phone_initial_euler_deg','phone_initial_velocity_m_s','phone_initial_angular_velocity_rad_s','drop_height_m']),
      'pillow':tuple(SimBinding(k) for k in ['pillow_present','pillow_center_m','pillow_orientation_quaternion_wxyz','pillow_young_modulus_pa','pillow_density_kg_m3']),
      'extra_book':tuple(SimBinding(k) for k in ['accent_book_present']+reserved)},total_frames=96)


# --- Display-only ADD geometry -----------------------------------------------
# The published edit_dsl of the ADD case is the shared DSL's BETWEEN form:
#   ADD extra_book BETWEEN book AND bed_below_book AT 1/3 FROM bed_below_book
# pcve_edit_dsl.parse(edit_dsl, VOCAB) needs a GeometryAnchor for both endpoints and for the new body.
# The anchors below are named points used only to place that line and word its prompts, the same way
# other scenes declare display anchors (e.g. rigid_rigid/kitchen_tin_collision stack_anchor).
# Centres are where each endpoint is at frame 1 of the ADD case, in the native frame (metres); radii only
# feed parse()'s overlap check. They live under display_anchor_* keys that no solver, renderer or SET/DELETE
# binding reads. The native "ADD ... AT PRESET" kept in native_edit_dsl still places the body; no existing
# id, binding or physical value changes.
# book: the blue book's release centre (0.025, 0.3, 0.9803) m. bed_below_book: the point of the mattress top
# straight below it, (0.025, 0.3, 0.4513) m (baseline actual_cushion_reference_bounds_m top z). The 1/3 point from
# bed_below_book, (0.025, 0.3, 0.6276) m, is 0.74 cm from the added book's frame-1 centre (0.0250, 0.2988, 0.6203) m
# (it lies on the pillow, pre-settled).
import dataclasses as _dataclasses
import sys as _sys
_dsl = _sys.modules[type(VOCAB).__module__]
DISPLAY_ADD_ANCHORS = {
    "book": {
        "centre_m": [
            0.025,
            0.3,
            0.9802532509421079
        ],
        "radius_m": 0.018
    },
    "bed_below_book": {
        "zh": "蓝色书正下方的床垫面",
        "en": "the mattress top directly below the blue book",
        "centre_m": [
            0.025,
            0.3,
            0.45126611399650574
        ],
        "radius_m": 0.001
    }
}
DISPLAY_ADD_NEW_BODY_RADIUS_M = {
    "extra_book": 0.015
}
DISPLAY_NAME_UPDATES = {
    "extra_book": {
        "zh": "平放的棕色精装本",
        "en": "a brown book lying flat"
    }
}


def _with_display_add_anchors(vocab):
    objects = {k: dict(v) for k, v in vocab.objects.items()}
    physics = dict(vocab.baseline_physics)
    geometry = dict(vocab.geometry)
    for name, names in DISPLAY_NAME_UPDATES.items():
        objects[name] = dict(names)
    for name, anchor in DISPLAY_ADD_ANCHORS.items():
        if name not in objects:
            objects[name] = {'zh': anchor['zh'], 'en': anchor['en']}
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_centre_m'] = list(anchor['centre_m'])
        physics[f'display_anchor_{name}_radius_m'] = anchor['radius_m']
        geometry[name] = _dsl.GeometryAnchor(f'display_anchor_{name}_centre_m', f'display_anchor_{name}_radius_m')
    for name, radius in DISPLAY_ADD_NEW_BODY_RADIUS_M.items():
        if name in geometry:
            continue
        physics[f'display_anchor_{name}_radius_m'] = radius
        geometry[name] = _dsl.GeometryAnchor(vocab.add_bindings[name].location_key, f'display_anchor_{name}_radius_m')
    return _dataclasses.replace(vocab, objects=objects, baseline_physics=physics, geometry=geometry)


VOCAB = _with_display_add_anchors(VOCAB)
