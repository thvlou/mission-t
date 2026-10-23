"""Second-generation surface detailing and articulated vehicle parts.

Executed by build_porsche_fleet.py in Blender. All distances in metres.
"""
old_body=make_body
old_details=details
old_wheels=wheels
old_export=export_car
old_build=build_one
BRAKE=material('BrakeLamp',(.55,.003,.008),.25,.18,.25)
CENTER=material('CenterBrakeLamp',(.38,.002,.004),.15,.19,0)
REVERSE=material('ReverseLamp',(.65,.72,.8),.1,.21,0)
LEATHER=material('Interior leather',(.024,.026,.03),0,.48)
LENS=material('Optical smoked lens',(.022,.029,.038),.55,.12)
gp=next(n for n in GLASS.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
gp.inputs['Metallic'].default_value=.05
gp.inputs['Roughness'].default_value=.11
gp.inputs['Alpha'].default_value=.58
GLASS.diffuse_color=(.018,.032,.044,.58)
GLASS.surface_render_method='DITHERED'

def top_z(s,ctrl,x,y):
    w,z=smooth_interp(ctrl,x);t=min(.9999,abs(y/w));c=math.sqrt(1-t*t)
    front=exp(-((x-s['wb']/2)/.66)**2);rear=exp(-((x+s['wb']/2)/.60)**2)
    drop=.075 if s['kind']=='suv' else .105
    shoulder=.10*exp(-((x-(s['length']/2-.40))/.42)**2)*exp(-((t-.73)/.21)**2)
    return z-.10*(1-c)-drop*front*(1-t*t)+(.13*front+.095*rear)*t**3+shoulder

def cut(body,cutter):
    bpy.context.view_layer.objects.active=body
    mod=body.modifiers.new('Recessed aperture','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
    bpy.ops.object.modifier_apply(modifier=mod.name)
    bpy.data.objects.remove(cutter,do_unlink=True)

def make_body(s,paint):
    ctrl=old_body(s,paint)
    s['_body']=next(o for o in CAR.objects if 'sculpted body' in o.name)
    return ctrl

def roof_point(s,x,t,offset=0):
    z,w=smooth_interp(s['roof'],x);base=s['base'];a=abs(t)
    # A gently crowned roof meets a distinct shoulder, then inclined side glass.
    if a<=.67:
        zz=z-(z-base)*.075*(a/.67)**2
    else:
        u=(a-.67)/.33;zz=base+(z-base)*.925*(1-u)
    return (x,w*t,zz+offset)

def cabin(s,paint):
    ctrl=s['roof'];N=112;K=60;v=[];f=[];mi=[]
    for i in range(N+1):
        x=ctrl[0][0]+(ctrl[-1][0]-ctrl[0][0])*i/N
        for j in range(K+1):v.append(roof_point(s,x,-1+2*j/K))
    for i in range(N):
        x=ctrl[0][0]+(ctrl[-1][0]-ctrl[0][0])*(i+.5)/N
        for j in range(K):
            t=abs(-1+2*(j+.5)/K);a=i*(K+1)+j;f.append((a,a+K+1,a+K+2,a+1))
            front=s['front'];rear=s['rear'];edge=.07
            side=t>.715 and t<.965 and rear+.08<x<front+.12
            windshield=front+.10<x<ctrl[-1][0]-.065 and t<.68
            back=ctrl[0][0]+.08<x<rear-.07 and t<.66
            pillar=abs(x-(-.38 if s['kind'] in ['suv','ev'] else -.55))<.023
            mi.append(1 if (side and not pillar) or windshield or back else 0)
    o=mesh('Cabin glazing and structural pillars',v,f,[paint,GLASS])
    for p,m in zip(o.data.polygons,mi):p.material_index=m
    for sign in [-1,1]:
        # Continuous seals following the window shoulder and beltline.
        for t in [.715,.965]:
            pts=[roof_point(s,s['rear']+.08+(s['front']+.04-s['rear'])*i/70,sign*t,.003) for i in range(71)]
            line('Side glass weather seal',pts,TRIM,.004)
        line('A pillar edge',[roof_point(s,s['front']+.10,sign*t,.003) for t in [.1+i*.018 for i in range(49)]],TRIM,.003)
    # Wipers sit at the foot of the windscreen, following its actual surface.
    for sign in [-1,1]:
        x=ctrl[-1][0]-.10
        line('Windscreen wiper',[roof_point(s,x-.05*i/12,sign*(.08+.46*i/12),.009) for i in range(13)],TRIM,.008)
    return o

def lamp_surface(s,ctrl,cx,cy,rx,ry,mat,name,scale=1,offset=.001):
    v=[(cx,cy,top_z(s,ctrl,cx,cy)+offset)];f=[];K=64;R=8
    for j in range(1,R+1):
        r=j/R*scale
        for k in range(K):
            a=2*pi*k/K;x=cx+rx*r*cos(a);y=cy+ry*r*sin(a)
            v.append((x,y,top_z(s,ctrl,x,y)+offset))
    for k in range(K):f.append((0,1+k,1+(k+1)%K))
    for j in range(R-1):
        for k in range(K):
            a=1+j*K+k;b=1+j*K+(k+1)%K;f.append((a,b,b+K,a+K))
    return mesh(name,v,f,mat)

def front_details(s,paint,ctrl):
    front=s['length']/2;W=s['width']/2;kind=s['kind'];body=s['_body']
    for sign in [-1,1]:
        sporty=kind in ['coupe','track','mid'];cx=front-(.28 if sporty else .28);cy=sign*W*.66
        rx=.205 if sporty else .065;ry=.145 if sporty else .17
        # A real 45 mm pocket; optical surfaces follow the body to within 1 mm.
        outline=[]
        for k in range(64):
            a=2*pi*k/64;x=cx+rx*cos(a);y=cy+ry*sin(a);z=top_z(s,ctrl,x,y)
            outline.append((x,y,z))
        v=[(x,y,z+dz) for dz in [-.045,.06] for x,y,z in outline]
        f=[tuple(reversed(range(64))),tuple(range(64,128))]+[(k,(k+1)%64,(k+1)%64+64,k+64) for k in range(64)]
        # Surface-matched optical insert avoids destructive n-gon shading at the rim.
        lamp_surface(s,ctrl,cx,cy,rx,ry,TRIM,'Flush headlamp gasket',offset=.001)
        lamp_surface(s,ctrl,cx,cy,rx,ry,LENS,'Conformal optical cover',scale=.94,offset=.002)
        if sporty:
            pts=[]
            for k in range(65):
                a=2*pi*k/64;x=cx+rx*.80*cos(a);y=cy+ry*.80*sin(a);pts.append((x,y,top_z(s,ctrl,x,y)+.004))
            line('Inset light guide',pts,CHROME,.003,True)
            for a in [-1,1]:
                for b in [-1,1]:
                    x=cx+a*.061;y=cy+b*.054
                    lamp_surface(s,ctrl,x,y,.026,.023,LED,'Matrix LED module',offset=.004)
                    line('Optical module divider',[(x-.023,y,top_z(s,ctrl,x-.023,y)+.003),(x+.023,y,top_z(s,ctrl,x+.023,y)+.003)],DARK,.002)
        else:
            for a in [-1,1]:
                for b in [-1,1]:
                    x=cx+a*.026
                    pts=[(x,y,top_z(s,ctrl,x,y)+.002) for y in [cy+b*.08-.045,cy+b*.08+.045]]
                    line('Four point recessed DRL',pts,LED,.005)
        # Rounded openings cut through the bumper, with a dark back wall and inset vanes.
        z=.45 if kind=='suv' else .365
        cy=sign*W*.55
        cutter=box('Bumper aperture cutter',(front-.035,cy,z),(.34,.39,.18),TRIM,.045);cut(body,cutter)
        box('Intake shadow cavity',(front-.18,cy,z),(.018,.38,.17),TRIM,.035)
        for dz in [-.05,0,.05]:box('Recessed intake vane',(front-.065,cy,z+dz),(.10,.32,.012),DARK,.004)
        if kind=='suv':
            cutter=box('Low projector pocket',(front-.02,sign*W*.58,.70),(.25,.27,.16),TRIM,.035);cut(body,cutter)
            box('Low projector glass',(front-.052,sign*W*.58,.70),(.012,.25,.135),LENS,.025)
            box('Low beam module',(front-.043,sign*W*.58,.71),(.008,.105,.025),LED,.009)
        if kind=='ev':
            line('Taycan air curtain',[(front-.006,sign*W*.77,.66),(front+.002,sign*W*.78,.54),(front-.01,sign*W*.76,.43)],TRIM,.016)
    z=.36 if kind=='suv' else .285
    cut(body,box('Central air aperture',(front-.045,0,z),(.32,.60,.135),TRIM,.035))
    box('Central intake depth',(front-.19,0,z),(.02,.60,.12),TRIM,.025)
    for y in [-.24,-.16,-.08,0,.08,.16,.24]:box('Central grille rib',(front-.055,y,z),(.09,.009,.10),DARK,.003)
    line('Contoured front splitter',[(front-.06-.11*(abs(y)/W)**2,y,.19 if kind!='suv' else .25) for y in [-W*.84+j*W*1.68/60 for j in range(61)]],TRIM,.018)
    # Delineate the bonnet with surface-following seams rather than an unbroken toy shell.
    for sign in [-1,1]:
        pts=[]
        for i in range(65):
            t=i/64;x=.68+(front-.23-.68)*t;y=sign*(.53-.17*t)
            pts.append((x,y,top_z(s,ctrl,x,y)+.002))
        line('Bonnet panel gap',pts,TRIM,.0022)
    x=front-.42;lamp_surface(s,ctrl,x,0,.027,.020,GOLD,'Bonnet crest',offset=.002)
    if kind=='track':
        for sign in [-1,1]:
            for i in range(6):
                x=.85+i*.058;y=sign*.28
                lamp_surface(s,ctrl,x,y,.023,.13,TRIM,'Bonnet extractor slot',offset=.001)
            for i in range(5):
                x=s['wb']/2-.16+i*.072;y=sign*W*.78
                lamp_surface(s,ctrl,x,y,.022,.075,TRIM,'Fender pressure outlet',offset=.002)

def join_parts(parts,name,origin=None):
    bpy.ops.object.select_all(action='DESELECT')
    converted=[]
    for o in parts:
        o.select_set(True);bpy.context.view_layer.objects.active=o
        if o.type in ['CURVE','FONT']:bpy.ops.object.convert(target='MESH')
        converted.append(bpy.context.object);o.select_set(False)
    for o in converted:o.select_set(True)
    bpy.context.view_layer.objects.active=converted[0];bpy.ops.object.join();o=bpy.context.object;o.name=name
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    if origin is not None:
        bpy.context.scene.cursor.location=origin;bpy.ops.object.origin_set(type='ORIGIN_CURSOR')
    return o

def wheels(s):
    old_wheels(s)
    for o in list(CAR.objects):
        if o.name.startswith('Fixed brake caliper '):o.name='caliper_'+o.name.split('Fixed brake caliper ')[1]
    # A shallow drilled pattern gives the rotor readable construction at close range.
    for wheel in [o for o in CAR.objects if o.name.startswith('wheel_')]:
        center=wheel.location.copy();sign=1 if center.y>0 else -1;r=s['r'];depth=.285 if s['kind']=='track' else .235
        parts=[wheel]
        for k in range(32):
            a=2*pi*k/32
            for rr in [r-.15,r-.19]:parts.append(cyl('Rotor perforation',(center.x+rr*cos(a),center.y+sign*(depth/2-.022),r+rr*sin(a)),.006,.0015,TRIM,8))
        # Circumferential tread channels, just below the tread crown.
        for dy in [-.065,0,.065]:parts.append(torus('Tread channel',(center.x,center.y+dy,r),r-.009,.003,TRIM))
        join_parts(parts,wheel.name,center)

def interior(s):
    base=s['base'];before=set(CAR.objects)
    # Upper cabin details are visible through glazing and in the inspection view.
    box('Dashboard',(.40,0,base+.06),(.34,1.12,.12),LEATHER,.06)
    for sign in [-1,1]:
        box('Seat shoulder',(-.37,sign*.32,base+.12),(.16,.36,.34),LEATHER,.075)
        box('Seat headrest',(-.40,sign*.32,base+.31),(.14,.20,.13),LEATHER,.045)
    box('Centre console',(-.05,0,base-.005),(.57,.16,.09),TRIM,.03)
    box('Instrument binnacle',(.33,.32,base+.15),(.14,.32,.07),TRIM,.025)
    center=Vector((.20,.32,base+.20));parts=[]
    # Wheel lies in the YZ plane, local X is the steering-column rotation axis.
    pts=[tuple(center+Vector((0,.145*cos(2*pi*k/64),.145*sin(2*pi*k/64)))) for k in range(65)]
    parts.append(line('Leather steering rim',pts,LEATHER,.016,True))
    for a in [0,pi,pi*1.5]:parts.append(line('Steering spoke',[tuple(center),tuple(center+Vector((0,.13*cos(a),.13*sin(a))))],DARK,.013))
    parts.append(box('Steering airbag',center,(.035,.10,.085),LEATHER,.025))
    steering=join_parts(parts,'steering_wheel',center);steering['steering_axis']='x';steering['steering_ratio']=14

def details(s,paint,ctrl):
    old_details(s,paint,ctrl)
    # Dedicated materials, kept separate from body paint and turn signals.
    for o in CAR.objects:
        if o.type in ['MESH','CURVE']:
            for slot in o.material_slots:
                if slot.material==TAIL:slot.material=BRAKE
    rear=-s['length']/2;z=.85 if s['kind']=='suv' else .72
    for sign in [-1,1]:
        box('Reverse light optic',(rear-.028,sign*.49,z-.06),(.009,.12,.015),REVERSE,.006)
        for i in range(8):
            box('Tail lens optical rib',(rear-.037,sign*(.48+i*.031),z),(.006,.003,.026),BRAKE,.001)
    # On the deck lip; the old high position left the strip floating above the body.
    line('Center high mount stop lamp',[(rear-.022,-.18,z+.045),(rear-.022,.18,z+.045)],CENTER,.006)
    interior(s)

def export_car(scene,col,s):
    bpy.ops.object.select_all(action='DESELECT')
    for o in col.objects:
        if o.type=='MESH':o.select_set(True)
    bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
    body=s.get('_body')
    if body:
        bpy.context.view_layer.objects.active=body
        bevel=body.modifiers.new('Manufactured bumper edges','BEVEL');bevel.width=.009;bevel.segments=3;bevel.limit_method='ANGLE';bevel.angle_limit=.60
        bpy.ops.object.modifier_apply(modifier=bevel.name)
        for p in body.data.polygons:
            if len(p.vertices)>4 and abs(p.normal.x)>.85:p.use_smooth=False
    # Keep steering wheel and calipers independent; original export joins static parts.
    protected=[o for o in col.objects if o.name.startswith(('steering_wheel','caliper_'))]
    for o in protected:
        if o.type!='MESH':
            bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o.select_set(False)
        o['rig_role']='steering_wheel' if o.name.startswith('steering_wheel') else 'caliper'
        o.name='wheel_PROTECTED_'+o.name
    triangles=old_export(scene,col,s)
    for o in protected:o.name=o.name.replace('wheel_PROTECTED_','')
    if body:
        # Bow the complete fascia (including optics and intake cavities) as one assembly.
        # A broad continuous bumper radius replaces the earlier flat vertical end plate.
        front=s['length']/2;W=s['width']/2
        for o in col.objects:
            if o.type!='MESH':continue
            inv=o.matrix_world.inverted()
            for v in o.data.vertices:
                p=o.matrix_world@v.co
                if p.x>front-.42:
                    fade=min(1,max(0,(p.x-(front-.42))/.42))**2
                    p.x-=.13*(p.y/W)**2*fade
                    p.x+=.022*max(0,1-((p.z-.42)/.38)**2)*fade
                    v.co=inv@p
            o.data.update()
    # Export once more with the final semantic names.
    bpy.ops.object.select_all(action='DESELECT')
    for o in col.objects:o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUT/(s['id']+'.glb')),export_format='GLB',use_selection=True,use_active_scene=True,export_apply=True,export_yup=True,export_extras=True,export_cameras=False,export_lights=False)
    s.pop('_body',None)
    return triangles
