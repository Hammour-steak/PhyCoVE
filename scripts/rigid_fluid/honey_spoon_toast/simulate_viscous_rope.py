"""Genesis reservoir + 3-D discrete viscous rope + thin-film puddle.

Fluid particles that cross the spoon lip in the cached Genesis DFSPH run are
removed from the bulk and extruded, volume for volume, through a fixed lip
nozzle into a discrete viscous rope in the spirit of Discrete Viscous Threads
(Bergou et al. 2010): lumped node masses, gravity, implicit Trouton stretching
viscosity 3*mu*A, implicit viscous bending 3*mu*I and capillary tension.

Model features:
  * inflow enters at the root, so the strand is fed from above and stays
    continuous instead of starving behind the pendant head;
  * honey reaching the toast or the puddle surface joins a thin-film gravity
    current h_t = div(rho g h^3 / (3 mu) grad h) on the toast, so the puddle
    builds up as a mound and spreads instead of being a fixed Gaussian bump.
Landed rope is not kept as coils: robust rope-on-pile contact was tried and
stacked into towers; at the shot's scale the landing zone is ~1.5 cm wide.
This is NOT a full 3-D free-surface solve and is not experimentally calibrated.
"""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
import argparse
import json
import math
from pathlib import Path
import time

import numpy as np
import scipy.sparse as sp
from scipy.sparse.linalg import spsolve
from spoon_reservoir_geometry import SPOON_CENTER, BOWL_RX, BOWL_RY, rotation_y

G = 9.81


class Film:
    """Gravity-driven thin film on the flat toast top (upwind h^3 mobility)."""

    def __init__(self, center_xy, z, rho, mu, size=.05, cell=.0004):
        self.n = int(round(size/cell))
        self.cell = cell
        self.origin = np.asarray(center_xy, float)-.5*self.n*cell
        self.z = z
        self.h = np.zeros((self.n, self.n))
        self.mobility = rho*G/(3*mu)
        self.lost = 0.

    def volume(self):
        return float(self.h.sum())*self.cell**2

    def height(self, xy):
        f = (np.atleast_2d(xy)[:, :2]-self.origin)/self.cell-.5
        i = np.clip(np.floor(f).astype(int), 0, self.n-2)
        t = np.clip(f-i, 0, 1)
        h = self.h
        return ((1-t[:, 0])*(1-t[:, 1])*h[i[:, 0], i[:, 1]]+t[:, 0]*(1-t[:, 1])*h[i[:, 0]+1, i[:, 1]]
                + (1-t[:, 0])*t[:, 1]*h[i[:, 0], i[:, 1]+1]+t[:, 0]*t[:, 1]*h[i[:, 0]+1, i[:, 1]+1])

    def deposit(self, xy, volume, sigma):
        sigma = max(sigma, .75*self.cell)
        c = (np.asarray(xy[:2])-self.origin)/self.cell-.5
        reach = int(math.ceil(3*sigma/self.cell))+1
        i0, j0 = int(round(c[0])), int(round(c[1]))
        ii = np.arange(i0-reach, i0+reach+1)
        jj = np.arange(j0-reach, j0+reach+1)
        ii, jj = ii[(ii >= 0) & (ii < self.n)], jj[(jj >= 0) & (jj < self.n)]
        if not len(ii) or not len(jj):
            self.lost += volume
            return
        w = np.exp(-.5*(((ii[:, None]-c[0])**2+(jj[None, :]-c[1])**2)*(self.cell/sigma)**2))
        self.h[np.ix_(ii, jj)] += volume*w/(w.sum()*self.cell**2)

    def step(self, dt):
        done = 0.
        while done < dt:
            hmax = self.h.max()
            if hmax <= 0:
                return
            sub = min(dt-done, .2*self.cell**2/(self.mobility*hmax**3))
            h = self.h
            out = np.zeros_like(h)
            for axis in (0, 1):
                a = h[:-1, :] if axis == 0 else h[:, :-1]
                b = h[1:, :] if axis == 0 else h[:, 1:]
                # Flux a->b with upstream mobility: an empty cell cannot donate.
                up = np.where(b > a, b, a)
                flux = -self.mobility*up**3*(b-a)/self.cell
                if axis == 0:
                    out[:-1, :] += flux
                    out[1:, :] -= flux
                else:
                    out[:, :-1] += flux
                    out[:, 1:] -= flux
            self.h -= sub*out/self.cell
            done += sub


class Rope:
    """Chain of nodes; edge e joins node e and e+1 and carries a fixed volume.

    Node 0 is the kinematic extrusion node moving out of the lip nozzle.
    Inactive edges (on=False) separate detached pieces.
    """

    def __init__(self, nozzle, direction, nozzle_radius, rho, mu, sigma, args, rng):
        self.nozzle, self.dir = nozzle, direction/np.linalg.norm(direction)
        self.rn, self.rho, self.mu, self.sigma = nozzle_radius, rho, mu, sigma
        self.a, self.rng = args, rng
        self.x = np.zeros((0, 3))
        self.v = np.zeros((0, 3))
        self.vol = np.zeros(0)
        self.on = np.zeros(0, bool)
        self.pending = 0.
        self.u = 0.
        self.breaks = []

    # -- geometry helpers -------------------------------------------------
    def lengths(self):
        return np.maximum(np.linalg.norm(self.x[1:]-self.x[:-1], axis=1), 1e-7)

    def degree(self):
        deg = np.zeros(len(self.x), int)
        deg[:-1] += self.on
        deg[1:] += self.on
        return deg

    def radii(self, L=None):
        """Edge radius (0 for inactive edges).

        An edge squeezed below half the remeshing length is not allowed to
        inflate into a disc, and a strand-end edge (pendant or leading drop)
        is never wider than the sphere of its volume.
        """
        L = self.lengths() if L is None else L
        area = self.vol/np.maximum(L, .5*self.a.min_edge)
        deg = self.degree()
        end = (deg[:-1] == 1) | (deg[1:] == 1)
        area = np.where(end, np.minimum(area, math.pi*(3*self.vol/(4*math.pi))**(2/3)), area)
        return np.where(self.on, np.sqrt(area/math.pi), 0.)

    def node_radius(self, L=None):
        r = self.radii(L)
        s, c = np.zeros(len(self.x)), np.zeros(len(self.x))
        s[:-1] += r**2
        s[1:] += r**2
        c[:-1] += self.on
        c[1:] += self.on
        return np.sqrt(s/np.maximum(c, 1))

    def rope_volume(self):
        return float((self.vol*self.on).sum())

    # -- topology edits ---------------------------------------------------
    def _insert_node(self, k, x, v):
        self.x = np.insert(self.x, k, x, axis=0)
        self.v = np.insert(self.v, k, v, axis=0)

    def _delete_node(self, k):
        self.x = np.delete(self.x, k, axis=0)
        self.v = np.delete(self.v, k, axis=0)

    def extrude(self, draw, dt):
        """Push `draw` m^3 out of the nozzle during dt (kinematic root)."""
        self.u = draw/dt/(math.pi*self.rn**2)
        self.pending += draw
        if not len(self.x):
            self._insert_node(0, self.nozzle, np.zeros(3))
        self.v[0] = self.u*self.dir

    def spawn(self):
        travel = float(np.dot(self.x[0]-self.nozzle, self.dir))
        if travel < self.a.spawn_length:
            return
        # Release the kinematic node and start a new one at the nozzle; the
        # segment between them holds exactly the volume extruded meanwhile.
        noise = self.rng.normal(0, self.a.lateral_noise, 3)
        noise -= np.dot(noise, self.dir)*self.dir
        self.x[0] += noise
        self._insert_node(0, self.nozzle, self.u*self.dir)
        self.vol = np.insert(self.vol, 0, self.pending)
        self.on = np.insert(self.on, 0, True)
        self.pending = 0.

    # -- dynamics -----------------------------------------------------------
    def solve(self, dt):
        """Backward-Euler step of gravity + viscous stretching/bending."""
        N = len(self.x)
        if N < 2:
            return
        x, on = self.x, self.on
        L = self.lengths()
        d = (x[1:]-x[:-1])/L[:, None]
        A = np.where(on, self.vol/L, 0.)
        deg = self.degree()
        m = np.zeros(N)
        m[:-1] += .5*self.rho*self.vol*on
        m[1:] += .5*self.rho*self.vol*on
        free = deg > 0
        free[0] = False
        if not free.any():
            return
        force = np.zeros((N, 3))
        force[:, 2] -= m*G
        e = np.flatnonzero(on)
        i, j = e, e+1
        if self.sigma > 0:
            r_e = np.sqrt(A[e]/math.pi)
            tension = math.pi*self.sigma*r_e
            tip = (deg[i] == 1) | (deg[j] == 1)
            tension[tip] *= np.clip(1-r_e[tip]/L[e][tip], 0, 1)
            np.add.at(force, i, tension[:, None]*d[e])
            np.add.at(force, j, -tension[:, None]*d[e])
        # Trouton extensional viscosity: axial force 3*mu*A*(dL/dt)/L
        c = 3*self.mu*A[e]/L[e]
        K = c[:, None, None]*d[e][:, :, None]*d[e][:, None, :]
        rows = [i, j, i, j]
        cols = [i, j, j, i]
        mats = [K, K, -K, -K]
        # viscous bending 3*mu*I on the curvature rate at interior nodes
        k = np.flatnonzero(on[:-1] & on[1:])+1
        if len(k):
            h_, j_ = k-1, k+1
            l1, l2 = L[k-1], L[k]
            t = x[j_]-x[h_]
            t /= np.maximum(np.linalg.norm(t, axis=1), 1e-12)[:, None]
            P = np.eye(3)[None]-t[:, :, None]*t[:, None, :]
            r2 = .5*(A[k-1]+A[k])/math.pi
            w = 3*self.mu*math.pi*r2**2/4/(.5*(l1+l2))
            coef = (1/l1, -(1/l1+1/l2), 1/l2)
            nodes = (h_, k, j_)
            for p in range(3):
                for q in range(3):
                    rows.append(nodes[p])
                    cols.append(nodes[q])
                    mats.append((w*coef[p]*coef[q])[:, None, None]*P)
        rows, cols, mats = np.concatenate(rows), np.concatenate(cols), np.concatenate(mats)
        keep = free[rows]
        rows, cols, mats = rows[keep], cols[keep], mats[keep]
        index = np.full(N, -1)
        fidx = np.flatnonzero(free)
        index[fidx] = np.arange(len(fidx))
        rhs = m[fidx, None]*self.v[fidx]+dt*force[fidx]
        bnd = ~free[cols]
        if bnd.any():
            np.add.at(rhs, index[rows[bnd]], -dt*np.einsum('nab,nb->na', mats[bnd], self.v[cols[bnd]]))
        inner = ~bnd
        rr, cc, mm = index[rows[inner]], index[cols[inner]], dt*mats[inner]
        ar = (3*rr[:, None, None]+np.arange(3)[None, :, None]).repeat(3, 2)
        ac = (3*cc[:, None, None]+np.arange(3)[None, None, :]).repeat(3, 1)
        nf = len(fidx)
        M = sp.coo_matrix((np.r_[mm.ravel(), np.repeat(m[fidx], 3)],
                           (np.r_[ar.ravel(), np.arange(3*nf)], np.r_[ac.ravel(), np.arange(3*nf)])),
                          shape=(3*nf, 3*nf)).tocsc()
        self.v[fidx] = spsolve(M, rhs.ravel()).reshape(-1, 3)

    def absorb(self, film):
        """Strand reaching the toast or puddle surface joins the film."""
        if len(self.x) < 2:
            return 0.
        r = self.node_radius()
        idx = np.flatnonzero(self.degree() > 0)
        idx = idx[idx > 0]
        if not len(idx):
            return 0.
        surface = film.z+film.height(self.x[idx])
        hit = idx[self.x[idx, 2]-self.a.contact_fraction*r[idx] <= surface]
        if not len(hit):
            return 0.
        rad = self.radii()
        absorbed = 0.
        for n in hit:
            for e in (n-1, n):
                if 0 <= e < len(self.vol) and self.on[e]:
                    film.deposit(self.x[n], self.vol[e], rad[e])
                    absorbed += self.vol[e]
                    self.vol[e], self.on[e] = 0., False
        self._drop_isolated()
        return absorbed

    def _drop_isolated(self):
        deg = self.degree()
        for k in np.flatnonzero(deg == 0)[::-1]:
            if k == 0:
                continue
            idx = k if k < len(self.vol) else k-1
            self.vol = np.delete(self.vol, idx)
            self.on = np.delete(self.on, idx)
            self._delete_node(k)

    def remesh(self):
        a = self.a
        L = self.lengths()
        for e in np.flatnonzero(self.on & (L > a.max_edge))[::-1]:
            self._insert_node(e+1, .5*(self.x[e]+self.x[e+1]), .5*(self.v[e]+self.v[e+1]))
            half = .5*self.vol[e]
            self.vol[e] = half
            self.vol = np.insert(self.vol, e+1, half)
            self.on = np.insert(self.on, e+1, True)
        e = len(self.vol)-1
        while e >= 0:
            if e < len(self.vol) and self.on[e]:
                length = np.linalg.norm(self.x[e+1]-self.x[e])
                if length < a.min_edge:
                    deg = self.degree()
                    for k in (e+1, e):
                        if 0 < k < len(self.x)-1 and deg[k] == 2:
                            # merge edges k-1 and k into one, conserving volume
                            self.vol[k-1] += self.vol[k]
                            self.vol = np.delete(self.vol, k)
                            self.on = np.delete(self.on, k)
                            self._delete_node(k)
                            break
            e -= 1

    def breakup(self, t):
        """Sub-resolution necks pinch off; the neck volume goes to both sides."""
        r = self.radii()
        L = self.lengths()
        deg = self.degree()
        for k in np.flatnonzero(self.on & (r < self.a.break_radius) & (L > .0005)):
            if k == 0 or k >= len(self.vol)-1 or deg[k] != 2 or deg[k+1] != 2:
                continue
            self.vol[k-1] += .5*self.vol[k]
            self.vol[k+1] += .5*self.vol[k]
            self.breaks.append(dict(physics_time_s=t, z_m=float(.5*(self.x[k, 2]+self.x[k+1, 2])),
                                    radius_m=float(r[k])))
            self.vol[k], self.on[k] = 0., False
            return


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--source", type=Path, required=True)
    p.add_argument("--out", type=Path, required=True)
    # Honey's capillary speed sigma/mu ~ 6 mm/s is far below the 0.1-1 m/s
    # strand speeds, so rod capillary tension defaults to off.
    p.add_argument("--sigma", type=float, default=0.)
    p.add_argument("--dt", type=float, default=1e-4)
    p.add_argument("--nozzle-radius", type=float, default=.0025)
    # The lip flux arrives as whole SPH particles (1-17 per frame); the
    # meniscus buffer smooths that discretization noise out of the strand.
    p.add_argument("--meniscus-time", type=float, default=.2,
                   help="relaxation time of the lip meniscus buffer (s)")
    p.add_argument("--spawn-length", type=float, default=.0008)
    p.add_argument("--max-edge", type=float, default=.0010)
    p.add_argument("--min-edge", type=float, default=.00030)
    p.add_argument("--break-radius", type=float, default=.00005)
    p.add_argument("--lateral-noise", type=float, default=2e-5)
    p.add_argument("--contact-fraction", type=float, default=.5,
                   help="a node joins the film once its centre is this many radii above the surface")
    p.add_argument("--film-cell", type=float, default=.0004)
    p.add_argument("--landing-height", type=float, default=.7995,
                   help="Measured top of the flat receiving surface in metres")
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--frames", type=int, default=96)
    p.add_argument("--inflow", type=Path,
                   help="debug: per-frame lip crossing counts (json) instead of reading particles")
    args = p.parse_args()
    args.out.mkdir(parents=True, exist_ok=False)
    (args.out/"particles").mkdir()
    (args.out/"rope_states").mkdir()
    inflow = json.loads(args.inflow.read_text()) if args.inflow else None
    source = inflow["report"] if inflow else json.loads((args.source/"simulation_report.json").read_text())
    dx = source["numerics"]["dx_m"]
    rho = source["physics"]["honey_density_kg_m3"]
    mu = rho*source["physics"]["honey_kinematic_viscosity_m2_s"]
    particle_volume = .8*dx**3
    removed = np.zeros(source["particles"], dtype=bool)
    nozzle = SPOON_CENTER+rotation_y(15)@np.array((BOWL_RX, 0, .0006))
    z_toast = args.landing_height
    dt_frame = source["numerics"]["playback_time_scale"]/24
    rng = np.random.default_rng(args.seed)
    rope = Rope(nozzle, np.array((0., 0., -1.)), args.nozzle_radius, rho, mu, args.sigma, args, rng)
    film = Film(nozzle[:2], z_toast, rho, mu, cell=args.film_cell)
    buffer = transferred = 0.
    rows, first_contact = [], None
    start = time.monotonic()
    for f in range(1, args.frames+1):
        if inflow:
            incoming = inflow["counts"][f-1]*particle_volume
        else:
            state = np.load(args.source/"particles"/f"frame_{f:04d}.npz")
            pos, vel = state["honey_pos"], state["honey_vel"]
            q = (pos-SPOON_CENTER)@rotation_y(15)
            r2 = (q[:, 0]/BOWL_RX)**2+(q[:, 1]/BOWL_RY)**2
            leaving = (r2 > 1.02) & (q[:, 0] > .020) & (~removed)
            incoming = float(leaving.sum())*particle_volume
            removed |= leaving
        transferred += incoming
        steps = 0 if f == 1 else math.ceil(dt_frame/args.dt)
        dt = dt_frame/max(steps, 1)
        absorbed = 0.
        for sub in range(steps):
            t = (f-2)*dt_frame+(sub+1)*dt
            buffer += incoming/steps
            draw = buffer*min(1., dt/args.meniscus_time)
            if buffer > 0:
                buffer -= draw
                rope.extrude(draw, dt)
            rope.solve(dt)
            rope.x += dt*rope.v
            film.step(dt)
            absorbed += rope.absorb(film)
            if len(rope.x):
                rope.spawn()
                rope.remesh()
                rope.breakup(t)
            if not np.isfinite(rope.x).all():
                raise RuntimeError(f"nonfinite rope at frame {f}")
        if absorbed > 0 and first_contact is None:
            first_contact = f
        total = buffer+rope.pending+rope.rope_volume()+film.volume()+film.lost
        if abs(total-transferred) > max(1e-15, transferred*1e-9):
            raise RuntimeError(f"volume conservation failed: {total} != {transferred}")
        if film.h.min() < -1e-7:
            raise RuntimeError(f"negative film height {film.h.min()}")
        if not inflow:
            np.savez_compressed(args.out/"particles"/f"frame_{f:04d}.npz",
                                honey_pos=pos[~removed], honey_vel=vel[~removed])
        L = rope.lengths() if len(rope.x) > 1 else np.zeros(0)
        radius = rope.radii(L) if len(rope.x) > 1 else np.zeros(0)
        np.savez_compressed(args.out/"rope_states"/f"rope_{f:04d}.npz",
                            x=rope.x, v=rope.v, vol=rope.vol, on=rope.on, radius=radius,
                            film_h=film.h, film_origin=film.origin, film_cell=film.cell,
                            film_z=film.z, nozzle=nozzle, nozzle_radius=args.nozzle_radius,
                            pending=rope.pending, buffer=buffer)
        live = radius[rope.on] if len(radius) else np.zeros(0)
        h = film.h
        wet = h > 2.5e-4
        row = dict(frame=f, playback_time_s=(f-1)/24, physics_time_s=(f-1)*dt_frame, spoon_tilt_deg=15.,
                   reservoir_particles=None if inflow else int((~removed).sum()),
                   transferred_volume_ml=transferred*1e6, meniscus_buffer_volume_ml=(buffer+rope.pending)*1e6,
                   thread_volume_ml=rope.rope_volume()*1e6, deposited_volume_ml=film.volume()*1e6,
                   absorbed_this_frame_ml=absorbed*1e6, extrusion_speed_m_s=rope.u,
                   nodes=int(len(rope.x)), pieces=int(1+(~rope.on).sum()) if len(rope.on) else int(len(rope.x) > 0),
                   min_thread_radius_m=float(live.min()) if len(live) else 0.,
                   max_thread_radius_m=float(live.max()) if len(live) else 0.,
                   max_speed_m_s=float(np.linalg.norm(rope.v, axis=1).max()) if len(rope.x) else 0.,
                   lowest_thread_z_above_toast_m=float(rope.x[:, 2].min()-z_toast) if len(rope.x) else None,
                   max_lateral_offset_m=float(np.linalg.norm(rope.x[:, :2]-nozzle[:2], axis=1).max()) if len(rope.x) else 0.,
                   puddle_max_height_m=float(h.max()), puddle_wet_radius_m=float(math.sqrt(wet.sum()*film.cell**2/math.pi)),
                   breakup_count=len(rope.breaks), mean_edge_m=float(L.mean()) if len(L) else 0.)
        if row["max_thread_radius_m"] > .006:
            raise RuntimeError(f"degenerate thread radius at frame {f}: {row['max_thread_radius_m']}")
        rows.append(row)
        if f == 1 or f % 4 == 0:
            print("ROPE", json.dumps(row), flush=True)
    report = dict(source)
    report.update(
        solver="Genesis SPH reservoir + 3-D discrete viscous rope + thin-film gravity current",
        hybrid_model=dict(
            rho_kg_m3=rho, dynamic_viscosity_Pa_s=mu, surface_tension_N_m=args.sigma, dt_s=args.dt,
            nozzle_m=nozzle.tolist(), nozzle_radius_m=args.nozzle_radius, meniscus_time_s=args.meniscus_time,
            spawn_length_m=args.spawn_length, edge_length_range_m=[args.min_edge, args.max_edge],
            break_radius_m=args.break_radius, lateral_noise_m=args.lateral_noise, seed=args.seed,
            contact_fraction=args.contact_fraction, film_cell_m=args.film_cell,
            toast_top_z_m=z_toast, particle_volume_m3=particle_volume,
            landing_surface_z_m=z_toast,
            incoming_mass_source="only original SPH particles crossing the front bowl lip",
            volume_conservation_relative_tolerance=1e-9,
            assumptions=["one-way transfer from Genesis reservoir; no feedback to bulk",
                         "lip inflow extruded through a fixed circular nozzle at the lowest rim point",
                         "rod model: Trouton stretching 3*mu*A and viscous bending 3*mu*I; no twist; "
                         "rod capillary tension off by default (sigma/mu << strand speed)",
                         "strand reaching the toast or puddle joins the film at once; no rope coiling on the pile",
                         "puddle: lubrication gravity current, no surface tension, flat non-porous toast"],
            reference="https://www.cs.columbia.edu/cg/threads/"),
        source_frames=source["frames"], frames=rows, breakup_events=rope.breaks,
        first_contact_frame=first_contact, film_volume_lost_outside_grid_ml=film.lost*1e6,
        thread_simulation_seconds=time.monotonic()-start)
    (args.out/"simulation_report.json").write_text(json.dumps(report, indent=2)+"\n")


if __name__ == "__main__":
    main()
