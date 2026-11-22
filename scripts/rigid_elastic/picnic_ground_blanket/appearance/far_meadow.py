"""Continue scanned turf through the actual camera footprint at metric scale."""
from pathlib import Path
import hashlib
import math
import bpy
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree


def smoothstep(x):
    x=np.clip(x,0.,1.)
    return x*x*(3.-2.*x)


def continue_meadow(scene,density=500.,aperture=16.,overlap_floor=.30):
    """Fill missing background roots without touching near-field contact grass."""
    rng=np.random.default_rng(20261031)
    camera=scene.camera;camera.data.dof.aperture_fstop=aperture
    transform=np.asarray(camera.matrix_world);inverse=np.linalg.inv(transform)
    width,height=scene.render.resolution_x,scene.render.resolution_y
    focal=width*camera.data.lens/camera.data.sensor_width
    def project(xyz):
        local=xyz@inverse[:3,:3].T+inverse[:3,3];depth=-local[:,2]
        return np.column_stack([width*.5+focal*local[:,0]/depth,height*.5-focal*local[:,1]/depth]),depth
    # The upper edge sees ground 30--40 m away. Include a margin beyond all
    # image edges, so canopy tips and depth of field cannot reveal a cutoff.
    corners=[]
    for u,v in [(-48,-3),(width+48,-3),(width+48,190),(-48,190)]:
        direction=transform[:3,:3]@np.array([(u-width*.5)/focal,(height*.5-v)/focal,-1.])
        assert direction[2]<0
        corners.append(transform[:3,3]+(-.007-transform[2,3])/direction[2]*direction)
    corners=np.asarray(corners);lo=corners[:,:2].min(0)-.25;hi=corners[:,:2].max(0)+.25
    pitch=1/math.sqrt(density)
    x,y=np.meshgrid(np.arange(lo[0],hi[0],pitch),np.arange(lo[1],hi[1],pitch),indexing='ij')
    xy=np.column_stack([x.reshape(-1),y.reshape(-1)])+rng.uniform(-.47*pitch,.47*pitch,(x.size,2))
    xyz=np.column_stack([xy,np.full(len(xy),-.007)])
    uv,depth=project(xyz)
    valid=(uv[:,0]>=-48)&(uv[:,0]<=width+48)&(uv[:,1]>=-3)&(uv[:,1]<=190)&(depth>0)
    xyz=xyz[valid];uv=uv[valid];depth=depth[valid]
    # Match the density already present, rather than double-planting its
    # transition zone. Smooth the world-space density field over 1.5--2 m.
    existing=[]
    template=bpy.data.objects['Lawn | instanced photographed plant species'].modifiers[0].node_group
    for ob in scene.objects:
        if ob.type!='MESH' or 'plant_scale' not in ob.data.attributes:continue
        points=np.empty((len(ob.data.vertices),3),np.float64);ob.data.vertices.foreach_get('co',points.reshape(-1))
        m=np.asarray(ob.matrix_world);existing.append(points@m[:3,:3].T+m[:3,3])
    existing=np.vstack(existing)
    step=.5;edges=[np.arange(lo[k]-2,hi[k]+2+step,step)for k in [0,1]]
    field=np.histogram2d(existing[:,0],existing[:,1],bins=edges)[0]/(step*step)
    kernel=np.array([1,4,6,4,1],np.float64)/16.
    for axis in [0,1]:
        field=np.apply_along_axis(lambda a:np.convolve(a,kernel,mode='same'),axis,field)
    ij=np.floor((xyz[:,:2]-np.array([edges[0][0],edges[1][0]]))/step).astype(int)
    ij=np.clip(ij,0,np.asarray(field.shape)-1)
    # Some original instances are very narrow leaf cards: counting their
    # roots alone overestimates canopy cover. Keep a modest mixed understory
    # in the overlap instead of leaving a pale strip at the old lawn edge.
    deficit=np.clip(1-field[ij[:,0],ij[:,1]]/density,overlap_floor,1.)
    blend=smoothstep((depth-3.8)/2.5)
    # Gentle natural variation, at a metre scale; individual plants keep their
    # actual 4.5--8 cm height at every distance.
    variation=.91+.09*np.sin(xyz[:,0]*1.7+np.sin(xyz[:,1]*1.1))
    keep=rng.random(len(xyz))<deficit*blend*variation
    xyz=xyz[keep]
    # Plant on the same actual terrain meshes, including the outer continuation.
    trees=[]
    for name in ['Photographed meadow ground','Continuous distant photographed terrain']:
        ob=bpy.data.objects.get(name)
        if ob is None:continue
        points=np.asarray([v.co[:]for v in ob.data.vertices]);m=np.asarray(ob.matrix_world)
        points=points@m[:3,:3].T+m[:3,3]
        trees.append(BVHTree.FromPolygons(points.tolist(),[list(p.vertices)for p in ob.data.polygons]))
    assert len(trees)==2
    normal=np.zeros((len(xyz),3),np.float64);misses=0
    for i,(px,py,unused)in enumerate(xyz):
        hits=[tree.ray_cast(Vector((float(px),float(py),1.)),Vector((0,0,-1)),3.)for tree in trees]
        hits=[hit for hit in hits if hit[0] is not None]
        if not hits:misses+=1;continue
        hit=min(hits,key=lambda hit:hit[3]);xyz[i,2]=float(hit[0].z)-.0005;normal[i]=hit[1]
        # The historical continuation ring may have downward polygon winding.
        # Plant growth follows the upward geometric normal on either surface.
        if normal[i,2]<0:normal[i]*=-1
    if misses:raise RuntimeError(f'Background grass roots missed the actual terrain: {misses}')
    plants=[ob for ob in bpy.data.collections['Plant sources | Poly Haven CC0'].objects if ob.type=='MESH']
    heights=np.array([max(v.co.z for v in ob.data.vertices)for ob in plants])
    widths=np.array([max(np.ptp(np.asarray([v.co[:]for v in ob.data.vertices])[:,:2],axis=0))for ob in plants])
    choices=[];weights=[]
    for i,ob in enumerate(plants):
        if ob.name.startswith('grass_bermuda_01') and .04<=heights[i]<=.105 and widths[i]>=.045:
            choices.append(i);weights.append(.95 if 'dead'not in ob.name else .18)
        elif ob.name.startswith('grass_medium_01') and .045<=heights[i]<=.15 and widths[i]>=.06:
            choices.append(i);weights.append(.65)
        elif ob.name.startswith('shrub_sorrel_01') and widths[i]>.04:
            choices.append(i);weights.append(.045)
    weights=np.asarray(weights);weights/=weights.sum()
    ids=rng.choice(choices,len(xyz),p=weights).astype(np.int32)
    target_height=rng.uniform(.045,.080,len(xyz))
    scale=np.repeat((target_height/heights[ids])[:,None],3,axis=1)
    scale[:,:2]*=rng.uniform(.9,1.1,(len(xyz),2))
    shrink=np.minimum(1.,.16/(widths[ids]*scale[:,:2].max(1)+1e-12));scale[:,:2]*=shrink[:,None]
    rotation=np.zeros((len(xyz),3),np.float64)
    rotation[:,0]=np.arctan2(-normal[:,1],normal[:,2])+rng.uniform(-.05,.05,len(xyz))
    rotation[:,1]=np.arctan2(normal[:,0],normal[:,2])+rng.uniform(-.05,.05,len(xyz))
    rotation[:,2]=rng.uniform(-math.pi,math.pi,len(xyz))
    xyz=xyz.astype(np.float32);scale=scale.astype(np.float32);rotation=rotation.astype(np.float32)
    mesh=bpy.data.meshes.new('Metric far-meadow rooted point set');mesh.from_pydata(xyz.tolist(),[],[])
    for key,typ,values in [('plant_id','INT',ids),('plant_scale','FLOAT_VECTOR',scale),('plant_rotation','FLOAT_VECTOR',rotation)]:
        attr=mesh.attributes.new(key,typ,'POINT');attr.data.foreach_set('value' if typ=='INT' else 'vector',values.reshape(-1))
    ob=bpy.data.objects.new('Far meadow | continuous scanned turf',mesh);scene.collection.objects.link(ob)
    modifier=ob.modifiers.new('Same scanned plant species at real metric scale','NODES');modifier.node_group=template
    uv,depth=project(xyz);visible=(uv[:,0]>=0)&(uv[:,0]<width)&(uv[:,1]>=0)&(uv[:,1]<height)&(depth>0)
    old_uv,old_depth=project(existing)
    old_visible=(old_uv[:,0]>=0)&(old_uv[:,0]<width)&(old_uv[:,1]>=0)&(old_uv[:,1]<height)&(old_depth>0)
    bands=[0,20,40,80,120,190]
    rows=[dict(y0=a,y1=b,new_roots=int((visible&(uv[:,1]>=a)&(uv[:,1]<b)).sum()))for a,b in zip(bands,bands[1:])]
    for row in rows:
        row['existing_roots']=int((old_visible&(old_uv[:,1]>=row['y0'])&(old_uv[:,1]<row['y1'])).sum())
        row['total_roots']=row['existing_roots']+row['new_roots']
    assert all(row['new_roots']>0 for row in rows[:3]),rows
    assert all(row['total_roots']>0 for row in rows),rows
    return dict(seed=20261031,instances=len(xyz),layout_sha256=hashlib.sha256(xyz.tobytes()+ids.tobytes()+scale.tobytes()+rotation.tobytes()).hexdigest(),
        root_bounds=[xyz.min(0).tolist(),xyz.max(0).tolist()],
        physical_height_range_m=[.045,.080],maximum_clump_width_m=.16,target_density_per_m2=density,overlap_density_floor=overlap_floor,
        terrain_root_misses=misses,terrain_normals_oriented_up=True,root_embedding_m=.0005,screen_root_counts=rows,
        aperture_fstop=aperture,focus_distance_m=float(camera.data.dof.focus_distance),
        source='Existing Poly Haven CC0 scanned Bermuda grass, meadow grass and sparse sorrel; no new external asset',
        near_field_physics_and_contact_vegetation_unchanged=True,static_background=True)
