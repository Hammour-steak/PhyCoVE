"""Check public scene interfaces without starting a solver or Blender.

--strict additionally checks every scene's scene_manifest.json against its builder's --list-cases,
its entrypoints.json implementation_files and the videos in renders/pcve_suites/pcve_<scene>_suite.
supported_cases is compared with the cases of all workflows (main first, then --list-cases
--workflow <name> in declared order, each case once). Case IDs in case_video_sha256 are mapped to the
suite's case directories by public_case_ids, else by the builder's PCVE_SOURCE/PCVE_EDITS catalog
(case_id and native_cli_case_id -> catalog_case_id), else used as they are.
"""
from pathlib import Path
import argparse
import ast
import concurrent.futures
import hashlib
import json
import os
import subprocess
import sys
import tempfile
from pcve_case_metadata import metadata_errors, native_case_ids
from pcve_edit_catalog import load_catalog
from pcve_project_paths import suite_output_root

ROOT=Path(__file__).resolve().parents[1]

def sha256(path):
    h=hashlib.sha256()
    with open(path,'rb') as f:
        for block in iter(lambda:f.read(1<<20),b''):h.update(block)
    return h.hexdigest()

def strict_errors(row):
    try:return _strict_errors(row)
    except Exception as exc:return [f"{row['scene']}: strict check failed: {type(exc).__name__}: {exc}"]

def catalog_public_ids(builder):
    """Native and CLI case IDs -> suite case directory, from the builder's PCVE_* catalog ({} without one)."""
    try:catalog=load_catalog(builder)
    except (OSError,SyntaxError,ValueError,AssertionError,KeyError,TypeError):return {}
    mapping={}
    for record in [catalog['source'],*catalog['edits'].values()]:
        for native in (record.get('case_id'),record.get('native_cli_case_id')):
            if native:mapping.setdefault(native,record['catalog_case_id'])
    return mapping

def _strict_errors(row):
    """scene_manifest.json present, supported_cases == --list-cases over all workflows, implementation
    files exist, and the current suite's case_video_sha256 matches the published videos."""
    scene=row['scene'];folder=ROOT/row['directory'];errors=[]
    path=folder/'scene_manifest.json'
    if not path.is_file():return [f'{scene}: scene_manifest.json missing']
    manifest=json.loads(path.read_text())
    entry=json.loads((folder/'entrypoints.json').read_text())
    env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
    builder=folder/f'build_pcve_{scene}.py'
    def list_cases(*args):
        command=['--list-cases',*args]
        proc=subprocess.run([sys.executable,str(builder),*command],capture_output=True,text=True,env=env,timeout=30)
        try:
            listed=json.loads(proc.stdout)
            return list(listed['cases']),list(listed.get('workflows',[]))
        except (ValueError,KeyError,TypeError):
            errors.append(f'{scene}: {" ".join(command)} failed (exit {proc.returncode})')
            return None,[]
    cases,workflows=list_cases()
    for workflow in workflows if cases is not None else []:
        more,_=list_cases('--workflow',workflow)
        if more is None:
            cases=None;break
        cases+=[c for c in more if c not in cases]
    if cases is not None and manifest.get('supported_cases')!=cases:
        source='--list-cases'+(f' (workflows main, {", ".join(workflows)})' if workflows else '')
        errors.append(f'{scene}: scene_manifest.supported_cases {manifest.get("supported_cases")} differs from {source} {cases}')
    for rel in entry.get('implementation_files',[]):
        if not (folder/rel).is_file():errors.append(f'{scene}: missing implementation file {rel}')
    suite=ROOT/'renders'/'pcve_suites'/f'pcve_{scene}_suite'
    current={k:v for k,v in manifest.get('canonical_suites',{}).items()
             if k==suite.name or (ROOT/str(v.get('target',''))).resolve()==suite.resolve()}
    if not current:errors.append(f'{scene}: canonical_suites has no entry for {suite.relative_to(ROOT)}')
    videos={d.name:d/'video.mp4' for d in sorted((suite/'cases').iterdir()) if (d/'video.mp4').is_file()} if (suite/'cases').is_dir() else {}
    if not videos:errors.append(f'{scene}: no case videos in {suite.relative_to(ROOT)}')
    hashes={};catalog=None
    for key,data in current.items():
        if (ROOT/str(data.get('target',''))).resolve()!=suite.resolve():
            errors.append(f'{scene}: canonical_suites.{key}.target is {data.get("target")}, not {suite.relative_to(ROOT)}')
        public=data.get('public_case_ids',{})
        if 'case_video_sha256' in data and catalog is None:catalog=catalog_public_ids(builder)
        for label in ('case_video_sha256','public_case_video_sha256'):
            if label not in data:continue
            recorded={(public.get(c,catalog.get(c,c)) if label=='case_video_sha256' else c):v for c,v in data[label].items()}
            for case in sorted(set(recorded)|set(videos)):
                if case not in videos:errors.append(f'{scene}: {key}.{label} lists {case}, which has no video in the suite')
                elif case not in recorded:errors.append(f'{scene}: {key}.{label} omits suite case {case}')
                else:
                    if case not in hashes:hashes[case]=sha256(videos[case])
                    if recorded[case]!=hashes[case]:errors.append(f'{scene}: {key}.{label}[{case}] differs from the suite video')
    return errors

def main():
    p=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--json',type=Path)
    p.add_argument('--strict',action='store_true',help='also check scene_manifest.json, case lists, implementation files and suite video hashes for every scene')
    a=p.parse_args()
    registry=json.loads((ROOT/'scripts/scene_registry.json').read_text())['scenes']
    tasks=[];errors=[]
    for row in registry:
        folder=ROOT/row['directory']
        if not (folder/'README.md').is_file():errors.append(str(folder/'README.md'))
        metadata=json.loads((folder/'entrypoints.json').read_text())
        named_suite = metadata["entrypoints"]["build_pcve"].get("named_suite_output", False)
        if named_suite:
            errors.extend(metadata_errors(ROOT, row))
        for role in ['simulate','render','build_pcve']:
            path=folder/f'{role}_{row["scene"]}.py'
            if not path.is_file():errors.append(str(path));continue
            ast.parse(path.read_text(),filename=str(path))
            assert 'PCVE_UNIFIED_ENTRY_BEGIN' in path.read_text(),path
            assert metadata['entrypoints'][role]['file']==path.name
            tasks.append((row['scene'],role,path,named_suite))
        for workflow in metadata.get('workflows',{}).values():
            assert (folder/workflow['file']).is_file(),workflow
    with tempfile.TemporaryDirectory(prefix='pcve_entry_check_') as temporary:
        scratch=Path(temporary)
        def check(item):
            name,role,path,named_suite=item;out=scratch/name/role
            env={**os.environ,'PYTHONDONTWRITEBYTECODE':'1'}
            help_result=subprocess.run([sys.executable,str(path),'--help'],capture_output=True,text=True,env=env,timeout=30)
            dry=subprocess.run([sys.executable,str(path),'--out-root',str(out),'--dry-run'],capture_output=True,text=True,env=env,timeout=30)
            result={'scene':name,'role':role,'help_return_code':help_result.returncode,'plan_return_code':dry.returncode,'output_created':out.exists()}
            if named_suite and role == "build_pcve":
                def query(*args):
                    proc = subprocess.run([sys.executable, str(path), *args], capture_output=True, text=True, env=env, timeout=30, check=True)
                    return json.loads(proc.stdout)
                assert query("--list-cases")["cases"] == native_case_ids(path.parent, name)
                for args, parent in [((), suite_output_root(name).parent), (("--out-parent", str(scratch)), scratch)]:
                    plan = query(*args, "--dry-run")
                    expected = str(parent/f"pcve_{name}_suite")
                    assert plan["out_root"] == expected
                    command = plan["command"]
                    assert command.count("--out-root") == 1 and command[command.index("--out-root")+1] == expected
            if dry.returncode:result['error']=dry.stderr[-2000:]
            else:
                plan=json.loads(dry.stdout)
                assert plan['dry_run'] and plan['entry']==role and plan['scene']==name
                assert '--dry-run' not in plan['command']
                result['plan']=plan
            return result
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:results=list(pool.map(check,tasks))
        errors += [r for r in results if r['help_return_code'] or r['plan_return_code'] or r['output_created']]
        assert not any(scratch.iterdir()),'A read-only plan created directories'
    report={'passed':not errors,'scenes':len(registry),'public_entries':len(tasks),'errors':errors,'entries':results,
            'scope':'Public CLI structure and read-only execution planning; original physical and render implementations are not executed.'}
    keys=['passed','scenes','public_entries','errors']
    if a.strict:
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:per_scene=list(pool.map(strict_errors,registry))
        strict=[e for scene_errors in per_scene for e in scene_errors]
        report['strict']={'passed':not strict,'scenes_failing':sum(1 for s in per_scene if s),'errors':strict}
        keys.append('strict')
    if a.json:
        a.json.parent.mkdir(parents=True,exist_ok=True)
        a.json.write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps({k:report[k] for k in keys},indent=2))
    raise SystemExit(0 if report['passed'] and report.get('strict',{}).get('passed',True) else 1)

if __name__=='__main__':main()
