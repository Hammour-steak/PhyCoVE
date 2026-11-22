"""Fixed camera of the current look (appearance/realism.py); tools/export_ground_truth.py reads the same values.

Blender builds it as: camera at `location_m`, -Z towards `target_m`, +Y as close to world +Z as possible,
`lens_mm` on a `sensor_width_mm` sensor fitted horizontally, no lens shift. A tripod at 1.2 m in front of and to
the right of the chair, 2.8 m from it, looking towards the window corner: the chair, the scarf in every case and
the floor where it lands without the chair stay inside the frame.
"""
CAMERA = dict(location_m=(1.4, -2.3, 1.2), target_m=(-0.3, 0.1, 0.55), lens_mm=30.0, sensor_width_mm=36.0,
              shift=(0.0, 0.0), note="tripod view of the published look; the camera of the stored delivery is appearance/optics.py")
