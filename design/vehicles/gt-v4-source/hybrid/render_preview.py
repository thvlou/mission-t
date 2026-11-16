# blender --factory-startup -b -P render_preview.py -- <game.glb> <out dir> <repo> [samples]
# Picker previews for a game GLB the way blender/vertigo_v3.py render_views() makes them: its studio() lights and
# world, its sheet_look() finish (flake, lit lamps, dark shell inside), the GT's fitted cameras (blender/v3_fit),
# lens fitted until the box spans 88% of the frame. tools/make-thumbs.py then lays them on the backdrop.
import bpy, sys, os, ast, math, json
from mathutils import Vector
from bpy_extras.object_utils import world_to_camera_view

glb, out_dir, repo = sys.argv[sys.argv.index('--') + 1:][:3]
samples = int(sys.argv[sys.argv.index('--') + 4]) if len(sys.argv) > sys.argv.index('--') + 4 else 160
sc = bpy.context.scene
for o in list(bpy.data.objects): bpy.data.objects.remove(o, do_unlink=True)
bpy.ops.import_scene.gltf(filepath=glb)
meshes = [o for o in sc.objects if o.type == 'MESH']


def grab(path, names):
    src = open(path, encoding='utf-8').read()
    return '\n\n'.join(ast.get_source_segment(src, n) for n in ast.parse(src).body if isinstance(n, ast.FunctionDef) and n.name in names)


g = {'bpy': bpy, 'Vector': Vector, 'math': math, 'os': os}
exec(grab(os.path.join(repo, 'blender', 'vertigo_v3.py'), {'studio', 'bsdf'}), g)
# studio() takes the floor material from F['material'] unless it exists: make it here with the same values
fm = bpy.data.materials.new('V3 Floor'); fm.use_nodes = True
p = next(n for n in fm.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
p.inputs['Base Color'].default_value = (0.28, 0.275, 0.27, 1); p.inputs['Roughness'].default_value = 0.55
if sc.world is None: sc.world = bpy.data.worlds.new('World')
g['studio']()
sc.cycles.device = 'CPU'
sc.cycles.samples = samples


def bsdf(m): return next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')


# ---- sheet_look(): flake + glassy clearcoat on the paint, dark inside of the shell, lit lamps
paint = bpy.data.materials['GT Paint']
nt = paint.node_tree; pp = bsdf(paint); out = next(n for n in nt.nodes if n.type == 'OUTPUT_MATERIAL')
tex = nt.nodes.new('ShaderNodeTexNoise'); tex.inputs['Scale'].default_value = 2500.0; tex.inputs['Detail'].default_value = 0.0
bump = nt.nodes.new('ShaderNodeBump'); bump.inputs['Strength'].default_value = 0.12
nt.links.new(tex.outputs['Fac'], bump.inputs['Height']); nt.links.new(bump.outputs['Normal'], pp.inputs['Normal'])
pp.inputs['Coat Weight'].default_value = max(pp.inputs['Coat Weight'].default_value, 1.0)
pp.inputs['Coat Roughness'].default_value = 0.012
geo = nt.nodes.new('ShaderNodeNewGeometry'); dark = nt.nodes.new('ShaderNodeBsdfDiffuse')
dark.inputs['Color'].default_value = (0.012, 0.012, 0.013, 1)
mix = nt.nodes.new('ShaderNodeMixShader')
nt.links.new(geo.outputs['Backfacing'], mix.inputs[0]); nt.links.new(pp.outputs[0], mix.inputs[1])
nt.links.new(dark.outputs[0], mix.inputs[2]); nt.links.new(mix.outputs[0], out.inputs['Surface'])
for name, k, col in (('HeadLamp LED', 14.0, (1.0, 0.97, 0.92, 1)), ('TailLamp', 9.0, (1.0, 0.02, 0.02, 1)),
                     ('CenterBrakeLamp', 5.0, (1.0, 0.02, 0.02, 1))):
    m = bpy.data.materials.get(name)
    if not m: print('NO MATERIAL', name); continue
    q = bsdf(m); q.inputs['Emission Color'].default_value = col; q.inputs['Emission Strength'].default_value = k

# ---- cameras
cam = bpy.data.objects.new('Camera', bpy.data.cameras.new('Camera')); sc.collection.objects.link(cam); sc.camera = cam
pts = [o.matrix_world @ Vector(c) for o in meshes for c in o.bound_box]
lo = Vector((min(p.x for p in pts), min(p.y for p in pts), min(p.z for p in pts)))
hi = Vector((max(p.x for p in pts), max(p.y for p in pts), max(p.z for p in pts)))
centre = (lo + hi) / 2
corners = [Vector((x, y, z)) for x in (lo.x, hi.x) for y in (lo.y, hi.y) for z in (lo.z, hi.z)]
fitted = json.load(open(os.path.join(repo, 'blender', 'v3_fit', 'vertigo-gt.json')))['cams']
print('BOX', tuple(round(v, 3) for v in lo), tuple(round(v, 3) for v in hi))


def look(loc, target):
    cam.location = loc; cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


def spread():
    bpy.context.view_layer.update()
    uv = [world_to_camera_view(sc, cam, p) for p in corners]
    return uv, max(max(p.x for p in uv) - min(p.x for p in uv), (max(p.y for p in uv) - min(p.y for p in uv)) * 0.97)


def centre_shift(rw, rh):
    cam.data.shift_x = cam.data.shift_y = 0.0
    uv, _ = spread()
    cam.data.shift_x = (max(p.x for p in uv) + min(p.x for p in uv)) / 2 - 0.5
    cam.data.shift_y = ((max(p.y for p in uv) + min(p.y for p in uv)) / 2 - 0.5) * rh / rw


# the softboxes' thin strips drew bright loops in the curved glass (read as a white frame in the windshield): the
# lights stay out of reflections; the world's glossy studio still lays its panels on paint and glass
for o in sc.objects:
    if o.type == 'LIGHT': o.visible_glossy = False
os.makedirs(out_dir, exist_ok=True)
for view in ('front', 'rear', 'side'):
    cam.data.type = 'PERSP'; cam.data.sensor_fit = 'HORIZONTAL'; cam.data.sensor_width = 36
    cam.data.shift_x = cam.data.shift_y = 0.0
    if view in fitted:                                   # the fitted product camera, zoomed to frame the car
        rw, rh = 900, 520
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rw, rh, 100
        c = fitted[view]; look(Vector(c[:3]), Vector(c[3:6])); cam.data.lens = 50.0
        for _ in range(8):
            _, s = spread(); cam.data.lens *= 0.88 / s
    else:                                                # side: near-orthographic 200 mm, pulled until 88%
        rw, rh = 1800, 560
        sc.render.resolution_x, sc.render.resolution_y, sc.render.resolution_percentage = rw, rh, 100
        cam.data.lens = 200; target = centre + Vector((0, 0, -0.08)); dist = 8.0
        for _ in range(12):
            pos = centre + Vector((0, 1, 0)) * dist; pos.z = 0.62; look(pos, target)
            _, s = spread(); dist *= s / 0.88
    centre_shift(rw, rh)
    sc.render.filepath = os.path.join(out_dir, f'vertigo-gt_{view}.png')
    bpy.ops.render.render(write_still=True)
    print('RENDERED', sc.render.filepath, flush=True)
print('DONE')
