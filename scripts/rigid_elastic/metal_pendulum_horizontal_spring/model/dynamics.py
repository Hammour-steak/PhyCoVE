"""Native two-way hinge / guided spring contact, with a derived axial elastic mode.

The slide coordinate is compression, not a prescribed animation. The material
energy is 1/2 k x^2 with k=G d^4/(8 D^3 Na), representing torsional strain of
the helical wire. A linear axial mode gives active-wire modal mass m/3; the
moving closed turn contributes its full mass. Internal wire vibration, buckling,
plasticity and coil binding are excluded; the actual stroke stays far from bind.
"""

import math
import sys
from pathlib import Path

if __name__ == "__main__" and not __package__:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import mujoco
import numpy as np


def centerline(c, compression=0.0):
    s = c["physics"]["spring"]
    if not s["present"]:
        return np.empty((0, 3))
    # Fixed end is first. Closed end turns keep their wire-diameter axial pitch.
    # Active pitch is the reduced axial deformation mode, driven by native qpos.
    d = 2 * s["wire_radius_m"]
    seg = c["simulation_quality"]["visual_segments_per_turn"]
    n = s["active_turns"]
    u = np.linspace(0, n + 2, (n + 2) * seg + 1)
    advance = np.where(
        u <= 1,
        d * u,
        np.where(
            u <= n + 1,
            d + (u - 1) * (s["active_length_m"] - compression) / n,
            d + s["active_length_m"] - compression + (u - n - 1) * d,
        ),
    )
    angle = 2 * np.pi * u
    return np.column_stack(
        [
            s["fixed_seat_x_m"] - advance,
            s["mean_coil_radius_m"] * np.cos(angle),
            s["axis_z_m"] + s["mean_coil_radius_m"] * np.sin(angle),
        ]
    )


def build_model(c):
    p = c["physics"]["pendulum"]
    s = c["physics"]["spring"]
    q = c["simulation_quality"]
    ct = c["physics"]["contact"]
    mb = p["ball_mass_kg"]
    mr = p["rod_mass_kg"]
    L = p["length_m"]
    lr = p["rod_length_m"]
    total = mb + mr
    com = (mb * L + mr * lr / 2) / total
    it = p["hinge_inertia_kg_m2"] - total * com * com
    iz = p["ball_inertia_cm_kg_m2"] + 0.5 * mr * p["rod_radius_m"] ** 2

    def v(seq):
        return " ".join(format(float(x), ".17g") for x in seq)

    slider = ""
    if s["present"]:
        mh = s["head_mass_kg"]
        mg = s["guide_rod_mass_kg"]
        ms = s["spring_effective_axial_mass_kg"]
        mc = s["retaining_collar_mass_kg"]
        mass = mh + mg + ms + mc
        rg = s["head_thickness_m"] / 2 + s["guide_rod_length_m"] / 2
        rc = (
            s["fixed_seat_x_m"]
            + s["bushing_length_m"]
            + s["retaining_collar_thickness_m"] / 2
            - s["head_rest_center_x_m"]
        )
        cm = (mg * rg + mc * rc) / mass
        ix = (
            0.5 * mh * s["head_radius_m"] ** 2
            + 0.5 * mg * s["guide_rod_radius_m"] ** 2
            + ms * s["mean_coil_radius_m"] ** 2 / 2
            + mc
            * (s["retaining_collar_radius_m"] ** 2 + s["guide_rod_radius_m"] ** 2)
            / 2
        )
        iy = (
            mh * (3 * s["head_radius_m"] ** 2 + s["head_thickness_m"] ** 2) / 12
            + mg
            * (3 * s["guide_rod_radius_m"] ** 2 + s["guide_rod_length_m"] ** 2)
            / 12
            + (mh + ms) * cm**2
            + mg * (rg - cm) ** 2
            + ms * s["mean_coil_radius_m"] ** 2 / 4
            + mc
            * (
                3 * (s["retaining_collar_radius_m"] ** 2 + s["guide_rod_radius_m"] ** 2)
                + s["retaining_collar_thickness_m"] ** 2
            )
            / 12
            + mc * (rc - cm) ** 2
        )
        slider = f"""<body name="guided_head" pos="{s['head_rest_center_x_m']} 0 {s['axis_z_m']}">
   <joint name="compression" type="slide" axis="1 0 0" stiffness="{s['axial_stiffness_N_m']}" springref="0" damping="{s['axial_viscous_damping_N_s_m']}" limited="true" range="0 {s['maximum_guide_stroke_m']}" solreflimit=".0003 1" solimplimit=".95 .999 .00005"/>
   <inertial pos="{cm} 0 0" mass="{mass}" diaginertia="{v([ix,iy,iy])}"/>
   <geom name="head_face" type="box" size="{s['head_thickness_m']/2} {s['head_radius_m']} {s['head_radius_m']}" contype="2" conaffinity="1"/>
  </body>"""
    # physics.pendulum.present (default true): false removes the swinging pendulum body (bob, rod) and its hinge.
    pendulum = ""
    if p.get("present", True):
        pendulum = f"""<body name="pendulum" pos="{v(p['pivot_m'])}">
   <joint name="pivot" type="hinge" axis="0 -1 0" damping="{p['bearing_damping_Nm_s']}"/>
   <inertial pos="0 0 -{com}" mass="{total}" diaginertia="{v([it,it,iz])}"/>
   <geom name="ball" type="sphere" pos="0 0 -{L}" size="{p['ball_radius_m']}" contype="1" conaffinity="2"/>
   <geom name="rod" type="capsule" fromto="0 0 0 0 0 -{lr}" size="{p['rod_radius_m']}" contype="0" conaffinity="0"/>
  </body>"""
    xml = f"""<mujoco model="{c['scene']}_{c['case']}">
 <compiler angle="radian" autolimits="true" fusestatic="false"/>
 <option timestep="{1/(q['fps']*q['substeps_per_frame'])}" gravity="0 0 -{c['physics']['gravity_m_s2']}" integrator="{q['integrator']}" solver="Newton" iterations="{q['solver_iterations']}" tolerance="{q['solver_tolerance']}"><flag energy="enable"/></option>
 <default><geom friction="0 0 0" condim="1" solref="{v(ct['solref'])}" solimp="{v(ct['solimp'])}" margin="{ct['margin_m']}"/></default>
 <worldbody>
  <geom name="walnut_base" type="box" pos="{v(c['appearance']['base_center_m'])}" size="{v(np.array(c['appearance']['base_dimensions_m'])/2)}" contype="0" conaffinity="0"/>
  <geom name="fixed_backing" type="box" pos=".130 0 .065" size=".002 .025 .04" contype="0" conaffinity="0"/>
  {pendulum}
  {slider}
 </worldbody></mujoco>"""
    m = mujoco.MjModel.from_xml_string(xml)
    d = mujoco.MjData(m)
    if p.get("present", True):
        d.qpos[0] = math.radians(p["release_angle_deg"])
        d.qvel[0] = p["initial_angular_velocity_rad_s"]
    mujoco.mj_forward(m, d)
    if d.ncon:
        raise RuntimeError("Initial geometry contains unintended contact")
    if m.nu or np.any(m.dof_armature):
        raise RuntimeError("Unexpected actuator or artificial inertia")
    return m, d, xml


def contacts(m, d):
    ball = mujoco.mj_name2id(m, mujoco.mjtObj.mjOBJ_GEOM, "ball")
    force = np.zeros(3)
    torque = 0.0
    depth = 0.0
    count = 0
    for j in range(d.ncon):
        co = d.contact[j]
        if ball not in co.geom:
            continue
        f = np.zeros(6)
        mujoco.mj_contactForce(m, d, j, f)
        fw = co.frame.reshape(3, 3).T @ f[:3]
        if co.geom[0] == ball:
            fw = -fw
        force += fw
        torque += np.cross(co.pos - d.xpos[m.geom_bodyid[ball]], fw) @ np.array(
            [0, -1, 0]
        )
        depth = max(depth, -float(co.dist))
        count += 1
    return count, force, torque, depth
