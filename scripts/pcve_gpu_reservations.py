"""Read only GPU binding fields of live processes; never print full environments."""
from pathlib import Path
import os
def reservations(gpu_rows,exclude=()):
    byindex={str(r[0]):r[1] for r in gpu_rows};uuids=list(byindex.values());found=[]
    for p in Path('/proc').iterdir():
        if not p.name.isdigit() or int(p.name) in exclude:continue
        try:
            args=(p/'cmdline').read_bytes().decode(errors='replace').split('\0')
            exe=Path(args[0]).name if args and args[0] else ''
            if exe!='blender' and not exe.startswith('python'):continue
            if any(Path(a).name=='worker_guard.py' for a in args) and '--gpu' in args:
                binding=args[args.index('--gpu')+1]
            else:
                env=(p/'environ').read_bytes().split(b'\0')
                binding=next((v.decode().split('=',1)[1] for v in env if v.startswith(b'CUDA_VISIBLE_DEVICES=')),'')
            if not binding and exe=='blender':
                for gpu in uuids:found.append({'gpu_uuid':gpu,'pid':p.name,'executable':exe,'binding':'unbound Blender; conservatively reserved'})
                continue
            if not binding or binding=='-1':continue
            selected=[]
            for token in binding.split(','):
                if token in byindex:selected.append(byindex[token])
                else:selected.extend(u for u in uuids if u==token or (token.startswith('GPU-') and u.startswith(token)))
            if binding.lower()=='all':selected=uuids
            for gpu in set(selected):found.append({'gpu_uuid':gpu,'pid':p.name,'executable':exe,'binding':binding})
        except (OSError,ValueError,IndexError):pass
    return found
if __name__=='__main__':
    import subprocess,csv,io
    text=subprocess.check_output(['nvidia-smi','--query-gpu=index,uuid,memory.used,utilization.gpu','--format=csv,noheader,nounits'],text=True,timeout=15)
    rows=list(csv.reader(io.StringIO(text),skipinitialspace=True));print(text,end='')
    print(subprocess.check_output(['nvidia-smi','--query-compute-apps=gpu_uuid,pid','--format=csv,noheader,nounits'],text=True,timeout=15),end='')
    for item in reservations(rows,exclude=(os.getpid(),)):print(item['gpu_uuid']+', '+item['pid'])
