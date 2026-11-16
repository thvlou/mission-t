# blender -b <gt-v4-wheels.blend> -P render_wheels.py -- <out_dir> <tag>
# EEVEE studio renders of the wheel set on the volume base: wheel face-on (vs C3), left side (vs B2),
# front three-quarter (vs B5), plus a wheel three-quarter close-up. Writes <tag>_wheel.png, _wheel34.png, _side.png, _f34.png.
import bpy, sys, os, math
from mathutils import Vector

out, tag = sys.argv[sys.argv.index('--') + 1:][:2]
scene = bpy.context.scene
scene.render.engine = 'BLENDER_EEVEE'
scene.render.film_transparent = True
scene.view_settings.view_transform = 'AgX'
scene.render.image_settings.file_format = 'PNG'
scene.render.image_settings.color_mode = 'RGBA'
for name in ('bp_side', 'bp_top'):
    if name in bpy.data.objects: bpy.data.objects[name].hide_render = True

# studio HDRI bundled with Blender for reflections (metal reads as metal), plus soft area lights for shape
hdri = os.path.join(os.path.dirname(bpy.app.binary_path), bpy.app.version_string[:3], 'datafiles', 'studiolights', 'world', 'studio.exr')
world = bpy.data.worlds.new('studio'); scene.world = world; world.use_nodes = True
nt = world.node_tree
bg = next(n for n in nt.nodes if n.type == 'BACKGROUND')
env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(hdri)
mp = nt.nodes.new('ShaderNodeMapping'); tc = nt.nodes.new('ShaderNodeTexCoord')
mp.inputs['Rotation'].default_value = (0, 0, math.radians(120))
nt.links.new(tc.outputs['Generated'], mp.inputs['Vector']); nt.links.new(mp.outputs['Vector'], env.inputs['Vector'])
nt.links.new(env.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.6
scene.eevee.use_raytracing = True
scene.eevee.ray_tracing_options.resolution_scale = '1'
scene.eevee.use_fast_gi = True
scene.view_settings.look = 'AgX - Medium High Contrast'


def light(name, kind, loc, energy, size=3.0):
    l = bpy.data.lights.new(name, kind); l.energy = energy
    if kind == 'AREA': l.size = size
    o = bpy.data.objects.new(name, l); scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector((0, 0, 0.5)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


light('key', 'AREA', (4, 6, 6), 1800, 4)
light('rim', 'AREA', (-3, 5, 2.5), 900, 2)
light('top', 'AREA', (0, 0, 7), 800, 6)

cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); scene.collection.objects.link(cam); scene.camera = cam


def shoot(path, loc, look, ortho=None, lens=85, res=(1280, 720)):
    scene.render.resolution_x, scene.render.resolution_y = res
    cam.location = loc
    cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    if ortho: cam.data.type = 'ORTHO'; cam.data.ortho_scale = ortho
    else: cam.data.type = 'PERSP'; cam.data.lens = lens
    scene.render.filepath = path
    bpy.ops.render.render(write_still=True)


w = bpy.data.objects['wheel_FL'].location
shoot(os.path.join(out, f'{tag}_wheel.png'), (w.x, w.y + 4, w.z), (w.x, w.y, w.z), ortho=0.86, res=(1024, 1024))
shoot(os.path.join(out, f'{tag}_wheel34.png'), (w.x + 1.1, w.y + 1.7, w.z + 0.3), (w.x, w.y, w.z), lens=85, res=(1024, 1024))
shoot(os.path.join(out, f'{tag}_side.png'), (0, 20, 0.62), (0, 0, 0.62), ortho=5.2)
shoot(os.path.join(out, f'{tag}_f34.png'), (6.6, 6.0, 2.0), (0, 0, 0.5), lens=70)
if len(sys.argv[sys.argv.index('--') + 1:]) > 2:  # 'all': front and rear views too, for the body detail passes
    shoot(os.path.join(out, f'{tag}_front.png'), (20, 0, 0.62), (0, 0, 0.62), ortho=2.6)
    shoot(os.path.join(out, f'{tag}_rear.png'), (-20, 0, 0.62), (0, 0, 0.62), ortho=2.6)
    shoot(os.path.join(out, f'{tag}_r34.png'), (-6.6, -6.0, 2.0), (0, 0, 0.5), lens=70)
print('DONE')
if len(sys.argv[sys.argv.index('--') + 1:]) > 2:  # close-ups for surface checks: greenhouse and mirror from the front left
    shoot(os.path.join(out, f'{tag}_cabin.png'), (3.2, 2.6, 1.9), (0.4, 0.5, 0.95), lens=60)
    shoot(os.path.join(out, f'{tag}_mirror.png'), (1.9, 2.1, 1.25), (0.65, 0.85, 0.85), lens=85)
