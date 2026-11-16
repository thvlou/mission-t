# blender -b <gt-v4-wheels.blend> -P zebra.py -- <body blend> <body object> <out png prefix>
# Surface check: the body in mirror-black paint under a striped sky, with the wheels in place. Ripples bend the
# stripes; fender clearance shows where tyres meet arches. Writes <prefix>_f34.png, _r34.png, _front.png, _side.png.
import bpy, sys, math
from mathutils import Vector

body_blend, body_name, prefix = sys.argv[sys.argv.index('--') + 1:][:3]
scene = bpy.context.scene
with bpy.data.libraries.load(body_blend) as (src, dst):
    dst.objects = [body_name]
body = dst.objects[0]; scene.collection.objects.link(body)
body.hide_render = False
for o in scene.objects:
    if o.name in ('body_retopo', 'body_src', 'ref_hunyuan21', 'body_smooth') or o.type == 'EMPTY': o.hide_render = True
m = bpy.data.materials.new('zebra'); m.use_nodes = True
b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
b.inputs['Base Color'].default_value = (0.01, 0.01, 0.01, 1); b.inputs['Roughness'].default_value = 0.03
b.inputs['Metallic'].default_value = 1.0
body.data.materials.clear(); body.data.materials.append(m)
for p in body.data.polygons: p.use_smooth = True

world = bpy.data.worlds.new('stripes'); scene.world = world; world.use_nodes = True
nt = world.node_tree; bg = next(n for n in nt.nodes if n.type == 'BACKGROUND')
tc = nt.nodes.new('ShaderNodeTexCoord'); sep = nt.nodes.new('ShaderNodeSeparateXYZ')
nt.links.new(tc.outputs['Generated'], sep.inputs[0])
mul = nt.nodes.new('ShaderNodeMath'); mul.operation = 'MULTIPLY'; mul.inputs[1].default_value = 26
nt.links.new(sep.outputs['Z'], mul.inputs[0])
sn = nt.nodes.new('ShaderNodeMath'); sn.operation = 'SINE'; nt.links.new(mul.outputs[0], sn.inputs[0])
gt = nt.nodes.new('ShaderNodeMath'); gt.operation = 'GREATER_THAN'; gt.inputs[1].default_value = 0.0
nt.links.new(sn.outputs[0], gt.inputs[0])
nt.links.new(gt.outputs[0], bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.0
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = False
scene.view_settings.view_transform = 'Standard'
scene.render.image_settings.file_format = 'PNG'
cam = bpy.data.objects.new('zcam', bpy.data.cameras.new('zcam')); scene.collection.objects.link(cam); scene.camera = cam


def shoot(tag, loc, look, ortho=None, lens=70):
    scene.render.resolution_x, scene.render.resolution_y = 1280, 720
    cam.location = loc; cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    scene.render.filepath = f'{prefix}_{tag}.png'; bpy.ops.render.render(write_still=True)


shoot('f34', (6.6, 6.0, 2.0), (0, 0, 0.5))
shoot('r34', (-6.6, -6.0, 2.0), (0, 0, 0.5))
shoot('front', (20, 0, 0.62), (0, 0, 0.62), ortho=2.6)
shoot('side', (0, 20, 0.62), (0, 0, 0.62), ortho=5.2)
print('DONE')
