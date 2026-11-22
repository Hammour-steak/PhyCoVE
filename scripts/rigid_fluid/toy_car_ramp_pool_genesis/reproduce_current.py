"""Launch the retained current source/edit pipeline in a fresh workspace.

The selected source is a frozen physical take. Native review gates remain in
place; this adapter changes workspace locations, not physical or image inputs.
"""
import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

HERE=Path(__file__).resolve().parent
p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--out-root',type=Path,required=True)
p.add_argument('--kind',choices=['source','edits'],required=True)
p.add_argument('--plan',type=Path)
p.add_argument('--stage',choices=['all','prepare','simulate','surface','render','verify'],default='all')
p.add_argument('--dry-run',action='store_true')
a=p.parse_args()
plan_path=a.plan or HERE/'recipes'/('source_plan.json' if a.kind=='source' else 'edit_plan.json')
plan=json.loads(plan_path.read_text())
out=a.out_root.expanduser().resolve()
old_work,old_root=plan['work'],plan['root']
REPO=HERE.parents[2]
REPO_RELATIVE=('renders/','assets/','work/','scripts/','.venv')
def relocate(value):
    # Plan paths are relative to the repository root; the plan's root and work become the fresh workspace.
    if isinstance(value,str):
        value=value.replace(old_root,str(out/'result')).replace(old_work,str(out))
        return str(REPO/value) if value.startswith(REPO_RELATIVE) else value
    if isinstance(value,list):return [relocate(v) for v in value]
    if isinstance(value,dict):return {k:relocate(v) for k,v in value.items()}
    return value
plan=relocate(plan)
programs={'source':{'simulate':'initialize_source.py','surface':'initialize_source.py','render':'pipeline_source.py'},
          'edits':{'simulate':'launch_physics.py','surface':'surface_edits.py','render':'pipeline_edits.py','verify':'check_physics.py'}}
stage='simulate' if a.stage=='all' else a.stage
command=[sys.executable,str(out/'source'/programs[a.kind].get(stage,''))] if stage!='prepare' else None
description={'workspace':str(out),'plan':plan,'stage':a.stage,'command':command,
             'source_code':str(HERE/a.kind),'review_policy':'Native preview/full-clip acceptance gates are retained; inspect workspace status.json and the documented review markers.'}
if a.dry_run:
    print(json.dumps(description,indent=2));raise SystemExit(0)
if a.stage in ['prepare','all']:
    assert not out.exists(),'Use a fresh --out-root'
    out.mkdir(parents=True)
    (out/'result').mkdir()
    shutil.copytree(HERE/a.kind,out/'source')
    (out/plan_path.name).write_text(json.dumps(plan,indent=2)+'\n')
    # The original drivers expect this current code folder and plan layout.
    (out/'workspace.json').write_text(json.dumps(description,indent=2)+'\n')
else:
    assert (out/'workspace.json').is_file(),'Run --stage prepare first'
if command:
    assert Path(command[1]).is_file(),f'No {a.stage} stage for {a.kind}'
    subprocess.run(command,check=True,env={**os.environ,'PYTHONPATH':str(HERE)})
