"""Water coverage samples outside the instantaneous physical car footprint."""
import itertools
from mathutils import Quaternion,Vector
POINTS=[(.1,0),(.3,0),(.5,0),(.7,0),(.9,0),(.3,-.15),(.5,-.15),(.7,-.15),(.3,.15),(.5,.15),(.7,.15)]
def samples(evaluated,row,present):
    bounds=None
    if present:
        rotation=Quaternion(row['car_quat_wxyz']).to_matrix();center=Vector(row['car_pos'])
        corners=[center+rotation@Vector(p) for p in itertools.product((-.08,.08),(-.0355,.0355),(-.0275,.0275))]
        bounds=[(min(p[k] for p in corners)-.02,max(p[k] for p in corners)+.02) for k in (0,1)]
    records=[]
    for x,y in POINTS:
        excluded=bool(bounds and bounds[0][0]<=x<=bounds[0][1] and bounds[1][0]<=y<=bounds[1][1])
        hit,p,n,i=evaluated.ray_cast(Vector((x,y,.6)),Vector((0,0,-1)))
        records.append({'xy':[x,y],'hit':hit,'z':p.z if hit else None,'excluded_by_car_footprint':excluded})
    tested=[r for r in records if not r['excluded_by_car_footprint']]
    assert len(tested)>=5 and all(r['hit'] for r in tested),records
    return records
