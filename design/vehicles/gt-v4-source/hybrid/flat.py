# blender -b <gt-v4-parts.blend> -P flat.py -- <out png prefix> [body]
# Colour check: the body shows its baked albedo unlit (no reflections), so class edges and specks are what they
# are, not glare. Writes <prefix>_f34.png, _r34.png, _front.png, _side.png.
import bpy, sys
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
prefix = args[0]
BODY_ONLY = len(args) > 1 and args[1] == 'body'   # hide wheels, liners and parts: shows holes as background
scene = bpy.context.scene
mat = bpy.data.materials['GT4 Paint']; nt = mat.node_tree
tex = next(n for n in nt.nodes if n.type == 'TEX_IMAGE' and 'albedo' in n.image.name)
out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
em = nt.nodes.new('ShaderNodeEmission'); nt.links.new(tex.outputs['Color'], em.inputs['Color'])
nt.links.new(em.outputs[0], out.inputs['Surface'])
for o in scene.objects:
    if o.name in ('body_src', 'body_smooth', 'ref_hunyuan21') or o.type == 'EMPTY': o.hide_render = True
    if BODY_ONLY and o.name != 'body_detail' and o.type == 'MESH': o.hide_render = True
world = bpy.data.worlds.new('flat'); scene.world = world; world.use_nodes = True
next(n for n in world.node_tree.nodes if n.type == 'BACKGROUND').inputs['Color'].default_value = (0.5, 0.5, 0.5, 1)
scene.render.engine = 'BLENDER_EEVEE'; scene.view_settings.view_transform = 'Standard'
scene.render.film_transparent = False
cam = bpy.data.objects.new('fcam', bpy.data.cameras.new('fcam')); scene.collection.objects.link(cam); scene.camera = cam
scene.render.resolution_x, scene.render.resolution_y = 1280, 720
for tag, loc, ortho in (('f34', (6.6, 6.0, 2.0), None), ('r34', (-6.6, -6.0, 2.0), None),
                        ('front', (20, 0, 0.62), 2.6), ('side', (0, 20, 0.62), 5.2)):
    look = (0, 0, 0.62) if ortho else (0, 0, 0.5)
    cam.location = loc; cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = 70
    scene.render.filepath = f'{prefix}_{tag}.png'; bpy.ops.render.render(write_still=True)
print('DONE')
