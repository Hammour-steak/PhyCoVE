"""Metric Y profile shared verbatim by physics and remote Blender geometry."""
import numpy as np
OUTLINE=np.array([[-.011,.018],[-.014,.057],[-.024,.080],[-.051,.119],[-.053,.140],[-.034,.140],[-.032,.121],[-.020,.105],[-.010,.096],[0.,.093],[.010,.096],[.020,.105],[.032,.121],[.034,.140],[.053,.140],[.051,.119],[.024,.080],[.014,.057],[.011,.018]])
HALF_DEPTH=.0095

# Nominal SI geometry shared by Bullet and Blender. Manufacturing bevels and
# decorative screw threads do not change these conservative contact envelopes.
TABLE_EDGE_Y=-.08
MOUNT_BOXES=[
 dict(id='mounting_foot',name='Maple mounting foot',center=[0.,0.,.009],size=[.054,.085,.018],material='wood',bevel=.0015),
 dict(id='clamp_upper_jaw',name='Clamp steel upper jaw',center=[-.004,-.035,.022],size=[.044,.024,.007],material='metal',bevel=.001),
 dict(id='clamp_bridge',name='Clamp bridge over table',center=[-.004,-.0635,.022],size=[.021,.057,.007],material='metal',bevel=.001),
 dict(id='clamp_spine',name='Clamp C spine',center=[-.004,-.092,-.025],size=[.021,.015,.10],material='metal',bevel=.002),
 dict(id='clamp_lower_jaw',name='Clamp lower jaw',center=[-.004,-.066,-.072],size=[.021,.067,.012],material='metal',bevel=.001),
]
MOUNT_CYLINDERS=[
 dict(id='clamp_screw',name='Clamp screw shaft',center=[-.004,-.053,-.058],radius=.003,depth=.050,axis=[0,0,1]),
 dict(id='clamp_pressure_swivel',name='Clamp lower pressure swivel',center=[-.004,-.053,-.031],radius=.009,depth=.004,axis=[0,0,1]),
 dict(id='clamp_crossbar',name='Clamp screw crossbar',center=[-.004,-.053,-.090],radius=.0018,depth=.055,axis=[1,0,0]),
]
MOUNT_SPHERES=[dict(id='clamp_end_'+str(i),name='Clamp handle ball end',center=[x,-.053,-.090],radius=.003)for i,x in enumerate([-.032,.024])]
