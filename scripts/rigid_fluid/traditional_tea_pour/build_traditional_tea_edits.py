"""Build four isolated tea edits from the accepted source physics and the refined environment scene."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PHYSICS,APPEARANCE,TOOLS=HERE/'physics',HERE/'appearance',HERE/'tools'
# The accepted source physics (BASE) and refined environment scene (ENV) live in the published suite's inputs.
INPUT_CASES=ROOT/'renders/pcve_suites/pcve_traditional_tea_pour_suite/inputs/source/cases'
BASE=INPUT_CASES/'source_run'
ENV=INPUT_CASES/'environment_render'
PYTHON=ROOT/'.venv-genesis-mpm-sph/bin/python'
CASES=['speed_2x','speed_0p5x','remove_tea','stop_flow_at_2s']
INPUTS=['input_config.json','cup_collider.obj','visible_solid_closed.obj','audit_cavity_closed.obj','actual_inner_open.obj','actual_inner_open.npz','visual_cup_world.npz','collider_repair.json','coaster_world.obj']
def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while chunk:=f.read(8*1024*1024):h.update(chunk)
    return h.hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out-root',type=Path,required=True)
    p.add_argument('--resume',action='store_true')
    p.add_argument('--dry-run',action='store_true')
    p.add_argument('--cases',nargs='+',choices=CASES,default=CASES)
    a=p.parse_args();out=a.out_root.expanduser().resolve();selected=a.cases
    definition={'scene_id':'traditional_tea_pour','source_physics':str(BASE),'source_environment':str(ENV),
        'out_root':str(out),'quality':{'width':1280,'height':720,'fps':24,'frames':96,'samples':128},
        'edits':{'speed_2x':{'speed_scale':2.},'speed_0p5x':{'speed_scale':.5},'remove_tea':{'delete_at_sec':0.},'stop_flow_at_2s':{'stop_flow_at_sec':2.,'velocity_after_m_s':[0.,0.,0.],'retain_existing_liquid':True,'continues_source_after_frame':48}},
        'generated_cases':selected,'time_convention':'display t=(frame-1)/24; inlet velocity becomes zero at2s, frame49',
        'delete_semantics':'Only remove_tea deletes all liquid from the start. Decorative dry leaves remain.',
        'flow_stop_semantics':'stop_flow_at_2s sets inlet velocity and volume flux to zero; tea already emitted continues the SPH solve without deletion. It continues the accepted source solve from its state after frame 48 (solver time 2.0 s), so frames 1-48 are the particles and surfaces of the source itself.',
        'solver':'Genesis1.4.3 DFSPH, fixed/prescribed rigid objects; not two-way FSI',
        'domain_expansion':'Only speed_2x uses x/y bounds +/-2m; baseline +/-0.24m truncated faster splashes. Other numerical parameters stay fixed.'}
    if a.dry_run:print(json.dumps(definition,indent=2));return
    if out.exists() and not a.resume:raise FileExistsError('Choose a fresh root or explicitly --resume')
    out.mkdir(parents=True,exist_ok=True)
    if not (out/'reference_integrity_before.json').exists():
        files=[ENV/'scene_environment_refined.blend',ENV/'genesis_liquid_cache.abc',ENV/'delivery_manifest.json',BASE/'experiment.json',BASE/'input_config.json',BASE/'simulation_result.json']
        for sub in ('particles','surfaces'):files+=sorted((BASE/sub).glob('*.npz'))
        rows={str(f):{'size':f.stat().st_size,'mtime_ns':f.stat().st_mtime_ns,'sha256':sha(f)} for f in files}
        (out/'reference_integrity_before.json').write_text(json.dumps(rows,indent=2)+'\n')
    for name in selected:
        case=out/name;case.mkdir(parents=True,exist_ok=True)
        for filename in INPUTS:
            target=case/filename
            if not target.exists():shutil.copy2(BASE/filename,target)
            assert sha(target)==sha(BASE/filename)
    (out/'suite_definition.json').write_text(json.dumps(definition,indent=2)+'\n')
    subprocess.run([sys.executable,str(PHYSICS/'run_compute.py'),str(out),'--cases',*selected],check=True)
    for name in selected:
        subprocess.run([str(PYTHON),str(TOOLS/'validate_tea_edit.py'),str(out/name),'--baseline',str(BASE)],check=True)
        if not (out/name/'actual_cup_audit.json').exists():
            with open(out/name/'cup_audit.log','w') as log:
                subprocess.run([str(PYTHON),str(TOOLS/'audit_tea_edit_cup.py'),str(out/name)],stdout=log,stderr=subprocess.STDOUT,check=True)
    subprocess.run([sys.executable,str(APPEARANCE/'run_render.py'),str(out),'--cases',*selected],check=True)
    subprocess.run([sys.executable,str(TOOLS/'package_tea_edits.py'),str(out),'--cases',*selected],check=True)
    shutil.copy2(ENV/'asset_manifest_inherited.json',out/'asset_manifest_inherited.json')
    print('TEA_EDITS_GENERATED: numerical/native/video checks passed; full-sequence qualitative visual review remains a separate acceptance step.',flush=True)
if __name__=='__main__':main()
