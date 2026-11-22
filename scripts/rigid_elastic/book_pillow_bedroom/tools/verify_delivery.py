"""Read-only verification of book_pillow_bedroom (build_pcve --stage verify).

1. The accepted physics delivery (scene_manifest.json native_delivery): every file and alias of
   its delivery_manifest.json (sha256, bytes), each case's native cache against
   acceptance/accepted_case.json, a passed motion audit, and the strict edit policy of its packaged suite.
2. The published video suite (scene_manifest.json canonical_suites): source plus the five edits, each
   video's sha256 against suite_manifest.json, provenance.json and the scene_manifest pointer; the
   1280x720 / 24 fps / 96-frame media contract (ffprobe, full decode); prompts.json equal to the
   builder's catalog; ground_truth_transforms.json (pcve_ground_truth/1) with 96 frames at i/24 s; the
   video rendered from the accepted native cache of its case (native_metadata/render_report.json).
Nothing is written.

    python3 tools/verify_delivery.py [--delivery DIR] [--suite DIR] [--cases CASE ...]
"""
from pathlib import Path
import argparse
import ast
import json
import shutil
import subprocess
import sys

CASE=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(CASE.parents[1]),str(CASE)]
from edit_vocab import VOCAB
from pcve_edit_policy import audit_suite_manifest
from pcve_media_contract import require_times,require_video
from scene_paths import canonical_suite,native_delivery,sha,suite_dir


def read(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def inside(root,relative):
    path=(root/relative).resolve()
    if not path.is_relative_to(root.resolve()) or path==root.resolve():
        raise RuntimeError(f'Manifest path escapes the delivery: {relative}')
    return path


def catalog():
    values={}
    for node in ast.parse((CASE/'build_pcve_book_pillow_bedroom.py').read_text(encoding='utf-8')).body:
        if isinstance(node,ast.Assign) and isinstance(node.targets[0],ast.Name) and node.targets[0].id in ('PCVE_SOURCE','PCVE_EDITS'):
            values[node.targets[0].id]=ast.literal_eval(node.value)
    return values['PCVE_SOURCE'],values['PCVE_EDITS']


def verify_native(root,selection):
    root=Path(root)
    spec=read(root/'delivery_manifest.json')
    for row in spec['files']:
        path=inside(root,row['remote'])
        if not path.is_file() or ('sha256' in row and (path.stat().st_size!=row['bytes'] or sha(path)!=row['sha256'])):
            raise RuntimeError(f'Delivery file differs: {row["remote"]}')
    for row in spec['aliases']:
        if sha(inside(root,row['remote']))!=row['sha256'] or sha(inside(root,row['source']))!=row['sha256']:
            raise RuntimeError(f'Delivery alias differs: {row["remote"]}')
    record=read(root/'acceptance/accepted_case.json')
    suites=sorted(root.glob('benchmark/*/scenes/*/suite_manifest.json'))
    if len(suites)!=1:
        raise RuntimeError(f'Expected one packaged suite manifest, found {suites}')
    if not audit_suite_manifest(read(suites[0]),VOCAB,root)['all_edits_compliant']:
        raise RuntimeError('Strict edit audit of the accepted delivery failed')
    caches={}
    for row in record['variants']:
        case=row['id']
        if case not in selection:
            continue
        native=root/'cases'/case
        if sha(native/'simulation.npz')!=row['native_cache_sha256']:
            raise RuntimeError(f'Accepted native cache bytes differ for {case}')
        if not read(native/'motion_audit.json')['passed']:
            raise RuntimeError(f'Motion audit of {case} did not pass')
        caches[case]=row['native_cache_sha256']
    if set(caches)!=set(selection):
        raise RuntimeError('An accepted branch is missing')
    return {'delivery':str(root),'delivery_files_verified':len(spec['files']),'aliases_verified':len(spec['aliases']),
            'native_cache_sha256':caches,'packaged_suite_edits_compliant':True}


def decoded_frames(video):
    """Frames ffprobe decodes from the whole stream (None when ffprobe is not installed)."""
    if not shutil.which('ffprobe'):
        return None
    out=subprocess.run(['ffprobe','-v','error','-count_frames','-select_streams','v:0','-show_entries',
                        'stream=nb_read_frames','-of','csv=p=0',str(video)],capture_output=True,text=True,check=True)
    return int(out.stdout.strip())


def verify_suite(root,selection,native_caches):
    root=Path(root)
    manifest=read(root/'suite_manifest.json')
    pointer=canonical_suite()['case_video_sha256']
    source,edits=catalog()
    records={manifest['source']['case_id']:manifest['source'],**{e['case_id']:e for e in manifest['edits']}}
    if set(records)!={'source',*('edit_'+k for k in edits)}:
        raise RuntimeError(f'Suite cases differ from the catalog: {sorted(records)}')
    rows=[]
    for native in selection:
        case='source' if native=='source' else 'edit_'+native
        record=records[case]
        declared=source if native=='source' else edits[native]
        folder=root/'cases'/case
        video=folder/'video.mp4'
        digest=sha(video)
        prompts=read(folder/'prompts.json')
        provenance=read(folder/'provenance.json')
        if not digest==record['video_sha256']==provenance['video_sha256']==pointer[native]:
            raise RuntimeError(f'Video sha256 of {case} disagrees between file, suite manifest, provenance and pointer')
        if prompts['prompts']!=declared['prompts'] or record['prompts']!=declared['prompts']:
            raise RuntimeError(f'Prompts of {case} differ from the builder catalog')
        if native!='source':
            for key in ('edit_dsl','physics_override','physics_diff'):
                if prompts[key]!=declared[key]:
                    raise RuntimeError(f'{key} of {case} differs from the builder catalog')
        media=require_video(video)
        decoded=decoded_frames(video)
        if decoded not in (None,96):
            raise RuntimeError(f'{case}: {decoded} decodable frames')
        gt=read(folder/'ground_truth_transforms.json')
        if gt.get('format_version')!='pcve_ground_truth/1' or gt['frame_end']!=96 or len(gt['frames'])!=96:
            raise RuntimeError(f'Ground truth of {case} is not pcve_ground_truth/1 with 96 frames')
        require_times([f['time_sec'] for f in gt['frames']])
        if read(folder/'native_metadata/render_report.json')['input_cache_sha256']!=native_caches[native]:
            raise RuntimeError(f'The video of {case} was not rendered from the accepted native cache')
        rows.append({'case':case,'video_sha256':digest,'media':{k:media[k] for k in ('width','height','fps','frames','duration_s','codec')},
                     'decoded_frames':decoded,
                     'ground_truth_frames':len(gt['frames'])})
    return {'suite':str(root),'cases':rows,'catalog_prompts_equal':True}


def verify(delivery,suite,selection):
    native=verify_native(delivery,selection)
    return {'native_delivery':native,'suite':verify_suite(suite,selection,native['native_cache_sha256'])}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter)
    cases=read(CASE/'entrypoints.json')['entrypoints']['build_pcve']['cases']
    parser.add_argument('--delivery',type=Path,default=None)
    parser.add_argument('--suite',type=Path,default=None)
    parser.add_argument('--cases',nargs='+',choices=cases,default=cases)
    args=parser.parse_args()
    print(json.dumps(verify(args.delivery or native_delivery(),args.suite or suite_dir(),args.cases),indent=2,ensure_ascii=False))
