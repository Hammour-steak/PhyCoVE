"""One shared camera and room layout for the source and all five edits."""
from common import LAYOUT
OPTICS=dict(revision='single_curtain_native_scarf',camera_lens_mm=40.,camera_location=[2.25,-.25,2.3],camera_target=[-.025,.055,.65],background_bed_offset_x=.50,window_curtain_closed=True,
            exposure=.9,view_look='AgX - Medium Low Contrast')
CAMERA_LAYOUT=dict(LAYOUT,camera_lens=OPTICS['camera_lens_mm'],camera_location=OPTICS['camera_location'],camera_target=OPTICS['camera_target'])
