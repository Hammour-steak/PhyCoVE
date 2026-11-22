"""Inspect every full-resolution frame and generate exhaustive review sheets."""
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1]))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parents[1] / 'tools'))
import argparse
import json
import math
from pathlib import Path
import numpy as np
from PIL import Image,ImageDraw
from scene_config import save_json

def main():
    p=argparse.ArgumentParser();p.add_argument('--case-dir',type=Path,required=True);a=p.parse_args();folder=a.case_dir
    meta=json.loads((folder/'scenario_metadata.json').read_text());r=json.loads((folder/'physics_transforms.json').read_text());out=folder/'review';out.mkdir(exist_ok=True)
    render=meta['configuration']['render'];fps=render['fps'];total=round(fps*render['duration_sec'])
    rows=[];thumbnails=[];motion_thumbnails=[];w,h=render['resolution'];projections=meta['projected_bounds']
    # Fixed review instants, given in 1/60 s ticks, mapped to the nearest video frame.
    target_frames={min(total,round((k-1)/60*fps)+1) for k in (1,20,35,45,49,52,54,55,56,57,60,65,75,90,120,150,180,210,240)}
    for event in [r['outcome']['ramp_exit'],r['outcome']['first_collision']]:
        if event:
            center=math.ceil(event['time_sec']*meta['configuration']['render']['fps'])+1
            target_frames.update(f for f in range(center-2,center+3) if 1<=f<=total)
    motion_box=(0,290,1280,530)
    motion_height=round((motion_box[3]-motion_box[1])/2)
    for f in range(1,total+1):
        path=folder/'frames'/('frame_%04d.png'%f)
        with Image.open(path) as image:
            assert image.size==(w,h),path;im=image.convert('RGB');arr=np.array(im);info={'frame':f,'readable':True,'size':[w,h]}
            for name,o in projections[f-1]['objects'].items():
                if name!='ball':continue
                u,v=o['uv'];cx=u*w;cy=(1-v)*h;rad=o['bounding_diameter_px']/2
                x0=max(0,int(cx-rad-3));x1=min(w,int(cx+rad+4));y0=max(0,int(cy-rad-3));y1=min(h,int(cy+rad+4));crop=arr[y0:y1,x0:x1].astype(float)
                yy,xx=np.mgrid[y0:y1,x0:x1];R,G,B=crop[:,:,0],crop[:,:,1],crop[:,:,2];mx=crop.max(axis=2);mn=crop.min(axis=2)
                saturated=(mx-mn)/(mx+1)>.43;hue=((B>1.15*R)&(B>1.08*G))|((R>1.4*G)&(R>1.5*B))|((R>1.65*B)&(G>1.45*B)&(G>.65*R))
                mask=saturated&hue&(mx>65)&((xx-cx)**2+(yy-cy)**2<(rad*.86)**2)
                count=int(mask.sum());expected=math.pi*rad*rad;coverage=count/expected
                offset=math.hypot(float(xx[mask].mean())-cx,float(yy[mask].mean())-cy) if count else 1e9
                info.update({'ball_colored_pixel_count':count,'ball_colored_fraction':coverage,'ball_mask_centroid_offset_px':offset,'ball_visible_at_solved_position':coverage>.12 and offset<rad*.65})
            thumb=im.resize((320,180),Image.Resampling.LANCZOS);draw=ImageDraw.Draw(thumb);draw.rectangle((0,0,105,17),fill=(245,245,241));draw.text((4,3),'%03d / %.3f s'%(f,(f-1)/fps),fill=(30,30,30));thumbnails.append(thumb)
            foreground=im.crop(motion_box).resize((640,motion_height),Image.Resampling.LANCZOS);draw=ImageDraw.Draw(foreground);draw.rectangle((0,0,112,15),fill=(245,245,241));draw.text((4,2),'%03d / %.3f s'%(f,(f-1)/fps),fill=(30,30,30));motion_thumbnails.append(foreground)
            if f in target_frames:
                im.save(out/('full_%04d.jpg'%f),quality=94)
                # Full-size crop of the foreground interaction band, enlarged only for review.
                im.crop(motion_box).resize((1920,motion_height*3),Image.Resampling.LANCZOS).save(out/('motion_%04d.jpg'%f),quality=95)
            rows.append(info)
    for first in range(0,total,24):
        sheet=Image.new('RGB',(1280,1080),(248,248,245))
        for k,im in enumerate(thumbnails[first:first+24]):sheet.paste(im,((k%4)*320,(k//4)*180))
        sheet.save(out/('all_frames_%03d_%03d.jpg'%(first+1,first+24)),quality=93)
        sheet=Image.new('RGB',(1280,12*motion_height),(248,248,245))
        for k,im in enumerate(motion_thumbnails[first:first+24]):sheet.paste(im,((k%2)*640,(k//2)*motion_height))
        sheet.save(out/('motion_frames_%03d_%03d.jpg'%(first+1,first+24)),quality=94)
    checks={'all_full_resolution_frames_decoded':len(rows)==total,'all_dynamic_bounding_spheres_in_frame':meta['all_objects_in_frame'],
        'ball_diameter_at_least_29px':meta['minimum_ball_diameter_px']>=29 if r['configuration']['physics']['ball']['present'] else True,
        'ball_visible_at_solved_position_every_frame':all(v.get('ball_visible_at_solved_position',True) for v in rows)}
    report={'accepted':all(checks.values()),'checks':checks,'frames':rows,'review_sheets':len(range(0,total,24)),'motion_review_crop':motion_box,
        'scope':'All PNGs decoded at formal resolution. Color-panel visibility checked around each projected solved ball position; exhaustive contact sheets plus full-resolution event frames. Qualitative review remains separately recorded.'}
    save_json(folder/'frame_audit.json',report);print(json.dumps({'accepted':report['accepted'],'checks':checks,'failures':[r for r in rows if not r.get('ball_visible_at_solved_position',True)]}));raise SystemExit(0 if report['accepted'] else 2)
if __name__=='__main__':main()
