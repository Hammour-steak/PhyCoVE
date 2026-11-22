"""Manufactured fittings for the common metro concourse."""
import math
from pathlib import Path

import bpy

from detail_refinement import bolt
from scene_environment import cube, cylinder, image_material, material, micro

from scene_paths import ASSETS


def printed_face(name, location, width, height, filename, emission=0):
    face = image_material(name, ASSETS/'station_art'/filename, emission)
    bpy.ops.mesh.primitive_plane_add(size=1, location=location, rotation=(math.pi/2, 0, 0))
    obj = bpy.context.object
    obj.name = name
    obj.scale = (width, height, 1)
    obj.data.materials.append(face)


def build(p):
    materials = bpy.data.materials
    steel = materials['Brushed satin stainless steel']
    dark = materials['Dark graphite coated steel']
    accent = material('Glazed teal station enamel', (.035, .139, .167), .29)
    micro(accent, 560, .000016, .12)
    # Enamel modules have vertical breaks aligned to the porcelain panel grid.
    for index in range(-6, 7):
        cube('Glazed wall datum band', (index+.5, 5.112, .83), (.996, .007, .21), accent, .001)
    for x in (-2.4, 2.3):
        for height in (1.70, 1.865):
            cube('Column enamel front cladding', (x, 2.486, height), (.418, .010, .16), accent, .002)
            cube('Column enamel side return', (x+.211, 2.70, height), (.008, .421, .16), accent, .002)

    x, y, z = .40, 2.54, 2.43
    cube('Suspended wayfinding aluminium housing', (x, y, z), (2.10, .087, .32), dark, .007)
    printed_face('Wayfinding recessed backlit face', (x, y-.044, z), 2.065, .288, 'wayfinding.png', .26)
    for delta in (-.147, .147):
        cube('Wayfinding folded face trim', (x, y-.045, z+delta), (2.095, .014, .011), steel, .001)
    for delta in (-.81, .81):
        cylinder('Ceiling sign suspension tube', (x+delta, y, 2.875), .012, .58, steel)
        cylinder('Sign ceiling suspension escutcheon', (x+delta, y, 3.16), .038, .018, steel)
        cylinder('Sign enclosure suspension collar', (x+delta, y, 2.594), .024, .019, steel)

    cube('Rail directory wall mounting back', (.02, 5.111, 1.55), (.99, .025, .62), dark, .004)
    cube('Rail directory aluminium frame', (.02, 5.084, 1.55), (.98, .040, .61), steel, .006)
    printed_face('Rail directory printed insert', (.02, 5.0635, 1.55), .938, .566, 'directory.png')
    for x in (-.448, .488):
        for z in (1.27, 1.83):
            bolt('Directory frame fixing', (x, 5.063, z), 'Y', steel, dark, .0026)

    green = material('Green gate indicator lens', (.016, .36, .125), .23)
    shader = green.node_tree.nodes.get('Principled BSDF')
    shader.inputs['Emission Color'].default_value = (.02, .7, .18, 1)
    shader.inputs['Emission Strength'].default_value = 1.2
    for x in (-.20, .70, 1.60):
        cube('Fare gate front display bezel', (x, 2.998, .898), (.155, .014, .090), dark, .006)
        for side in (-1, 1):
            arrow = cube('Fare gate entry chevron lens', (x+side*.013, 2.989, .903), (.042, .005, .009), green, .002)
            arrow.rotation_euler.y = side*math.radians(39)
        cube('Fare gate entry centre stem', (x, 2.989, .885), (.008, .005, .035), green, .001)
        cube('Fare gate lower kick plate', (x, 2.998, .127), (.264, .009, .145), steel, .003)

    pickup_x = p['pickup_end_x_m']
    pickup_z = p['pickup_height_m']
    cube('Pickup notice mounted plate', (pickup_x-.29, -.322, pickup_z-.040), (.25, .011, .058), dark, .003)
    printed_face('Pickup notice printed insert', (pickup_x-.29, -.328, pickup_z-.040), .233, .048, 'pickup.png')
    return {'overhead_wayfinding': 'Ceiling tubes, folded aluminium housing and recessed print',
            'wall_directory': 'Mounted map frame and generic bilingual line graphic',
            'fare_gate_indicators': 3, 'station_enamel_cladding': True,
            'pickup_identifier': True}
