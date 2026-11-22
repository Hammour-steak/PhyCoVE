import json
import math
import os

import numpy as np
import taichi as ti


ROOT = os.environ.get("PCVE_SCENE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_DIR = os.environ.get("PCVE_WORK_DIR", os.path.join(ROOT, "work"))
os.makedirs(WORK_DIR, exist_ok=True)
SURFACE = os.path.join(WORK_DIR, "mpm_hammock_surface.npz")
RUN_NAME = os.environ.get("MPM_RUN_NAME", "mpm_fixed")
OUT = os.path.join(WORK_DIR, f"{RUN_NAME}_cache.npz")
METRICS = os.path.join(WORK_DIR, f"{RUN_NAME}_metrics.json")

FPS = 24
FRAMES = int(os.environ.get("MPM_FRAMES", "96"))
SUBSTEPS = int(os.environ.get("MPM_SUBSTEPS", "100"))
DT = 1.0 / (FPS * SUBSTEPS)
GRID_N = int(os.environ.get("MPM_GRID", "64"))
DOMAIN_ORIGIN = np.array([-1.15, -10.75, 2.20], dtype=np.float32)
DOMAIN_ORIGIN_TUPLE = (-1.15, -10.75, 2.20)
DOMAIN_SIZE = 3.84
DX = DOMAIN_SIZE / GRID_N
INV_DX = 1.0 / DX

YOUNG = float(os.environ.get("MPM_YOUNG", "15000"))
YOUNG_AFTER = float(os.environ.get("MPM_YOUNG_AFTER", str(YOUNG)))
YOUNG_CHANGE_TIME = float(os.environ.get("MPM_YOUNG_CHANGE_TIME", "-1.0"))
TIMED_YOUNG_EDIT = YOUNG_CHANGE_TIME >= 0.0 and YOUNG_AFTER != YOUNG
POISSON = float(os.environ.get("MPM_POISSON", "0.30"))
DENSITY = float(os.environ.get("MPM_DENSITY", "6"))
THICKNESS = float(os.environ.get("MPM_THICKNESS", "0.15"))
BALL_MASS = float(os.environ.get("MPM_BALL_MASS", "0.25"))
BALL_RADIUS = 0.16
BALL_VZ = float(os.environ.get("MPM_BALL_VZ", "-1.0"))
BALL_START_X = float(os.environ.get("MPM_BALL_X", "0.80"))
BALL_START_Y = float(os.environ.get("MPM_BALL_Y", "-8.92"))
LOCK_LATERAL = int(os.environ.get("MPM_LOCK_LATERAL", "0"))
BALL_RESTITUTION = float(os.environ.get("MPM_RESTITUTION", "0.0"))
BALL_DAMPING = float(os.environ.get("MPM_BALL_DAMPING", "0.9995"))
CONTACT_FRICTION = float(os.environ.get("MPM_FRICTION", "0.22"))
PRE_ROLL_SECONDS = float(os.environ.get("MPM_PRE_ROLL_SECONDS", "4.0"))
PRE_ROLL_DAMPING = float(os.environ.get("MPM_PRE_ROLL_DAMPING", "0.998"))
VISIBLE_DAMPING = float(os.environ.get("MPM_VISIBLE_DAMPING", "0.9999"))
STRAIN_LIMIT_MIN = float(os.environ.get("MPM_STRAIN_LIMIT_MIN", "0.0"))
STRAIN_LIMIT_MAX = float(os.environ.get("MPM_STRAIN_LIMIT_MAX", "1000000.0"))
STRAIN_LIMIT_ENABLED = int(os.environ.get("MPM_STRAIN_LIMIT_ENABLED", "0"))
INPLANE_TETHER_HZ = float(os.environ.get("MPM_INPLANE_TETHER_HZ", "0.0"))
INPLANE_TETHER_DAMPING_RATIO = float(os.environ.get("MPM_INPLANE_TETHER_DAMPING_RATIO", "0.0"))
INPLANE_TETHER_OMEGA = 2.0 * math.pi * INPLANE_TETHER_HZ
END_TRANSITION_WIDTH = float(os.environ.get("MPM_END_TRANSITION_WIDTH", "0.0"))
END_TETHER_HZ = float(os.environ.get("MPM_END_TETHER_HZ", "0.0"))
END_TETHER_DAMPING_RATIO = float(os.environ.get("MPM_END_TETHER_DAMPING_RATIO", "0.0"))
END_TETHER_OMEGA = 2.0 * math.pi * END_TETHER_HZ
HARD_PIN_WIDTH = 0.14
# 0 = all cores (the original behaviour). 1 makes the run bit-reproducible: with one thread the
# particle-to-grid atomic sums are always added in the same order.
CPU_THREADS = int(os.environ.get("MPM_CPU_THREADS", "0"))
# Timed edit only: also write the unedited continuation (the source case) into this work
# directory. Both branches share one simulated prefix: the state at the start of the first frame
# whose substeps reach the change time is copied, the edit runs on, the copy is restored and the
# source runs on, so every frame up to and including the change frame is identical in both.
SOURCE_BRANCH_WORK_DIR = os.environ.get("MPM_SOURCE_BRANCH_WORK_DIR", "")
if SOURCE_BRANCH_WORK_DIR and not TIMED_YOUNG_EDIT:
    raise SystemExit("MPM_SOURCE_BRANCH_WORK_DIR needs a timed Young's modulus edit")
# Presence switches for DELETE edits; both default to 1 (every published case).
# MPM_BALL_PRESENT=0: the visible frames run without the ball (no grid coupling, the ball is not integrated;
# its recorded rows keep the release pose and are not rendered).
# MPM_HAMMOCK_PRESENT=0: no MPM body and no pre-roll; the ball falls from its release state under the same
# gravity and per-substep damping onto the sand, whose height under the ball is MPM_GROUND_Z (the ball centre
# stays at or above MPM_GROUND_Z + BALL_RADIUS); an impact reverses the normal velocity with the restitution
# MPM_GROUND_RESTITUTION, and below MPM_GROUND_REST_SPEED the ball comes to rest on the sand.
BALL_PRESENT = int(os.environ.get("MPM_BALL_PRESENT", "1"))
HAMMOCK_PRESENT = int(os.environ.get("MPM_HAMMOCK_PRESENT", "1"))
GROUND_Z = float(os.environ.get("MPM_GROUND_Z", "nan"))
GROUND_RESTITUTION = float(os.environ.get("MPM_GROUND_RESTITUTION", "0.4"))
GROUND_REST_SPEED = float(os.environ.get("MPM_GROUND_REST_SPEED", "0.05"))
if not (BALL_PRESENT or HAMMOCK_PRESENT):
    raise SystemExit("at least one body must be present")
if not HAMMOCK_PRESENT and (not math.isfinite(GROUND_Z) or TIMED_YOUNG_EDIT or SOURCE_BRANCH_WORK_DIR):
    raise SystemExit("MPM_HAMMOCK_PRESENT=0 needs MPM_GROUND_Z and no timed hammock edit")


def sample_hammock(data):
    vertices = data["vertices"].astype(np.float32)
    triangles = data["triangles"].astype(np.int32)
    particles = [p.copy() for p in vertices]
    layer_values = (-0.5, 0.0, 0.5)
    subdivisions = 4
    area = 0.0
    for tri in triangles:
        a, b, c = vertices[tri]
        normal_raw = np.cross(b - a, c - a)
        tri_area = 0.5 * float(np.linalg.norm(normal_raw))
        if tri_area < 1.0e-10:
            continue
        area += tri_area
        normal = normal_raw / (2.0 * tri_area)
        for i in range(subdivisions + 1):
            for j in range(subdivisions + 1 - i):
                u = (i + 0.33) / (subdivisions + 1.0)
                v = (j + 0.33) / (subdivisions + 1.0)
                if u + v >= 0.96:
                    scale = 0.95 / (u + v)
                    u *= scale
                    v *= scale
                center = a * (1.0 - u - v) + b * u + c * v
                for layer in layer_values:
                    particles.append(center + normal * (layer * THICKNESS))
    particles = np.asarray(particles, dtype=np.float32)
    y_min = float(vertices[:, 1].min())
    y_max = float(vertices[:, 1].max())
    pin = np.logical_or(
        particles[:, 1] <= y_min + HARD_PIN_WIDTH,
        particles[:, 1] >= y_max - HARD_PIN_WIDTH,
    )
    return vertices, triangles, particles, pin.astype(np.int32), area


data = np.load(SURFACE)
surface_rest, triangles, particle_rest, pin_np, surface_area = sample_hammock(data)
n_surface = len(surface_rest)
n_particles = len(particle_rest)
REST_Y_MIN = float(surface_rest[:, 1].min())
REST_Y_MAX = float(surface_rest[:, 1].max())
PIN_Y_MIN = float(surface_rest[:, 1].min() + 0.17)
PIN_Y_MAX = float(surface_rest[:, 1].max() - 0.17)
PIN_X_MIN = float(surface_rest[:, 0].min() - 0.18)
PIN_X_MAX = float(surface_rest[:, 0].max() + 0.18)
PIN_Z_MIN = float(surface_rest[:, 2].min() - 0.25)
PIN_Z_MAX = float(surface_rest[:, 2].max() + 0.25)
total_volume = surface_area * THICKNESS
particle_volume = total_volume / n_particles
particle_mass = DENSITY * particle_volume

ti.init(arch=ti.cpu, default_fp=ti.f32, cpu_max_num_threads=CPU_THREADS if CPU_THREADS > 0 else (os.cpu_count() or 8))

x = ti.Vector.field(3, dtype=ti.f32, shape=n_particles)
v = ti.Vector.field(3, dtype=ti.f32, shape=n_particles)
C = ti.Matrix.field(3, 3, dtype=ti.f32, shape=n_particles)
F = ti.Matrix.field(3, 3, dtype=ti.f32, shape=n_particles)
rest = ti.Vector.field(3, dtype=ti.f32, shape=n_particles)
pinned = ti.field(dtype=ti.i32, shape=n_particles)
grid_v = ti.Vector.field(3, dtype=ti.f32, shape=(GRID_N, GRID_N, GRID_N))
grid_m = ti.field(dtype=ti.f32, shape=(GRID_N, GRID_N, GRID_N))
ball_pos = ti.Vector.field(3, dtype=ti.f32, shape=())
ball_vel = ti.Vector.field(3, dtype=ti.f32, shape=())
reaction = ti.Vector.field(3, dtype=ti.f32, shape=())

x.from_numpy(particle_rest)
rest.from_numpy(particle_rest)
v.fill(0)
C.fill(0)
pinned.from_numpy(pin_np)
F.from_numpy(np.repeat(np.eye(3, dtype=np.float32)[None, :, :], n_particles, axis=0))

ball_pos[None] = ti.Vector([BALL_START_X, BALL_START_Y, 4.72])
ball_vel[None] = ti.Vector([0.0, 0.0, BALL_VZ])

def lame_parameters(young):
    return (
        young / (2.0 * (1.0 + POISSON)),
        young * POISSON / ((1.0 + POISSON) * (1.0 - 2.0 * POISSON)),
    )


mu_before, lam_before = lame_parameters(YOUNG)
mu_after, lam_after = lame_parameters(YOUNG_AFTER)


@ti.kernel
def substep(use_ball: ti.i32, transfer_damping: ti.f32, active_mu: ti.f32, active_lam: ti.f32):
    for I in ti.grouped(grid_m):
        grid_v[I] = ti.Vector.zero(ti.f32, 3)
        grid_m[I] = 0.0

    for p in x:
        xp = (x[p] - ti.Vector(DOMAIN_ORIGIN_TUPLE)) * INV_DX
        base = (xp - 0.5).cast(int)
        fx = xp - base.cast(float)
        w = [0.5 * (1.5 - fx) ** 2,
             0.75 - (fx - 1.0) ** 2,
             0.5 * (fx - 0.5) ** 2]
        F[p] = (ti.Matrix.identity(ti.f32, 3) + DT * C[p]) @ F[p]
        U, sig, V = ti.svd(F[p])
        if ti.static(STRAIN_LIMIT_ENABLED == 1):
            for d in ti.static(range(3)):
                sig[d, d] = ti.max(STRAIN_LIMIT_MIN, ti.min(STRAIN_LIMIT_MAX, sig[d, d]))
            F[p] = U @ sig @ V.transpose()
        R = U @ V.transpose()
        J = 1.0
        for d in ti.static(range(3)):
            J *= sig[d, d]
        stress = 2.0 * active_mu * (F[p] - R) @ F[p].transpose()
        stress += ti.Matrix.identity(ti.f32, 3) * active_lam * J * (J - 1.0)
        affine = (-DT * particle_volume * 4.0 * INV_DX * INV_DX) * stress
        affine += particle_mass * C[p]
        transfer_velocity = v[p]
        if ti.static(INPLANE_TETHER_HZ > 0.0):
            lateral_offset = rest[p] - x[p]
            lateral_acceleration = ti.Vector([
                INPLANE_TETHER_OMEGA * INPLANE_TETHER_OMEGA * lateral_offset[0]
                - 2.0 * INPLANE_TETHER_DAMPING_RATIO * INPLANE_TETHER_OMEGA * v[p][0],
                INPLANE_TETHER_OMEGA * INPLANE_TETHER_OMEGA * lateral_offset[1]
                - 2.0 * INPLANE_TETHER_DAMPING_RATIO * INPLANE_TETHER_OMEGA * v[p][1],
                0.0,
            ])
            transfer_velocity += DT * lateral_acceleration
        if ti.static(END_TETHER_HZ > 0.0 and END_TRANSITION_WIDTH > HARD_PIN_WIDTH):
            distance_to_end = ti.min(rest[p][1] - REST_Y_MIN, REST_Y_MAX - rest[p][1])
            end_weight = (END_TRANSITION_WIDTH - distance_to_end) / (
                END_TRANSITION_WIDTH - HARD_PIN_WIDTH
            )
            end_weight = ti.max(0.0, ti.min(1.0, end_weight))
            end_weight = end_weight * end_weight * (3.0 - 2.0 * end_weight)
            vertical_acceleration = end_weight * (
                END_TETHER_OMEGA * END_TETHER_OMEGA * (rest[p][2] - x[p][2])
                - 2.0 * END_TETHER_DAMPING_RATIO * END_TETHER_OMEGA * v[p][2]
            )
            transfer_velocity[2] += DT * vertical_acceleration
        momentum = particle_mass * transfer_velocity
        for i, j, k in ti.static(ti.ndrange(3, 3, 3)):
            offset = ti.Vector([i, j, k])
            dpos = (offset.cast(float) - fx) * DX
            weight = w[i][0] * w[j][1] * w[k][2]
            node = base + offset
            if 0 <= node[0] < GRID_N and 0 <= node[1] < GRID_N and 0 <= node[2] < GRID_N:
                ti.atomic_add(grid_v[node], weight * (momentum + affine @ dpos))
                ti.atomic_add(grid_m[node], weight * particle_mass)

    reaction[None] = ti.Vector.zero(ti.f32, 3)
    for I in ti.grouped(grid_m):
        if grid_m[I] > 0.0:
            grid_v[I] = grid_v[I] / grid_m[I]
            grid_v[I] += DT * ti.Vector([0.0, 0.0, -9.81])
            grid_v[I] *= transfer_damping
            node_world = ti.Vector(DOMAIN_ORIGIN_TUPLE) + (I.cast(float) + 0.5) * DX
            fixed_end = (node_world[1] <= PIN_Y_MIN) or (node_world[1] >= PIN_Y_MAX)
            inside_anchor_box = (
                PIN_X_MIN <= node_world[0] <= PIN_X_MAX
                and PIN_Z_MIN <= node_world[2] <= PIN_Z_MAX
            )
            if fixed_end and inside_anchor_box:
                grid_v[I] = ti.Vector.zero(ti.f32, 3)
            elif use_ball == 1:
                sphere_offset = node_world - ball_pos[None]
                sphere_distance = sphere_offset.norm()
                contact_radius = BALL_RADIUS + 0.60 * DX
                if sphere_distance < contact_radius and sphere_distance > 1.0e-6:
                    normal = sphere_offset / sphere_distance
                    relative_velocity = grid_v[I] - ball_vel[None]
                    normal_speed = relative_velocity.dot(normal)
                    if normal_speed < 0.0:
                        tangent_velocity = relative_velocity - normal_speed * normal
                        corrected_relative = (
                            tangent_velocity * (1.0 - CONTACT_FRICTION)
                            - BALL_RESTITUTION * normal_speed * normal
                        )
                        corrected_grid_velocity = ball_vel[None] + corrected_relative
                        ti.atomic_add(
                            reaction[None],
                            grid_m[I] * (corrected_grid_velocity - grid_v[I]),
                        )
                        grid_v[I] = corrected_grid_velocity
            if I[0] < 3 and grid_v[I][0] < 0:
                grid_v[I][0] = 0
            if I[0] > GRID_N - 4 and grid_v[I][0] > 0:
                grid_v[I][0] = 0
            if I[1] < 3 and grid_v[I][1] < 0:
                grid_v[I][1] = 0
            if I[1] > GRID_N - 4 and grid_v[I][1] > 0:
                grid_v[I][1] = 0
            if I[2] < 3 and grid_v[I][2] < 0:
                grid_v[I][2] = 0
            if I[2] > GRID_N - 4 and grid_v[I][2] > 0:
                grid_v[I][2] = 0

    for p in x:
        xp = (x[p] - ti.Vector(DOMAIN_ORIGIN_TUPLE)) * INV_DX
        base = (xp - 0.5).cast(int)
        fx = xp - base.cast(float)
        w = [0.5 * (1.5 - fx) ** 2,
             0.75 - (fx - 1.0) ** 2,
             0.5 * (fx - 0.5) ** 2]
        new_v = ti.Vector.zero(ti.f32, 3)
        new_C = ti.Matrix.zero(ti.f32, 3, 3)
        for i, j, k in ti.static(ti.ndrange(3, 3, 3)):
            offset = ti.Vector([i, j, k])
            dpos = (offset.cast(float) - fx) * DX
            weight = w[i][0] * w[j][1] * w[k][2]
            node = base + offset
            if 0 <= node[0] < GRID_N and 0 <= node[1] < GRID_N and 0 <= node[2] < GRID_N:
                gv = grid_v[node]
                new_v += weight * gv
                new_C += 4.0 * INV_DX * INV_DX * weight * gv.outer_product(dpos)
        next_x = x[p] + DT * new_v
        if pinned[p] == 1:
            x[p] = rest[p]
            v[p] = ti.Vector.zero(ti.f32, 3)
            C[p] = ti.Matrix.zero(ti.f32, 3, 3)
        else:
            x[p] = next_x
            v[p] = new_v
            C[p] = new_C

    if use_ball == 1:
        ball_vel[None] += DT * ti.Vector([0.0, 0.0, -9.81])
        if ti.static(LOCK_LATERAL == 1):
            ball_vel[None][2] -= reaction[None][2] / BALL_MASS
            ball_vel[None][0] = 0.0
            ball_vel[None][1] = 0.0
        else:
            ball_vel[None] -= reaction[None] / BALL_MASS
        ball_vel[None] *= BALL_DAMPING
        ball_pos[None] += DT * ball_vel[None]
        if ti.static(LOCK_LATERAL == 1):
            ball_pos[None][0] = BALL_START_X
            ball_pos[None][1] = BALL_START_Y


@ti.kernel
def ball_on_ground():
    """One substep of the ball alone (no hammock): gravity, the source's ball damping, sand contact."""
    ball_vel[None] += DT * ti.Vector([0.0, 0.0, -9.81])
    ball_vel[None] *= BALL_DAMPING
    ball_pos[None] += DT * ball_vel[None]
    rest_z = GROUND_Z + BALL_RADIUS
    if ball_pos[None][2] < rest_z:
        ball_pos[None][2] = rest_z
        if ball_vel[None][2] < 0.0:
            if -ball_vel[None][2] > GROUND_REST_SPEED:
                ball_vel[None][2] = -GROUND_RESTITUTION * ball_vel[None][2]
            else:
                ball_vel[None][2] = 0.0


@ti.kernel
def zero_dynamic_state():
    for p in x:
        v[p] = ti.Vector.zero(ti.f32, 3)
        C[p] = ti.Matrix.zero(ti.f32, 3, 3)


surface_frames = np.empty((FRAMES, n_surface, 3), dtype=np.float32)
ball_frames = np.empty((FRAMES, 3), dtype=np.float32)
ball_velocity_frames = np.empty((FRAMES, 3), dtype=np.float32)
center_index = int(np.argmin((surface_rest[:, 0] - 0.7587) ** 2 + (surface_rest[:, 1] + 8.9193) ** 2))

# Pre-equilibrate the hammock under gravity without the sphere. Crucially, the
# converged deformation gradient is retained so visible frame 1 has prestress.
pre_roll_steps = int(round(PRE_ROLL_SECONDS / DT))
pre_roll_samples = []
for step in range(pre_roll_steps if HAMMOCK_PRESENT else 0):
    substep(0, PRE_ROLL_DAMPING, mu_before, lam_before)
    if (step + 1) % (FPS * SUBSTEPS) == 0:
        particle_velocity = v.to_numpy()
        surface_now = x.to_numpy()[:n_surface]
        sample = {
            "time_s": (step + 1) * DT,
            "max_speed_m_s": float(np.linalg.norm(particle_velocity, axis=1).max()),
            "rms_speed_m_s": float(np.sqrt(np.mean(np.sum(particle_velocity ** 2, axis=1)))),
            "center_z_m": float(surface_now[center_index, 2]),
        }
        pre_roll_samples.append(sample)
        print("PRE_ROLL", json.dumps(sample))

zero_dynamic_state()
ball_pos[None] = ti.Vector([BALL_START_X, BALL_START_Y, 4.72])
ball_vel[None] = ti.Vector([0.0, 0.0, BALL_VZ])
equilibrium_surface = x.to_numpy()[:n_surface].copy()


def run_visible_frames(first_frame, timed, surface_out, ball_out, ball_velocity_out, before_frame=None):
    """Record frame rows first_frame.. and step between them; row f is the state at t = f / FPS."""
    for frame in range(first_frame, FRAMES):
        if before_frame is not None:
            before_frame(frame)
        surface_out[frame] = x.to_numpy()[:n_surface]
        ball_out[frame] = ball_pos[None]
        ball_velocity_out[frame] = ball_vel[None]
        if frame < FRAMES - 1:
            for visible_substep in range(SUBSTEPS):
                simulation_time = frame / FPS + visible_substep * DT
                after_change = timed and simulation_time >= YOUNG_CHANGE_TIME
                active_mu = mu_after if after_change else mu_before
                active_lam = lam_after if after_change else lam_before
                if HAMMOCK_PRESENT:
                    substep(BALL_PRESENT, VISIBLE_DAMPING, active_mu, active_lam)
                else:
                    ball_on_ground()
        if frame == 0 or (frame + 1) % 8 == 0:
            print(
                "MPM_FRAME",
                frame + 1,
                "ball", ball_out[frame].tolist(),
                "center_z", float(surface_out[frame, center_index, 2]),
            )


def snapshot_state():
    return {name: field.to_numpy() for name, field in
            (("x", x), ("v", v), ("C", C), ("F", F), ("ball_pos", ball_pos), ("ball_vel", ball_vel))}


def restore_state(state):
    for name, field in (("x", x), ("v", v), ("C", C), ("F", F), ("ball_pos", ball_pos), ("ball_vel", ball_vel)):
        field.from_numpy(state[name])


def summarize(surface_frames, ball_frames, ball_velocity_frames, timed):
    center_z = surface_frames[:, center_index, 2]
    min_ball_surface_distance = np.linalg.norm(
        surface_frames - ball_frames[:, None, :], axis=2
    ).min(axis=1)
    velocity_impulse = np.diff(ball_velocity_frames[:, 2])
    contact_candidates = np.where(velocity_impulse > 0.5)[0]
    contact_frame = int(contact_candidates[0] + 2) if len(contact_candidates) else None
    pre_contact_last_index = max(0, (contact_frame or 2) - 2)
    pre_contact_drift = float(np.max(np.abs(center_z[:pre_contact_last_index + 1] - center_z[0])))
    pre_contact_surface_drift = float(np.linalg.norm(
        surface_frames[:pre_contact_last_index + 1] - surface_frames[0], axis=2
    ).max())
    post_contact_vz = ball_velocity_frames[(contact_frame or 1) - 1:, 2]
    velocity_zero_crossings = int(np.sum(post_contact_vz[:-1] * post_contact_vz[1:] < 0.0))
    young_change_frame = int(round(YOUNG_CHANGE_TIME * FPS)) + 1 if timed else None
    settled_frame = None
    settle_search_start = (contact_frame or 1) - 1
    if young_change_frame is not None:
        settle_search_start = max(settle_search_start, young_change_frame - 1)
    for candidate in range(settle_search_start, FRAMES - 11):
        window_v = np.abs(ball_velocity_frames[candidate:candidate + 12, 2])
        window_z = ball_frames[candidate:candidate + 12, 2]
        window_center = center_z[candidate:candidate + 12]
        if (
            float(window_v.max()) < 0.01
            and float(window_z.max() - window_z.min()) < 0.002
            and float(window_center.max() - window_center.min()) < 0.002
        ):
            settled_frame = candidate + 1
            break
    metrics = {
        "solver": "Taichi MLS-MPM, fixed-corotated elasticity",
        "frames": FRAMES,
        "fps": FPS,
        "substeps_per_frame": SUBSTEPS,
        "pre_roll_seconds": PRE_ROLL_SECONDS,
        "pre_roll_damping_per_substep": PRE_ROLL_DAMPING,
        "visible_damping_per_substep": VISIBLE_DAMPING,
        "strain_limit_enabled": bool(STRAIN_LIMIT_ENABLED),
        "strain_limit_min": STRAIN_LIMIT_MIN if STRAIN_LIMIT_ENABLED else None,
        "strain_limit_max": STRAIN_LIMIT_MAX if STRAIN_LIMIT_ENABLED else None,
        "inplane_tether_hz": INPLANE_TETHER_HZ,
        "inplane_tether_damping_ratio": INPLANE_TETHER_DAMPING_RATIO,
        "end_transition_width_m": END_TRANSITION_WIDTH,
        "end_tether_hz": END_TETHER_HZ,
        "end_tether_damping_ratio": END_TETHER_DAMPING_RATIO,
        "pre_roll_samples": pre_roll_samples,
        "grid_resolution": GRID_N,
        "particle_count": n_particles,
        "surface_vertex_count": n_surface,
        "surface_area_m2": surface_area,
        "thickness_m": THICKNESS,
        "density_kg_m3": DENSITY,
        "hammock_mass_kg": particle_mass * n_particles,
        "young_modulus_pa": YOUNG,
        "young_modulus_after_pa": YOUNG_AFTER if timed else YOUNG,
        "young_modulus_change_time_s": YOUNG_CHANGE_TIME if timed else None,
        "young_modulus_change_frame": young_change_frame,
        "poisson_ratio": POISSON,
        "ball_mass_kg": BALL_MASS,
        "ball_radius_m": BALL_RADIUS,
        "ball_initial_velocity_m_s": [0.0, 0.0, BALL_VZ],
        "ball_start_xy_m": [BALL_START_X, BALL_START_Y],
        "ball_lateral_translation_locked": bool(LOCK_LATERAL),
        "ball_damping_per_substep": BALL_DAMPING,
        "contact_restitution": BALL_RESTITUTION,
        "center_vertex_index": center_index,
        "center_rest_z_m": float(center_z[0]),
        "center_min_z_m": float(center_z.min()),
        "center_min_frame": int(center_z.argmin() + 1),
        "max_center_deflection_m": float(center_z[0] - center_z.min()),
        "ball_min_z_m": float(ball_frames[:, 2].min()),
        "ball_min_frame": int(ball_frames[:, 2].argmin() + 1),
        "ball_final_z_m": float(ball_frames[-1, 2]),
        "contact_frame": contact_frame,
        "pre_contact_center_drift_m": pre_contact_drift,
        "pre_contact_max_surface_vertex_drift_m": pre_contact_surface_drift,
        "post_contact_ball_vz_zero_crossings": velocity_zero_crossings,
        "final_ball_vertical_speed_m_s": float(ball_velocity_frames[-1, 2]),
        "settled_frame_12_frame_window": settled_frame,
        "post_settle_frame48_to_end_max_surface_vertex_delta_m": float(np.linalg.norm(
            surface_frames[47:] - surface_frames[47], axis=2
        ).max()) if FRAMES >= 48 else None,
        "ball_frame48_to_end_z_delta_m": float(ball_frames[-1, 2] - ball_frames[47, 2]) if FRAMES >= 48 else None,
        "ball_max_lateral_displacement_m": float(np.linalg.norm(
            ball_frames[:, :2] - ball_frames[0, :2], axis=1
        ).max()),
        "ball_final_lateral_displacement_m": float(np.linalg.norm(
            ball_frames[-1, :2] - ball_frames[0, :2]
        )),
        "equilibrium_surface_matches_frame1": bool(np.allclose(equilibrium_surface, surface_frames[0])),
        "ball_present": bool(BALL_PRESENT),
        "hammock_present": bool(HAMMOCK_PRESENT),
    }
    return metrics


def write_outputs(cache_path, metrics_path, surface_frames, ball_frames, ball_velocity_frames, metrics):
    np.savez_compressed(
        cache_path,
        surface_frames=surface_frames,
        ball_frames=ball_frames,
        ball_velocity_frames=ball_velocity_frames,
        rest_vertices=surface_rest,
        triangles=triangles,
    )
    with open(metrics_path, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, ensure_ascii=False, indent=2)
    print("MPM_COMPLETE", cache_path)
    print(json.dumps(metrics, ensure_ascii=False, indent=2))


if not SOURCE_BRANCH_WORK_DIR:
    run_visible_frames(0, TIMED_YOUNG_EDIT, surface_frames, ball_frames, ball_velocity_frames)
    metrics = summarize(surface_frames, ball_frames, ball_velocity_frames, TIMED_YOUNG_EDIT)
    metrics["cpu_threads"] = CPU_THREADS if CPU_THREADS > 0 else (os.cpu_count() or 8)
    if not HAMMOCK_PRESENT:
        metrics["sand_contact"] = {"ground_z_m": GROUND_Z, "ball_rest_centre_z_m": GROUND_Z + BALL_RADIUS,
                                   "restitution": GROUND_RESTITUTION, "rest_speed_m_s": GROUND_REST_SPEED}
    write_outputs(OUT, METRICS, surface_frames, ball_frames, ball_velocity_frames, metrics)
else:
    # First frame whose substeps include t >= YOUNG_CHANGE_TIME: its starting state is shared.
    branch_frame = next(f for f in range(FRAMES)
                        if any(f / FPS + s * DT >= YOUNG_CHANGE_TIME for s in range(SUBSTEPS)))
    shared = {}

    def keep_branch_state(frame):
        if frame == branch_frame:
            shared["state"] = snapshot_state()

    run_visible_frames(0, True, surface_frames, ball_frames, ball_velocity_frames, keep_branch_state)
    source_surface = surface_frames.copy()
    source_ball = ball_frames.copy()
    source_ball_velocity = ball_velocity_frames.copy()
    restore_state(shared["state"])
    run_visible_frames(branch_frame, False, source_surface, source_ball, source_ball_velocity)
    handoff = max(
        float(np.abs(source_surface[branch_frame] - surface_frames[branch_frame]).max()),
        float(np.abs(source_ball[branch_frame] - ball_frames[branch_frame]).max()),
        float(np.abs(source_ball_velocity[branch_frame] - ball_velocity_frames[branch_frame]).max()),
    )
    if handoff != 0.0:
        raise SystemExit(f"source branch does not restart from the shared state (max diff {handoff})")
    for a, b in ((surface_frames, source_surface), (ball_frames, source_ball),
                 (ball_velocity_frames, source_ball_velocity)):
        assert np.array_equal(a[:branch_frame + 1], b[:branch_frame + 1])
    branch = {
        "branch_frame": branch_frame + 1,
        "branch_time_s": branch_frame / FPS,
        "identical_frames": [1, branch_frame + 1],
        "handoff_max_abs_diff": handoff,
        "cpu_threads": CPU_THREADS if CPU_THREADS > 0 else (os.cpu_count() or 8),
    }
    metrics = summarize(surface_frames, ball_frames, ball_velocity_frames, True)
    metrics["cpu_threads"] = branch["cpu_threads"]
    metrics["same_run_branch"] = dict(branch, role="edit", other_branch_cache=os.path.join(
        SOURCE_BRANCH_WORK_DIR, os.path.basename(OUT)))
    write_outputs(OUT, METRICS, surface_frames, ball_frames, ball_velocity_frames, metrics)
    os.makedirs(SOURCE_BRANCH_WORK_DIR, exist_ok=True)
    source_metrics = summarize(source_surface, source_ball, source_ball_velocity, False)
    source_metrics["cpu_threads"] = branch["cpu_threads"]
    source_metrics["same_run_branch"] = dict(branch, role="source", other_branch_cache=OUT)
    write_outputs(os.path.join(SOURCE_BRANCH_WORK_DIR, os.path.basename(OUT)),
                  os.path.join(SOURCE_BRANCH_WORK_DIR, os.path.basename(METRICS)),
                  source_surface, source_ball, source_ball_velocity, source_metrics)
