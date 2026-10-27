"""Inspect the actual game GLBs without rebuilding or overwriting them.
Adds the runtime tail-pipe specification in a disposable Blender scene only.
"""
import bpy, math, json, hashlib
from pathlib import Path
from mathutils import Vector
ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'design/vehicles/target-quality-2026-10-26'
REF=OUT/'source-renders';REF.mkdir(parents=True,exist_ok=True)
CARS=[
 ('gt','assets/car.glb',4.736,.05,[(.13,.38),(-.13,.38)]),
 ('arc','assets/vehicles/vertigo-arc.glb',4.62,.042,[(.48,.30),(-.48,.30)]),
 ('apex','assets/vehicles/vertigo-apex.glb',4.50,.038,[(.07,.40),(-.07,.40),(.20,.40),(-.20,.40)]),
 ('grand','assets/vehicles/vertigo-grand.glb',4.96,.038,[(.40,.31),(.53,.31),(-.40,.31),(-.53,.31)]),
 ('terra','assets/vehicles/vertigo-terra.glb',4.80,.055,[(.56,.56),(-.56,.56)]),
 ('r','assets/vehicles/vertigo-r.glb',4.68,.07,[(0,.43)]),
]
def mat(name,color,metal=0,rough=.3):
 m=bpy.data.materials.new(name);m.diffuse_color=(*color,1);m.use_nodes=True
 p=next(n for n in m.node_tree.nodes if n.type=='BSDF_PRINCIPLED')
 p.inputs['Base Color'].default_value=(*color,1);p.inputs['Metallic'].default_value=metal;p.inputs['Roughness'].default_value=rough
 return m
chrome=mat('Inspection chrome',(.65,.68,.72),1,.19);soot=mat('Inspection exhaust bore',(.005,.005,.006),.2,.7)
floor=mat('Inspection floor',(.14,.16,.18),0,.6)
report=[]
for ident,relative,length,radius,tips in CARS:
 scene=bpy.data.scenes.new('Latest GLB inspection '+ident);bpy.context.window.scene=scene
 before=set(scene.objects);bpy.ops.import_scene.gltf(filepath=str(ROOT/relative));objects=[o for o in scene.objects if o not in before]
 meshes=[o for o in objects if o.type=='MESH'];bounds=[o.matrix_world@Vector(c) for o in meshes for c in o.bound_box]
 low=Vector(tuple(min(v[k] for v in bounds) for k in range(3)));high=Vector(tuple(max(v[k] for v in bounds) for k in range(3)))
 # Import returns Blender coordinates +X forward +Z up. Match game length normalization.
 scale=length/max(high.x-low.x,high.y-low.y);center=(high+low)/2
 root=bpy.data.objects.new('Inspection normalization',None);scene.collection.objects.link(root)
 for o in objects:
  if o.parent is None:o.parent=root
 root.scale=(scale,scale,scale);root.location=(-center.x*scale,-center.y*scale,-low.z*scale)
 bpy.context.view_layer.update()
 # Runtime fits pipes by ray casting +X from behind the car at the registered tip positions.
 for across,height in tips:
  # Three.js across +Z maps to Blender -Y.
  y=-across;hits=[]
  for o in meshes:
   if 'wheel' in o.name.lower() or 'caliper' in o.name.lower():continue
   inv=o.matrix_world.inverted();origin=inv@Vector((-length,height*0+y,height));direction=(inv.to_3x3()@Vector((1,0,0))).normalized()
   ok,p,n,index=o.ray_cast(origin,direction)
   if ok:hits.append((o.matrix_world@p).x)
  x=min(hits) if hits else -length/2+.08;x=min(x,-length/2+.45)-.035
  bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius,depth=.20,end_fill_type='NOTHING',location=(x+.10,y,height),rotation=(0,math.pi/2,0))
  bpy.context.object.name='Runtime exhaust tube';bpy.context.object.data.materials.append(chrome)
  bpy.ops.mesh.primitive_torus_add(major_segments=32,minor_segments=10,major_radius=radius,minor_radius=radius*.12,location=(x,y,height),rotation=(0,math.pi/2,0))
  bpy.context.object.data.materials.append(chrome)
  bpy.ops.mesh.primitive_cylinder_add(vertices=32,radius=radius*.92,depth=.002,location=(x+.03,y,height),rotation=(0,math.pi/2,0))
  bpy.context.object.data.materials.append(soot)
 bpy.ops.mesh.primitive_plane_add(size=200,location=(0,0,-.015));bpy.context.object.data.materials.append(floor)
 world=bpy.data.worlds.new('Inspection world');world.use_nodes=True;scene.world=world
 bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs[0].default_value=(.23,.26,.31,1);bg.inputs[1].default_value=.5
 for loc,power,size in [((2,-4,6),1100,5),((-3,2,5),1400,4),((1,5,3),800,4)]:
  data=bpy.data.lights.new('Inspection softbox','AREA');data.energy=power;data.shape='DISK';data.size=size
  o=bpy.data.objects.new('Inspection softbox',data);scene.collection.objects.link(o);o.location=loc;o.rotation_euler=(Vector((0,0,.6))-o.location).to_track_quat('-Z','Y').to_euler()
 data=bpy.data.cameras.new('Inspection camera');cam=bpy.data.objects.new('Inspection camera',data);scene.collection.objects.link(cam);scene.camera=cam;data.type='ORTHO';data.ortho_scale=6.1
 scene.render.engine='CYCLES';scene.cycles.samples=16;scene.cycles.use_denoising=True
 try:
  pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
  for d in pref.devices:d.use=d.type!='CPU'
  if any(d.use for d in pref.devices):scene.cycles.device='GPU'
 except Exception:pass
 scene.render.resolution_x=1200;scene.render.resolution_y=780;scene.render.resolution_percentage=100
 scene.render.image_settings.file_format='PNG';scene.view_settings.view_transform='AgX'
 for angle,loc in [('front',(6,-8,3.4)),('rear',(-6,8,3.0))]:
  cam.location=loc;cam.rotation_euler=(Vector((0,0,.7))-cam.location).to_track_quat('-Z','Y').to_euler()
  scene.render.filepath=str(REF/f'{ident}-{angle}.png');bpy.ops.render.render(write_still=True)
 report.append({'id':ident,'source':relative,'sha256':hashlib.sha256((ROOT/relative).read_bytes()).hexdigest(),'bytes':(ROOT/relative).stat().st_size,'exhaust_tips':tips,'exhaust_radius':radius})
 (OUT/'source-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
 print('INSPECTED',ident,flush=True)
