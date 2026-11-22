"""Coupled finite-strain foam, guided cup, rolling steel ball and passive lever."""

import argparse
import hashlib
import json
import math
from pathlib import Path
import socket
import time

import numpy as np
from scipy.optimize import minimize

from config import BASELINE, CASE_DSL, H, PLATEN_STOP_Z, TIMED_DSL, parameters, timed_schedule
from rig import (EDGE_X, FLAG_COM, FLAG_INERTIA, FLAG_MASS, FOAM_BOTTOM,
                        FOAM_SIZE, G, Hinge_X, Hinge_Z, PLATE_BOTTOM, RADIUS,
                        RAMP_ANGLE, RAMP_END, RAMP_LENGTH, tetrahedral_box)

FLAG_LIMIT = 1.12
CUP_FLOOR = .004
CUP_RIM = .016
CUP_RADIUS = .028
CUP_OUTER_RADIUS = .031
PLATE_HALF_LENGTH = .040
CONTACT_MODULUS = 5e7
CACHE_FPS = 96
CELLS = (6, 6, 8)
STEP_HZ = 1920


class Foam:
    def __init__(self, params, cells, dt):
        self.dt = dt
        self.rest, self.tets, self.faces = tetrahedral_box(cells)
        self.free = self.rest[:, 2] > FOAM_BOTTOM + 1e-8
        self.count = 3 * int(self.free.sum())
        self.inv = np.linalg.inv(self.edges(self.rest))
        self.volume = np.linalg.det(self.edges(self.rest)) / 6
        self.gradient_shape = np.concatenate((-self.inv.sum(axis=1)[:, None], self.inv), axis=1)
        self.mass = np.zeros(len(self.rest))
        surface_area = np.zeros(len(self.rest))
        for corner in range(4):
            np.add.at(self.mass, self.tets[:, corner], self.volume * params["foam_density_kg_m3"] / 4)
        for face in self.faces:
            a, b, c = self.rest[face]
            surface_area[face] += np.linalg.norm(np.cross(b-a, c-a)) / 6
        self.surface = np.flatnonzero((surface_area > 0) & self.free)
        self.surface_k = CONTACT_MODULUS * surface_area[self.surface]
        self.surface_z_dofs = 3 * (np.cumsum(self.free)[self.surface]-1) + 2
        young = params["foam_young_modulus_pa"]
        nu = params["foam_poisson_ratio"]
        self.mu = young / (2 * (1 + nu))
        self.lam = young * nu / ((1 + nu) * (1 - 2 * nu))
        self.eta_s = params["foam_shear_viscosity_pa_s"]
        self.eta_b = params["foam_bulk_viscosity_pa_s"]
        self.mass_vector = np.repeat(self.mass[self.free], 3)
        top_area = np.zeros_like(surface_area)
        top = self.rest[:, 2] > FOAM_BOTTOM + FOAM_SIZE[2] - 1e-8
        top_area[top] = surface_area[top]
        self.diagonal = np.repeat(self.mass[self.free]/dt**2 + young*.072 + CONTACT_MODULUS*top_area[self.free], 3)
        self.points = self.rest.copy()
        self.previous_C = np.broadcast_to(np.eye(3), self.inv.shape).copy()

    def edges(self, points):
        corners = points[self.tets]
        return np.swapaxes(corners[:, 1:] - corners[:, :1], 1, 2)

    def evaluate(self, flat, plate):
        x = self.rest.copy()
        x[self.free] = flat.reshape(-1, 3)
        F = self.edges(x) @ self.inv
        cof = np.stack((np.cross(F[:, :, 1], F[:, :, 2]), np.cross(F[:, :, 2], F[:, :, 0]),
                        np.cross(F[:, :, 0], F[:, :, 1])), axis=-1)
        J = (F[:, :, 0] * cof[:, :, 0]).sum(axis=1)
        smooth = np.sqrt(J**2 + 1e-6)
        positive = .5 * (J + smooth)
        dpositive = .5 * (1 + J/smooth)
        log_j = np.log(positive)
        compression = np.maximum(.55-J, 0)
        W = (.5*self.mu*((F*F).sum(axis=(1, 2))-3) - self.mu*log_j + .5*self.lam*log_j**2
             + .2*self.mu*compression**4/positive**2)
        bulk = ((self.lam*log_j-self.mu)*dpositive/positive
                + .2*self.mu*(-4*compression**3/positive**2-2*compression**4*dpositive/positive**3))
        P = self.mu*F + bulk[:, None, None]*cof
        C = np.swapaxes(F, 1, 2) @ F
        rate = (C-self.previous_C) / (2*self.dt)
        trace = np.trace(rate, axis1=1, axis2=2)
        spherical = trace[:, None, None]*np.eye(3)
        dev = rate - spherical/3
        W += self.dt*(self.eta_s*(dev*dev).sum(axis=(1, 2)) + .5*self.eta_b*trace**2)
        P += F @ (2*self.eta_s*dev + self.eta_b*spherical)
        local = (P[:, None] @ self.gradient_shape[:, :, :, None]).squeeze(-1)*self.volume[:, None, None]
        g = np.zeros_like(x)
        for corner in range(4):
            for axis in range(3):
                g[:, axis] += np.bincount(self.tets[:, corner], local[:, corner, axis], minlength=len(x))
        g[:, 2] += self.mass*G
        gradient = g[self.free].ravel()
        energy = float(W@self.volume + (self.mass*G)@x[:, 2])
        top = np.maximum(x[self.surface, 2]-plate, 0)
        floor = np.maximum(.008-x[self.surface, 2], 0)
        top_force = self.surface_k*top
        floor_force = self.surface_k*floor
        gradient[self.surface_z_dofs] += top_force-floor_force
        energy += .5*(top_force@top + floor_force@floor)
        return energy, gradient, float(top_force.sum()), float(J.min()), x, C, float(max(top.max(), floor.max()))


class PressRig:
    def __init__(self, params, cells, dt):
        self.dt = dt
        self.foam = Foam(params, cells, dt) if params["foam_present"][0] else None
        self.n = self.foam.count if self.foam is not None else 0
        self.ball_mass = params["ball_mass_kg"]
        self.platen_mass = params["platen_mass_kg"] + params["ballast_mass_kg"]*params["ballast_present"][0]
        # Fixed outer radius and steel density. Reduced mass removes a concentric core.
        retained = self.ball_mass / BASELINE["ball_mass_kg"]
        self.inner_radius = RADIUS * (1-retained)**(1/3)
        inertia = .4*self.ball_mass*(RADIUS**5-self.inner_radius**5)/(RADIUS**3-self.inner_radius**3)
        self.friction = params["cup_contact_friction"]
        self.cup_k = params["cup_normal_stiffness_n_m"]
        self.cup_damping = params["cup_normal_damping_n_s_m"]
        self.rolling_length = params["rolling_resistance_length_m"]
        self.tangent = np.array([math.cos(RAMP_ANGLE), -math.sin(RAMP_ANGLE)])
        self.ramp_accel = G*math.sin(RAMP_ANGLE)/(1 + inertia/(self.ball_mass*RADIUS**2))
        self.exit_time = math.sqrt(2*RAMP_LENGTH/self.ramp_accel)
        self.exit_speed = self.exit_time*self.ramp_accel
        self.rigid_masses = np.array([self.platen_mass, self.ball_mass, self.ball_mass, FLAG_INERTIA, inertia])
        self.masses = np.r_[self.foam.mass_vector if self.foam is not None else [], self.rigid_masses]
        self.q = np.r_[self.foam.rest[self.foam.free].ravel() if self.foam is not None else [],
                       PLATE_BOTTOM, RAMP_END - RAMP_LENGTH*self.tangent, 0., 0.]
        self.velocity = np.zeros_like(self.q)
        effective_k = self.cup_k + self.cup_damping/dt
        d = self.rigid_masses/dt**2 + [CONTACT_MODULUS*np.prod(FOAM_SIZE[:2])+effective_k,
                                        3*effective_k, 3*effective_k, .025, 25.]
        self.scale = 1/np.sqrt(np.r_[self.foam.diagonal if self.foam is not None else [], d])
        self.rail = None                 # (t0, distance, speed) once a timed mass edit changed the rolling law
        # DELETE steel_ball (ball_present [0]): the ball's coordinates stay parked where it would start, with no
        # gravity, contact or inertia coupling, so platen, foam and flag evolve as if no ball were there.
        self.ball_present = bool(params.get("ball_present", [1])[0])
        self.cup_bounds = (
            ((-PLATE_HALF_LENGTH, 0.), (PLATE_HALF_LENGTH, CUP_FLOOR)),
            ((-CUP_OUTER_RADIUS, CUP_FLOOR), (-CUP_RADIUS, CUP_RIM)),
            ((CUP_RADIUS, CUP_FLOOR), (CUP_OUTER_RADIUS, CUP_RIM)),
        )

    def set_ball_mass(self, mass, t):
        """Timed SET steel_ball.mass at time t: the ball keeps its position, velocity and spin; its mass, hollow core,
        inertia (and, while it rolls on the track, its rolling acceleration and rail exit) change from t on."""
        on_rail = t < self.exit_time
        if on_rail:
            if self.rail is None:
                d0, v0 = .5*self.ramp_accel*t**2, self.ramp_accel*t
            else:
                tau = t-self.rail[0]
                d0, v0 = self.rail[1]+self.rail[2]*tau+.5*self.ramp_accel*tau**2, self.rail[2]+self.ramp_accel*tau
        self.ball_mass = mass
        retained = self.ball_mass / BASELINE["ball_mass_kg"]
        self.inner_radius = RADIUS * (1-retained)**(1/3)
        inertia = .4*self.ball_mass*(RADIUS**5-self.inner_radius**5)/(RADIUS**3-self.inner_radius**3)
        self.ramp_accel = G*math.sin(RAMP_ANGLE)/(1 + inertia/(self.ball_mass*RADIUS**2))
        self.rigid_masses = np.array([self.platen_mass, self.ball_mass, self.ball_mass, FLAG_INERTIA, inertia])
        n = self.n
        self.masses = np.r_[self.masses[:n], self.rigid_masses]
        effective_k = self.cup_k + self.cup_damping/self.dt
        d = self.rigid_masses/self.dt**2 + [CONTACT_MODULUS*np.prod(FOAM_SIZE[:2])+effective_k,
                                            3*effective_k, 3*effective_k, .025, 25.]
        self.scale = np.r_[self.scale[:n], 1/np.sqrt(d)]
        if on_rail:
            self.rail = (t, d0, v0)
            a = self.ramp_accel
            tau_exit = (-v0 + math.sqrt(v0*v0 + 2*a*(RAMP_LENGTH-d0)))/a
            self.exit_time, self.exit_speed = t+tau_exit, v0+a*tau_exit
        return on_rail

    def cup_contacts(self, plate, bx, bz):
        x, z = bx, bz-plate
        contacts = {}
        for i, ((left, bottom), (right, top)) in enumerate(self.cup_bounds):
            if x < left-RADIUS or x > right+RADIUS or z < bottom-RADIUS or z > top+RADIUS:
                continue
            dx = x-min(max(x, left), right)
            dz = z-min(max(z, bottom), top)
            distance = math.hypot(dx, dz)
            if distance == 0.:
                distances = (x-left, right-x, z-bottom, top-z)
                side = min(range(4), key=distances.__getitem__)
                normal = ((-1., 0.), (1., 0.), (0., -1.), (0., 1.))[side]
                distance = -distances[side]
            else:
                normal = (dx/distance, dz/distance)
            if distance < RADIUS:
                contacts[i] = (RADIUS-distance, normal)
        return contacts

    def evaluate(self, q, predicted, released, contacts):
        n = self.n
        pz, bx, bz, angle, phi = q[n:]
        delta = q-predicted
        energy = .5*(self.masses*delta)@delta/self.dt**2
        gradient = self.masses*delta/self.dt**2
        energy += self.platen_mass*G*pz + FLAG_MASS*G*FLAG_COM*math.sin(angle)
        gradient[n] += self.platen_mass*G
        gradient[n+3] += FLAG_MASS*G*FLAG_COM*math.cos(angle)
        J, points, C = None, None, None
        overlap = 0.
        if self.foam is not None:
            e, g, normal, J, points, C, overlap = self.foam.evaluate(q[:n], pz)
            energy += e
            gradient[:n] += g
            gradient[n] -= normal
        if released:
            energy += self.ball_mass*G*bz
            gradient[n+2] += self.ball_mass*G
            for i, (depth, normal) in self.cup_contacts(pz, bx, bz).items():
                # Only approaching contact dissipates normal work. Unloading never pulls.
                closing = max(depth-contacts.get(i, (0., None))[0], 0.)
                force = self.cup_k*depth + self.cup_damping/self.dt*closing
                energy += .5*(self.cup_k*depth**2 + self.cup_damping/self.dt*closing**2)
                gradient[n] += force*normal[1]
                gradient[n+1] -= force*normal[0]
                gradient[n+2] -= force*normal[1]
                overlap = max(overlap, depth)
            dx, dz = q[n+1:n+3]-self.q[n+1:n+3]
            dp = pz-self.q[n]
            dphi = phi-self.q[-1]
            for depth, normal in contacts.values():
                force = self.cup_k*depth
                tx, tz = -normal[1], normal[0]
                slip = tx*dx+tz*(dz-dp)+RADIUS*dphi
                length = math.hypot(slip, .001*self.dt)
                drag = self.friction*force*slip/length
                energy += self.friction*force*length
                gradient[n:n+3] += drag*np.array([-tz, tx, tz])
                gradient[-1] += drag*RADIUS
                roll = math.hypot(dphi, .05*self.dt)
                energy += self.rolling_length*force*roll
                gradient[-1] += self.rolling_length*force*dphi/roll
        ca, sa = math.cos(angle), math.sin(angle)
        lever = Hinge_Z + ((EDGE_X-Hinge_X)*sa+.001)/ca
        depth = max(lever-pz, 0.)
        force = 5000.*depth
        energy += .5*force*depth
        gradient[n] -= force
        gradient[n+3] += force*(EDGE_X-Hinge_X+.001*sa)/ca**2
        da = angle-self.q[n+3]
        energy += .5e-5/self.dt*da**2
        gradient[n+3] += 1e-5/self.dt*da
        return energy, gradient, J, points, C, float(max(overlap, depth))

    def advance(self, t):
        n = self.n
        origin = self.q+self.dt*self.velocity
        on_rail = t <= self.exit_time and self.ball_present
        departure_step = self.ball_present and not on_rail and t-self.dt <= self.exit_time
        prescribed = on_rail or departure_step or not self.ball_present
        if not self.ball_present:
            v, speed = np.zeros(2), 0.
        elif on_rail:
            if self.rail is None:
                distance = .5*self.ramp_accel*t**2
                speed = self.ramp_accel*t
            else:                        # rolling law after a timed mass change on the track
                tau = t-self.rail[0]
                distance = self.rail[1]+self.rail[2]*tau+.5*self.ramp_accel*tau**2
                speed = self.rail[2]+self.ramp_accel*tau
            v = speed*self.tangent
            origin[n+1:n+3] = RAMP_END-(RAMP_LENGTH-distance)*self.tangent
            origin[-1] = distance/RADIUS
        elif departure_step:
            tau = t-self.exit_time
            speed = self.exit_speed
            v = speed*self.tangent + [0., -G*tau]
            origin[n+1:n+3] = RAMP_END + speed*self.tangent*tau + [0., -.5*G*tau**2]
            origin[-1] = (RAMP_LENGTH+speed*tau)/RADIUS
        bounds = [(None, None)]*len(origin)
        bounds[n] = ((PLATEN_STOP_Z-origin[n])/self.scale[n], None)
        bounds[-2] = (-origin[-2]/self.scale[-2], (FLAG_LIMIT-origin[-2])/self.scale[-2])
        if prescribed:
            for i in (n+1, n+2, len(origin)-1):
                bounds[i] = (0., 0.)
        contacts = self.cup_contacts(*self.q[n:n+3]) if not prescribed else {}

        def objective(y):
            value, grad, *_ = self.evaluate(origin+y*self.scale, origin, not prescribed, contacts)
            return value, grad*self.scale

        fit = minimize(objective, np.zeros_like(origin), jac=True, bounds=bounds, method="L-BFGS-B",
                       options={"maxiter": 600, "maxls": 45, "maxcor": 24, "gtol": 2e-7, "ftol": 5e-13})
        q = origin+fit.x*self.scale
        _, g, J, points, C, overlap = self.evaluate(q, origin, not prescribed, contacts)
        if not fit.success or not np.isfinite(q).all() or (J is not None and J <= .10):
            raise RuntimeError(f"Invalid step at {t:.7f} s, J={J}, {fit.message}")
        self.velocity = (q-self.q)/self.dt
        if prescribed:
            self.velocity[n+1:n+3] = v
            self.velocity[-1] = speed/RADIUS
            if departure_step and self.cup_contacts(*q[n:n+3]):
                raise RuntimeError("The analytical departure step reached cup contact")
        self.q = q
        if self.foam is not None:
            self.foam.points, self.foam.previous_C = points, C
        at_stop = q[n] <= PLATEN_STOP_Z + 1e-9
        ball_overlap = max((depth for depth, _ in self.cup_contacts(*q[n:n+3]).values()), default=0.) if not prescribed else 0.
        return (J, overlap, fit.nit, at_stop, ball_overlap, max(0., float(g[n])) if at_stop else 0.)


def simulate(case, output, step_hz=STEP_HZ, duration=4., cells=CELLS):
    if step_hz % CACHE_FPS or abs(duration*CACHE_FPS-round(duration*CACHE_FPS)) > 1e-9:
        raise ValueError("The integration grid must contain every 96 Hz native sample.")
    output.mkdir(parents=True, exist_ok=True)
    if any(output.iterdir()):
        raise FileExistsError(output)
    params = parameters(case)
    rig = PressRig(params, cells, 1/step_hz)
    switch = None
    if case in TIMED_DSL:
        frame, change = timed_schedule(case)
        if set(change) != {"ball_mass_kg"}:
            raise ValueError("Only a timed ball-mass change is implemented")
        switch = {"frame": frame, "step": (frame-1)*step_hz//24, "time_s": (frame-1)/24, "change": change,
                  "before": {key: params[key] for key in change}}
        if switch["step"]*24 != (frame-1)*step_hz:
            raise ValueError("The edit frame is not on the integration grid")
    times, points, states, spins, speeds = [], [], [], [], []
    records = []
    min_ballast_clearance = math.inf
    max_captured_abs_x = 0.
    start = time.monotonic()
    count = round(duration*step_hz)
    for step in range(count+1):
        t = step/step_hz
        if step % (step_hz//CACHE_FPS) == 0:
            times.append(t)
            points.append(rig.foam.points.copy() if rig.foam is not None else np.empty((0, 3)))
            states.append(rig.q[-5:-1].copy())
            spins.append(rig.q[-1])
            speeds.append(rig.velocity[-5:].copy())
        if switch is not None and step == switch["step"]:
            switch["ball_on_track"] = rig.set_ball_mass(switch["change"]["ball_mass_kg"], t)
            switch.update(exit_time_s=rig.exit_time, exit_speed_m_s=rig.exit_speed)
            print(case, f"timed edit at {t:.6f}s: ball mass -> {rig.ball_mass}", flush=True)
        if step % (step_hz//4) == 0:
            print(case, f"{t:.2f}s", f"platen={rig.q[-5]*1000:.2f}mm",
                  f"flag={math.degrees(rig.q[-2]):.1f}deg", f"wall={time.monotonic()-start:.1f}s", flush=True)
        if step < count:
            records.append(rig.advance((step+1)/step_hz))
            plate, bx, bz, _, _ = rig.q[-5:]
            if rig.ball_present and t > rig.exit_time + .17:
                max_captured_abs_x = max(max_captured_abs_x, abs(bx))
                if abs(bx) >= CUP_RADIUS or bz < plate+CUP_FLOOR+RADIUS-.001:
                    raise RuntimeError(f"The steel ball escaped the modelled capture at {t:.6f} s.")
            if params["ballast_present"][0]:
                dx = max(params["ballast_inner_radius_m"]-abs(bx),
                         abs(bx)-params["ballast_outer_radius_m"], 0.)
                z = bz-plate-CUP_FLOOR
                dz = max(-z, z-params["ballast_height_m"], 0.)
                min_ballast_clearance = min(min_ballast_clearance, math.hypot(dx, dz)-RADIUS)
                if min_ballast_clearance < 0.:
                    raise RuntimeError("The ball contacted the added collar outside the modelled cup contacts.")
    cache = output/"simulation.npz"
    foam = rig.foam
    np.savez_compressed(cache, times=np.array(times), states=np.array(states), ball_spin_rad=np.array(spins),
                        rigid_velocity=np.array(speeds), elastic_positions=np.array(points),
                        elastic_rest=foam.rest if foam is not None else np.empty((0, 3)),
                        elastic_tets=foam.tets if foam is not None else np.empty((0, 4), np.int32),
                        elastic_faces=foam.faces if foam is not None else np.empty((0, 3), np.int32))
    min_j, overlap, iterations, stops, ball_overlap, stop_force = zip(*records)
    report = {
        "case": case, "edit_dsl": TIMED_DSL[case] if switch else CASE_DSL[case], "physics": params, "dt_s": rig.dt,
        "timed_edit": None if switch is None else {**switch, "physics_after_edit": {**params, **switch["change"]},
                                                   "method": "same solve: source parameters until the edit step, edited value from there on"}, "duration_s": duration,
        "grid_cells": list(cells), "cache_fps": CACHE_FPS, "solver_host": socket.gethostname(),
        "solver": "Implicit tetrahedral foam with finite-strain objective viscosity, coupled planar rigid contact",
        "ball_inner_radius_m": rig.inner_radius, "ball_inertia_kg_m2": float(rig.rigid_masses[-1]),
        "ball_rail_exit_s": rig.exit_time, "ball_rail_exit_speed_m_s": rig.exit_speed,
        "moving_platen_mass_kg": rig.platen_mass, "platen_stop_z_m": PLATEN_STOP_Z,
        "minimum_J": min(min_j) if foam is not None else None, "max_contact_compliance_m": max(overlap),
        "max_ball_contact_compliance_m": max(ball_overlap), "max_step_iterations": int(max(iterations)),
        "max_captured_ball_abs_x_m": max_captured_abs_x,
        "min_ball_to_ballast_clearance_m": min_ballast_clearance if params["ballast_present"][0] else None,
        "first_cup_contact_s": next((i/step_hz for i, depth in enumerate(ball_overlap, 1) if depth > 0), None),
        "first_lower_stop_s": next((i/step_hz for i, stopped in enumerate(stops, 1) if stopped), None),
        "lower_stop_duration_s": sum(stops)/step_hz, "max_lower_stop_reaction_N": max(stop_force),
        "material_calibrated": False, "cache_sha256": hashlib.sha256(cache.read_bytes()).hexdigest(),
        "elapsed_s": time.monotonic()-start,
    }
    (output/"config.json").write_text(json.dumps(report, indent=2, ensure_ascii=False)+"\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case", required=True, choices=[*CASE_DSL, *TIMED_DSL])
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--step-hz", type=int, default=STEP_HZ)
    parser.add_argument("--duration", type=float, default=4.)
    parser.add_argument("--cells", type=int, nargs=3, default=CELLS)
    args = parser.parse_args()
    simulate(args.case, args.out, args.step_hz, args.duration, args.cells)


if __name__ == "__main__":
    main()
