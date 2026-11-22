"""Shared metric layout of the dining-table scene (metres, z up, table top at z = 0).

Imported by both the geometry/collider builders and the Blender Cycles renderer so
all tabletop props match their simulation colliders.
"""

CUP_ASSET_OBJECT = "MUG.004"      # BlenderKit coffee cup set: hero ceramic mug
CUP_ASSET_COFFEE = "Circle.003"   # Coffee disk used to centre the mug cavity in x/y
CUP_HEIGHT = 0.072                # Overall mug height (m)
CUP_ASSET_ID = "a89253f5-fa09-48af-8f9d-3f8a104c4b2b"

SAUCER_ASSET_OBJECT = "plate.004"
SPOON_ASSET_OBJECT = "spoon.000"

TABLE_SIZE = (1.30, 0.96, 0.065)  # Solid timber table slab, top face at z = 0.0

# Authored porcelain saucer + stainless spoon placed to the back-left of the landing zone
PLATE_XY = (-0.27, 0.10)
SAUCER_SCALE = 1.42
SAUCER_YAW_DEG = 22.0
PLATE_RADIUS = 0.06682 * SAUCER_SCALE
PLATE_RIM_HEIGHT = 0.0135 * SAUCER_SCALE

# Three-fold woven kitchen linen placed to the back-right of the landing zone
NAPKIN_XY = (0.26, 0.15)
NAPKIN_SIZE = (0.180, 0.145)
NAPKIN_TOP = 0.0085
NAPKIN_YAW_DEG = -16.0

# Elevated 45 mm dining-table camera framing the full 0.284 m drop and tabletop splash
CAMERA_LOCATION = (0.48, -0.74, 0.66)
CAMERA_TARGET = (0.0, 0.0, 0.17)
CAMERA_FOCUS_TARGET = (0.0, 0.0, 0.045)
CAMERA_LENS_MM = 45.0
CAMERA_SENSOR_MM = 36.0
CAMERA_FSTOP = 8.0
