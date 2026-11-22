"""Close the visible room return with actual architecture, not a backdrop."""
import bpy,math
from scene_environment import cube,cylinder,material,area
from detail_refinement import bolt,wire

def build():
    m=bpy.data.materials;steel=m['Brushed satin stainless steel'];dark=m['Dark graphite coated steel'];wall=m['Large ceramic wall panels']
    x=-5.;lo,hi=-3.2,5.2;yl,yr=1.18,2.22;floor=-.005;top=3.165;door_top=2.18
    for a,b in ((lo,yl),(yr,hi)):
        cube('Concourse return structural wall',(x,(a+b)/2,(floor+top)/2),(.16,b-a,top-floor),wall,.003)
        cube('Return wall stainless skirting',(-4.914,(a+b)/2,.075),(.015,b-a,.16),steel,.002)
    cube('Return wall over utility doorway',(x,(yl+yr)/2,(door_top+top)/2),(.16,yr-yl,top-door_top),wall,.003)
    door=material('Utility door satin powder coating',(.26,.285,.29),.43)
    for y in (yl+.03,yr-.03):cube('Recessed utility door frame jamb',(-4.98,y,1.0875),(.12,.060,2.185),steel,.003)
    cube('Utility door frame head',(-4.98,1.70,2.1475),(.12,1.04,.065),steel,.003)
    cube('Closed utility door leaf',(-4.986,1.70,1.055),(.044,.916,2.11),door,.003)
    for y in (1.24,2.16):cube('Utility door perimeter EPDM seal',(-4.964,y,1.055),(.006,.006,2.11),dark,.001)
    cube('Utility door upper EPDM seal',(-4.964,1.70,2.112),(.006,.923,.006),dark,.001)
    for z in (.35,1.06,1.77):
        cylinder('Utility door hinge barrel',(-4.945,1.24,z),.009,.14,steel)
        cube('Utility door hinge mounting leaf',(-4.956,1.26,z),(.014,.060,.05),steel,.001)
        for dz in (-.015,.015):bolt('Utility door hinge fixing',(-4.948,1.28,z+dz),'X',steel,dark,.0026)
    cylinder('Utility door handle escutcheon',(-4.960,2.05,1.04),.029,.007,steel,'X')
    wire('Utility door return-to-door lever',[(-4.954,2.05,1.04),(-4.921,2.05,1.04),(-4.918,1.95,1.04),(-4.932,1.935,1.04)],.008,steel)
    cylinder('Utility door lock cylinder',(-4.960,2.05,.96),.012,.008,steel,'X')
    cube('Utility door kick plate',(-4.963,1.70,.15),(.002,.87,.22),steel,.001)
    cube('Utility room identification plate',(-4.962,1.70,1.76),(.002,.37,.11),dark,.002)
    ink=material('Utility room sign white ink',(.82,.86,.85),.52)
    bpy.ops.object.text_add(location=(-4.9608,1.70,1.76),rotation=(math.pi/2,0,math.pi/2))
    text=bpy.context.object;text.name='Utility room extruded staff lettering';text.data.body='STAFF ONLY';text.data.align_x='CENTER';text.data.align_y='CENTER';text.data.size=.034;text.data.extrude=.00015;text.data.materials.append(ink)
    # Wall panel reveals have depth and are anchored in the structural return.
    for y in (-2.7,-1.8,-.9,0.,.9,2.7,3.6,4.5):
        cube('Return wall vertical panel reveal',(-4.918,y,1.58),(.004,.0025,3.17),dark,.0005)
    for z in (.79,1.58,2.37):
        for a,b in ((lo,yl),(yr,hi)):
            cube('Return wall horizontal reveal',(-4.918,(a+b)/2,z),(.004,b-a,.0025),dark,.0005)
    # An actual wall light adds a restrained illumination gradient behind the rig.
    cube('Utility door wall light housing',(-4.90,1.70,2.43),(.04,.72,.08),dark,.004)
    luminous=m['Ceiling diffusers'];cube('Utility door wall light diffuser',(-4.877,1.70,2.425),(.008,.68,.037),luminous,.002)
    area('Utility doorway wall wash',(-4.78,1.70,2.43),(-4.94,1.70,1.10),36,.68,(.94,.97,1))
    # Recessed air grille with individual vanes and fixing screws.
    cube('Return wall grille recessed plenum',(-4.903,3.55,2.55),(.034,.82,.25),dark,.002)
    for z in (2.43,2.67):cube('Wall air grille horizontal frame',(-4.877,3.55,z),(.022,.85,.018),steel,.002)
    for y in (3.135,3.965):cube('Wall air grille vertical frame',(-4.877,y,2.55),(.022,.018,.25),steel,.002)
    for k in range(8):
        ob=cube('Wall grille angled metal vane',(-4.881,3.55,2.45+k*.028),(.019,.80,.011),steel,.0008);ob.rotation_euler.y=math.radians(20)
    for y in (3.135,3.965):
        for z in (2.43,2.67):bolt('Wall grille retained fixing',(-4.8655,y,z),'X',steel,dark,.0025)
    return {'return_wall_x_m':x,'door_opening_width_m':yr-yl,'door_recess_depth_m':.044,'background_is_modeled_architecture':True}
