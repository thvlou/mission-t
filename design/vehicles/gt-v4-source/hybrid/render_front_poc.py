# blender -b <gt-v4-wheels.blend> -P render_front_poc.py -- <poc blend> <out prefix>
# Review renders of the front-quarter proof of concept: EEVEE studio (front three-quarter, front, side-front close),
# a clay matcap and a matcap with the mesh wireframe (Workbench), all framed on the front of the car.
import bpy, sys, os, math
from mathutils import Vector

poc, pre = sys.argv[sys.argv.index('--') + 1:][:2]
scene = bpy.context.scene
for o in scene.objects:
    if o.name.startswith(('body_', 'ref_', 'bp_')): o.hide_render = True
with bpy.data.libraries.load(poc) as (src, dst):
    dst.objects = [n for n in src.objects]
for o in dst.objects:
    if o is not None: scene.collection.objects.link(o); o.hide_render = False
body = bpy.data.objects['body_front']
scene.render.image_settings.file_format = 'PNG'
cam = bpy.data.objects.new('cam', bpy.data.cameras.new('cam')); scene.collection.objects.link(cam); scene.camera = cam
VIEWS = {'f34': ((5.0, 3.1, 1.35), (1.55, 0.25, 0.55), 45), 'front': ((6.5, 0.0, 0.75), (2.0, 0.0, 0.58), 55),
         'side': ((1.9, 4.2, 0.85), (1.75, 0.4, 0.6), 40), 'lamp': ((3.6, 1.6, 0.85), (2.2, 0.62, 0.62), 70),
         'r34': ((-5.2, 3.2, 1.45), (-1.5, 0.2, 0.6), 45), 'rear': ((-6.8, 0.0, 0.8), (-2.0, 0.0, 0.6), 55),
         'fullside': ((0.0, 9.0, 0.75), (0.0, 0.0, 0.6), 50), 'tail': ((-3.7, 1.5, 0.95), (-2.25, 0.55, 0.62), 60),
         'mirror': ((1.55, 2.0, 1.1), (0.62, 0.93, 0.87), 75),
         'arch34': ((3.1, 2.6, 1.05), (1.43, 0.85, 0.48), 50), 'archside': ((1.43, 4.2, 0.5), (1.43, 0.8, 0.48), 65)}
SET = os.environ.get('POC_SET', 'front')                  # 'car': side and rear views as well
STUDIO = ('f34', 'front', 'side', 'lamp') if SET == 'front' else ('f34', 'r34', 'rear', 'fullside', 'tail', 'front', 'mirror')
CLAY = ('f34', 'lamp') if SET == 'front' else ('f34', 'r34', 'fullside')
if os.environ.get('POC_ONLY'):                          # a quick check of a few studio views only
    STUDIO = tuple(os.environ['POC_ONLY'].split(',')); CLAY = ()


def shoot(tag, view, res=(1600, 1000)):
    loc, look, lens = VIEWS[view]
    scene.render.resolution_x, scene.render.resolution_y = res
    cam.location = loc; cam.rotation_euler = (Vector(look) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
    cam.data.lens = lens
    scene.render.filepath = f'{pre}_{tag}_{view}.png'
    bpy.ops.render.render(write_still=True)


# ---- studio (EEVEE, studio HDRI + soft areas)
scene.render.engine = 'BLENDER_EEVEE'; scene.render.film_transparent = False
scene.view_settings.view_transform = 'AgX'; scene.view_settings.look = 'AgX - Medium High Contrast'
hdri = os.path.join(os.path.dirname(bpy.app.binary_path), bpy.app.version_string[:3], 'datafiles', 'studiolights', 'world', 'studio.exr')
world = bpy.data.worlds.new('studio'); scene.world = world; world.use_nodes = True
nt = world.node_tree; bg = next(n for n in nt.nodes if n.type == 'BACKGROUND')
env = nt.nodes.new('ShaderNodeTexEnvironment'); env.image = bpy.data.images.load(hdri)
nt.links.new(env.outputs['Color'], bg.inputs['Color']); bg.inputs['Strength'].default_value = 1.2
scene.eevee.use_raytracing = os.environ.get('POC_RT', '1') == '1'; scene.eevee.ray_tracing_options.resolution_scale = '1'   # POC_RT=0 when the GPU is shared
for name, loc, e, size in (('key', (5, 5, 6), 1500, 4), ('fill', (6, -3, 3), 500, 3), ('top', (1.5, 0, 6), 900, 5), ('back', (-6, 3, 4), 1200, 4)):
    l = bpy.data.lights.new(name, 'AREA'); l.energy = e; l.size = size
    o = bpy.data.objects.new(name, l); scene.collection.objects.link(o); o.location = loc
    o.rotation_euler = (Vector((1.5, 0, 0.5)) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()
bpy.ops.mesh.primitive_plane_add(size=40, location=(0, 0, 0)); floor = bpy.context.active_object
fm = bpy.data.materials.new('floor'); fm.use_nodes = True
fb = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED'); fb.inputs['Base Color'].default_value = (0.08, 0.085, 0.09, 1); fb.inputs['Roughness'].default_value = 0.45
floor.data.materials.append(fm)
if os.environ.get('POC_ENGINE') == 'CYCLES':            # CPU path tracing when EEVEE cannot get the GPU
    scene.render.engine = 'CYCLES'; scene.cycles.device = 'CPU'; scene.cycles.samples = 48
    scene.cycles.use_denoising = True
for v in STUDIO: shoot('studio', v)

# ---- clay matcap and wireframe (Workbench)
scene.render.engine = 'BLENDER_WORKBENCH'
sh = scene.display.shading
sh.light = 'MATCAP'; sh.studio_light = 'hard_surface_grey.exr'; sh.color_type = 'MATERIAL'; sh.show_cavity = False
scene.world.color = (0.16, 0.17, 0.18)
floor.hide_render = True
for m in bpy.data.materials: m.diffuse_color = (0.8, 0.8, 0.8, 1)
for v in CLAY: shoot('clay', v)
# wireframe overlay: a copy of the body's front with a thin wireframe modifier, drawn black on the clay
bm_src = body
wire = body.copy(); wire.data = body.data.copy(); wire.name = 'wire'; scene.collection.objects.link(wire)
import bmesh
bm = bmesh.new(); bm.from_mesh(wire.data)
bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.calc_center_median().x < 1.0], context='FACES')
bm.to_mesh(wire.data); bm.free()
wm = bpy.data.materials.new('wire'); wm.diffuse_color = (0.02, 0.02, 0.02, 1)
wire.data.materials.clear(); wire.data.materials.append(wm)
wf = wire.modifiers.new('wf', 'WIREFRAME'); wf.thickness = 0.0009; wf.use_replace = True; wf.offset = 1.0
for v in (('f34', 'lamp') if SET == 'front' else ()): shoot('wire', v)
print('DONE')
