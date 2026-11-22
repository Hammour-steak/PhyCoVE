"""Common compressible cotton-batting surrogate in the coupled ABD/FEM/IPC solve."""
from pathlib import Path
import sys, os, json
import numpy as np

HERE = Path(__file__).resolve().parent
# BOOK_PILLOW_KIT_SUPPORT: helper directory inside the restored worker kit (set by tools/launch.py).
sys.path.insert(0, str(Path(os.environ['BOOK_PILLOW_KIT_SUPPORT'])/'bedding'))
import physics_bedding as prior

ROOT, DATA = prior.ROOT, prior.DATA
ASSETS = DATA / 'assets/quilt'
CASES = prior.CASES

def overrides_for(case, material):
    if material == 'cotton':
        if case == 'heavy_book':
            return {'phone_mass_kg': 1.0}
        if case == 'soft_pillow':
            return {'pillow_young_modulus_pa': 200.}
        if case == 'firm_pillow':
            return {'pillow_young_modulus_pa': 2000.}
    return dict(CASES[case])

def config_for(case, rate=1200, material='cotton'):
    c = prior.config_for(case, rate)
    # The nominal pillow-clearance field is not the release binding.
    # Retain the actual unchanged world transform through the mattress reference.
    c.pop('book_drop_height_above_pillow_m',None)
    c.update(simulation_fps=24, dense_fps=24,
        duvet_young_modulus_pa=1000., duvet_poisson_ratio=.12,
        duvet_density_kg_m3=24., duvet_shear_viscosity_pa_s=8., duvet_bulk_viscosity_pa_s=100.,
        contact_fixed_kappa=1e10, native_linear_tolerance=1e-5,
        native_velocity_tolerance_m_s=.00025,
        cushion_asset_path=(ASSETS / 'mattress_volume.npz').relative_to(ROOT).as_posix())
    with np.load(ASSETS / 'mattress_volume.npz') as z:
        c['drop_height_m'] = .946 - float(z['vertices'][:, 2].max())
        c['actual_cushion_reference_geometry_vertices'] = len(z['vertices'])
        c['actual_cushion_reference_bounds_m'] = [z['vertices'].min(0).tolist(), z['vertices'].max(0).tolist()]
    if material != 'cotton':
        raise ValueError('Undeclared common material')
    c.update(duvet_young_modulus_pa=2400.,duvet_poisson_ratio=.35,
        duvet_shear_viscosity_pa_s=20.,duvet_bulk_viscosity_pa_s=200.,
        native_velocity_tolerance_m_s=.00005,native_linear_tolerance=1e-6,
        accent_book_center_m=[.025,.30,.89])
    # Softer shear response and a stronger bulk modulus allow the
    # quilt to reshape around the book while supporting its load.
    c.update(
        duvet_young_modulus_pa=1800.,
        duvet_poisson_ratio=.40,
        duvet_shear_viscosity_pa_s=24.,
        duvet_bulk_viscosity_pa_s=125.,
    )
    c['pillow_young_modulus_pa'] = 400.
    c.update(overrides_for(case, material))
    c['bedding_material_revision']=material
    return c

class Simulation(prior.Simulation):
    def __init__(self, c, out):
        self.orientation_records = []
        self.record_visible_dynamics = False
        self.micro_book_records = []
        self.out = Path(out)
        super().__init__(c, out)
        self.mattress_inverse = self.inverse(self.sv, self.st)
        self.config.update(scene_id='book_pillow_bedroom',
            model_revision='same 3D quilt/contact model for source and every edit',
            material_calibrated=False,
            media_contract={'width':1280, 'height':720, 'fps':24, 'frames':96, 'duration_s':4., 'physical_time_scale':1.})
        self.config['duvet'].update(self_contact_enabled=True,
            geometry='artist-derived folded 3D volume, not a heightfield',
            model='compressible effective cotton batting and cover; lower shear resistance and dissipative bulk compression',
            limitations='No individually resolved fibres, woven shell or air transport; effective coefficients are not measured calibration.',
            orientation_checked_every_substep=True,
            material={'young_modulus_pa':c['duvet_young_modulus_pa'], 'poisson_ratio':c['duvet_poisson_ratio'],
                'density_kg_m3':c['duvet_density_kg_m3'], 'shear_viscosity_pa_s':c['duvet_shear_viscosity_pa_s'],
                'bulk_viscosity_pa_s':c['duvet_bulk_viscosity_pa_s']})
        prior.old.coupled.base.json_save(self.out / 'physics_config.json', self.config)

    @staticmethod
    def inverse(x, tet):
        return np.linalg.inv(np.stack([x[tet[:,i]]-x[tet[:,0]] for i in (1,2,3)], -1))

    def accent_speed(self):
        if self.c['bedding_material_revision'] != 'cotton':
            return super().accent_speed()
        if self.accent_book_index is None:
            return 0.
        self.abd.copy_to(self.ag)
        velocity = np.asarray(self.ag.instances().find(
            self.rt['builtin'].velocity).view())[self.accent_book_index]
        # A_dot has units 1/s. Multiplying by local vertices converts its
        # contribution to m/s before combining it with translation.
        surface_velocity = (np.asarray(self.accent_book.vertices)
                            @ velocity[:3,:3].T + velocity[:3,3])
        speed = float(np.linalg.norm(surface_velocity, axis=1).max())
        self.accent_motion = {
            'maximum_surface_speed_m_s': speed,
            'translation_speed_m_s': float(np.linalg.norm(velocity[:3,3])),
            'affine_rate_norm_s_inv': float(np.linalg.norm(velocity[:3,:3])),
        }
        return speed

    def _add_bodies_before_world_init(self, rt, table, phone_contact):
        # Add unchanged pillow and genuinely new lower book, then the common folded quilt.
        prior.old.Simulation._add_bodies_before_world_init(self, rt, table, phone_contact)
        with np.load(ASSETS / 'duvet_volume.npz') as z:
            self.duvet_rest, self.duvet_tets, self.duvet_fixed = z['vertices'], z['tetrahedra'], z['fixed']
        c, view, builtin = self.c, rt['view'], rt['builtin']
        mesh = rt['tetmesh'](self.duvet_rest, self.duvet_tets)
        rt['label_surface'](mesh); rt['label_triangle_orient'](mesh)
        mesh = rt['flip_inward_triangles'](mesh)
        E, nu = c['duvet_young_modulus_pa'], c['duvet_poisson_ratio']
        mu = E / (2*(1+nu)); lam = E*nu/((1+nu)*(1-2*nu)) + mu
        rt['StableNeoHookean']().apply_to(mesh, rt['ElasticModuli'].youngs_poisson(E, nu), mass_density=c['duvet_density_kg_m3'])
        view(mesh.tetrahedra().find('mu')).reshape(-1)[:] = mu
        view(mesh.tetrahedra().find('lambda')).reshape(-1)[:] = lam
        rt['native_kv_runtime'].constitute(mesh, c['duvet_shear_viscosity_pa_s'], c['duvet_bulk_viscosity_pa_s'])
        slot = mesh.vertices().find(builtin.is_fixed)
        if slot is None: slot = mesh.vertices().create(builtin.is_fixed, 0)
        view(slot).reshape(-1)[:] = self.duvet_fixed
        slot = mesh.meta().find(builtin.self_collision)
        if slot is None: slot = mesh.meta().create(builtin.self_collision, 1)
        view(slot).reshape(-1)[:] = 1
        table.default_element().apply_to(mesh)
        self.scene.objects().create('padded_duvet').geometries().create(mesh)
        self.duvet_inverse = self.inverse(self.duvet_rest, self.duvet_tets)

    def advance(self):
        super().advance()
        self.fem.copy_to(self.fg)
        x = np.asarray(self.fg.positions().view()).reshape(-1, 3)
        bodies = [(self.duvet_mapping, self.duvet_tets, self.duvet_inverse),
                  (self.mapping, self.st, self.mattress_inverse)]
        if len(self.pillow_tets): bodies.append((self.pillow_mapping, self.pillow_tets, self.pillow_rest_inverse))
        minima = []
        for mapping, tet, inv in bodies:
            v = x[mapping]
            minima.append(float(np.linalg.det(np.stack([v[tet[:,i]]-v[tet[:,0]] for i in (1,2,3)], -1) @ inv).min()))
        self.orientation_records.append([self.steps, *minima])
        if not np.isfinite(minima).all() or min(minima) <= 0:
            (self.out / 'orientation_failure.json').write_text(json.dumps({'step':self.steps, 'minima':minima}))
            raise FloatingPointError('Reject nonpositive volume before another viscous step')
        if self.record_visible_dynamics:
            self.abd.copy_to(self.ag)
            b=self.rt['builtin']
            v=np.asarray(self.ag.instances().find(b.velocity).view())[self.phone_index]
            pose=np.asarray(self.ag.instances().find(b.transform).view())[self.phone_index]
            self.micro_book_records.append([(self.steps-self.visible_origin_step)*self.c['simulation_dt_s'],
                *v[:3,3].tolist(),float(pose[2,3])])

write_cache = prior.write_cache
