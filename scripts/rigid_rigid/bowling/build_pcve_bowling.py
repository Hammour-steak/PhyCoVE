"""Source-gated three-pin bowling suite using existing simulate/render/build conventions."""
from __future__ import annotations
# Scene-local modules live in the scene directory and its physics/, appearance/ and tools/ subdirectories.
import sys as _scene_sys
from pathlib import Path as _ScenePath
import sys as _pcve_assets_sys
from pathlib import Path as _PcveAssetsPath
_pcve_assets_sys.path.append(str(_PcveAssetsPath(__file__).resolve().parents[2]))
from pcve_assets import blender
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'appearance'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'physics'))
_scene_sys.path.insert(1, str(_ScenePath(__file__).resolve().parent / 'tools'))
# PCVE_UNIFIED_ENTRY_BEGIN
if __name__=="__main__":
    import sys as _sys
    from pathlib import Path as _Path
    if _Path(__file__).with_name("entrypoints.json").is_file() and (_Path(__file__).resolve().parents[2]/"pcve_scene_entry.py").is_file():
        _sys.path.insert(0,str(_Path(__file__).resolve().parents[2]))
        from pcve_scene_entry import prepare_entry
        prepare_entry(__file__,"build_pcve")
# PCVE_UNIFIED_ENTRY_END
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import copy
import shutil
from scene_config import CASES,scenario,signature
from simulate_bowling import simulate,dump,export_csv
from validate_bowling import validate
from edit_vocab import edit_info

HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
SOURCE_DESCRIPTION={
 "vague":{"zh":"深蓝色保龄球在室内球馆球道上自然滚动，先撞前排球瓶，再引发后排球瓶响应和倾倒。","en":"A deep-blue bowling ball rolls down an indoor lane, strikes the front pin, and initiates subsequent contacts and toppling in the rear row."},
 "quantitative":{"zh":"直径 21.5 cm、质量 5 kg 的深蓝色保龄球从三瓶前方 2.5 m 处以 4 m/s、匹配的前滚角速度开始运动。三只 38 cm、1.5 kg 球瓶组成中心距 30 cm 的等边三角形，首先被撞的是前排中央的球瓶。","en":"A 21.5 cm diameter, 5 kg deep-blue ball starts 2.5 m ahead of three 38 cm tall, 1.5 kg pins at 4 m/s with matching forward rolling spin. The pins form a 30 cm center-spaced equilateral triangle, and the front-center pin is struck first."}}

def checked(path,case,source=None):
    result=json.loads(path.read_text());report=validate(result,case,source);dump(path.with_name("physics_validation.json"),report)
    if not report["accepted"]:raise RuntimeError(f"Rejected {case}: {[k for k,v in report['checks'].items() if not v]}")
    return result

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument("--out-root",type=Path,required=True)
    p.add_argument("--stage",choices=["all","graybox","simulate","render","verify"],default="all");p.add_argument("--cases",nargs="+",choices=list(CASES),default=list(CASES))
    p.add_argument("--blender",type=Path,default=blender())
    p.add_argument("--threads-native",type=int,default=8);p.add_argument("--device",choices=["auto","cpu"],default="auto");p.add_argument("--skip-existing",action="store_true");p.add_argument("--reuse-physics-root",type=Path,help="Reuse validated cached dynamics for an appearance-only change; physics, numerical quality and render specifications must match.")
    a=p.parse_args();out=a.out_root.expanduser().resolve();out.mkdir(parents=True,exist_ok=True)
    if a.stage=="graybox":
        from graybox_bowling import run
        gate=simulate(scenario());dump(out/"graybox_source/physics_transforms.json",gate)
        report=validate(gate,"source");dump(out/"graybox_source/physics_validation.json",report)
        if not report["accepted"]:raise RuntimeError("Source gate failed; do not create edit scans")
        run(out/"graybox_edits","edits");return
    cfg=scenario();manifest_path=out/"suite_manifest.json"
    if manifest_path.exists():
        manifest=json.loads(manifest_path.read_text());assert manifest["configuration"]==cfg,"Use a fresh root for changed inputs"
    else:
        if any(out.iterdir()):raise FileExistsError("Nonempty output root without this suite manifest")
        manifest={"schema_version":3,"suite_name":"pcve_bowling_suite","scene":"bowling","interaction_category":"rigid_rigid","configuration":cfg,
          "configuration_sha256":signature(cfg),"source_case_id":"source","source":None,"edits":[],"status":"running",
          "resolution":cfg["render"]["resolution"],"fps":cfg["render"]["fps"],"duration_sec":cfg["render"]["duration_sec"],"total_frames":round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]),"samples":cfg["render"]["samples"],
          "playback_rate":1.,"solver":"PyBullet 3.2.7 independent free zero-joint bodies, 16 convex bands per pin, actual integrated inertia",
          "formal_settings_note":"1280x720 / 24 fps / 96 frames / Cycles 128 samples with OIDN denoising; 0.25-frame motion blur (persistent data off); no DOF; four seconds to include rear pit motion"}
        dump(manifest_path,manifest)
    if a.reuse_physics_root:
        if a.stage not in ['all','simulate'] or not a.skip_existing:
            raise ValueError('Cache reuse requires --stage simulate/all and --skip-existing')
        provenance={}
        for case in a.cases:
            source_path=a.reuse_physics_root.resolve()/'cases'/case/'physics_transforms.json'
            original=json.loads(source_path.read_text());expected=scenario(case=case)
            for section in ['physics','simulation_quality','render']:
                if original['configuration'][section]!=expected[section]:raise ValueError(f'{case}: cache reuse would change {section}')
            reused=copy.deepcopy(original);reused['configuration']=expected;reused['configuration_sha256']=signature(expected)
            before={k:v for k,v in original.items() if k not in ['configuration','configuration_sha256']}
            after={k:v for k,v in reused.items() if k not in ['configuration','configuration_sha256']}
            assert before==after
            target=out/'cases'/case;target.mkdir(parents=True,exist_ok=True)
            dump(target/'physics_transforms.json',reused)
            if source_path.with_name('trajectory.csv').exists():shutil.copy2(source_path.with_name('trajectory.csv'),target/'trajectory.csv')
            provenance[case]={'original_cache':str(source_path),'original_file_sha256':hashlib.sha256(source_path.read_bytes()).hexdigest(),'identical_cached_dynamics_sha256':signature(before),'only_cached_configuration_appearance_updated':True}
        dump(out/'physics_reuse_provenance.json',provenance)
    source_file=out/"cases/source/physics_transforms.json"
    if a.stage in ["all","simulate"] and not(a.skip_existing and source_file.exists()):
        r=simulate(cfg);dump(source_file,r);export_csv(source_file.with_name("trajectory.csv"),r)
    source=checked(source_file,"source")
    for case in a.cases:
        folder=out/"cases"/case;folder.mkdir(parents=True,exist_ok=True);path=folder/"physics_transforms.json";expected=scenario(case=case)
        info=edit_info(case) if case!="source" else None
        if info:
            dump(folder/"scenario_overrides.json",info["physics_override"]);dump(folder/"prompts.json",{"schema_version":2,"case_id":case,"source_case_id":"source",**info})
        else:
            dump(folder/"prompts.json",{"schema_version":2,"case_id":"source","prompts":SOURCE_DESCRIPTION,"editable_object_ids":["B01","P01","P02","P03"]})
        if a.stage in ["all","simulate"] and case!="source" and not(a.skip_existing and path.exists()):
            r=simulate(expected);dump(path,r);export_csv(folder/"trajectory.csv",r)
        result=checked(path,case,source if info else None);assert result["configuration"]==expected
        dump(folder/"settings.json",expected);dump(folder/"contacts.json",{"first_contacts":result["contact_events"],"episodes":result["contact_episodes"],"toppling_times":result["tilt_threshold_times_sec"]})
        record={"case_id":case,"kind":"edit" if info else "source","status":"physics_accepted","source_case_id":"source","case_dir":str(folder),
          "quality":result["quality"],"simulation_wall_sec":result["simulation_wall_sec"],"observed_outcome":{"toppled_count":result["quality"]["toppled_count"],"contact_order":[{"objects":e["objects"],"time_sec":e["first_time_sec"]} for e in result["contact_events"]],"toppling_times":result["tilt_threshold_times_sec"],"final_objects":result["final_state"]["objects"]}}
        if info:record.update(info)
        else:record["description"]=SOURCE_DESCRIPTION
        if a.stage in ["all","render"]:
            command=[str(a.blender.expanduser()),"-b","-t",str(int(os.environ.get("OMP_NUM_THREADS",a.threads_native))),"--python-exit-code","1","--python",str(HERE/"render_bowling.py"),"--","--physics-json",str(path),"--out-dir",str(folder),"--mode","animation","--device",a.device]
            if a.skip_existing:command.append("--skip-existing")
            start=time.perf_counter()
            with (folder/"render.log").open("a") as log:subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,check=True,cwd=ROOT)
            record["render_pipeline_wall_sec"]=time.perf_counter()-start
        if a.stage in ["all","render","verify"]:
            subprocess.run([sys.executable,str(ROOT/"scripts/pcve_verify_video.py"),str(folder/"video.mp4"),"--out",str(folder/"video_validation.json"),"--resolution",*[str(x) for x in cfg["render"]["resolution"]],"--fps",str(cfg["render"]["fps"]),"--frames",str(round(cfg["render"]["fps"]*cfg["render"]["duration_sec"]))],check=True)
            record["status"]="technically_verified_pending_visual_review"
        record["outputs"]={k:str(folder/f) for k,f in [("video","video.mp4"),("physics","physics_transforms.json"),("trajectory","trajectory.csv"),("contacts","contacts.json"),("scene","bowling.blend"),("metadata","scenario_metadata.json")]}
        if case=="source":manifest["source"]=record
        else:manifest["edits"]=[e for e in manifest["edits"] if e["case_id"]!=case]+[record]
        dump(manifest_path,manifest);print(case,record["status"],flush=True)
    dump(out/"implementation_manifest.json",{"configuration":cfg,"configuration_sha256":signature(cfg),"runtime_python":sys.executable,"python_version":sys.version,"asset_manifests":[str(ROOT/"assets/bowling_documentary"/name/"asset_manifest.json") for name in ["retired_pin","ball_ramprasath","white_maple_veneer","fonts"]],"asset_registry_entries":["polyhaven/poly_wool_herringbone","polyhaven/blue_metal_plate"],"asset_policy":"Authored maintained hall, parked machinery and exact active contact boundaries; BlenderKit David Geuens pin coating (printed maker marks painted out) and Ramprasath ball pattern, Royalty Free; Poly Haven White Maple Veneer, poly_wool_herringbone (masking fabric) and blue_metal_plate (roughness/normal scuffs only), CC0. No text, numerals or logos in frame. B01 bores and all dynamics retained; original source UV atlas on pins, all dependencies packed."})

if __name__=="__main__":main()
