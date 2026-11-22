"""Export the actual visible toast as a collider and sampled receiving surface."""
from pathlib import Path
import argparse,hashlib,json,sys
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

parser=argparse.ArgumentParser()
parser.add_argument('--input-blend',type=Path,required=True)
parser.add_argument('--out-dir',type=Path,required=True)
parser.add_argument('--cell',type=float,default=.0005)
args=parser.parse_args(sys.argv[sys.argv.index('--')+1:])
args.out_dir.mkdir(parents=True,exist_ok=True)
bpy.ops.wm.open_mainfile(filepath=str(args.input_blend.resolve()))
obj=bpy.data.objects['PCVE_ToastTextured']
evaluated=obj.evaluated_get(bpy.context.evaluated_depsgraph_get())
mesh=evaluated.to_mesh();mesh.calc_loop_triangles()
vertices=np.array([list(obj.matrix_world@v.co) for v in mesh.vertices])
triangles=np.array([list(p.vertices) for p in mesh.loop_triangles])
tree=BVHTree.FromPolygons(vertices.tolist(),triangles.tolist(),all_triangles=True)
collision=args.out_dir/'toast_collision.obj'
with collision.open('w') as stream:
    for p in vertices:stream.write('v '+' '.join(f'{v:.10g}' for v in p)+'\n')
    for face in triangles:stream.write('f '+' '.join(str(int(i)+1) for i in face)+'\n')
lo=vertices.min(0);hi=vertices.max(0)
xs=np.arange(lo[0]-args.cell,hi[0]+1.5*args.cell,args.cell)
ys=np.arange(lo[1]-args.cell,hi[1]+1.5*args.cell,args.cell)
z=np.full((len(xs),len(ys)),.775);valid=np.zeros(z.shape,bool)
for i,x in enumerate(xs):
    for j,y in enumerate(ys):
        hit,_,_,_=tree.ray_cast(Vector((x,y,.83)),Vector((0,0,-1)))
        if hit is not None:
            z[i,j]=hit.z;valid[i,j]=True
surface=args.out_dir/'toast_surface.npz'
np.savez_compressed(surface,x=xs,y=ys,z=z,valid=valid)
record={'source_scene':str(args.input_blend.resolve()),'object':'PCVE_ToastTextured',
    'vertices':len(vertices),'triangles':len(triangles),'bounds_m':[lo.tolist(),hi.tolist()],
    'sample_cell_m':args.cell,'grid_shape':list(z.shape),'sampled_columns':int(valid.sum()),
    'collision':str(collision),'collision_sha256':hashlib.sha256(collision.read_bytes()).hexdigest(),
    'surface':str(surface),'surface_sha256':hashlib.sha256(surface.read_bytes()).hexdigest()}
(args.out_dir/'toast_contact_manifest.json').write_text(json.dumps(record,indent=2)+'\n')
print('TOAST_CONTACT_EXPORTED',json.dumps(record),flush=True)
