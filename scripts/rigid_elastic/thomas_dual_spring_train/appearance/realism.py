"""Appearance overlay: direct sun through the existing window and a lived-in table."""
from pathlib import Path
import sys

HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(HERE), str(HERE.parent), str(HERE.parents[2])]
import pcve_realism_kit as kit
import toy_railway_props as toys
from pcve_assets import asset

# Track, springs, train and the added block stay inside this volume in every case.
KEEPOUT = ((-.72, -.10, .50), (.72, .10, .85))
PROPS = asset("scenes/thomas_dual_spring_train/realism")


def prop(*args, **kw):
    return kit.prop(PROPS, *args, **kw)


def overlay(scene):
    import bpy
    from mathutils import Vector
    sun = bpy.data.objects["Soft afternoon sunlight"]
    sun.data.energy = 15.0
    sun.data.angle = .03
    # The delivered direction was blocked by the window pier; this one enters the aperture.
    sun.rotation_euler = Vector((1, .35, -.6)).to_track_quat("-Z", "Y").to_euler()
    for obj in scene.objects:  # Sheer curtains would otherwise swallow the whole sun beam.
        if "curtain" in obj.name.lower():
            obj.visible_shadow = False
    bg = scene.world.node_tree.nodes["Background"]
    bg.inputs["Strength"].default_value = 1.5
    bpy.data.objects["Daylight through actual left aperture"].data.energy = 28
    scene.view_settings.look = "AgX - Medium High Contrast"
    scene.view_settings.exposure = .55
    scene.cycles.sample_clamp_indirect = 8.0
    cam = scene.camera
    target = Vector((0, .015, .595))
    cam.location = (.78, -1.74, .92)
    cam.rotation_euler = (target - cam.location).to_track_quat("-Z", "Y").to_euler()
    cam.data.dof.focus_distance = (Vector((0, 0, .597)) - cam.location).length
    cam.data.dof.aperture_fstop = 5.6
    table_z = .56
    for j in range(3):  # The railway accessories replace the delivered painted toy blocks.
        bpy.data.objects.remove(bpy.data.objects["Toy block background " + str(j)], do_unlink=True)
    wood = next(m for m in bpy.data.materials if "maple" in m.name.lower())
    rough = kit.scan_material("Rough sawn toy timber", PROPS / "rough_wood", "rough_wood")
    bare = kit.stained_wood(rough, "Aged toy timber", (1.0, .78, .54), wear=.25)
    leaf = kit.stained_wood(rough, "Green milk paint on timber", (.42, .56, .27))
    roof = kit.stained_wood(rough, "Barn red milk paint on timber", (.80, .26, .16))
    red = kit.stained_wood(rough, "Signal red milk paint on timber", (.95, .20, .13))
    white = kit.stained_wood(rough, "Chalky whitewash on timber", (1.0, .98, .92), wear=.2)
    pieces = toys.tunnel((.19, .30, table_z), 1.33, bare, roof)
    pieces += toys.tree((.47, .33, table_z), bare, leaf)
    pieces += toys.tree((.53, .27, table_z), bare, leaf, height=.066, radius=.023)
    pieces += toys.tree((.37, .24, table_z), bare, leaf, height=.058, radius=.021)
    pieces += toys.signal((-.27, .19, table_z), .25, bare, red, white)
    audit = [
        kit.assert_clear(pieces, KEEPOUT, "toy railway accessories"),
        prop("carved_wooden_elephant", (-.44, .29, table_z), .9, KEEPOUT, rests=True, scale=.5),
        prop("wicker_basket_02", (-.70, .90, 0), .2, KEEPOUT, rests=True),
    ]
    # Handling marks and dust on the worked surfaces; every table in use has them.
    table_mats = {m for o in scene.objects if o.type == "MESH" and o.name.startswith("Cube") for m in o.data.materials if m}
    for mat in table_mats:
        if mat.node_tree and any(n.type == "BSDF_PRINCIPLED" for n in mat.node_tree.nodes):
            kit.add_surface_wear(mat, smudge=.12, grime=.11, scratch=.13, scale=.45)
    kit.sawdust("Table crumbs and dust", [(-.70, -.30, .70, .40, 1), (-.25, .10, .60, .36, 3)], 900,
                ((-.72, -.10), (.72, .10)), color=(.50, .44, .34), size=(.0004, .0014), z=table_z)
    kit.lens_finish(scene)
    kit.write_json(HERE.parents[3] / "renders/thomas_dual_spring_train/last_overlay.json", {
        "worker": kit.host_record(), "dressing_audit": audit})


if __name__ == "__main__":
    import render
    render.OVERLAY = overlay
    render.main()
