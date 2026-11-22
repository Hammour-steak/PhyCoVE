"""Shared analytic tangency ledger, metres, Z up. No simulation dependency."""
import math

CUP_TILT_DEG=58.0
CUP_HEIGHT=.055
CUP_OUTER_RADIUS=.037
CUP_INNER_RADIUS=.0315
CUP_BOTTOM_THICKNESS=.006
SUPPORT_SIZE=(.035,.045,.028)
_a=math.radians(CUP_TILT_DEG)
CUP_CENTER_Z=CUP_OUTER_RADIUS*math.sin(_a)+.5*CUP_HEIGHT*math.cos(_a)
SUPPORT_CENTER_X=(-.5*CUP_HEIGHT-math.cos(_a)*(SUPPORT_SIZE[2]-CUP_CENTER_Z))/math.sin(_a)-.5*SUPPORT_SIZE[0]
LOW_INNER_RIM_Z=CUP_CENTER_Z+.5*CUP_HEIGHT*math.cos(_a)-CUP_INNER_RADIUS*math.sin(_a)


def ledger():
    return {'cup_center_m':[0,0,CUP_CENTER_Z],
            'cup_euler_deg':[0,CUP_TILT_DEG,0],
            'support_center_m':[SUPPORT_CENTER_X,0,.5*SUPPORT_SIZE[2]],
            'support_size_m':list(SUPPORT_SIZE),
            'cup_min_z_m':CUP_CENTER_Z-CUP_OUTER_RADIUS*math.sin(_a)-.5*CUP_HEIGHT*math.cos(_a),
            'support_front_edge_signed_gap_m':math.sin(_a)*(SUPPORT_CENTER_X+.5*SUPPORT_SIZE[0])+math.cos(_a)*(SUPPORT_SIZE[2]-CUP_CENTER_Z)+.5*CUP_HEIGHT,
            'low_inner_rim_z_m':LOW_INNER_RIM_Z}
