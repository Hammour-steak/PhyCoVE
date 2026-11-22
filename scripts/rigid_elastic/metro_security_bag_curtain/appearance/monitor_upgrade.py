"""A credited, pre-existing inspection image displayed within a modeled LCD."""
import bpy
from pathlib import Path
from scene_paths import ASSETS
def upgrade():
    screen=bpy.data.objects['Inspection monitor'];screen.dimensions.x=.274*1024/745
    image=bpy.data.images.load(str(ASSETS/'xray_monitor/Xray-verkehrshaus.jpg'),check_existing=True)
    for mat in screen.data.materials:
        if mat and mat.use_nodes:
            for node in mat.node_tree.nodes:
                if node.type=='TEX_IMAGE':node.image=image
            mat.node_tree.nodes.get('Principled BSDF').inputs['Emission Strength'].default_value=.30
    screen['display_content']='Prior inspection photo, not the live X-ray of the current simulated bag'
    screen['attribution']='Xray-verkehrshaus.jpg, IDuke, CC BY 2.5, https://commons.wikimedia.org/wiki/File:Xray-verkehrshaus.jpg'
