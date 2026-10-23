"""Retain the user's original sculpted Mission S mesh; add working details."""
import bpy, math, json, shutil
from pathlib import Path
from mathutils import Vector
from mathutils.bvhtree import BVHTree
ROOT=Path('C:/Users/user/Desktop/AIA/Tesla')
source=(ROOT/'tools/build_porsche_fleet.py').read_text(encoding='utf-8').split('# Geometry and articulated')[0]
exec(source)
exec((ROOT/'tools/fleet_refinement.py').read_text(encoding='utf-8'))
with bpy.data.libraries.load(str(OUT/'backup-v1/original-vertigo-gt.blend'),link=False) as (src,dst):dst.scenes=src.scenes
original=dst.scenes[0];bpy.context.window.scene=original
deps=bpy.context.evaluated_depsgraph_get()
parts=[]
excluded=('Cyclorama','ArchCutter','sedan_','crossover_','hatch_','van_')
for o in original.objects:
    if o.type not in ['MESH','CURVE'] or o.name.startswith(excluded):continue
    data=bpy.data.meshes.new_from_object(o.evaluated_get(deps),depsgraph=deps)
    copy=bpy.data.objects.new(o.name.split('.')[0],data);copy.matrix_world=o.matrix_world.copy();parts.append(copy)
scene=bpy.data.scenes.new('Mission S • revised original');bpy.context.window.scene=scene
CAR=bpy.data.collections.new('mission-s');scene.collection.children.link(CAR);col=CAR
for o in parts:CAR.objects.link(o)
body=next(o for o in parts if o.name.startswith('Body.'))
# Keep the original canopy and wide arches. Soften the bonnet crown and sharpen its shoulder.
for vertex in body.data.vertices:
    x,y,z=vertex.co
    if .85<x<2.2 and z>.65:
        vertex.co.z-=.018*math.sin(math.pi*(x-.85)/1.35)**2*max(0,1-(abs(y)/.72)**2)
body.data.update()
paint_index=next(i for i,m in enumerate(body.data.materials) if m.name.startswith('Paint'))
glass_indices={i for i,m in enumerate(body.data.materials) if m.name.startswith('Glass')}
for face in body.data.polygons:
    x,y,z=face.center
    if face.material_index in glass_indices and -.78<x<.15 and abs(y)<.43 and z>1.08:
        face.material_index=paint_index
verts=[body.matrix_world@v.co for v in body.data.vertices]
bvh=BVHTree.FromPolygons(verts,[tuple(p.vertices) for p in body.data.polygons])
def surface(x,y):
    hit=bvh.ray_cast(Vector((x,y,3)),Vector((0,0,-1)))
    return hit[0]
def back(y,z):
    hit=bvh.ray_cast(Vector((-4,y,z)),Vector((1,0,0)))
    return hit[0]
# Panels use ray-cast positions on the existing shell, including the compound bonnet curvature.
for sign in [-1,1]:
    pts=[]
    for i in range(81):
        t=i/80;p=surface(.76+1.32*t,sign*(.49-.15*t))
        if p:p.z+=.002;pts.append(tuple(p))
    line('Mission S bonnet shutline',pts,TRIM,.002)
    pts=[]
    for i in range(45):
        x=-1.75+i*.014;p=surface(x,sign*.52)
        if p:p.z+=.003;pts.append(tuple(p))
    line('Rear deck service panel',pts,TRIM,.002)
# Use readable optical layers without bulb-shaped projectors.
for o in list(CAR.objects):
    if o.name.startswith('Projector_'):
        bounds=[o.matrix_world@Vector(c) for c in o.bound_box]
        center=sum(bounds,Vector())/8
        for v in o.data.vertices:
            world=o.matrix_world@v.co;world.x=center.x+(world.x-center.x)*.18
            v.co=o.matrix_world.inverted()@world
    for slot in o.material_slots:
        if not slot.material:continue
        if slot.material.name.startswith('TailLamp'):slot.material=BRAKE
        if slot.material.name.startswith('Glass'):slot.material=GLASS
# Shape the three stop-light sections to the existing rear surface.
for sign in [-1,1]:
    pts=[]
    for i in range(41):
        y=sign*(.36+.40*i/40);p=back(y,.70)
        if p:p.x-=.004;pts.append(tuple(p))
    line('Additional brake light segment',pts,BRAKE,.009)
    pts=[]
    for i in range(13):
        p=back(sign*(.38+i*.009),.61)
        if p:p.x-=.005;pts.append(tuple(p))
    line('Reverse optic',pts,REVERSE,.005)
pts=[]
for i in range(31):
    p=back(-.18+.36*i/30,.78)
    if p:p.x-=.004;pts.append(tuple(p))
line('Center high mount brake light',pts,CENTER,.007)
s=dict(id='mission-s',name='Mission S / original Vertigo GT',color='Pearl White',hex='#e9edf0',length=4.736,width=2.025,height=1.25,wb=2.76,r=.36,kind='original',base=.77)
interior(s)
for o in col.objects:o['vehicle_id']='mission-s'
triangles=export_car(scene,col,s)
cam=studio(scene)
for angle,loc in [('front',(6.5,-8,3.4)),('rear',(-6.5,8,2.8)),('side',(0,-9,1.8))]:
    point_camera(cam,loc,scale=6.25);scene.render.filepath=str(RENDERS/('mission-s_'+angle+'.png'));bpy.ops.render.render(write_still=True)
bpy.data.libraries.write(str(OUT/'mission-s.blend'),{scene},fake_user=True)
shutil.copy2(OUT/'mission-s.glb',ROOT/'assets/car.glb')
shutil.copy2(OUT/'mission-s.blend',ROOT/'assets/vertigo-gt.blend')
s.update(triangles=triangles,bytes=(OUT/'mission-s.glb').stat().st_size)
(OUT/'mission-s.json').write_text(json.dumps(s,ensure_ascii=False,indent=2),encoding='utf-8')
result=s
