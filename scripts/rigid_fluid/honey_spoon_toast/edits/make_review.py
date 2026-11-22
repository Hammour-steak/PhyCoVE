"""Review sheets of one rendered edit: all 96 frames, the last frame next to the source's, landing close-ups."""
from pathlib import Path
import json,subprocess
from PIL import Image,ImageDraw,ImageFont
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[3]))
from pcve_assets import REPO

ROOT=REPO
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--case',required=True);parser.add_argument('--work-dir',type=Path,required=True)
parser.add_argument('--source-video',type=Path,default=ROOT/'renders/pcve_suites/pcve_honey_spoon_toast_suite/cases/source/video.mp4',
                    help='source video whose last frame is shown next to the edit')
args=parser.parse_args()
OUT=args.work_dir.resolve()/args.case/'render'
review=OUT/'review';review.mkdir(exist_ok=True)
font=ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf',16)
for batch in range(4):
    sheet=Image.new('RGB',(1600,6*248),(24,24,24));draw=ImageDraw.Draw(sheet)
    for slot in range(24):
        frame=batch*24+slot+1
        path=OUT/f'frame_{frame:04d}.png'
        with Image.open(path) as image:
            assert image.size==(1280,720)
            image.load();thumb=image.convert('RGB').resize((400,225),Image.Resampling.LANCZOS)
        x,y=slot%4*400,slot//4*248
        sheet.paste(thumb,(x,y));draw.text((x+8,y+228),f'Frame {frame:02d}  |  {(frame-1)/24:.3f} s',font=font,fill='white')
    sheet.save(review/f'frames_{batch*24+1:02d}_{batch*24+24:02d}.jpg',quality=93)

comparison=Image.new('RGB',(2560,760),(24,24,24));draw=ImageDraw.Draw(comparison)
before=review/'source_frame_0096.png'
subprocess.run(['ffmpeg','-nostdin','-y','-v','error','-i',str(args.source_video),'-vf','select=eq(n\\,95)','-vsync','0',
                '-frames:v','1',str(before)],check=True)
with Image.open(before) as image:comparison.paste(image.convert('RGB'),(0,40))
with Image.open(OUT/'frame_0096.png') as image:comparison.paste(image.convert('RGB'),(1280,40))
draw.text((20,10),'SOURCE  |  honey on toast',font=font,fill='white')
draw.text((1300,10),'EDIT  |  '+args.case,font=font,fill='white')
comparison.save(OUT/'before_after.jpg',quality=95)

# Close views of the physical landing. No generation or compositing of honey.
frames=[1,8,12,24,48,60,72,96]
contact=Image.new('RGB',(4*640,2*430),(24,24,24));draw=ImageDraw.Draw(contact)
for i,frame in enumerate(frames):
    with Image.open(OUT/f'frame_{frame:04d}.png') as image:
        crop=image.convert('RGB').crop((230,320,870,720)).resize((640,400),Image.Resampling.LANCZOS)
    x,y=i%4*640,i//4*430;contact.paste(crop,(x,y));draw.text((x+8,y+403),f'Frame {frame}',font=font,fill='white')
contact.save(review/'landing_keyframes.jpg',quality=94)
print(json.dumps({'status':'all_96_pngs_decoded','review_sheets':4,'comparison':str(OUT/'before_after.jpg')}))
