"""A small joinery workshop built around the simulator's workbench.

The simulation knows three things: the floor z = 0, the workbench (a 2.65 m x
1.25 m top, 9 cm thick, on four plank legs) and the moving bodies. This module
draws the bench exactly on its collision boxes, so the face the ball rolls on is
the collision face, and builds an ordinary workshop around it: a concrete floor
whose top is z = 0, whitewashed brick walls, a steel-framed window in the back
wall, an OSB tool board with hand tools, a worn shelf unit and a few things on
and under the bench. All of it comes from Poly Haven (CC0).

Light is daylight only: a sun lamp low in the east-south-east shines through a
window in the east wall, which is behind the right edge of the frame, and a
physical sky is sampled through area-light portals in both windows. What the
camera sees through the back window is a farmland HDRI, used for camera rays
only and turned so that its sun sits where the sun lamp is.

Nothing here is simulated, so ``check_clearance`` refuses a take in which a
moving body comes within 2 cm of a prop, and ``check_sightlines`` refuses one in
which a prop hides a moving body from the camera.
"""
from __future__ import annotations

import math
from pathlib import Path
from typing import Any

import bmesh
import bpy
from mathutils import Matrix, Vector

WALL_THICK_M = 0.24


# ------------------------------------------------------------------ geometry


def _finish(bm: bmesh.types.BMesh, name: str, material, smooth: bool = False) -> bpy.types.Object:
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    for poly in mesh.polygons:
        poly.use_smooth = smooth
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    if material is not None:
        obj.data.materials.append(material)
    return obj


def _rectangle(x0: float, x1: float, y0: float, y1: float) -> list[Vector]:
    return [Vector((x0, y0)), Vector((x1, y0)), Vector((x1, y1)), Vector((x0, y1))]


def _slab(name: str, outline: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed prism over a convex outline."""
    bm = bmesh.new()
    low = [bm.verts.new((p.x, p.y, z0)) for p in outline]
    high = [bm.verts.new((p.x, p.y, z1)) for p in outline]
    bm.faces.new(low)
    bm.faces.new(high)
    for i in range(len(outline)):
        j = (i + 1) % len(outline)
        bm.faces.new((low[i], low[j], high[j], high[i]))
    return _finish(bm, name, material)


def _ring(name: str, outer: list[Vector], inner: list[Vector], z0: float, z1: float, material) -> bpy.types.Object:
    """A closed band between two outlines with matching corners."""
    bm = bmesh.new()
    o0, o1, i0, i1 = [[bm.verts.new((p.x, p.y, z)) for p in outline]
                      for outline in (outer, inner) for z in (z0, z1)]
    for i in range(len(outer)):
        j = (i + 1) % len(outer)
        bm.faces.new((o0[i], o0[j], o1[j], o1[i]))
        bm.faces.new((i0[i], i1[i], i1[j], i0[j]))
        bm.faces.new((o0[i], i0[i], i0[j], o0[j]))
        bm.faces.new((o1[i], o1[j], i1[j], i1[i]))
    return _finish(bm, name, material)


def box(name: str, centre, size, material, yaw: float = 0.0, bevel: float = 0.0,
        matrix: Matrix | None = None) -> bpy.types.Object:
    """A box mesh baked in world space; ``matrix`` (rotation) overrides ``yaw``."""
    bm = bmesh.new()
    bmesh.ops.create_cube(bm, size=1.0)
    bmesh.ops.scale(bm, vec=Vector(size), verts=bm.verts)
    rotation = matrix.to_4x4() if matrix is not None else Matrix.Rotation(yaw, 4, 'Z')
    bmesh.ops.transform(bm, matrix=Matrix.Translation(Vector(centre)) @ rotation, verts=bm.verts)
    obj = _finish(bm, name, material)
    if bevel:
        mod = obj.modifiers.new('Eased edges', 'BEVEL')
        mod.width, mod.segments = bevel, 2
        obj.modifiers.new('Weighted normals', 'WEIGHTED_NORMAL')
    return obj


def cylinder(name: str, start, end, radius: float, material, vertices: int = 24) -> bpy.types.Object:
    a, b = Vector(start), Vector(end)
    bm = bmesh.new()
    bmesh.ops.create_cone(bm, cap_ends=True, segments=vertices, radius1=radius, radius2=radius, depth=(b - a).length)
    rotation = (b - a).to_track_quat('Z', 'Y').to_matrix().to_4x4()
    bmesh.ops.transform(bm, matrix=Matrix.Translation((a + b) / 2) @ rotation, verts=bm.verts)
    obj = _finish(bm, name, material, smooth=True)
    return obj


def _cut(target: bpy.types.Object, cutter: bpy.types.Object) -> None:
    mod = target.modifiers.new(f'cut {cutter.name}', 'BOOLEAN')
    mod.operation = 'DIFFERENCE'
    mod.solver = 'EXACT'
    mod.object = cutter
    bpy.context.view_layer.objects.active = target
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter, do_unlink=True)


def world_bounds(objects) -> tuple[Vector, Vector]:
    """Axis-aligned bounds of the evaluated meshes (modifiers included)."""
    depsgraph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(depsgraph)
        mesh = evaluated.to_mesh()
        points += [evaluated.matrix_world @ v.co for v in mesh.vertices]
        evaluated.to_mesh_clear()
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    return lo, hi


# ----------------------------------------------------------------- materials


def _nodes(mat):
    return mat.node_tree.nodes, mat.node_tree.links


def material(name: str, colour, roughness: float, metallic: float = 0.0) -> bpy.types.Material:
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*colour, 1.0)
    mat.use_nodes = True
    bsdf = mat.node_tree.nodes.get('Principled BSDF')
    bsdf.inputs['Base Color'].default_value = (*colour, 1.0)
    bsdf.inputs['Roughness'].default_value = roughness
    bsdf.inputs['Metallic'].default_value = metallic
    return mat


def _image(nodes, path: Path, colour: bool):
    node = nodes.new('ShaderNodeTexImage')
    node.image = bpy.data.images.load(str(path), check_existing=True)
    if not colour:
        node.image.colorspace_settings.name = 'Non-Color'
    node.extension = 'REPEAT'
    return node


def scanned(name: str, asset_dir: Path, stem: str, tile_m: float, *, rotate_deg: float = 0.0,
            roughness_range=(0.0, 1.0), normal_strength: float = 1.0, tint=None, box_blend: float = 0.15) -> bpy.types.Material:
    """A Poly Haven texture set (colour, roughness, OpenGL normal) at its real size.

    Box projection on object coordinates in metres, so walls, floor and
    boards all get the scan at the size it was photographed; the meshes here
    are built in world space, so object and world coordinates coincide.
    """
    mat = material(name, (0.5, 0.5, 0.5), 0.5)
    nodes, links = _nodes(mat)
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Scale'].default_value = (1.0 / tile_m,) * 3
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, math.radians(rotate_deg))
    links.new(coord.outputs['Object'], mapping.inputs['Vector'])

    def tex(kind: str, colour: bool):
        node = _image(nodes, asset_dir / f'{stem}_{kind}_2k.jpg', colour)
        node.projection = 'BOX'
        node.projection_blend = box_blend
        links.new(mapping.outputs['Vector'], node.inputs['Vector'])
        return node

    colour = tex('diff', True).outputs['Color']
    if tint is not None:
        mix = nodes.new('ShaderNodeMix')
        mix.data_type = 'RGBA'
        mix.blend_type = 'MULTIPLY'
        mix.inputs['Factor'].default_value = 1.0
        links.new(colour, mix.inputs['A'])
        mix.inputs['B'].default_value = (*tint, 1.0)
        colour = mix.outputs['Result']
    links.new(colour, bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = roughness_range
    links.new(tex('rough', False).outputs['Color'], rough.inputs['Value'])
    links.new(rough.outputs['Result'], bsdf.inputs['Roughness'])
    normal = nodes.new('ShaderNodeNormalMap')
    normal.inputs['Strength'].default_value = normal_strength
    links.new(tex('nor_gl', False).outputs['Color'], normal.inputs['Color'])
    links.new(normal.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def _math(nodes, links, operation, a, b=None, c=None):
    node = nodes.new('ShaderNodeMath')
    node.operation = operation
    for index, value in enumerate((a, b, c)):
        if value is None:
            continue
        if isinstance(value, (int, float)):
            node.inputs[index].default_value = value
        else:
            links.new(value, node.inputs[index])
    return node.outputs[0]


def solid_wood(name: str, asset_dir: Path, stem: str, *, axis: str, pith=(0.35, 0.22), tile_m: float = 1.0,
               offset=(0.0, 0.0), oil: float = 0.8, roughness_range=(0.32, 0.55), coat: float = 0.15,
               ring_m: float = 0.0045, tint=(1.0, 1.0, 1.0), figure: float = 0.0,
               albedo=None, scan_mean=None) -> bpy.types.Material:
    """Sawn hardwood made from a flat veneer scan, wrapped the way a board grows.

    ``axis`` is the grain direction in object space. A point's texture
    coordinate is (distance along the grain, distance from a pith line parallel
    to it), so long-grain faces show the scan running along the grain and the
    two end-grain faces, where that coordinate degenerates, get growth rings of
    the same timber, darker and rougher, centred on the same pith line. The
    same rule wraps a turned ball: long grain round its middle, end grain at
    its two poles. ``oil`` darkens and saturates the scan as an oil finish does;
    ``tint`` multiplies it (an oiled timber is warmer than its raw veneer scan)
    and ``figure`` raises the contrast of the grain, as oil does by soaking
    deeper into the porous late wood. With ``albedo`` and ``scan_mean`` (the
    scan's mean colour, linear RGB) the scan is instead graded so its mean is
    ``albedo`` and ``figure`` is a luminance exponent.
    """
    index = 'xyz'.index(axis)
    mat = material(name, (0.4, 0.25, 0.15), 0.45)
    nodes, links = _nodes(mat)
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], split.inputs['Vector'])
    along = split.outputs['XYZ'[index]]
    across = [split.outputs['XYZ'[i]] for i in range(3) if i != index]
    da = _math(nodes, links, 'SUBTRACT', across[0], pith[0])
    db = _math(nodes, links, 'SUBTRACT', across[1], pith[1])
    radius = _math(nodes, links, 'SQRT', _math(nodes, links, 'ADD', _math(nodes, links, 'MULTIPLY', da, da),
                                                   _math(nodes, links, 'MULTIPLY', db, db)))
    uv = nodes.new('ShaderNodeCombineXYZ')
    links.new(_math(nodes, links, 'MULTIPLY_ADD', along, 1.0 / tile_m, offset[0]), uv.inputs['X'])
    links.new(_math(nodes, links, 'MULTIPLY_ADD', radius, 1.0 / tile_m, offset[1]), uv.inputs['Y'])
    diff = _image(nodes, asset_dir / f'{stem}_diff_2k.jpg', True)
    rough_map = _image(nodes, asset_dir / f'{stem}_rough_2k.jpg', False)
    for node in (diff, rough_map):
        links.new(uv.outputs['Vector'], node.inputs['Vector'])
    # Oil: deeper and a touch more saturated than the raw veneer scan.
    hsv = nodes.new('ShaderNodeHueSaturation')
    hsv.inputs['Saturation'].default_value = 1.0 + 0.25 * oil
    hsv.inputs['Value'].default_value = 1.0 - 0.28 * oil
    contrast = nodes.new('ShaderNodeBrightContrast')
    contrast.inputs['Contrast'].default_value = figure
    links.new(diff.outputs['Color'], contrast.inputs['Color'])
    links.new(contrast.outputs['Color'], hsv.inputs['Color'])
    warm = nodes.new('ShaderNodeMix')
    warm.data_type = 'RGBA'
    warm.blend_type = 'MULTIPLY'
    warm.inputs['Factor'].default_value = 1.0
    links.new(hsv.outputs['Color'], warm.inputs['A'])
    warm.inputs['B'].default_value = (*tint, 1.0)
    oiled = warm.outputs['Result']
    if albedo is not None:
        # Graded to a measured colour instead: scale the scan so its mean lands
        # on ``albedo`` (both linear RGB) and steepen the grain in luminance
        # only, so the hue stays that of the timber, not of a contrast curve.
        for node in (hsv, contrast, warm):
            nodes.remove(node)
        graded = nodes.new('ShaderNodeMix')
        graded.data_type = 'RGBA'
        graded.blend_type = 'MULTIPLY'
        graded.inputs['Factor'].default_value = 1.0
        links.new(diff.outputs['Color'], graded.inputs['A'])
        graded.inputs['B'].default_value = (*(a / m for a, m in zip(albedo, scan_mean)), 1.0)
        luma = nodes.new('ShaderNodeRGBToBW')
        links.new(diff.outputs['Color'], luma.inputs['Color'])
        mean_luma = 0.2126 * scan_mean[0] + 0.7152 * scan_mean[1] + 0.0722 * scan_mean[2]
        grain = _math(nodes, links, 'POWER', _math(nodes, links, 'DIVIDE', luma.outputs['Val'], mean_luma), figure)
        scaled = nodes.new('ShaderNodeVectorMath')
        scaled.operation = 'SCALE'
        links.new(graded.outputs['Result'], scaled.inputs[0])
        links.new(grain, scaled.inputs['Scale'])
        oiled = scaled.outputs['Vector']
    # End grain: annual rings of the same pith line, darker and thirstier.
    rings = _math(nodes, links, 'FRACT', _math(nodes, links, 'DIVIDE', radius, ring_m))
    ring_band = nodes.new('ShaderNodeMapRange')
    ring_band.interpolation_type = 'SMOOTHSTEP'
    ring_band.inputs['From Min'].default_value, ring_band.inputs['From Max'].default_value = 0.55, 0.95
    links.new(rings, ring_band.inputs['Value'])
    end_tone = nodes.new('ShaderNodeMix')
    end_tone.data_type = 'RGBA'
    end_tone.blend_type = 'MULTIPLY'
    links.new(ring_band.outputs['Result'], end_tone.inputs['Factor'])
    links.new(oiled, end_tone.inputs['A'])
    end_tone.inputs['B'].default_value = (0.55, 0.47, 0.42, 1.0)
    end_dark = nodes.new('ShaderNodeMix')
    end_dark.data_type = 'RGBA'
    end_dark.blend_type = 'MULTIPLY'
    end_dark.inputs['Factor'].default_value = 1.0
    links.new(end_tone.outputs['Result'], end_dark.inputs['A'])
    end_dark.inputs['B'].default_value = (0.70, 0.64, 0.60, 1.0)
    # How much a face looks down the grain: |object normal . axis|.
    normal_split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Normal'], normal_split.inputs['Vector'])
    facing = _math(nodes, links, 'ABSOLUTE', normal_split.outputs['XYZ'[index]])
    end_mask = nodes.new('ShaderNodeMapRange')
    end_mask.interpolation_type = 'SMOOTHSTEP'
    end_mask.inputs['From Min'].default_value, end_mask.inputs['From Max'].default_value = 0.55, 0.85
    links.new(facing, end_mask.inputs['Value'])
    colour = nodes.new('ShaderNodeMix')
    colour.data_type = 'RGBA'
    links.new(end_mask.outputs['Result'], colour.inputs['Factor'])
    links.new(oiled, colour.inputs['A'])
    links.new(end_dark.outputs['Result'], colour.inputs['B'])
    links.new(colour.outputs['Result'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = roughness_range
    links.new(rough_map.outputs['Color'], rough.inputs['Value'])
    rough_end = _math(nodes, links, 'MULTIPLY_ADD', end_mask.outputs['Result'], 0.25, rough.outputs['Result'])
    links.new(rough_end, bsdf.inputs['Roughness'])
    # Grain relief from the scan's luminance (a tangent-space normal map would
    # need UVs that follow the grain, which these procedural coordinates are not).
    luma = nodes.new('ShaderNodeRGBToBW')
    links.new(diff.outputs['Color'], luma.inputs['Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.25
    bump.inputs['Distance'].default_value = 0.0004
    links.new(luma.outputs['Val'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    if coat:
        bsdf.inputs['Coat Weight'].default_value = coat
        bsdf.inputs['Coat Roughness'].default_value = 0.35
    return mat


def bench_top(name: str, asset_dir: Path, stem: str, strip_m: float = 0.045) -> bpy.types.Material:
    """A laminated hardwood worktop: strips along x, each its own piece of the scan.

    Every 4.5 cm strip (by y) samples the veneer at a random offset, is flipped
    or not, and is a few percent lighter or darker, as glued-up strips are; the
    surface is planed and oiled, then worn: pencil-grey grime and duller
    roughness drift over it at a few decimetres.
    """
    mat = material(name, (0.6, 0.5, 0.4), 0.5)
    nodes, links = _nodes(mat)
    bsdf = nodes.get('Principled BSDF')
    coord = nodes.new('ShaderNodeTexCoord')
    split = nodes.new('ShaderNodeSeparateXYZ')
    links.new(coord.outputs['Object'], split.inputs['Vector'])
    strip = _math(nodes, links, 'FLOOR', _math(nodes, links, 'DIVIDE', split.outputs['Y'], strip_m))
    noise = nodes.new('ShaderNodeTexWhiteNoise')
    noise.noise_dimensions = '1D'
    links.new(strip, noise.inputs['W'])
    rnd = nodes.new('ShaderNodeSeparateColor')
    links.new(noise.outputs['Color'], rnd.inputs['Color'])
    uv = nodes.new('ShaderNodeCombineXYZ')
    # Strips run along x; the scan's grain runs along its u axis.
    links.new(_math(nodes, links, 'ADD', split.outputs['X'], _math(nodes, links, 'MULTIPLY', rnd.outputs['Red'], 7.0)),
              uv.inputs['X'])
    links.new(_math(nodes, links, 'ADD', _math(nodes, links, 'ADD', split.outputs['Y'], split.outputs['Z']),
                    _math(nodes, links, 'MULTIPLY', rnd.outputs['Green'], 5.0)), uv.inputs['Y'])
    diff = _image(nodes, asset_dir / f'{stem}_diff_2k.jpg', True)
    rough_map = _image(nodes, asset_dir / f'{stem}_rough_2k.jpg', False)
    for node in (diff, rough_map):
        links.new(uv.outputs['Vector'], node.inputs['Vector'])
    shade = nodes.new('ShaderNodeHueSaturation')
    links.new(diff.outputs['Color'], shade.inputs['Color'])
    links.new(_math(nodes, links, 'MULTIPLY_ADD', rnd.outputs['Blue'], 0.26, 0.78), shade.inputs['Value'])
    links.new(_math(nodes, links, 'MULTIPLY_ADD', rnd.outputs['Red'], 0.03, 0.485), shade.inputs['Hue'])
    shade.inputs['Saturation'].default_value = 1.0
    # Years of oil and light have yellowed the ash.
    aged = nodes.new('ShaderNodeMix')
    aged.data_type = 'RGBA'
    aged.blend_type = 'MULTIPLY'
    aged.inputs['Factor'].default_value = 1.0
    links.new(shade.outputs['Color'], aged.inputs['A'])
    aged.inputs['B'].default_value = (0.95, 0.89, 0.80, 1.0)
    # Glue lines between strips: half a millimetre of darker joint.
    within = _math(nodes, links, 'FRACT', _math(nodes, links, 'DIVIDE', split.outputs['Y'], strip_m))
    edge = _math(nodes, links, 'MINIMUM', within, _math(nodes, links, 'SUBTRACT', 1.0, within))
    joint = nodes.new('ShaderNodeMapRange')
    joint.inputs['From Min'].default_value, joint.inputs['From Max'].default_value = 0.0, 0.012
    joint.inputs['To Min'].default_value, joint.inputs['To Max'].default_value = 0.55, 0.0
    links.new(edge, joint.inputs['Value'])
    glued = nodes.new('ShaderNodeMix')
    glued.data_type = 'RGBA'
    glued.blend_type = 'MULTIPLY'
    links.new(joint.outputs['Result'], glued.inputs['Factor'])
    links.new(aged.outputs['Result'], glued.inputs['A'])
    glued.inputs['B'].default_value = (0.45, 0.38, 0.30, 1.0)
    shade = glued
    # Workshop grime: large soft patches, slightly grey and darker.
    grime = nodes.new('ShaderNodeTexNoise')
    grime.inputs['Scale'].default_value = 3.0
    grime.inputs['Detail'].default_value = 6.0
    grime.inputs['Roughness'].default_value = 0.6
    links.new(coord.outputs['Object'], grime.inputs['Vector'])
    grime_mask = nodes.new('ShaderNodeMapRange')
    grime_mask.inputs['From Min'].default_value, grime_mask.inputs['From Max'].default_value = 0.45, 0.75
    grime_mask.inputs['To Max'].default_value = 0.45
    links.new(grime.outputs['Fac'], grime_mask.inputs['Value'])
    dirty = nodes.new('ShaderNodeMix')
    dirty.data_type = 'RGBA'
    dirty.blend_type = 'MULTIPLY'
    links.new(grime_mask.outputs['Result'], dirty.inputs['Factor'])
    links.new(shade.outputs['Result'], dirty.inputs['A'])
    dirty.inputs['B'].default_value = (0.55, 0.52, 0.50, 1.0)
    links.new(dirty.outputs['Result'], bsdf.inputs['Base Color'])
    rough = nodes.new('ShaderNodeMapRange')
    rough.inputs['To Min'].default_value, rough.inputs['To Max'].default_value = 0.50, 0.70
    links.new(rough_map.outputs['Color'], rough.inputs['Value'])
    links.new(_math(nodes, links, 'ADD', rough.outputs['Result'], grime_mask.outputs['Result']), bsdf.inputs['Roughness'])
    luma = nodes.new('ShaderNodeRGBToBW')
    links.new(diff.outputs['Color'], luma.inputs['Color'])
    bump = nodes.new('ShaderNodeBump')
    bump.inputs['Strength'].default_value = 0.15
    bump.inputs['Distance'].default_value = 0.0003
    links.new(luma.outputs['Val'], bump.inputs['Height'])
    links.new(bump.outputs['Normal'], bsdf.inputs['Normal'])
    return mat


def thin_glass() -> bpy.types.Material:
    """Thin float glass: a 4 % Fresnel reflection over a see-through layer.

    Cycles' Fresnel node inverts the IOR on back faces, so a ray leaving the
    pane at a grazing angle would be totally reflected and the pane would go
    black; feeding 1/1.52 on back faces cancels that inversion.
    """
    existing = bpy.data.materials.get('Clear float glass')
    if existing is not None:
        return existing
    mat = bpy.data.materials.new('Clear float glass')
    mat.use_nodes = True
    nodes, links = _nodes(mat)
    for node in [n for n in nodes if n.type != 'OUTPUT_MATERIAL']:
        nodes.remove(node)
    clear = nodes.new('ShaderNodeBsdfTransparent')
    reflection = nodes.new('ShaderNodeBsdfGlossy')
    reflection.inputs['Roughness'].default_value = 0.0
    fresnel = nodes.new('ShaderNodeFresnel')
    geometry = nodes.new('ShaderNodeNewGeometry')
    ior = nodes.new('ShaderNodeMath')
    ior.operation = 'MULTIPLY_ADD'
    ior.inputs[1].default_value = 1.0 / 1.52 - 1.52
    ior.inputs[2].default_value = 1.52
    links.new(geometry.outputs['Backfacing'], ior.inputs[0])
    links.new(ior.outputs['Value'], fresnel.inputs['IOR'])
    pane = nodes.new('ShaderNodeMixShader')
    links.new(fresnel.outputs['Fac'], pane.inputs['Fac'])
    links.new(clear.outputs['BSDF'], pane.inputs[1])
    links.new(reflection.outputs['BSDF'], pane.inputs[2])
    links.new(pane.outputs['Shader'], nodes['Material Output'].inputs['Surface'])
    return mat


# ------------------------------------------------------------------ daylight


def _aim(obj: bpy.types.Object, point) -> None:
    obj.rotation_euler = (Vector(point) - obj.location).to_track_quat('-Z', 'Y').to_euler()


def daylight(spec: dict[str, Any], hdri: Path, target) -> dict[str, Any]:
    """A sun lamp and a physical sky for lighting; a farmland HDRI for the view.

    ``sun_heading_deg`` is the direction the light travels, in degrees from +x
    towards +y. The HDRI is visible to camera rays only (it is what the back
    window shows) and is turned so its own sun, at azimuth ``hdri_sun_u`` of
    the equirectangular image, lies where the sun lamp shines from.
    """
    el = math.radians(float(spec['sun_elevation_deg']))
    heading = math.radians(float(spec['sun_heading_deg']))
    travel = Vector((math.cos(el) * math.cos(heading), math.cos(el) * math.sin(heading), -math.sin(el)))
    sun_data = bpy.data.lights.new('Morning sun', 'SUN')
    sun_data.energy = float(spec['sun_energy'])
    sun_data.angle = math.radians(0.53)
    sun_data.color = tuple(spec['sun_color'])
    sun = bpy.data.objects.new('Morning sun', sun_data)
    bpy.context.collection.objects.link(sun)
    sun.location = Vector(target) - 8.0 * travel
    _aim(sun, sun.location + travel)

    scene = bpy.context.scene
    scene.world = bpy.data.worlds.new('Morning sky')
    scene.world.use_nodes = True
    nodes, links = scene.world.node_tree.nodes, scene.world.node_tree.links
    sky = nodes.new('ShaderNodeTexSky')
    sky.sky_type = 'NISHITA'
    # The lamp is the sun; the sky model's own disc would be a second one.
    sky.sun_disc = False
    sky.sun_elevation = el
    # Nishita puts the sun at (sin r, cos r) in the ground plane: r = 0 is +y.
    sky.sun_rotation = math.atan2(-travel.x, -travel.y)
    sky.air_density, sky.dust_density = 1.0, 2.0
    lighting = nodes['Background']
    links.new(sky.outputs['Color'], lighting.inputs['Color'])
    lighting.inputs['Strength'].default_value = float(spec['sky_strength'])

    # Camera-only view: Blender's equirectangular lookup puts direction d at
    # u = atan2(d.y, -d.x) / 2pi + 0.5, so the HDRI's sun points along azimuth
    # (u - 0.5) * 2pi measured from -x towards +y. Rotate the lookup so the
    # direction the sun lamp shines from lands on it.
    sun_from = math.atan2(-travel.y, -travel.x)
    hdri_sun = math.pi - (float(spec['hdri_sun_u']) - 0.5) * 2.0 * math.pi
    coord = nodes.new('ShaderNodeTexCoord')
    mapping = nodes.new('ShaderNodeMapping')
    mapping.inputs['Rotation'].default_value = (0.0, 0.0, hdri_sun - sun_from)
    links.new(coord.outputs['Generated'], mapping.inputs['Vector'])
    environment = nodes.new('ShaderNodeTexEnvironment')
    environment.image = bpy.data.images.load(str(hdri), check_existing=True)
    links.new(mapping.outputs['Vector'], environment.inputs['Vector'])
    view = nodes.new('ShaderNodeBackground')
    links.new(environment.outputs['Color'], view.inputs['Color'])
    view.inputs['Strength'].default_value = float(spec['view_strength'])
    path = nodes.new('ShaderNodeLightPath')
    mix = nodes.new('ShaderNodeMixShader')
    links.new(path.outputs['Is Camera Ray'], mix.inputs['Fac'])
    links.new(lighting.outputs['Background'], mix.inputs[1])
    links.new(view.outputs['Background'], mix.inputs[2])
    links.new(mix.outputs['Shader'], nodes['World Output'].inputs['Surface'])
    return {key: spec[key] for key in ('sun_elevation_deg', 'sun_heading_deg', 'sun_energy', 'sky_strength', 'view_strength')}


def _portal(name: str, centre, size, inward) -> None:
    """An area-light portal across an opening, so Cycles samples the sky
    through it instead of waiting for a bounce to find it."""
    data = bpy.data.lights.new(name, 'AREA')
    data.shape = 'RECTANGLE'
    data.size, data.size_y = size
    data.cycles.is_portal = True
    obj = bpy.data.objects.new(name, data)
    bpy.context.collection.objects.link(obj)
    obj.location = centre
    _aim(obj, Vector(centre) + Vector(inward))


# ---------------------------------------------------------------------- room


def _wall_frames(room: dict[str, Any]) -> dict[str, tuple[float, Vector, Vector]]:
    """Inner-face coordinate, along-wall direction and inward normal of each wall."""
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    along_y, along_x = Vector((0.0, 1.0, 0.0)), Vector((1.0, 0.0, 0.0))
    return {'east': (float(x_hi), along_y, Vector((-1.0, 0.0, 0.0))),
            'west': (float(x_lo), along_y, Vector((1.0, 0.0, 0.0))),
            'north': (float(y_hi), along_x, Vector((0.0, -1.0, 0.0))),
            'south': (float(y_lo), along_x, Vector((0.0, 1.0, 0.0)))}


def _window(index: int, spec: dict[str, Any], frames, walls, steel, sill) -> dict[str, Any]:
    """A steel-framed workshop window: a hole through the brick, a painted
    steel frame with glazing bars set in the middle of the reveal, thin glass,
    a concrete sill and a sky portal."""
    face, along, inward = frames[spec['wall']]
    outward = -inward
    s0, s1 = (float(v) for v in spec['span'])
    z0, z1 = (float(v) for v in spec['z'])
    width, height = s1 - s0, z1 - z0
    sc, zc = (s0 + s1) / 2.0, (z0 + z1) / 2.0
    base = Vector((face, sc, zc)) if along.y else Vector((sc, face, zc))
    yaw = math.atan2(along.y, along.x)

    def at(depth: float, offset: float = 0.0, z: float = zc) -> Vector:
        return base + outward * depth + along * offset + Vector((0.0, 0.0, z - zc))

    name = f'Window {index + 1} ({spec["wall"]})'
    _cut(walls, box(f'{name} hole', at(WALL_THICK_M / 2), (width, WALL_THICK_M + 0.2, height), None, yaw))
    depth = WALL_THICK_M * 0.55
    rail, thick, bar = 0.045, 0.040, 0.022
    box(f'{name} head', at(depth, 0.0, z1 - rail / 2), (width, thick, rail), steel, yaw, 0.002)
    box(f'{name} bottom rail', at(depth, 0.0, z0 + rail / 2), (width, thick, rail), steel, yaw, 0.002)
    for sign in (-1, 1):
        box(f'{name} jamb {sign:+d}', at(depth, sign * (width - rail) / 2), (rail, thick, height - 2 * rail), steel, yaw, 0.002)
    columns, rows = int(spec['panes'][0]), int(spec['panes'][1])
    inner_w, inner_h = width - 2 * rail, height - 2 * rail
    for k in range(1, columns):
        offset = -inner_w / 2 + k * inner_w / columns
        box(f'{name} glazing bar v{k}', at(depth, offset), (bar, thick - 0.008, inner_h), steel, yaw, 0.001)
    for k in range(1, rows):
        z = z0 + rail + k * inner_h / rows
        box(f'{name} glazing bar h{k}', at(depth, 0.0, z), (inner_w, thick - 0.010, bar), steel, yaw, 0.001)
    pane = box(f'{name} glass', at(depth), (inner_w, 0.004, inner_h), thin_glass(), yaw)
    pane.visible_shadow = False
    box(f'{name} sill', at(depth / 2 - 0.02, 0.0, z0 - 0.02), (width + 0.06, depth + 0.07, 0.04), sill, yaw, 0.003)
    _portal(f'{name} sky portal', at(WALL_THICK_M + 0.01), (width, height), inward)
    return {'wall': spec['wall'], 'span': [s0, s1], 'z': [z0, z1], 'panes': [columns, rows],
            'centre': [round(v, 4) for v in at(0.0)]}


# ------------------------------------------------------------------- props


def place_model(path: Path, name: str, *, yaw_deg: float = 0.0, axes=None, **anchor: float) -> list[bpy.types.Object]:
    """Import a glTF model, bake it, turn it and set its bounding box on an anchor.

    Every mesh that carries a material is baked to world space from the
    evaluated depsgraph (so rigged models keep their rest pose) and helper
    geometry without a material is dropped. ``axes`` gives the world
    directions of the model's local x and y axes (to hang a saw on a wall);
    otherwise the model is turned by ``yaw_deg`` about z. Anchor keys: ``x`` /
    ``y`` (box centre), ``x_min`` / ``x_max`` / ``y_min`` / ``y_max`` (faces),
    ``z`` (bottom) or ``z_max`` (top).
    """
    before = set(bpy.data.objects)
    bpy.ops.import_scene.gltf(filepath=str(path))
    bpy.context.view_layer.update()
    imported = [o for o in bpy.data.objects if o not in before]
    for obj in imported:
        obj.animation_data_clear()
    depsgraph = bpy.context.evaluated_depsgraph_get()
    if axes is not None:
        ax, ay = Vector(axes[0]).normalized(), Vector(axes[1]).normalized()
        rotation = Matrix((ax, ay, ax.cross(ay))).transposed().to_4x4()
    else:
        rotation = Matrix.Rotation(math.radians(yaw_deg), 4, 'Z')
    parts = []
    for source in imported:
        if source.type != 'MESH' or not any(slot.material for slot in source.material_slots):
            continue
        evaluated = source.evaluated_get(depsgraph)
        data = bpy.data.meshes.new_from_object(evaluated, preserve_all_data_layers=True, depsgraph=depsgraph)
        data.transform(rotation @ source.matrix_world)
        part = bpy.data.objects.new(f'{name} {len(parts) + 1}', data)
        bpy.context.collection.objects.link(part)
        parts.append(part)
    for obj in imported:
        if obj.name in bpy.data.objects:
            bpy.data.objects.remove(obj, do_unlink=True)
    if not parts:
        raise ValueError(f'No textured mesh in {path}')
    points = [v.co for part in parts for v in part.data.vertices]
    lo = Vector([min(p[i] for p in points) for i in range(3)])
    hi = Vector([max(p[i] for p in points) for i in range(3)])
    shift = Vector((0.0, 0.0, 0.0))
    for axis, index in (('x', 0), ('y', 1)):
        if axis in anchor:
            shift[index] = anchor[axis] - (lo[index] + hi[index]) / 2.0
        elif f'{axis}_min' in anchor:
            shift[index] = anchor[f'{axis}_min'] - lo[index]
        elif f'{axis}_max' in anchor:
            shift[index] = anchor[f'{axis}_max'] - hi[index]
    shift.z = anchor['z_max'] - hi.z if 'z_max' in anchor else anchor.get('z', 0.0) - lo.z
    for part in parts:
        part.data.transform(Matrix.Translation(shift))
    bpy.context.view_layer.update()
    return parts


def surface_below(x: float, y: float, z_from: float, ignore=()) -> float:
    """Height of the first surface straight below (x, y, z_from)."""
    scene = bpy.context.scene
    depsgraph = bpy.context.evaluated_depsgraph_get()
    origin = Vector((x, y, z_from))
    while True:
        hit, location, _, _, obj, _ = scene.ray_cast(depsgraph, origin, Vector((0, 0, -1)))
        if not hit:
            raise ValueError(f'Nothing below ({x}, {y}, {z_from})')
        if obj not in ignore:
            return location.z
        origin = location + Vector((0, 0, -1e-4))


class Props:
    """Every object that is not simulated, with its world bounds, by name."""

    def __init__(self) -> None:
        self.items: dict[str, list[bpy.types.Object]] = {}

    def add(self, name: str, objects) -> list[bpy.types.Object]:
        objects = list(objects) if isinstance(objects, (list, tuple)) else [objects]
        if name in self.items:
            raise ValueError(f'Duplicate prop name {name}')
        self.items[name] = objects
        return objects

    def bounds(self) -> dict[str, tuple[Vector, Vector]]:
        return {name: world_bounds(objs) for name, objs in self.items.items()}

    def objects(self) -> set:
        return {obj for objs in self.items.values() for obj in objs}


def check_clearance(props: Props, samples: list[tuple[Vector, float]], margin: float = 0.02) -> dict[str, float]:
    """Smallest gap between any moving body's bounding sphere and each prop's box.

    ``samples`` are (centre, radius) for every present body in every frame of
    the take.
    """
    gaps = {}
    for name, (lo, hi) in props.bounds().items():
        gaps[name] = min(math.sqrt(sum(max(lo[i] - c[i], 0.0, c[i] - hi[i]) ** 2 for i in range(3))) - radius
                         for c, radius in samples)
    for name, gap in gaps.items():
        if gap < margin:
            raise ValueError(f'a moving body passes within {gap:.3f} m of {name}; move it')
    closest = sorted(gaps.items(), key=lambda item: item[1])[:4]
    print('[workshop] closest props: ' + ', '.join(f'{k} {v:.3f} m' for k, v in closest), flush=True)
    return {k: round(v, 4) for k, v in gaps.items()}


def check_sightlines(scene, camera, moving: dict[str, bpy.types.Object], frames: list[int], blockers: set) -> int:
    """Refuse a take in which a prop hides part of a moving body from the camera.

    Rays go from the camera to the centre and to the middle of the top face of
    every moving body's evaluated bounds in every frame; the first thing a ray
    meets must be one of the moving bodies (they may hide each other).
    """
    rays = 0
    moving_set = set(moving.values())
    for index in frames:
        scene.frame_set(index)
        depsgraph = bpy.context.evaluated_depsgraph_get()
        origin = camera.matrix_world.translation.copy()
        for key, obj in moving.items():
            corners = [obj.matrix_world @ Vector(c) for c in obj.bound_box]
            centre = sum(corners, Vector()) / 8.0
            top = Vector((centre.x, centre.y, max(c.z for c in corners) - 0.004))
            for point in (centre, top):
                direction = point - origin
                hit, _, _, _, obj_hit, _ = scene.ray_cast(depsgraph, origin, direction.normalized(),
                                                          distance=direction.length)
                rays += 1
                if hit and obj_hit not in moving_set and obj_hit in blockers:
                    raise RuntimeError(f'{obj_hit.name} hides {key} from the camera at frame {index}')
    return rays


# ------------------------------------------------------------------ assembly


def _model(asset_dir: Path, model: str) -> Path:
    return asset_dir / model / f'{model}_1k.gltf'


def build_workshop(room: dict[str, Any], look: dict[str, Any], asset_dir: Path, table: list[dict[str, Any]]):
    """Floor, walls, windows, the bench on its collision boxes, props and daylight.

    ``table`` is the simulator's bench (``building_geometry.table_parts``):
    its top box and four legs are drawn as they are, so the bench top the
    camera sees is the collision face. Returns (info, props).
    """
    (x_lo, x_hi), (y_lo, y_hi) = room['x'], room['y']
    ceiling_z = float(room['ceiling_m'])
    grow = lambda d: _rectangle(x_lo - d, x_hi + d, y_lo - d, y_hi + d)
    props = Props()

    brick = scanned('Whitewashed brick', asset_dir, look['brick']['stem'], look['brick']['tile_m'],
                    roughness_range=(0.75, 0.95))
    floor = scanned('Garage concrete floor', asset_dir, look['floor']['stem'], look['floor']['tile_m'],
                    roughness_range=(0.55, 0.9))
    osb = scanned('Oriented strand board', asset_dir, look['board']['stem'], look['board']['tile_m'],
                  roughness_range=(0.6, 0.85), normal_strength=0.6)
    sill = scanned('Concrete window sill', asset_dir, look['floor']['stem'], look['floor']['tile_m'],
                   roughness_range=(0.6, 0.85), tint=(1.25, 1.22, 1.18))
    ceiling = material('Limewashed ceiling', (0.70, 0.69, 0.66), 0.92)
    steel = material('Painted steel window frame', (0.045, 0.055, 0.050), 0.42)

    def ash(name: str, axis: str, offset) -> bpy.types.Material:
        return solid_wood(name, asset_dir, look['bench_top'], axis=axis, offset=offset, pith=(0.4, -0.3), oil=0.35,
                          roughness_range=(0.45, 0.65), coat=0.0)

    # --- shell: the floor's top face is the simulator's ground plane z = 0
    _slab('Concrete floor', grow(WALL_THICK_M), -0.05, 0.0, floor)
    _slab('Ceiling', grow(WALL_THICK_M), ceiling_z, ceiling_z + 0.12, ceiling)
    walls = _ring('Brick walls', grow(WALL_THICK_M), grow(0.0), -0.05, ceiling_z + 0.12, brick)
    frames = _wall_frames(room)
    windows = [_window(i, w, frames, walls, steel, sill) for i, w in enumerate(look['windows'])]
    ground = box('Ground outside', (0.0, 0.0, -0.4), (200.0, 200.0, 0.3), material('Ground outside', (0.16, 0.15, 0.12), 0.9))
    ground.visible_camera = False

    # --- the bench, on the simulator's boxes
    top = table[0]
    box('Workbench top', top['location'], top['size'], bench_top('Laminated ash worktop', asset_dir, look['bench_top']),
        bevel=0.002)
    for k, leg in enumerate(table[1:]):
        box(f'Workbench leg {k + 1}', leg['location'], leg['size'], ash(f'Ash leg {k + 1}', 'z', (0.2 * k, 0.1)), bevel=0.002)
    legs_x = sorted({round(leg['location'][0], 4) for leg in table[1:]})
    leg_half = table[1]['size'][0] / 2
    shelf_x = (legs_x[0] + leg_half, legs_x[-1] - leg_half)
    shelf_mid = (shelf_x[0] + shelf_x[1]) / 2
    rails = []
    for side in (-1, 1):
        rails.append(box(f'Shelf rail {side:+d}', (shelf_mid, side * 0.28, 0.12), (shelf_x[1] - shelf_x[0], 0.045, 0.045),
                         ash(f'Ash rail {side:+d}', 'x', (0.5 + side * 0.2, 0.3)), bevel=0.002))
    lower = box('Lower shelf', (shelf_mid, 0.0, 0.151), (shelf_x[1] - shelf_x[0], 0.64, 0.018), osb, bevel=0.001)
    props.add('Bench shelf and rails', [lower, *rails])

    # --- tool board on the back wall, standing off on 2 cm battens
    board = look['tool_board']
    face_y = y_hi - 0.02 - 0.018
    props.add('OSB tool board', box('OSB tool board', ((board['x'][0] + board['x'][1]) / 2, y_hi - 0.02 - 0.009,
                                                       (board['z'][0] + board['z'][1]) / 2),
                                    (board['x'][1] - board['x'][0], 0.018, board['z'][1] - board['z'][0]), osb, bevel=0.001))
    peg_wood = material('Beech dowel', (0.42, 0.30, 0.20), 0.55)
    hang = [('Handsaw', 'handsaw_wood', ((0, 1, 0), (0, 0, 1)), 0.78, 1.86, [(0.0, -0.035)]),
            ('Cross-pein hammer', 'cross_pein_hammer', ((1, 0, 0), (0, 1, 0)), 1.12, 1.80, [(-0.03, -0.045), (0.03, -0.045)]),
            ('Hand drill', 'vintage_hand_drill', ((1, 0, 0), (0, 1, 0)), 1.40, 1.88, [(0.0, -0.13)]),
            ('Screwdrivers', 'screwdrivers_02', ((1, 0, 0), (0, 0, 1)), 1.68, 1.78, [])]
    for name, model, axes, x, z_top, pegs in hang:
        parts = place_model(_model(asset_dir, model), name, axes=axes, x=x, y_max=face_y - 0.004, z_max=z_top)
        lo, hi = world_bounds(parts)
        for k, (dx, dz) in enumerate(pegs):
            parts.append(cylinder(f'{name} peg {k + 1}', (x + dx, face_y, z_top + dz), (x + dx, lo.y - 0.006, z_top + dz),
                                  0.006, peg_wood, 12))
        if model == 'screwdrivers_02':
            parts.append(box('Screwdriver rack', (x, face_y - 0.02, z_top - 0.08), (0.13, 0.04, 0.022), peg_wood, bevel=0.002))
        props.add(name, parts)

    # --- worn shelf unit in the back-left corner, a few things on it
    props.add('Wooden shelf unit', place_model(_model(asset_dir, 'wooden_bookshelf_worn'), 'Wooden shelf unit',
                                               x_min=x_lo + 0.02, y_max=y_hi - 0.015, z=0.0))
    shelf_y = y_hi - 0.30
    for name, model, x, z_from, yaw in (('Spray paint cans', 'spray_paint_bottles', -2.02, 1.75, 12.0),
                                        ('Cleaner tin', 'cleaner_tin_01', -2.36, 1.75, 30.0),
                                        ('Oil can', 'small_oil_can_01', -2.12, 1.35, -25.0),
                                        ('Cheese box', 'CheeseBox_01', -2.50, 1.35, 8.0),
                                        ('Lubricant spray', 'lubricant_spray', -1.84, 0.95, 0.0),
                                        ('Rusted can', 'can_rusted', -2.22, 0.95, 0.0)):
        z = surface_below(x, shelf_y, z_from)
        props.add(name, place_model(_model(asset_dir, model), name, yaw_deg=yaw, x=x, y=shelf_y, z=z))
    # Offcuts kept for small jobs: three boards stacked on the lowest shelf.
    z = surface_below(-2.30, shelf_y, 0.55)
    offcuts = []
    for k, (stem, length, width, dx, dyaw) in enumerate((('cherry_veneer', 0.52, 0.13, 0.0, 2.0),
                                                        ('american_walnut_veneer', 0.46, 0.11, 0.03, -4.0),
                                                        ('ash_veneer', 0.50, 0.12, -0.02, 6.0))):
        wood = solid_wood(f'Offcut {k + 1}', asset_dir, stem, axis='x', pith=(0.3, -0.2), offset=(0.3 * k, 0.2),
                          oil=0.2, roughness_range=(0.55, 0.75), coat=0.0)
        offcuts.append(box(f'Offcut {k + 1}', (-2.30 + dx, shelf_y, z + 0.0125 + 0.025 * k), (length, width, 0.025), wood,
                           yaw=math.radians(dyaw), bevel=0.0015))
    props.add('Offcut stack', offcuts)

    # --- on the bench, all well behind the ball's lane or at its far left end
    table_z = top['location'][2] + top['size'][2] / 2
    front = top['location'][1] - top['size'][1] / 2
    # The vice's tommy bar hangs 8.6 cm below its base, in front of the bench edge.
    props.add('Bench vice', place_model(_model(asset_dir, 'bench_vice_01'), 'Bench vice', x=-0.98, y_min=front - 0.035,
                                        z=table_z - 0.086))
    props.add('Smoothing plane', place_model(_model(asset_dir, 'hand_plane_no4'), 'Smoothing plane', yaw_deg=-18.0,
                                             x=-0.55, y=0.42, z=table_z))
    props.add('Tape measure', place_model(_model(asset_dir, 'measuring_tape_01'), 'Tape measure', yaw_deg=35.0,
                                          x=0.88, y=0.44, z=table_z))
    # A carpenter's pencil beside the plane: flat-sided, so it lies still.
    pencil_paint = material('Carpenter pencil paint', (0.62, 0.36, 0.04), 0.45)
    props.add('Pencil', box('Carpenter pencil', (-0.22, 0.31, table_z + 0.004), (0.175, 0.012, 0.008), pencil_paint,
                            yaw=math.radians(24.0), bevel=0.0015))
    props.add('Toolbox under bench', place_model(_model(asset_dir, 'metal_toolbox'), 'Toolbox under bench', yaw_deg=4.0,
                                                 x=-0.40, y=-0.02, z=0.16))

    bounds = props.bounds()
    for name, (lo, hi) in bounds.items():
        print(f'[workshop] {name}: {tuple(round(v, 3) for v in lo)} .. {tuple(round(v, 3) for v in hi)}', flush=True)
    light = daylight(look['daylight'], asset_dir / look['daylight']['hdri'], Vector((0.3, 0.0, table_z)))
    info = {'source': 'built', 'room_lines': {'x': [x_lo, x_hi], 'y': [y_lo, y_hi]}, 'ceiling_z': ceiling_z,
            'windows': windows, 'daylight': light,
            'props': {name: {'bbox_min': [round(v, 4) for v in lo], 'bbox_max': [round(v, 4) for v in hi]}
                      for name, (lo, hi) in bounds.items()}}
    return info, props
