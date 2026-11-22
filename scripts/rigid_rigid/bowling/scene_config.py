"""Three-pin bowling, SI units; shared geometry, physics and rendering inputs."""
from __future__ import annotations
import copy
import hashlib
import json
import math
from pathlib import Path as _Path

# Radius profile in metres. Flat sole, rounded belly, shoulder, neck and head.
PIN_PROFILE = [[0, .026], [.004, .029], [.012, .032], [.025, .037],
    [.045, .045], [.070, .053], [.095, .058], [.120, .060],
    [.145, .0585], [.170, .053], [.195, .044], [.218, .034],
    [.240, .026], [.260, .0215], [.280, .020], [.297, .021],
    [.312, .0255], [.327, .0315], [.342, .034], [.354, .0325],
    [.365, .027], [.374, .018], [.379, .008], [.380, .0001]]

BASELINE = {
 "physics": {
  "units": {"length":"m","mass":"kg","time":"s","up_axis":"Z","forward_axis":"+X"},
  "gravity": [0.,0.,-9.81],
  "ball": {"id":"B01","radius_m":.1075,"mass_kg":5.,"lateral_friction":.22,
   "restitution":.42,"rolling_friction":.00035,"spinning_friction":.0001,
   "linear_damping":0.,"angular_damping":0.,"inertia_factor":.4,
   "initial_position_m":[-2.5,.030,.1075],"initial_velocity_m_per_s":[4.,0.,0.],
   "initial_angular_velocity_rad_per_s":[0.,4/.1075,0.],
   "initial_quaternion_xyzw":[0.,0.,0.,1.]},
  "pins": {"ids":["P01","P02","P03"],"height_m":.380,"max_diameter_m":.120,
   "spacing_m":.300,"profile_z_radius_m":PIN_PROFILE,
   "masses_kg":[1.5,1.5,1.5],"frictions":[.36,.36,.36],
   "restitutions":[.25,.25,.25],"active":[1,1,1],
   "rolling_friction":.0005,"spinning_friction":.0002,
   "linear_damping":0.,"angular_damping":0.},
  "lane": {"width_m":1.054,"front_x_m":-18.29,"deck_end_x_m":.95,
   "thickness_m":.10,"lateral_friction":.32,"restitution":.35,
   "gutter_width_m":.235,"gutter_depth_m":.105,"gutter_segments":20,
   "lane_pitch_m":1.70,"pit_end_x_m":2.85,"pit_floor_z_m":-.32,
   "pit_half_width_m":.80,"pit_wall_height_m":1.15,"pit_side_top_z_m":0.0,
   "pit_friction":.65,"pit_restitution":.12}
 },
 "simulation_quality": {"substeps_per_frame":400,"solver_iterations":160,
  "collision_margin_m":0.,"contact_breaking_threshold_m":.00015,
  "contact_processing_threshold_m":0.,"contact_slop_m":.000005,
  "restitution_velocity_threshold_m_per_s":.08,"use_split_impulse":True,
  "split_impulse_penetration_threshold_m":0.,"pin_radial_segments":48,
  "pin_convex_boundaries_m":[0.,.004,.012,.025,.045,.070,.095,.145,.195,.240,.260,.280,.297,.312,.342,.365,.380],
  "trajectory_hz":240,"contact_force_threshold_N":.00001,"ccd_swept_radius_m":.08},
 # Appearance changes have no effect on the physics or simulation-quality sections.
 "appearance": json.loads((_Path(__file__).parent / 'appearance/appearance_venue.json').read_text())['appearance'],
 "render":{"resolution":[1280,720],"fps":24,"duration_sec":4.,"samples":128,
  "engine":"CYCLES","denoising":True,"denoising_use_gpu":True,
  "motion_blur_shutter_frames":.25,"color_management":"AgX"}
}

CASES = {"source":{},"edit_light_ball":{"physics":{"ball":{"mass_kg":.05}}},
 "edit_heavy_P01":{"physics":{"pins":{"masses_kg":[150.,1.5,1.5]}}},
 "edit_remove_P01":{"physics":{"pins":{"active":[0,1,1]}}},
 "edit_grippy_P01":{"physics":{"pins":{"frictions":[2.5,.36,.36]}}}}

def merge(base, updates):
    out=copy.deepcopy(base)
    for k,v in updates.items():
        if k not in out: raise ValueError("Unknown configuration field: "+k)
        out[k]=merge(out[k],v) if isinstance(v,dict) and isinstance(out[k],dict) else copy.deepcopy(v)
    return out

def scenario(overrides=None,case="source"):
    return merge(merge(BASELINE,CASES[case]),overrides or {})

def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":")).encode()).hexdigest()

def differences(a,b,prefix=""):
    if isinstance(a,dict) and isinstance(b,dict):
        result={}
        for k in sorted(a.keys()|b.keys()):result.update(differences(a.get(k),b.get(k),f"{prefix}.{k}".strip(".")))
        return result
    if isinstance(a,list) and isinstance(b,list) and len(a)==len(b):
        result={}
        for i,(x,y) in enumerate(zip(a,b)):result.update(differences(x,y,f"{prefix}.{i}"))
        return result
    return {} if a==b else {prefix:{"before":a,"after":b}}

def pin_radius(z,profile=PIN_PROFILE):
    """Shape-preserving cubic Hermite interpolation without external dependencies."""
    x=[p[0] for p in profile];y=[p[1] for p in profile]
    h=[b-a for a,b in zip(x,x[1:])];d=[(b-a)/v for a,b,v in zip(y,y[1:],h)]
    slopes=[d[0]]
    for i in range(1,len(x)-1):
        if d[i-1]*d[i]<=0:slopes.append(0.)
        else:
            w1=2*h[i]+h[i-1];w2=h[i]+2*h[i-1]
            slopes.append((w1+w2)/(w1/d[i-1]+w2/d[i]))
    slopes.append(d[-1])
    i=next((i for i in range(len(x)-1) if z<=x[i+1]),len(x)-2)
    t=max(0.,min(1.,(z-x[i])/h[i]))
    return (2*t**3-3*t*t+1)*y[i]+(t**3-2*t*t+t)*h[i]*slopes[i]+(-2*t**3+3*t*t)*y[i+1]+(t**3-t*t)*h[i]*slopes[i+1]

def pin_mass_properties(profile=PIN_PROFILE):
    """Axisymmetric uniform solid: integrate volume, COM and principal inertia per kg."""
    n=4000;dz=profile[-1][0]/n
    samples=[((i+.5)*dz,pin_radius((i+.5)*dz,profile)) for i in range(n)]
    volume=sum(math.pi*r*r*dz for z,r in samples)
    com=sum(z*math.pi*r*r*dz for z,r in samples)/volume
    iz=sum(.5*r*r*math.pi*r*r*dz for z,r in samples)/volume
    ix=sum((.25*r*r+(z-com)**2)*math.pi*r*r*dz for z,r in samples)/volume
    return {"volume_m3":volume,"com_height_m":com,"inertia_per_kg_m2":[ix,ix,iz],"density_model":"uniform axisymmetric solid; scale density only for mass edits"}

def pin_positions(cfg):
    d=cfg["physics"]["pins"]["spacing_m"]
    return [(0.,0.),(math.sqrt(3)*d/2,d/2),(math.sqrt(3)*d/2,-d/2)]

def fixed_geometry(cfg):
    """Closed lane, curved gutters, continuous pin deck and physical rear pit."""
    l=cfg["physics"]["lane"];w=l["width_m"];end=l["deck_end_x_m"];front=l["front_x_m"]
    result=[{"id":"lane_deck","kind":"box","center":[(front+end)/2,0,-l["thickness_m"]/2],
        "size":[end-front,w,l["thickness_m"]],"friction":l["lateral_friction"],"restitution":l["restitution"]}]
    for sign in [-1,1]:
        for j in range(l["gutter_segments"]):
            def yz(k):
                a=math.pi*k/l["gutter_segments"]
                return sign*(w/2+l["gutter_width_m"]*(1-math.cos(a))/2),-l["gutter_depth_m"]*math.sin(a)
            y0,z0=yz(j);y1,z1=yz(j+1)
            vertices=[(x,y,z) for x in [front,end] for y,z in [(y0,z0),(y1,z1),(y1,z1-.018),(y0,z0-.018)]]
            result.append({"id":f"gutter_{sign}_{j:02}","kind":"convex","vertices":vertices,"friction":.24,"restitution":.25})
        result.append({"id":f"lane_divider_{sign}","kind":"box","center":[(front+end)/2,sign*(w/2+l["gutter_width_m"]+.035),-.025],
          "size":[end-front,.07,.05],"friction":.32,"restitution":.25})
    px=l["pit_end_x_m"];z=l["pit_floor_z_m"];pw=l["pit_half_width_m"]
    result += [{"id":"pit_floor","kind":"box","center":[(end+px)/2,0,z-.05],"size":[px-end,2*pw,.10],"friction":l["pit_friction"],"restitution":l["pit_restitution"]},
      {"id":"pit_back","kind":"box","center":[px+.06,0,(l["pit_wall_height_m"]+z)/2],"size":[.12,2*pw,l["pit_wall_height_m"]-z],"friction":l["pit_friction"],"restitution":l["pit_restitution"]}]
    for sign in [-1,1]:
        top=l["pit_side_top_z_m"]
        result.append({"id":f"pit_side_{sign}","kind":"box","center":[(end+px)/2,sign*(pw+.04),(z+top)/2],"size":[px-end,.08,top-z],"friction":.5,"restitution":.12})
    return result

def environment_fixed_geometry(cfg):
    """Adjacent lanes and the hall are static too; one shared scale for visuals and solver."""
    result=[];pitch=cfg["physics"]["lane"]["lane_pitch_m"]
    for lane in range(-2,3):
        for original in fixed_geometry(cfg):
            c=copy.deepcopy(original)
            if lane:c["id"]=f"L{lane+7:02}_"+c["id"]
            if c["kind"]=="box":c["center"][1]+=lane*pitch
            else:c["vertices"]=[(x,y+lane*pitch,z) for x,y,z in c["vertices"]]
            result.append(c)
    for name,center,size in [("hall_floor",[-5.,0.,-.48],[28.,12.,.18]),("hall_back_wall",[3.30,0.,1.70],[.22,12.,4.2]),("hall_side_wall",[-5.,5.05,1.8],[28.,.18,4.4]),("hall_ceiling",[-5.,0.,4.0],[28.,12.,.14])]:
        result.append({"id":name,"kind":"box","center":center,"size":size,"friction":.6,"restitution":.12})
    return result
