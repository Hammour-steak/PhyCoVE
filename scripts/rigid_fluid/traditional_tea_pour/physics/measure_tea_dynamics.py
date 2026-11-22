"""Particle-space motion measures independent of materials and mesh smoothing."""
import argparse
import json
from pathlib import Path

import numpy as np
from scipy.spatial import cKDTree

p = argparse.ArgumentParser()
p.add_argument("cases", type=Path, nargs="+")
p.add_argument("--frames", type=int, nargs="+", default=[20,24,48,72,84,90,96])
p.add_argument("--all-frames", action="store_true")
a = p.parse_args()
for case in a.cases:
    case = case.resolve()
    experiment = json.loads((case / "experiment.json").read_text())
    d = experiment["after"]["particle_size_m"]
    mass = experiment["after"]["particle_mass_kg"]
    geometry = np.load(case / "actual_inner_open.npz")
    centre = geometry["vertices"][geometry["rim_indices"], :2].mean(0)
    floor = geometry["vertices"][:, 2].min()
    rim = geometry["vertices"][geometry["rim_indices"], 2].min()
    rows = {}
    for f in (range(1,97) if a.all_frames else a.frames):
        path = case / "particles" / f"frame_{f:04d}.npz"
        if not path.exists():
            continue
        with np.load(path) as z:
            pos, vel = z["pos"].astype(float), z["vel"].astype(float)
        radial = np.linalg.norm(pos[:, :2] - centre, axis=1)
        bulk = (radial < .018) & (pos[:, 2] > floor+2*d) & (pos[:, 2] < rim-.003)
        indices = np.flatnonzero(bulk)
        if len(indices) > 4096:
            indices = indices[np.linspace(0, len(indices)-1, 4096).astype(int)]
        row = {"interior_sample_particles": len(indices),
               "total_kinetic_energy_J": .5*mass*float((vel**2).sum())}
        if len(indices):
            dist, neighbours = cKDTree(pos).query(pos[indices], k=min(24,len(pos)))
            weights = np.maximum(1.-dist/(2*d), 0.)**2
            weights[:, 0] = 0.
            mean = (vel[neighbours]*weights[...,None]).sum(1)/np.maximum(weights.sum(1,keepdims=True),1e-12)
            incoherent = np.linalg.norm(vel[indices]-mean, axis=1)
            row.update(interior_median_speed_m_s=float(np.median(np.linalg.norm(vel[indices],axis=1))),
                       local_velocity_residual_rms_m_s=float(np.sqrt((incoherent**2).mean())),
                       local_velocity_residual_median_m_s=float(np.median(incoherent)),
                       local_velocity_residual_p95_m_s=float(np.percentile(incoherent,95)),
                       interior_height_p99_m=float(np.percentile(pos[bulk,2],99)))
        landed = (pos[:,2] < .003) & (radial>.042)
        speed = np.linalg.norm(vel,axis=1)
        old_side = (np.abs(np.abs(pos[:,0])-.075)<2*d) | (np.abs(np.abs(pos[:,1])-.065)<2*d)
        row.update(landed_droplets_count=int(landed.sum()),
                   landed_median_speed_m_s=float(np.median(speed[landed])) if landed.any() else 0.,
                   particles_touching_old_rectangular_sides=int((old_side & landed).sum()),
                   maximum_abs_xy_m=np.max(np.abs(pos[:,:2]),axis=0).tolist() if len(pos) else [0.,0.])
        bounds=experiment["after"].get("domain_bounds_m",[[-.075,-.065,-.012],[.075,.065,.16]])
        side_dist=np.minimum(pos[:,:2]-np.array(bounds[0][:2]),np.array(bounds[1][:2])-pos[:,:2])
        row["current_domain_side_near_particles"] = int((side_dist.min(1)<2*d).sum())
        rows[str(f)]=row
    result={"case":str(case),"frames":rows,
            "method":"Raw particle velocities, 24-neighbour kernel-weighted residual, fixed interior ROI radius18mm; no render/temporal filtering. Residual includes some resolved flow gradients and is a comparison metric, not a ground-truth error.",
            "parameters":experiment["after"]}
    (case/"motion_diagnostics.json").write_text(json.dumps(result,indent=2)+"\n")
    print("TEA_MOTION="+json.dumps({"case":case.name,"frames":rows}),flush=True)
