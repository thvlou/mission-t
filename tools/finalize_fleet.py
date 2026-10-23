"""Create a single Blender review scene with all five finished vehicles."""
import bpy, math
from pathlib import Path
from mathutils import Vector
ROOT=Path('C:/Users/user/Desktop/AIA/Tesla')
IDS=['macan-4s','911-carrera','718-cayman','taycan','911-gt3-rs']
NAMES=['MACAN 4S','911 CARRERA','718 CAYMAN','TAYCAN','911 GT3 RS']
scene=bpy.data.scenes.new('Mission T • Porsche Collection')
bpy.context.window.scene=scene
slots=[(-5.8,3.0),(0,3.0),(5.8,3.0),(-3.0,-3.4),(3.0,-3.4)]
for vehicle,label,(x,y) in zip(IDS,NAMES,slots):
    with bpy.data.libraries.load(str(ROOT/'assets/vehicles'/(vehicle+'.blend')),link=False) as (src,dst):
        dst.scenes=src.scenes
    loaded=dst.scenes[0]
    col=next(c for c in loaded.collection.children if any(o.get('vehicle_id')==vehicle for o in c.objects))
    instance=bpy.data.objects.new(label,None);instance.instance_type='COLLECTION';instance.instance_collection=col
    scene.collection.objects.link(instance);instance.location=(x,y,0)
    font=bpy.data.curves.new(label+' label','FONT');font.body=label;font.size=.24;font.align_x='CENTER';font.space_character=1.2
    obj=bpy.data.objects.new(label+' label',font);scene.collection.objects.link(obj);obj.location=(x,y-1.72,.01);obj.rotation_euler.z=.48

floor_mat=bpy.data.materials.new('Collection • floor');floor_mat.diffuse_color=(.13,.16,.20,1);floor_mat.use_nodes=True
p=next(n for n in floor_mat.node_tree.nodes if n.type=='BSDF_PRINCIPLED');p.inputs['Base Color'].default_value=(.13,.16,.20,1);p.inputs['Roughness'].default_value=.52
bpy.ops.mesh.primitive_plane_add(size=200);floor=bpy.context.object;floor.name='Collection studio floor';floor.data.materials.append(floor_mat)
world=bpy.data.worlds.new('Collection studio world');scene.world=world;world.use_nodes=True
bg=next(n for n in world.node_tree.nodes if n.type=='BACKGROUND');bg.inputs[0].default_value=(.28,.32,.40,1);bg.inputs[1].default_value=.65
for name,loc,power,size in [('Softbox',(1,-4,13),4200,10),('Rim',(-6,8,10),5200,9),('Fill',(9,1,8),3500,8)]:
    d=bpy.data.lights.new(name,'AREA');d.energy=power;d.size=size
    obj=bpy.data.objects.new(name,d);scene.collection.objects.link(obj);obj.location=loc;obj.rotation_euler=(Vector((0,0,0))-obj.location).to_track_quat('-Z','Y').to_euler()
d=bpy.data.cameras.new('Collection camera');cam=bpy.data.objects.new('Collection camera',d);scene.collection.objects.link(cam)
cam.location=(12,-22,21);target=Vector((0,.2,.25));cam.rotation_euler=(target-cam.location).to_track_quat('-Z','Y').to_euler();d.type='ORTHO';d.ortho_scale=20.2;scene.camera=cam
scene.render.engine='CYCLES';scene.cycles.samples=24;scene.cycles.use_denoising=True
try:
    pref=bpy.context.preferences.addons['cycles'].preferences;pref.compute_device_type='OPTIX';pref.get_devices()
    for device in pref.devices:device.use=device.type!='CPU'
    if any(d.use for d in pref.devices):scene.cycles.device='GPU'
except Exception:pass
scene.render.resolution_x=2000;scene.render.resolution_y=1400;scene.render.resolution_percentage=100
scene.view_settings.view_transform='AgX';scene.render.image_settings.file_format='PNG';scene.render.filepath=str(ROOT/'renders/vehicles/collection.png')
bpy.ops.render.render(write_still=True)
for area in bpy.context.screen.areas:
    if area.type=='VIEW_3D':
        area.spaces.active.region_3d.view_distance=23
        area.spaces.active.region_3d.view_location=target
        area.spaces.active.region_3d.view_rotation=cam.rotation_euler.to_quaternion()
bpy.data.libraries.write(str(ROOT/'assets/vehicles/porsche-collection.blend'),{scene},fake_user=True)
result={'blend':str(ROOT/'assets/vehicles/porsche-collection.blend'),'render':scene.render.filepath,'vehicles':5}
