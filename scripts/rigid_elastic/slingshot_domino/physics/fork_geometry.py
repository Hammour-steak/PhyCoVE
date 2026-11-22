"""Exact common Y-frame profile, static Bullet mesh and finite-width band contact."""
import numpy as np
from numba import njit
from fork_profile import OUTLINE,HALF_DEPTH

def cross(a,b):return float(a[0]*b[1]-a[1]*b[0])

def mesh():
    # Ear clipping the concave 2D polygon; no Blender execution or extraction.
    area=sum(cross(OUTLINE[i],OUTLINE[(i+1)%len(OUTLINE)])for i in range(len(OUTLINE)))/2
    remaining=list(range(len(OUTLINE)))
    if area<0:remaining.reverse()
    triangles=[]
    while len(remaining)>3:
        found=False
        for k,b in enumerate(remaining):
            a=remaining[k-1];c=remaining[(k+1)%len(remaining)];A,B,C=OUTLINE[[a,b,c]]
            if cross(B-A,C-B)<=1e-14:continue
            contained=False
            for j in remaining:
                if j in(a,b,c):continue
                p=OUTLINE[j]
                if min(cross(B-A,p-A),cross(C-B,p-B),cross(A-C,p-C))>=-1e-14:contained=True;break
            if contained:continue
            triangles.append((a,b,c));remaining.pop(k);found=True;break
        if not found:raise ValueError('Non-simple Y-frame profile')
    triangles.append(tuple(remaining));n=len(OUTLINE)
    vertices=np.array([(x,y,z)for x in(-HALF_DEPTH,HALF_DEPTH)for y,z in OUTLINE])
    faces=[]
    for a,b,c in triangles:faces.extend([(c,b,a),(a+n,b+n,c+n)])
    for i in range(n):
        j=(i+1)%n
        if area>0:faces.extend([(i,j,j+n),(i,j+n,i+n)])
        else:faces.extend([(i,j+n,j),(i,i+n,j+n)])
    return vertices,np.array(faces,dtype=np.int32)

@njit(cache=False)
def sdf(point):
    y,z=point[1],point[2];inside=False;best=1e9;closest_y=0.;closest_z=0.
    for i in range(len(OUTLINE)):
        a=OUTLINE[i];b=OUTLINE[(i+1)%len(OUTLINE)];dy=b[0]-a[0];dz=b[1]-a[1]
        if (a[1]>z)!=(b[1]>z):
            if y<dy*(z-a[1])/dz+a[0]:inside=not inside
        u=max(0.,min(1.,((y-a[0])*dy+(z-a[1])*dz)/(dy*dy+dz*dz)))
        cy=a[0]+u*dy;cz=a[1]+u*dz;dist=(y-cy)**2+(z-cz)**2
        if dist<best:best=dist;closest_y=cy;closest_z=cz
    distance=max(best,1e-24)**.5;ny=(y-closest_y)/distance;nz=(z-closest_z)/distance
    if inside:distance=-distance;ny=-ny;nz=-nz
    dx=abs(point[0])-HALF_DEPTH;nx=1. if point[0]>=0 else -1.
    if dx<=0 and distance<=0:
        if dx>distance:return dx,np.array([nx,0.,0.])
        return distance,np.array([0.,ny,nz])
    ax=max(dx,0.);ay=max(distance,0.);out=(ax*ax+ay*ay)**.5
    if out<1e-12:return 0.,np.array([nx,0.,0.])
    return out,np.array([nx*ax/out,ny*ay/out,nz*ay/out])

@njit(cache=False)
def contact(x,v,directors,l0,width,thickness):
    maximum_projection=0.
    for i in range(1,len(x)-1):
        if i*l0<.014:continue
        # Broad phase includes the actual finite strip width.
        if abs(x[i,0])>HALF_DEPTH+width/2+.0002 or abs(x[i,1])>.056 or x[i,2]<.015 or x[i,2]>.143:continue
        length=np.linalg.norm(x[i+1]-x[i-1])/2;stretch=max(length/l0,1.)
        w=width/stretch**.5;h=thickness/stretch**.5
        for iteration in range(2):
            for k in range(5):
                sample=x[i]+((k-2)/4)*w*directors[i]
                distance,normal=sdf(sample);gap=h/2+.000015-distance
                if gap<=0:continue
                x[i]+=normal*gap;vn=np.dot(v[i],normal)
                if vn<0:
                    impulse=-1.02*vn;v[i]+=normal*impulse
                    tangent=v[i]-np.dot(v[i],normal)*normal;speed=np.linalg.norm(tangent)
                    if speed>1e-12:v[i]-=min(1.,.6*impulse/speed)*tangent
                maximum_projection=max(maximum_projection,gap)
    return maximum_projection
