"""Install the pinned Linux Blender-Python SciPy wheel into this scene only."""
import argparse,hashlib,json,platform,tempfile,urllib.request,zipfile
from pathlib import Path

VERSION='1.11.4'
WHEEL='scipy-1.11.4-cp311-cp311-manylinux_2_17_x86_64.manylinux2014_x86_64.whl'
SHA256='530f9ad26440e85766509dbf78edcfe13ffd0ab7fec2560ee5c36ff74d6269ff'
URL='https://files.pythonhosted.org/packages/6b/d4/d62ce38ba00dc67d7ec4ec5cc19d36958d8ed70e63778715ad626bcbc796/'+WHEEL

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--target',type=Path,default=Path(__file__).resolve().parents[4]/'.runtime/juice_dispenser_orange_cup/solver_vendor')
    p.add_argument('--wheel',type=Path,help='Use an existing wheel with the pinned checksum.')
    args=p.parse_args()
    if platform.system()!='Linux' or platform.machine() not in {'x86_64','AMD64'}:
        p.error('This pinned wheel is for Linux x86_64 and Blender 4.3.2 Python 3.11.')
    manifest=args.target/'_pcve_dependency.json'
    if manifest.exists() and json.loads(manifest.read_text()).get('sha256')==SHA256:
        print('Pinned solver dependency already installed:',args.target)
        return
    if args.target.exists() and any(args.target.iterdir()):
        raise RuntimeError('Refusing to replace a nonempty dependency directory: '+str(args.target))
    with tempfile.TemporaryDirectory(prefix='pcve-viscosity-') as scratch:
        wheel=args.wheel or Path(scratch)/WHEEL
        if args.wheel is None:
            urllib.request.urlretrieve(URL,wheel)
        if hashlib.sha256(wheel.read_bytes()).hexdigest()!=SHA256:
            raise RuntimeError('SciPy wheel checksum mismatch')
        args.target.mkdir(parents=True,exist_ok=True)
        with zipfile.ZipFile(wheel) as archive:
            for name in archive.namelist():
                path=Path(name)
                if path.is_absolute() or '..' in path.parts:
                    raise RuntimeError('Unsafe wheel member')
            archive.extractall(args.target)
    manifest.write_text(json.dumps({'version':VERSION,'wheel':WHEEL,'sha256':SHA256,'url':URL},indent=2)+'\n')
    print('Installed isolated solver dependency:',args.target)

if __name__=='__main__':
    main()
