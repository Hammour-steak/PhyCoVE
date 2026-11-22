"""Metro checkpoint architecture and manufactured props; common to all edits."""
import bpy,math
from pathlib import Path
from mathutils import Vector

def enrich(p):
    from scene_environment import cube,cylinder,material,micro,placard,area
    mats=bpy.data.materials
    steel=mats['Brushed satin stainless steel'];dark=mats['Dark graphite coated steel']
    cream=mats['Warm grey fine powder-coat']
    yellow=material('Safety yellow thermoplastic markings',(.73,.48,.055),.66);micro(yellow,650,.00006,.13)
    grout=material('Warm grey epoxy grout',(.18,.20,.19),.82)
    blue=material('Injection moulded blue polypropylene',(.045,.17,.26),.52);micro(blue,650,.000028,.12)
    warm=material('Subway porcelain panel warm variation',(.43,.46,.45),.38);micro(warm,650,.000025,.16)
    # A full concourse continues behind the ticket gates; wall fixtures move with it.
    for ob in bpy.context.scene.objects:
        if ob.name.startswith(('Station back wall','Station sign backing','Station bilingual sign')):
            ob.location.y+=2.10
            if not ob.name.startswith('Station back wall'):ob.location.y-=.010
        if ob.name.startswith(('Square station column','Column steel skirting')):ob.location.y+=.85
        if ob.name.startswith(('Distant fare gate','Fare gate top')):
            ob.location.y+=1.30
            if abs(ob.location.x-1.5)<.02:ob.location.x=1.3
            elif abs(ob.location.x-2.9)<.02:ob.location.x=3.1
    # Physical panel seams: attached to the wall, with small edge radii.
    for ob in list(bpy.context.scene.objects):
        if ob.name.startswith(('Wall panel joint','Wall horizontal joint')):bpy.data.objects.remove(ob,do_unlink=True)
    for col in range(-6,7):
        for row in range(4):
            mat=warm if (col+2*row)%5==0 else mats['Large ceramic wall panels']
            cube('Individual concourse wall panel',(col+.5,5.120, .395+row*.79),(.996,.010,.786),mat,.001)
    cube('Continuous wall stainless skirting',(0,5.107,.085),(14,.016,.18),steel,.002)
    # Parallel passenger inspection lane, separated from the baggage lane.
    for ob in bpy.context.scene.objects:
        if ob.name.startswith(('Queue post','Belt cassette','Retractable barrier belt')):ob.location.y=.80
    gate_x=-.70;gate_y=1.63
    for y in (gate_y-.48,gate_y+.48):
        cube('Walk-through detector floor foot',(gate_x,y,.0125),(.43,.25,.035),dark,.005)
        cube('Walk-through detector upright',(gate_x,y,1.0675),(.20,.145,2.075),cream,.009)
        cube('Detector graphite inner face',(gate_x+.002,y,1.10),(.207,.027,1.84),dark,.002)
        cylinder('Detector fixing bolt',(gate_x+.1015,y,.15),.005,.005,steel,'X')
        # Separate red/green indicator lenses fixed to the front of the post.
        for j in range(8):
            c=(.08,.40,.20) if j<6 else (.35,.05,.025)
            lamp=material('Detector segmented LED',c,.3);bs=lamp.node_tree.nodes.get('Principled BSDF');bs.inputs['Emission Color'].default_value=(*c,1);bs.inputs['Emission Strength'].default_value=.45
            cube('Detector vertical status lens',(gate_x+.103,y,1.40+j*.055),(.006,.018,.035),lamp,.001)
    cube('Walk-through detector top header',(gate_x,gate_y,2.145),(.23,1.11,.155),dark,.007)
    placard('Detector bilingual face',(gate_x+.116,gate_y,2.15),(1.03,.125),'gate_header.png',.1,front='X')
    # A wheeled return cart and nested moulded trays with real floor support.
    cx=-1.94;cy=-.91
    for x in (cx-.255,cx+.255):
        for y in (cy-.175,cy+.175):
            cylinder('Tray cart caster wheel',(x,y,.030),.035,.026,dark,'Y')
            cube('Tray cart caster fork',(x,y,.073),(.025,.047,.065),steel,.003)
            cylinder('Tray cart upright',(x,y,.359),.012,.54,steel)
    cube('Tray cart lower shelf',(cx,cy,.16),(.60,.43,.018),steel,.004)
    cube('Tray cart upper shelf',(cx,cy,.637),(.64,.46,.016),steel,.004)
    # Tapered shells nest without coincident vertical walls.
    for i in range(5):
        z=.645+i*.012
        vertices=[]
        for ax,ay,zz in [(.27,.17,0),(.30,.20,.060),(.296,.196,.060),(.266,.166,.006)]:
            vertices += [(-ax,-ay,zz),(ax,-ay,zz),(ax,ay,zz),(-ax,ay,zz)]
        faces=[(3,2,1,0),(12,13,14,15)]
        for j in range(4):
            k=(j+1)%4;faces.extend([(j,k,4+k,4+j),(4+j,4+k,8+k,8+j),(8+j,8+k,12+k,12+j)])
        mesh=bpy.data.meshes.new('Moulded tray tapered shell');mesh.from_pydata(vertices,[],faces);mesh.materials.append(blue);mesh.update()
        tray=bpy.data.objects.new('Nested tapered polypropylene tray',mesh);bpy.context.collection.objects.link(tray);tray.location=(cx,cy,z)
        bevel=tray.modifiers.new('Moulded polymer edge radius','BEVEL');bevel.width=.0012;bevel.segments=3
        tray.modifiers.new('Tray corner normals','WEIGHTED_NORMAL')
        for sx in (-1,1):
            for sy in (-1,1):cube('Tray nesting support lug',(cx+sx*.272,cy+sy*.172,z+.009),(.010,.010,.006),blue,.001)
    for sx in (-1,1):cube('Tray information mounting bracket',(cx+sx*.16,cy-.230,.618),(.022,.022,.050),steel,.002)
    cube('Tray information holder',(cx,cy-.238,.526),(.46,.012,.18),dark,.003)
    placard('Tray return instructions',(cx,cy-.245,.526),(.447,.166),'trays.png')
    # Floor route: tile bases touch the same measured floor used by all props.
    for i in range(24):
        x=-3.45+i*.30;y=1.64
        cube('Tactile paving tile',(x,y,-.0085),(.296,.296,.008),yellow,.001)
        for j in range(4):cube('Tactile directional raised bar',(x,y-.105+j*.07,-.0025),(.245,.023,.004),yellow,.002)
    # Low profile station inspection-zone paint, excluding the belt/exit area.
    queue_start, queue_end = -1.65, p['pickup_end_x_m']+.06
    for x in (queue_start,queue_end):cube('Inspection zone end marking',(x,-.63,-.0045),(.035,1.50,.001),yellow,.0002)
    cube('Inspection queue floor line',((queue_start+queue_end)/2,-1.38,-.0045),(queue_end-queue_start,.035,.001),yellow,.0002)
    # Correct operator working side: monitor, keyboard and cable face an open aisle.
    for ob in bpy.context.scene.objects:
        if ob.name.startswith(('Operator monitor base','Operator screen post','Monitor bezel','Inspection monitor')):ob.location.y-=1.30
    cube('Keyboard support tray',(-1.13,-.78,1.09),(.45,.25,.024),steel,.003)
    cube('Operator keyboard housing',(-1.13,-.80,1.108),(.35,.16,.012),dark,.003)
    keymat=material('Dark keyboard keycaps',(.032,.040,.046),.65)
    for row in range(5):
        for col in range(12):cube('Keyboard raised key',(-1.282+col*.0276,-.852+row*.025,1.116),(.023,.019,.005),keymat,.0008)
    # Generic wayfinding plate with concealed standoffs anchored in the wall.
    cube('Train direction sign backing',(1.61,5.105,2.66),(2.65,.020,.37),dark,.004)
    placard('Metro train direction sign',(1.61,5.0945,2.66),(2.63,.35),'wayfinding.png',.12)
    # Safety stripes are actual attached graphics, not time-dependent overlays.
    placard('Shielding portal caution stripe',(.0462,0,1.075),(.592,.037),'hazard.png',front='X')
    # Small rubber bumpers protect the outfeed corners; bolts are seated in the rail.
    for y in (-.323,.323):
        cube('Outfeed rubber corner guard',(.050,y,.70),(.10,.012,.083),dark,.006)
        for x in (.025,.075):cylinder('Guard attachment screw',(x,y+math.copysign(.007,y),.715),.003,.003,steel,'Y')
    # Far fare gates get glass wings and readers, retaining their grounded chassis.
    glass=material('Frosted fare gate glass',(.20,.47,.45),.24)
    bs=glass.node_tree.nodes.get('Principled BSDF');bs.inputs['Transmission Weight'].default_value=.25
    for x in (1.3,2.2,3.1):
        cube('Fare gate reader housing',(x,3.35,1.057),(.13,.15,.024),dark,.007)
        cube('Fare gate illuminated reader',(x,3.34,1.071),(.09,.09,.004),blue,.002)
    for x in (1.3,2.2):
        for hand,base in ((1,x),(-1,x+.9)):
            cube('Fare gate transparent wing',(base+hand*.30,3.45,.63),(.28,.018,.64),glass,.006)
            cube('Glass wing metal hinge',(base+hand*.164,3.45,.63),(.018,.036,.56),steel,.002)
    for ob in bpy.context.scene.objects:
        if ob.name.startswith(('Distant fare gate','Fare gate top','Fare gate reader','Fare gate illuminated','Fare gate transparent','Glass wing metal hinge')):ob.location.x-=1.50
    # Recessed ceiling slats form a real attached fixture grid.
    slat=material('Anodized ceiling fins',(.34,.38,.39),.36,.65)
    for j in range(31):cube('Suspended ceiling fin',(-3.8+j*.24,1.00,3.14),(.026,7.50,.050),slat,.001)
    # Mild handling wear on service panel edges stays in material coordinates.
    cube('Gate hall light fixture',(1.5,3.8,3.13),(3.4,.13,.07),dark,.003)
    cube('Gate hall light diffuser',(1.5,3.8,3.091),(3.35,.09,.008),mats['Ceiling diffusers'],.001)
    area('Gate concourse overhead',(1.4,3.7,2.85),(1.4,3.7,0),240,3.1,(.90,.96,1))
    area('Concourse side illumination',(2.1,1.5,2.8),(0,0,.7),210,2.6,(.88,.94,1))
    bpy.context.scene.world.node_tree.nodes.get('Background').inputs['Strength'].default_value=.12
    camera=bpy.context.scene.camera;camera.location=(2.98,-3.36,1.61);target=Vector((.18,.48,1.11))
    camera.rotation_euler=(target-camera.location).to_track_quat('-Z','Y').to_euler();camera.data.lens=35
    camera.data.dof.focus_distance=(Vector((.12,0,.91))-camera.location).length;camera.data.dof.aperture_fstop=11
    bpy.context.view_layer.update()
    return {'scene_revision':'metro_checkpoint','camera_target':list(target),'references':'Shenzhen Metro supplier project photos; original generic station layout'}
