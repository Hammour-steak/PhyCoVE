"""Seated, non-intersecting static paper props; no change to rigid-body inputs."""
from __future__ import annotations
import bpy
from mathutils import Vector

REVISION='seated_laminates'
THICKNESS=.00028
SUPPORT_GAP=.000004
FELT_GAP=.000008
CARD_NAMES=['Loosely dealt 8 of spades','Loosely dealt King of hearts']+[f'Deck card {i:02}' for i in range(1,51)]

def enabled(cfg):
    revision=cfg['appearance']['card_table'].get('paper_support_revision')
    if revision not in [None,REVISION]:raise ValueError('Unknown paper support revision: '+str(revision))
    return revision==REVISION

def flatten_lamina(obj):
    # Retain every outline vertex, face, UV, material and XY coordinate. A pressed
    # deck has flat laminas: warping each offset card independently made it cut
    # through its neighbour. The two loose cards use the same stiff-paper model.
    n=(len(obj.data.vertices)-2)//2
    assert len(obj.data.vertices)==2+2*n
    for vertex in obj.data.vertices:
        layer=1 if vertex.index==1 or vertex.index>=2+n else 0
        vertex.co.z=layer*THICKNESS
    # A planar paper face needs planar normals. Smooth normals across the full
    # triangle fan incorrectly bulged its reflection towards the thin side wall.
    for polygon in obj.data.polygons:polygon.use_smooth=False
    obj.data.update()
    obj['paper_support_revision']=REVISION
    obj['actual_dimensions_m']=[.063,.088,THICKNESS]
    obj['paper_shape_note']='Static stiff-paper lamina; not a cloth simulation.'

def seat_paper(cfg):
    if not enabled(cfg):return {}
    floor=cfg['physics']['floor_z']
    for name in CARD_NAMES:flatten_lamina(bpy.data.objects[name])
    lower=bpy.data.objects[CARD_NAMES[0]];upper=bpy.data.objects[CARD_NAMES[1]]
    assert lower.parent is None and upper.parent is None
    lower.location.z=floor+FELT_GAP
    upper.location.z=lower.location.z+THICKNESS+SUPPORT_GAP
    for i in range(50):
        obj=bpy.data.objects[f'Deck card {i+1:02}']
        obj.location.z=FELT_GAP+i*(THICKNESS+SUPPORT_GAP)
    bpy.context.view_layer.update()
    # The upper card's centre must be supported by the lower card, so its
    # overhang does not imply an unsupported floating sheet.
    upper_center_in_lower=lower.matrix_world.inverted()@upper.matrix_world.translation
    assert abs(upper_center_in_lower.x)<.0315-.0025
    assert abs(upper_center_in_lower.y)<.044-.0025
    return {'paper_support_revision':REVISION,'paper_thickness_m':THICKNESS,
            'paper_interlayer_gap_m':SUPPORT_GAP,'paper_felt_support_gap_m':FELT_GAP,
            'deck_height_m':50*THICKNESS+49*SUPPORT_GAP,
            'upper_loose_card_center_supported_by_lower':True,
            'paper_shape_model':'Static stiff-paper laminas; no paper deformation dynamics claimed.'}

def fibre_exclusion(cfg):
    """Return conservative card footprints enlarged beyond a full ribbon length."""
    if not enabled(cfg):return lambda x,y:False
    bpy.context.view_layer.update()
    transforms=[bpy.data.objects[name].matrix_world.inverted().copy() for name in CARD_NAMES]
    margin=.00055
    # Test the ribbon's starting XY; the expansion covers all six vertices.
    # Only called after all random draws for the ribbon, keeping fibres outside
    # the paper footprints bit-identical to the preserved appearance baseline.
    def exclude(x,y):
        world=Vector((x,y,cfg['physics']['floor_z']))
        for inverse in transforms:
            p=inverse@world
            if abs(p.x)<.0315+margin and abs(p.y)<.044+margin:return True
        return False
    return exclude
