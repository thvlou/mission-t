"""Procedural, editable game meshes, authored in Blender via its MCP add-on.

Run through tools/blender_client.py. Dimensions are metres, nose +X, up +Z.
The silhouettes and details are manually interpreted from official photographs;
these are stylised models, not factory CAD or downloaded Porsche meshes.
"""
import bpy
import math
import json
from mathutils import Vector
from pathlib import Path
from math import sin, cos, pi, exp

ROOT = Path('C:/Users/user/Desktop/AIA/Tesla')
OUT = ROOT/'assets/vehicles'
RENDERS = ROOT/'renders/vehicles'
OUT.mkdir(parents=True, exist_ok=True)
RENDERS.mkdir(parents=True, exist_ok=True)

SPECS = [
 dict(id='macan-4s',name='Macan 4S Electric',color='Oak Green Metallic',hex='#164e35',rgb=(.018,.115,.052),length=4.784,width=1.938,height=1.622,wb=2.893,r=.385,kind='suv',spokes=5,
      roof=[(-2.08,.94,.66),(-1.65,1.42,.72),(-1.05,1.60,.71),(-.1,1.61,.70),(.38,1.52,.68),(.88,1.03,.73)],front=.35,rear=-1.52,base=.99),
 dict(id='911-carrera',name='911 Carrera',color='Guards Red',hex='#cf1823',rgb=(.62,.012,.021),length=4.542,width=1.852,height=1.302,wb=2.450,r=.347,kind='coupe',spokes=5,
      roof=[(-1.83,.85,.59),(-1.25,1.10,.66),(-.68,1.285,.65),(-.12,1.28,.63),(.23,1.20,.62),(.83,.80,.72)],front=.22,rear=-1.20,base=.80),
 dict(id='718-cayman',name='718 Cayman',color='Racing Yellow',hex='#efc51e',rgb=(.92,.64,.014),length=4.379,width=1.801,height=1.295,wb=2.475,r=.335,kind='mid',spokes=10,
      roof=[(-1.53,.81,.56),(-1.04,1.13,.60),(-.55,1.28,.61),(-.08,1.28,.60),(.25,1.18,.59),(.79,.78,.68)],front=.20,rear=-.92,base=.78),
 dict(id='taycan',name='Taycan',color='Frozen Blue Metallic',hex='#639ec5',rgb=(.13,.37,.57),length=4.963,width=1.966,height=1.379,wb=2.900,r=.365,kind='ev',spokes=5,
      roof=[(-1.94,.84,.61),(-1.40,1.14,.68),(-.80,1.35,.68),(.06,1.36,.66),(.48,1.25,.64),(1.08,.82,.75)],front=.45,rear=-1.30,base=.82),
 dict(id='911-gt3-rs',name='911 GT3 RS',color='Ultraviolet / Satin Black',hex='#7143ac',rgb=(.20,.052,.40),length=4.572,width=1.900,height=1.322,wb=2.457,r=.350,kind='track',spokes=10,
      roof=[(-1.83,.85,.59),(-1.25,1.10,.66),(-.68,1.30,.65),(-.12,1.29,.63),(.23,1.21,.62),(.83,.80,.72)],front=.22,rear=-1.20,base=.80),
]

def material(name,rgb,metal=0,rough=.3,emission=0):
    m=bpy.data.materials.new(name); m.diffuse_color=(*rgb,1); m.use_nodes=True
    p=next((n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED'),None)
    if p is None:
        p=m.node_tree.nodes.new('ShaderNodeBsdfPrincipled')
        output=next((n for n in m.node_tree.nodes if n.type=='OUTPUT_MATERIAL'),None) or m.node_tree.nodes.new('ShaderNodeOutputMaterial')
        m.node_tree.links.new(p.outputs[0],output.inputs['Surface'])
    p.inputs['Base Color'].default_value=(*rgb,1)
    p.inputs['Metallic'].default_value=metal; p.inputs['Roughness'].default_value=rough
    if 'Coat Weight' in p.inputs: p.inputs['Coat Weight'].default_value=.38 if metal else .1
    if emission:
        p.inputs['Emission Color'].default_value=(*rgb,1); p.inputs['Emission Strength'].default_value=emission
    return m

TRIM=material('Fleet • graphite trim',(.012,.016,.021),.25,.32)
GLASS=material('Fleet • smoked glass',(.018,.032,.044),.45,.16)
RUBBER=material('Fleet • tire rubber',(.013,.015,.017),0,.73)
SILVER=material('Fleet • forged aluminium',(.52,.58,.65),.85,.24)
DARK=material('Fleet • wheel barrel',(.035,.043,.055),.8,.28)
DISC=material('Fleet • brake rotor',(.21,.24,.27),.85,.4)
RED=material('Fleet • brake caliper',(.65,.015,.018),.35,.3)
GOLD=material('Fleet • wheel crest',(.47,.29,.065),.7,.26)
LED=material('Fleet • white LED',(.78,.92,1),.1,.16,2)
TAIL=material('Fleet • red LED',(.7,.008,.018),.2,.22,1.8)
CHROME=material('Fleet • bright trim',(.65,.70,.76),.9,.18)
FLOOR=material('Fleet • studio',(.19,.215,.25),.05,.56)

def link_obj(obj):
    for col in list(obj.users_collection): col.objects.unlink(obj)
    CAR.objects.link(obj)
    return obj

def mesh(name,verts,faces,mat):
    data=bpy.data.meshes.new(name); data.from_pydata(verts,[],faces); data.update()
    obj=bpy.data.objects.new(name,data); CAR.objects.link(obj)
    for m in mat if isinstance(mat,list) else [mat]: data.materials.append(m)
    for f in data.polygons:f.use_smooth=True
    return obj

def box(name,loc,size,mat,bevel=.025):
    bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=link_obj(bpy.context.object);o.name=name
    o.scale=size; bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    o.data.materials.append(mat)
    if bevel:
        b=o.modifiers.new('Soft manufactured edges','BEVEL');b.width=bevel;b.segments=3
        bpy.context.view_layer.objects.active=o; bpy.ops.object.modifier_apply(modifier=b.name)
        for f in o.data.polygons:f.use_smooth=True
        n=o.modifiers.new('Weighted normals','WEIGHTED_NORMAL');bpy.ops.object.modifier_apply(modifier=n.name)
    return o

def ellipsoid(name,loc,scale,mat,rot=(0,0,0)):
    bpy.ops.mesh.primitive_uv_sphere_add(segments=32,ring_count=12,location=loc,rotation=rot)
    o=link_obj(bpy.context.object);o.name=name;o.scale=scale;o.data.materials.append(mat)
    bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
    for f in o.data.polygons:f.use_smooth=True
    return o

def line(name,pts,mat,r=.006,closed=False):
    d=bpy.data.curves.new(name,'CURVE');d.dimensions='3D';d.bevel_depth=r;d.bevel_resolution=2
    s=d.splines.new('POLY');s.points.add(len(pts)-1)
    for p,co in zip(s.points,pts):p.co=(*co,1)
    s.use_cyclic_u=closed
    o=bpy.data.objects.new(name,d);CAR.objects.link(o);o.data.materials.append(mat);return o

def cyl(name,loc,r,depth,mat,vertices=48):
    bpy.ops.mesh.primitive_cylinder_add(vertices=vertices,radius=r,depth=depth,location=loc,rotation=(pi/2,0,0))
    o=link_obj(bpy.context.object);o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=len(p.vertices)==4
    return o

def torus(name,loc,major,minor,mat):
    bpy.ops.mesh.primitive_torus_add(major_segments=64,minor_segments=10,location=loc,rotation=(pi/2,0,0),major_radius=major,minor_radius=minor)
    o=link_obj(bpy.context.object);o.name=name;o.data.materials.append(mat)
    for p in o.data.polygons:p.use_smooth=True
    return o

def smooth_interp(points,x):
    if x<=points[0][0]:return points[0][1:]
    if x>=points[-1][0]:return points[-1][1:]
    i=next(i for i in range(len(points)-1) if points[i][0]<=x<=points[i+1][0])
    a,b=points[i],points[i+1]; span=b[0]-a[0];t=(x-a[0])/span
    prev=points[max(0,i-1)];nxt=points[min(len(points)-1,i+2)]
    return tuple((2*t**3-3*t*t+1)*a[j]+(t**3-2*t*t+t)*span*(b[j]-prev[j])/(b[0]-prev[0])+(-2*t**3+3*t*t)*b[j]+(t**3-t*t)*span*(nxt[j]-a[j])/(nxt[0]-a[0]) for j in range(1,len(a)))

def make_body(s,paint):
    L=s['length'];W=s['width']/2; suv=s['kind']=='suv'; h=1.13 if suv else (.95 if s['kind']=='ev' else .89)
    points=[(-L/2,.83*W,h-.13),(-L*.43,.98*W,h+.02),(-s['wb']/2,W,h+.07),(-.4,.92*W,h),(.5,.92*W,h-.035),(s['wb']/2,.98*W,h+.035),(L*.43,.92*W,h-.10),(L/2,.78*W,h-.28)]
    vs=[];fs=[];N=160;K=96;low=.20 if suv else .15
    for i in range(N+1):
        x=-L/2+L*i/N;w,z=smooth_interp(points,x)
        bump=.075*sum(exp(-((x-a)/.43)**2) for a in [-s['wb']/2,s['wb']/2])
        for j in range(K):
            a=2*pi*j/K; y=w*sin(a);c=cos(a)
            if c>=0:
                zc=top_z(s,points,x,y)
            else:
                y=w*math.copysign(abs(sin(a))**.22,sin(a))
                zc=low+(z-.10-low)*(1+c)**.65
            vs.append((x,y,zc))
    for i in range(N):
        for j in range(K):
            a=i*K+j;b=i*K+(j+1)%K;fs.append((a,b,b+K,a+K))
    fs.append(tuple(reversed(range(K))))
    # Radial bumper topology gives the nose enough vertices to carry real curvature.
    front_ring=[vs[N*K+j] for j in range(K)];middle=(low+front_ring[0][2])*.5
    center=len(vs);vs.append((L/2,0,middle));rings=[]
    for r in [.17,.34,.51,.68,.85]:
        ring=[]
        for xx,yy,zz in front_ring:
            ring.append(len(vs));vs.append((xx,yy*r,middle+(zz-middle)*r))
        rings.append(ring)
    rings.append([N*K+j for j in range(K)])
    for j in range(K):fs.append((center,rings[0][j],rings[0][(j+1)%K]))
    for a,b in zip(rings,rings[1:]):
        for j in range(K):fs.append((a[j],b[j],b[(j+1)%K],a[(j+1)%K]))
    body=mesh(s['id']+' • sculpted body',vs,[tuple(reversed(f)) for f in fs],[paint,TRIM])
    # True geometric wheel openings, not black discs drawn over the body.
    for x in [-s['wb']/2,s['wb']/2]:
        cutter=cyl('temporary arch cutter',(x,0,s['r']),s['r']+.033,s['width']+.6,TRIM,64)
        bpy.context.view_layer.objects.active=body
        mod=body.modifiers.new('Wheel arch cut','BOOLEAN');mod.operation='DIFFERENCE';mod.solver='EXACT';mod.object=cutter
        bpy.ops.object.modifier_apply(modifier=mod.name);bpy.data.objects.remove(cutter,do_unlink=True)
    for sign in [-1,1]:
        # Low skirts and subtle arch lips.
        box('Sill',(0,sign*(W-.03),low+.07),(s['wb']-s['r']*1.8,.055,.10),TRIM,.018)
        for x in [-s['wb']/2,s['wb']/2]:
            pts=[]
            for j in range(41):
                a=pi*j/40;xx=x+(s['r']+.044)*cos(a);w,_=smooth_interp(points,xx)
                pts.append((xx,sign*(w+.002),s['r']+(s['r']+.044)*sin(a)))
            line('Arch lip',pts,TRIM if suv else paint,.014 if suv else .008)
    return points

def cabin(s,paint):
    ctrl=s['roof'];base=s['base'];N=68;K=28;verts=[];faces=[];mids=[]
    for i in range(N+1):
        x=ctrl[0][0]+(ctrl[-1][0]-ctrl[0][0])*i/N;z,w=smooth_interp(ctrl,x)
        for j in range(K+1):
            t=-1+2*j/K
            verts.append((x,w*t,base+(z-base)*(max(0,1-abs(t)**4))**.55))
    for i in range(N):
        x=ctrl[0][0]+(ctrl[-1][0]-ctrl[0][0])*(i+.5)/N
        for j in range(K):
            a=i*(K+1)+j;faces.append((a,a+1,a+K+2,a+K+1))
            t=abs(-1+2*(j+.5)/K)
            glass=(x>s['front']+.05 or x<s['rear']-.04) and t<.89
            side=t>.72 and ctrl[0][0]+.18<x<ctrl[-1][0]-.12
            pillar=abs(x-(-.35 if s['kind'] in ['suv','ev'] else -.50))<.035
            mids.append(1 if (glass or side) and not (pillar and t>.72) else 0)
    o=mesh('Cabin • glass and painted pillars',verts,[tuple(reversed(f)) for f in faces],[paint,GLASS])
    for p,m in zip(o.data.polygons,mids):p.material_index=m
    for sign in [-1,1]:
        line('Window belt',[(x,sign*w,base+.003) for x,_,w in ctrl],TRIM,.009)
    return o

def side_y(s,ctrl,x,zz):
    w,z=smooth_interp(ctrl,x);low=.20 if s['kind']=='suv' else .15
    if zz>=z-.10:return w
    c=max(-1,min(0,((max(0,zz-low)/(z-.10-low))**(1/.65))-1))
    return w*max(0,1-c*c)**.11

def top_z(s,ctrl,x,y):
    w,z=smooth_interp(ctrl,x);t=min(.99,abs(y/w));c=math.sqrt(1-t*t)
    bump=.075*sum(exp(-((x-a)/.43)**2) for a in [-s['wb']/2,s['wb']/2])
    return z-.10*(1-c)+bump*t**3

def side_patch(name,s,ctrl,sign,corners,mat):
    verts=[];faces=[];N=12
    for i in range(N+1):
        u=i/N
        for j in range(N+1):
            v=j/N
            x=sum(corners[k][0]*weight for k,weight in enumerate([(1-u)*(1-v),u*(1-v),u*v,(1-u)*v]))
            z=sum(corners[k][1]*weight for k,weight in enumerate([(1-u)*(1-v),u*(1-v),u*v,(1-u)*v]))
            verts.append((x,sign*(side_y(s,ctrl,x,z)+.012),z))
    for i in range(N):
        for j in range(N):
            a=i*(N+1)+j;faces.append((a,a+1,a+N+2,a+N+1))
    return mesh(name,verts,faces,mat)

def wheels(s):
    W=s['width']/2;r=s['r'];depth=.235 if s['kind']!='track' else .285
    for axle,x in [('F',s['wb']/2),('R',-s['wb']/2)]:
        for side,sign in [('L',1),('R',-1)]:
            center=Vector((x,sign*(W-.085),r));parts=[]
            parts.append(torus('Tire',center,r-.065,.065,RUBBER))
            # Fill tread width with a cylindrical annulus rather than a balloon tire.
            v=[];f=[]
            profile=[(-depth/2,r-.055),(-depth*.39,r-.008),(depth*.39,r-.008),(depth/2,r-.055),(depth/2,r-.112),(-depth/2,r-.112)]
            for yy,rr in profile:
                for k in range(64):
                    a=2*pi*k/64;v.append(tuple(center+Vector((rr*cos(a),yy,rr*sin(a)))))
            for j in range(len(profile)):
                for k in range(64):
                    a=j*64+k;b=j*64+(k+1)%64;c=((j+1)%len(profile))*64+(k+1)%64;d=((j+1)%len(profile))*64+k;f.append((a,b,c,d))
            parts.append(mesh('Tread and sidewall',v,f,RUBBER))
            facey=center.y+sign*(depth/2+.004)
            parts.append(cyl('Barrel',(x,center.y,r),r-.104,depth*.91,DARK))
            parts.append(torus('Machined rim lip',(x,facey,r),r-.093,.014,SILVER if s['kind']!='track' else DARK))
            parts.append(cyl('Ventilated rotor',(x,facey-sign*.035,r),r-.123,.012,DISC))
            # Caliper is deliberately outside rotating pivot.
            box('Fixed brake caliper '+axle+side,(x-.15,facey-sign*.02,r+.055),(.065,.042,.17),RED if s['kind']!='track' else GOLD,.02)
            for k in range(s['spokes']):
                a=2*pi*k/s['spokes']+.15
                offsets=[-.034,.034] if s['spokes']==5 and s['kind']=='ev' else [0]
                for off in offsets:
                    rr=(r-.095)*.61;xx=x+rr*sin(a+off);zz=r+rr*cos(a+off)
                    o=box('Forged spoke',(xx,facey,zz),(.048 if s['spokes']==10 else .067,.028,(r-.095)*.83),DARK if s['kind']=='track' else SILVER,.009)
                    o.rotation_euler.y=a+off;parts.append(o)
            parts.append(cyl('Hub',(x,facey+sign*.014,r),.067,.035,DARK,32))
            parts.append(cyl('Centre crest',(x,facey+sign*.035,r),.027,.008,GOLD,24))
            for k in range(5):
                a=2*pi*k/5
                parts.append(cyl('Lug',(x+.046*sin(a),facey+sign*.033,r+.046*cos(a)),.007,.008,CHROME,8))
            for o in parts:
                if o.type=='CURVE':
                    bpy.context.view_layer.objects.active=o;o.select_set(True);bpy.ops.object.convert(target='MESH');o.select_set(False)
            bpy.ops.object.select_all(action='DESELECT')
            for o in parts:o.select_set(True)
            bpy.context.view_layer.objects.active=parts[0];bpy.ops.object.join();wheel=bpy.context.object
            wheel.name='wheel_'+axle+side
            bpy.ops.object.transform_apply(location=False,rotation=True,scale=True)
            bpy.context.scene.cursor.location=center;bpy.ops.object.origin_set(type='ORIGIN_CURSOR')

def front_details(s,paint,body_ctrl):
    L=s['length'];W=s['width']/2;kind=s['kind'];front=L/2;z=.91 if kind=='suv' else .68
    for sign in [-1,1]:
        y=sign*W*.70
        if kind in ['coupe','track','mid']:
            hx=front-.30;w,hz=smooth_interp(body_ctrl,hx);c=math.sqrt(max(0,1-(y/w)**2))
            bump=.075*sum(exp(-((hx-a)/.43)**2) for a in [-s['wb']/2,s['wb']/2])
            loc=(hx,y,hz-.10*(1-c)+bump*abs(y/w)**3+.009)
            ellipsoid('Oval headlight housing',loc,(.165,.145,.037),TRIM,(0,.53,0))
            ellipsoid('Headlight optical lens',(loc[0]+.012,y,loc[2]+.027),(.145,.125,.021),GLASS,(0,.53,0))
            pts=[]
            for k in range(49):
                a=2*pi*k/48;u=.139*cos(a);v=.118*sin(a)
                pts.append((loc[0]+u*cos(.53)+.018,y+v,loc[2]-u*sin(.53)+.034))
            line('Oval LED perimeter',pts,LED,.007,True)
            for a in [-1,1]:
                for b in [-1,1]:ellipsoid('Four point LED',(loc[0]+a*.049,y+b*.048,loc[2]+.048-a*.024),(.018,.016,.009),LED,(0,.53,0))
        else:
            hx=front-.24;loc=(hx,y,top_z(s,body_ctrl,hx,y)+.012)
            ellipsoid('Slim DRL housing',loc,(.095,.21,.014),TRIM,(0,.28,sign*.10))
            for a in [-1,1]:
                for b in [-1,1]:
                    box('Four point light blade',(loc[0]+a*.028,y+b*.078,loc[2]+.020-a*.008),(.015,.097,.009),LED,.004)
            if kind=='suv':
                box('Lower headlight housing',(front+.018,sign*W*.64,.64),(.035,.24,.19),TRIM,.035)
                box('Lower projector',(front+.041,sign*W*.64,.66),(.018,.11,.045),GLASS,.014)
            else:
                line('Air curtain teardrop',[(front-.03,sign*W*.84,.71),(front+.005,sign*W*.87,.59),(front-.035,sign*W*.84,.40)],TRIM,.032)
        # Bumper corners are distinct from the central intake.
        box('Corner intake',(front+.012,sign*W*.57,.38 if kind!='suv' else .46),(.035,.37,.17),TRIM,.045)
        for dz in [-.043,.005,.05]:
            box('Intake louvre',(front+.035,sign*W*.57,(.38 if kind!='suv' else .46)+dz),(.012,.28,.012),DARK,.004)
    box('Central front intake',(front+.019,0,.31 if kind!='suv' else .40),(.035,W*.75,.14),TRIM,.04)
    box('Front splitter',(front-.025,0,.19 if kind!='suv' else .26),(.17,W*1.62,.043),TRIM,.019)
    # Small generic shield, no texture dependency.
    ellipsoid('Bonnet badge',(front-.42,0,.84 if kind!='suv' else 1.04),(.029,.023,.004),GOLD)
    if kind=='track':
        for sign in [-1,1]:
            for dx in [-.16,-.08,0,.08,.16]:
                xx=.93+dx;yy=sign*.24
                box('Bonnet radiator vent',(xx,yy,top_z(s,body_ctrl,xx,yy)+.009),(.071,.20,.014),TRIM,.009)
            for i in range(5):
                xx=s['wb']/2-.18+i*.073;yy=sign*W*.80
                box('Fender louvre',(xx,yy,top_z(s,body_ctrl,xx,yy)+.012),(.034,.16,.012),TRIM,.007)
            line('Bumper canard',[(front-.35,sign*W,.28),(front-.1,sign*(W+.075),.34),(front-.02,sign*(W-.01),.34)],TRIM,.014)

def details(s,paint,body_ctrl):
    L=s['length'];W=s['width']/2;kind=s['kind'];rear=-L/2;z=.85 if kind=='suv' else .72
    # Full-width rear light signature, with the Cayman's separate lamp clusters.
    if kind=='mid':
        box('Rear lamp connector',(rear-.014,0,z),(.035,1.45,.045),TRIM,.02)
        for sign in [-1,1]:
            box('Cayman tail housing',(rear+.01,sign*.61,z+.014),(.055,.35,.105),TRIM,.035)
            line('Cayman red light contour',[(rear-.025,sign*.44,z+.035),(rear-.032,sign*.72,z+.042),(rear-.02,sign*.77,z-.015),(rear-.028,sign*.44,z-.022)],TAIL,.012)
    else:
        pts=[(rear-.022+.06*(abs(t)/.8)**2,t,z+.018*cos(t*1.5)) for t in [-.8+j*.04 for j in range(41)]]
        line('Rear light black surround',pts,TRIM,.035)
        line('Continuous red LED strip',[(x-.009,y,zz+.007) for x,y,zz in pts],TAIL,.011)
    box('Rear diffuser',(rear-.006,0,.27 if kind!='suv' else .32),(.055,1.42,.14),TRIM,.025)
    for y in [-.55,-.28,0,.28,.55]:box('Diffuser fin',(rear+.025,y,.23 if kind!='suv' else .28),(.30,.016,.13),DARK,.006)
    if kind not in ['suv','ev']:
        ys=[-.47,.47] if kind=='coupe' else [-.105,.105]
        for y in ys:
            o=cyl('Exhaust bright rim',(rear-.07,y,.29),.055,.1,CHROME,32);o.rotation_euler=(0,pi/2,0)
            o=cyl('Exhaust dark opening',(rear-.125,y,.29),.043,.005,TRIM,32);o.rotation_euler=(0,pi/2,0)
    # Plate and restrained lettering, visible on the game chase camera.
    box('Rear plate',(rear-.008,0,.48),(.012,.38,.095),DARK,.012)
    d=bpy.data.curves.new('Model lettering','FONT');d.body='MISSION T';d.align_x='CENTER';d.size=.048;d.extrude=.0005
    o=bpy.data.objects.new('Rear model lettering',d);CAR.objects.link(o);o.location=(rear-.018,0,.48);o.rotation_euler=(pi/2,0,-pi/2);o.data.materials.append(SILVER)
    for sign in [-1,1]:
        # Doors follow the actual shell width and sit just above it.
        xs=[(.62,s['base']-.01),(.68,.60),(.49,.28),(-.64,.26),(-.85,.44),(-.86,s['base']-.015)]
        if kind in ['suv','ev']:xs=[(.80,s['base']-.01),(.82,.60),(.64,.30),(-1.08,.30),(-1.18,.55),(-1.16,s['base']-.01)]
        pts=[]
        for x,zz in xs:
            pts.append((x,sign*(side_y(s,body_ctrl,x,zz)+.004),zz))
        line('Door shutline',pts,TRIM,.0035)
        if kind in ['suv','ev']:
            line('Rear door shutline',[(-.35,sign*(side_y(s,body_ctrl,-.35,zz)+.004),zz) for zz in [s['base'],.75,.5,.32]],TRIM,.0035)
        for x in ([-.1,-.94] if kind in ['suv','ev'] else [-.52]):
            w,_=smooth_interp(body_ctrl,x);box('Flush door handle',(x,sign*(w+.012),s['base']-.07),(.15,.017,.022),DARK if kind=='track' else paint,.009)
        # Mirrors with a visible underside and short pedestal.
        mx=.64 if kind not in ['suv','ev'] else .70
        line('Mirror stalk',[(mx,sign*.68,s['base']+.12),(mx+.04,sign*(W+.015),s['base']+.075)],TRIM,.019)
        ellipsoid('Mirror housing',(mx+.035,sign*(W+.065),s['base']+.11),(.13,.085,.056),TRIM if kind=='track' else paint)
        ellipsoid('Mirror glass',(mx-.06,sign*(W+.067),s['base']+.11),(.008,.062,.035),CHROME)
        if kind in ['mid','track']:
            # Large, swept mid-engine intake behind each door.
            w,_=smooth_interp(body_ctrl,-.97)
            side_patch('Swept side air intake',s,body_ctrl,sign,[(-.50,.79),(-.88,.85),(-.80,.47),(-.65,.49)],TRIM)
            line('Side intake dividing blade',[(xx,sign*(side_y(s,body_ctrl,xx,zz)+.022),zz) for xx,zz in [(-.62,.74),(-.67,.64),(-.74,.51)]],DARK,.009)
        if kind=='suv':
            mesh('Macan signature sideblade',[(xx,sign*(side_y(s,body_ctrl,xx,zz)+.007),zz) for xx,zz in [(-.98,.39),(-.80,.48),(.63,.44),(.70,.38)]],[(0,1,2,3)],DARK)
        if kind in ['coupe','track'] and sign==1:
            for j in range(11):
                yy=-.43+j*.086;box('Rear engine deck slat',(-1.71,yy,.91),(.28,.020,.014),TRIM,.005)
    if kind in ['suv','ev']:
        spoiler=box('Rear roof spoiler',(-1.91 if kind=='suv' else -2.0,0,1.13 if kind=='suv' else .91),(.26,1.39,.045),TRIM if kind=='suv' else paint,.025)
    if kind=='track':
        # Swan neck struts, two-plane wing, end plates and DRS-like upper element.
        for sign in [-1,1]:
            mesh('Swan neck wing support',[(-1.48,sign*.52,.94),(-1.38,sign*.52,1.57),(-1.87,sign*.52,1.57),(-1.93,sign*.52,1.48),(-1.53,sign*.52,1.44),(-1.61,sign*.52,.95)],[(0,1,2,3,4,5)],TRIM)
            box('Wing endplate',(-1.94,sign*1.02,1.47),(.57,.026,.24),TRIM,.016)
        box('GT3 RS lower wing',(-1.91,0,1.38),(.42,2.03,.041),TRIM,.018)
        wing=box('GT3 RS upper aerofoil',(-1.99,0,1.56),(.46,2.02,.046),TRIM,.02);wing.rotation_euler.y=-.10
        for sign in [-1,1]:box('GT3 RS side skirt extension',(0,sign*(W+.02),.17),(1.55,.095,.05),TRIM,.016)

def studio(scene):
    global CAR
    CAR=bpy.data.collections.new('Studio');scene.collection.children.link(CAR)
    box('Studio floor',(0,0,-.065),(200,200,.1),FLOOR,.0)
    world=bpy.data.worlds.new('Fleet studio world');scene.world=world;world.use_nodes=True
    bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND')
    bg.inputs[0].default_value=(.26,.30,.38,1)
    bg.inputs[1].default_value=.65
    for name,loc,power,size in [('Key',(3,-4,7),1600,5),('Fill',(0,5,5),1300,5),('Rim',(-4,-1,5),1800,4)]:
        data=bpy.data.lights.new(name,'AREA');data.energy=power;data.shape='DISK';data.size=size
        o=bpy.data.objects.new(name,data);CAR.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,.6))-o.location).to_track_quat('-Z','Y').to_euler()
    data=bpy.data.cameras.new('Review camera');cam=bpy.data.objects.new('Review camera',data);CAR.objects.link(cam);scene.camera=cam;data.type='ORTHO';data.ortho_scale=6.4
    scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
    try:
        prefs=bpy.context.preferences.addons['cycles'].preferences
        prefs.compute_device_type='OPTIX';prefs.get_devices()
        for device in prefs.devices:device.use=device.type!='CPU'
        if any(d.use for d in prefs.devices):scene.cycles.device='GPU'
    except Exception:pass
    scene.render.resolution_x=1200;scene.render.resolution_y=780;scene.render.resolution_percentage=100
    scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG'
    return cam

def point_camera(cam,loc,target=(0,0,.65),scale=6.4):
    cam.location=loc;cam.rotation_euler=(Vector(target)-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.ortho_scale=scale

def export_car(scene,col,s):
    bpy.ops.object.select_all(action='DESELECT')
    for o in list(col.objects):
        o.select_set(True)
        if o.type in ['CURVE','FONT']:
            bpy.context.view_layer.objects.active=o;bpy.ops.object.convert(target='MESH')
        o.select_set(False)
    # Reduce draw calls while preserving four independently animated wheel meshes.
    static=[o for o in col.objects if o.type=='MESH' and not o.name.startswith('wheel_')]
    for o in static:o.select_set(True)
    bpy.context.view_layer.objects.active=static[0];bpy.ops.object.join();body=bpy.context.object;body.name=s['id']+' • body details'
    bpy.ops.object.select_all(action='DESELECT')
    for o in col.objects:o.select_set(True)
    bpy.ops.export_scene.gltf(filepath=str(OUT/(s['id']+'.glb')),export_format='GLB',use_selection=True,use_active_scene=True,export_apply=True,export_yup=True,export_extras=True,export_cameras=False,export_lights=False)
    deps=bpy.context.evaluated_depsgraph_get();triangles=0
    for o in col.objects:
        if o.type=='MESH':
            m=o.evaluated_get(deps).to_mesh();m.calc_loop_triangles();triangles+=len(m.loop_triangles)
            o.evaluated_get(deps).to_mesh_clear()
    return triangles

def build_one(s):
    global CAR
    scene=bpy.data.scenes.new('Mission T • '+s['name']);bpy.context.window.scene=scene
    scene.unit_settings.system='METRIC'
    CAR=bpy.data.collections.new(s['id']);scene.collection.children.link(CAR);col=CAR
    paint=material('Paint • '+s['color'],s['rgb'],.15 if s['kind'] in ['coupe','mid','track'] else .50,.27)
    ctrl=make_body(s,paint);cabin(s,paint);wheels(s);front_details(s,paint,ctrl);details(s,paint,ctrl)
    for o in col.objects:o['vehicle_id']=s['id']
    triangles=export_car(scene,col,s)
    cam=studio(scene)
    for angle,loc in [('front',(6.5,-8,4.4)),('rear',(-6.5,8,3.5)),('side',(0,-9,2.05))]:
        point_camera(cam,loc,scale=6.5 if s['kind']=='suv' else 6.2)
        scene.render.filepath=str(RENDERS/(s['id']+'_'+angle+'.png'));bpy.ops.render.render(write_still=True)
    point_camera(cam,(6.5,-8,4.4))
    bpy.data.libraries.write(str(OUT/(s['id']+'.blend')),{scene},fake_user=True)
    s['triangles']=triangles;s['bytes']=(OUT/(s['id']+'.glb')).stat().st_size
    print('FLEET_COMPLETE',s['id'],triangles,flush=True)
    return scene,col

# Geometry and articulated components for the revised fleet.
exec((ROOT/'tools/fleet_refinement.py').read_text(encoding='utf-8'))

# The caller may supply FLEET_IDS to build a subset, allowing short MCP jobs.
chosen=globals().get('FLEET_IDS',[s['id'] for s in SPECS])
finished=[]
for spec in SPECS:
    if spec['id'] in chosen:
        sc,co=build_one(spec);finished.append({k:v for k,v in spec.items() if k not in ['roof','rgb']})
        (OUT/(spec['id']+'.json')).write_text(json.dumps(finished[-1],ensure_ascii=False,indent=2),encoding='utf-8')
result={'completed':finished,'output':str(OUT)}
