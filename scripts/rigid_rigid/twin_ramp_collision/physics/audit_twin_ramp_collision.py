"""Audit every formal PNG against projected solved state and declared inputs."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
from pathlib import Path
import argparse
import hashlib
import json
import math
import numpy as np
from PIL import Image,ImageDraw
from scene_config import CASES,differences
from validate_twin_ramp_collision import ALLOWED
from simulate_twin_ramp_collision import write_json

def audit(root):
    root=Path(root);reports=[];source=json.loads((root/"cases/source/settings.json").read_text())
    for case in CASES:
        folder=root/"cases"/case;r=json.loads((folder/"physics_transforms.json").read_text());m=json.loads((folder/"scenario_metadata.json").read_text())
        images=sorted((folder/"frames").glob("frame_*.png"));count=r["frame_end"];assert len(images)==count
        gate=30
        errors=[];matches=[];sheets=[];black_artifacts=[]
        for page in range(math.ceil(count/60)):
            canvas=Image.new("RGB",(1920,6*126),"#e9e9e7");draw=ImageDraw.Draw(canvas)
            for j,path in enumerate(images[page*60:(page+1)*60]):
                index=page*60+j;frame=index+1;im=Image.open(path).convert("RGB");assert im.size==tuple(source["render"]["resolution"])
                arr=np.asarray(im,dtype=float);height,width=arr.shape[:2]
                for name,b in m["projected_balls"][index]["objects"].items():
                    cx=b["uv"][0]*width;cy=(1-b["uv"][1])*height;rad=b["diameter_px"]/2
                    x0=max(0,int(cx-rad*1.15));x1=min(width,int(cx+rad*1.15)+1);y0=max(0,int(cy-rad*1.15));y1=min(height,int(cy+rad*1.15)+1)
                    crop=arr[y0:y1,x0:x1];red,green,blue=crop[:,:,0],crop[:,:,1],crop[:,:,2]
                    # The look is lit only by daylight from the windows behind and left of the apparatus, so the
                    # camera-facing half of each ball sits in shade (8-bit values 30-65); the colour-dominance
                    # ratios and the 6 px tolerance are unchanged, only the minimum-brightness gate is lower.
                    mask=(red>green*1.6)&(red>blue*1.5)&(red>gate) if name=="B_left" else (blue>red*1.3)&(blue>green*1.15)&(blue>gate)
                    ys,xs=np.where(mask)
                    err=math.hypot(float(xs.mean())+x0-cx,float(ys.mean())+y0-cy) if len(xs)>20 else 999.
                    matches.append({"frame":frame,"object":name,"centroid_error_px":err,"color_pixels":len(xs)})
                    if err>6:errors.append(matches[-1])
                    yy,xx=np.mgrid[y0:y1,x0:x1];inner=(xx-cx)**2+(yy-cy)**2<(.80*rad)**2
                    black_count=int(((crop.max(axis=2)<8)&inner).sum());black_fraction=black_count/int(inner.sum())
                    if black_count>8 and black_fraction>.01:black_artifacts.append({'frame':frame,'object':name,'black_pixels':black_count,'inner_fraction':black_fraction})
                thumb=im.resize((192,108));x=j%10*192;y=j//10*126;canvas.paste(thumb,(x,y));draw.text((x+3,y+109),f"{frame:03d} / {(frame-1)/source['render']['fps']:.3f} s",fill="black")
            dest=folder/"review"/f"all_frames_{page+1}.jpg";dest.parent.mkdir(exist_ok=True);canvas.save(dest,quality=94);sheets.append(str(dest))
        settings=json.loads((folder/"settings.json").read_text());diff=differences(source,settings)
        contact_gap=None
        if r["contact_events"] and abs(r["contact_events"][0]["time_sec"]*source["render"]["fps"]-round(r["contact_events"][0]["time_sec"]*source["render"]["fps"]))<.001:
            event=r["contact_events"][0];index=round(event["time_sec"]*source["render"]["fps"])
            a=m["projected_balls"][index]["objects"]["B_left"];b=m["projected_balls"][index]["objects"]["B_right"]
            contact_gap=math.hypot((a["uv"][0]-b["uv"][0])*1280,(a["uv"][1]-b["uv"][1])*720)-(a["diameter_px"]+b["diameter_px"])/2
        checks={"all_frame_pngs":len(images)==r["frame_end"]==round(source["render"]["fps"]*source["render"]["duration_sec"]),"all_rendered_ball_centers_match_physics":not errors,
            'no_near_black_sphere_artifacts':not black_artifacts,
            "all_silhouettes_in_frame":m["all_ball_silhouettes_in_frame"],"visible_ball_size":m["minimum_ball_diameter_px"]>38,
            "fixed_camera":m["camera_is_static"] and m["camera_keyframes"]==0,"unit_playback":m["playback_rate"]==1.,
            "exact_render_inputs":m["physics"]==r["configuration"]["physics"] and all(m[k]==source[k] for k in ["appearance","render","simulation_quality"]),
            "declared_input_diff":not diff if case=="source" else set(diff)==ALLOWED[case],
            "visible_contact_frame":contact_gap is None or abs(contact_gap)<1.5}
        report={"case_id":case,"passed":all(checks.values()),"checks":checks,"maximum_render_vs_physics_centroid_error_px":max(x["centroid_error_px"] for x in matches),
            "ball_color_brightness_gate":gate,"failed_observations":errors,'near_black_artifacts':black_artifacts,"first_contact_projected_silhouette_gap_px":contact_gap,
            "review_contact_sheets":sheets,"video_sha256":hashlib.sha256((folder/"video.mp4").read_bytes()).hexdigest()}
        write_json(folder/"render_audit.json",report);reports.append(report);print(case,report["passed"],report["maximum_render_vs_physics_centroid_error_px"],flush=True)
    result={"passed":all(x["passed"] for x in reports),"cases":reports,"scope":"Every full-resolution formal PNG: projected solved ball positions, color presence, size, framing and input invariants; visual contact sheets retained separately"}
    write_json(root/"render_audit.json",result);return result

if __name__=="__main__":
    p=argparse.ArgumentParser();p.add_argument("--out-root",type=Path,required=True);r=audit(p.parse_args().out_root);raise SystemExit(0 if r["passed"] else 1)
