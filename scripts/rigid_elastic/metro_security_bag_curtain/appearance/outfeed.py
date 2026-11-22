"""Compact powered nose, passive falling slide and lower pickup platform."""
import bpy,math
from mathutils import Vector
from scene_environment import cube,cylinder,material,micro
from detail_refinement import mesh_object,bolt

def span(name,a,b,width,depth,mat):
    a=Vector(a);b=Vector(b);o=cube(name,tuple((a+b)/2),((b-a).length,width,depth),mat,.002)
    o.rotation_euler.y=math.atan2(a.z-b.z,b.x-a.x);return o

def plate(name,a,b,width,gauge,mat):
    # The upper surface is the exact solver plane, with thickness below it.
    x0,z0=a;x1,z1=b;normal=Vector((z0-z1,0,x1-x0)).normalized()
    top=[Vector(v) for v in ((x0,-width/2,z0),(x1,-width/2,z1),(x1,width/2,z1),(x0,width/2,z0))]
    vertices=top+[v-normal*gauge for v in top]
    faces=[(0,1,2,3),(7,6,5,4),(0,4,5,1),(1,5,6,2),(2,6,7,3),(3,7,4,0)]
    ob=mesh_object(name,[tuple(v) for v in vertices],faces,mat)
    bevel=ob.modifiers.new('Pressed steel edge arris','BEVEL');bevel.width=.0003;bevel.segments=3;ob.modifiers.new('Sheet surface normals','WEIGHTED_NORMAL')
    return ob

def build(p):
    prefixes=('Outfeed steel edge extrusion','Dark edge seal','Conveyor steel roller','Roller axle','Roller bearing block','Conveyor support leg','Levelling foot','Levelling threaded stem','Support crossbar','Rail end and splice fixing','Welded conveyor support gusset','Support clamp bolt','Levelling stem real helical thread','Gearmotor mounting bridge','Motor bridge rail fixing','Gearmotor outside-return-belt hanger','Gearmotor lower cradle','Conveyor gearmotor body','Motor cooling fin','Drive reduction gearbox','Gearbox cover bolt')
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith(prefixes):bpy.data.objects.remove(ob,do_unlink=True)
    mats=bpy.data.materials;steel=mats['Brushed satin stainless steel'];dark=mats['Dark graphite coated steel']
    slide=material('Satin 304 stainless sliding and collection sheet',(.48,.52,.54),.32,.92);micro(slide,950,.000022,.15,(1,14,1))
    bs=slide.node_tree.nodes.get('Principled BSDF');anisotropic=bs.inputs.get('Anisotropic IOR Level') or bs.inputs.get('Anisotropic')
    assert anisotropic is not None,'Renderer must provide a principled anisotropy input';anisotropic.default_value=.5
    rubber=material('Collection stop dense EPDM rubber',(.012,.016,.018),.79);micro(rubber,1100,.000035,.17)
    end=p['belt_end_x_m'];nose=end-p['belt_nose_radius_m'];rend=p['ramp_end_x_m'];last=p['pickup_end_x_m'];top=p['belt_height_m'];bottom=p['pickup_height_m']
    # Cross section has a feathered fixed transfer lip, keeping the belt's
    # curved carcass below the actual support surface without a visual hump.
    xs=[nose,nose+.004,nose+.010,end];depths=[0.,.00020,.0012,.0015];v=[];f=[]
    for x,d in zip(xs,depths):v.extend([(x,-.275,top),(x,.275,top),(x,-.275,top-d),(x,.275,top-d)])
    for i in range(len(xs)-1):
        a=4*i;b=a+4;f.extend([(a,b,b+1,a+1),(a+2,a+3,b+3,b+2),(a,a+2,b+2,b),(a+1,b+1,b+3,a+3)])
    f.extend([(12,14,15,13)]);mesh_object('Fixed feathered transition plate',v,f,slide)
    plate('Downhill stainless slide',(end,top),(rend,bottom),.55,.002,slide)
    plate('Horizontal baggage pickup deck',(rend,bottom),(last,bottom),.55,.002,slide)
    for y in (-.303,.303):
        span('Compact belt supporting extrusion',(-1.61,y,top-.045),(end,y,top-.045),.035,.075,steel)
        span('Sloping outfeed structural rail',(end,y,top-.045),(rend,y,bottom-.045),.035,.075,steel)
        span('Pickup platform supporting extrusion',(rend,y,bottom-.045),(last+.018,y,bottom-.045),.035,.075,steel)
        span('Folded belt edge wiper',(-1.61,math.copysign(.282,y),top-.012),(nose,math.copysign(.282,y),top-.012),.009,.024,dark)
        # A continuous folded side cheek supports the sheet and guards its edge.
        yy=math.copysign(.282,y)
        for name,a,b in (('Slide folded side cheek',(end,yy,top+.008),(rend,yy,bottom+.008)),('Pickup folded side cheek',(rend,yy,bottom+.008),(last+.018,yy,bottom+.008))):span(name,a,b,.014,.075,slide)
        for x in (-1.34,-.55,end-.12):bolt('Belt frame seated socket fixing',(x,y-.019,top-.035),'Y',steel,dark,.0033)
        for x in (end+.10,rend-.10):
            z=top+(bottom-top)*(x-end)/(rend-end);bolt('Slide rail socket fixing',(x,y-.019,z-.032),'Y',steel,dark,.0033)
        for x in (rend+.13,last-.15):bolt('Pickup rail socket fixing',(x,y-.019,bottom-.032),'Y',steel,dark,.0033)
        # Cover ends terminate on the transverse end structure.
        cube('Pickup corner end cap',(last+.010,y,bottom-.043),(.025,.043,.080),dark,.005)
    # The transition's roller is below the feathered plate, not an unmodelled
    # moving load-bearing surface. Its axle is attached to both side rails.
    cylinder('Transfer lip support roller',(end-.012,0,top-.030),.012,.542,steel,'Y')
    cylinder('Transfer roller axle',(end-.012,0,top-.030),.005,.632,steel,'Y')
    for yy in (-.303,.303):cube('Transfer roller axle mounting',(end-.012,yy,top-.034),(.035,.036,.035),dark,.002)
    # Support the extended belt overhang independently of the receiving deck.
    for x in (-1.27,-.25,end-.10,rend+.11,last-.08):
        level=top if x<end else bottom
        for y in (-.303,.303):
            height=level-.080;cube('Conveyor support leg',(x,y,.035+height/2),(.040,.040,height),steel,.003)
            cylinder('Levelling foot',(x,y,.004),.036,.018,dark)
            cylinder('Levelling threaded stem',(x,y,.024),.0085,.040,steel)
            for k in range(8):cylinder('Levelling stem thread crest',(x,y,.016+k*.002),.0095,.0007,steel)
            # The triangular gusset joins leg and longitudinal rail directly.
            yy=y+math.copysign(.019,y)
            ob=mesh_object('Pickup and scanner welded leg gusset',[(x-.055,yy,level-.012),(x+.055,yy,level-.012),(x,yy,level-.115)],[(0,1,2)],steel)
            solid=ob.modifiers.new('2.5 mm gusset plate','SOLIDIFY');solid.thickness=.0025
            bolt('Leg gusset socket fixing',(x,yy-.002,level-.082),'Y',steel,dark,.0035)
        cube('Support crossbar',(x,0,.22),(.04,.646,.035),steel,.002)
    # Rubber front face is the same vertical stop used by the solver, x=last.
    cube('Pickup rubber end stop',(last+.003,0,bottom+.045),(.006,.562,.090),rubber,.001)
    cube('Pickup end stop folded backing',(last+.011,0,bottom+.042),(.010,.632,.096),slide,.002)
    for yy in (-.30,.30):bolt('Pickup stop countersunk fixing',(last+.017,yy,bottom+.044),'X',steel,dark,.0032)
    cube('Pickup transverse mounting header',(last+.006,0,bottom-.043),(.030,.632,.075),steel,.002)
    # Bare metal is visible at the two small sheet joints; no fake texture seam.
    for x,z in ((end,top),(rend,bottom)):
        for y in (-.280,.280):cube('Slide joint folded mounting tab',(x,y,z-.018),(.036,.025,.040),slide,.001)
    bpy.context.view_layer.update()
    return {'powered_upper_face_end_x_m':nose,'fixed_nose_plate_m':[nose,end],'ramp_x_m':[end,rend],'ramp_z_m':[top,bottom],'pickup_x_m':[rend,last],'pickup_height_m':bottom,'end_stop_x_m':last,'slope_degrees':math.degrees(math.atan2(top-bottom,rend-end)),'initial_actors_moved':False,'mechanism':'Extended driven belt to fixed feathered lip, passive steel slide and level collection platform'}
