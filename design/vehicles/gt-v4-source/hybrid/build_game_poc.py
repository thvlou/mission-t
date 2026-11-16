# blender -b <gt-v4-wheels.blend> -P build_game_poc.py -- <car poc blend> <out.glb> [body decimate ratio]
# Packs the carved GT (build_front_poc.py on the surfaced body, NOTES 19) into the layout the game loads, the same rules
# as build_game.py (src/car-model.js, src/vehicle-rig.js, src/rover.js):
#   vertigo-gt_Body        the carved body with every small part joined in (lamps, grilles, louvres, mirrors, wipers,
#                          fins): one mesh, one draw call per material. Decimated for the game.
#   wheel_* / caliper_* / wheelwell_*   from gt-v4-wheels.blend, unchanged (hub origins, axle along Blender Y)
#   exhaust_1 / exhaust_2  the two polished tips; the boost flames sit at their centres
# Material names drive the game: "paint" is tuned as clear-coated paint, "glass" as glass, ^TailLamp / ^CenterBrakeLamp
# / ^ReverseLamp are switched by the lamp rig, "headlamp" glows brighter. The wheel-arch walls are painted dark (wheel
# well). Fails, like build_game.py, when a rule is broken. GLB is +Y up, metres, Draco.
import bpy, bmesh, sys, os, math, re
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index('--') + 1:]
poc, out = args[:2]
RATIO = float(args[2]) if len(args) > 2 else 1.0
scene = bpy.context.scene
AXLE_X, TYRE_R, ARCH = 1.435, 0.40, {1: 0.43, -1: 0.42}


def activate(o):
    for x in scene.objects: x.select_set(x == o)
    bpy.context.view_layer.objects.active = o


def apply_all(o):
    activate(o)
    for m in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)


def decimate(o, ratio):
    activate(o)
    m = o.modifiers.new('decimate', 'DECIMATE'); m.ratio = ratio; m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=m.name)


# ---- scene: wheels, calipers, liners from the wheel file; everything else of it out
for o in list(scene.objects):
    if not re.match(r'^(wheel_|caliper_|wheelwell_)[FR][LR]$', o.name): bpy.data.objects.remove(o, do_unlink=True)
with bpy.data.libraries.load(poc) as (src, dst):
    dst.objects = list(src.objects)
car = [o for o in dst.objects if o is not None and o.type == 'MESH']
for o in car: scene.collection.objects.link(o); o.hide_render = False; o.hide_viewport = False
body = bpy.data.objects['body_front']
for o in car: apply_all(o)

# ---- materials the game understands
def rename(old, new):
    m = bpy.data.materials.get(old)
    if m: m.name = new
    return m


rename('GT LED', 'HeadLamp LED')
rename('GT TailLamp', 'TailLamp')
rename('GT Lens', 'GT HeadLamp Glass')
rename('GT Tail Lens', 'GT TailLamp Glass Lens')        # not ^TailLamp: the rig must not switch the lens itself
for name in ('GT HeadLamp Glass', 'GT TailLamp Glass Lens'):
    m = bpy.data.materials.get(name)
    if m and hasattr(m, 'surface_render_method'): m.surface_render_method = 'BLENDED'
# the centre brake lamp is the body's own tail-lamp slot (the CHMSL pocket): a copy named for the rig
tl = bpy.data.materials['TailLamp']
cb = tl.copy(); cb.name = 'CenterBrakeLamp'
for i, m in enumerate(body.data.materials):
    if m == tl: body.data.materials[i] = cb
gap = bpy.data.materials['GT Gap']

# ---- wheel-arch walls dark (the cylinder cuts were painted)
gi = list(body.data.materials).index(gap)
dark = 0
for p in body.data.polygons:
    c = p.center
    for side in (1, -1):
        dx, dz = c.x - side * AXLE_X, c.z - TYRE_R; r = math.hypot(dx, dz)
        n = p.normal; radial = (n.x * dx + n.z * dz) / max(r, 1e-6)   # the wall faces the axle: normal points in
        if abs(r - ARCH[side]) < 0.004 and abs(c.y) > 0.44 and abs(n.y) < 0.3 and radial < -0.7 and p.material_index == 0:
            p.material_index = gi; dark += 1
print('ARCH faces dark', dark)

# ---- reverse lamps: two small plates in the diffuser face (A4 columns 420 .. 470, rows 640 .. 655)
bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
rev = bpy.data.materials.new('ReverseLamp'); rev.use_nodes = True
b = next(n for n in rev.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
b.inputs['Base Color'].default_value = (0.9, 0.92, 0.95, 1); b.inputs['Roughness'].default_value = 0.2
b.inputs['Emission Color'].default_value = (0.9, 0.95, 1.0, 1); b.inputs['Emission Strength'].default_value = 0.0
for side in (1, -1):
    y0, y1 = side * (767.5 - 470) / 691, side * (767.5 - 420) / 691
    z0, z1 = (865 - 655) / 573, (865 - 640) / 573
    yc, zc = (y0 + y1) / 2, (z0 + z1) / 2
    hit = bvh.ray_cast(Vector((-4.0, yc, zc)), Vector((1, 0, 0)))
    x = (hit[0].x if hit[0] is not None else -2.3) - 0.004
    bm = bmesh.new()
    vs = [bm.verts.new((x, y, z)) for y, z in ((y0, z0), (y1, z0), (y1, z1), (y0, z1))]
    f = bm.faces.new(vs if side > 0 else vs[::-1])
    me = bpy.data.meshes.new('reverse'); bm.to_mesh(me); bm.free(); me.materials.append(rev)
    o = bpy.data.objects.new(f'reverse_{side}', me); scene.collection.objects.link(o); car.append(o)

# ---- exhaust tips: exhaust_1 / exhaust_2 (lips, flames at their centres); inner pipes not matching the pattern
tips = sorted([o for o in car if o.name.startswith('exhaust_tip_')], key=lambda o: o.location.y)
for k, o in enumerate(tips, 1): o.name = f'exhaust_{k}'
for o in car:
    if o.name.startswith('exhaust_pipe_'): o.name = 'exhaust_inner_' + ('L' if o.location.y > 0 else 'R')

# ---- body: decimate, then join every small part into it (one mesh; one draw call per material)
# RATIO 1.0 (the game build of NOTES 19-7, carved on a one-level body): no collapse, which smeared the grooves, only a
# planar dissolve of the boolean's coplanar triangle fans (2 degrees, never across materials or sharp edges)
if RATIO < 1.0:
    decimate(body, RATIO)
else:
    activate(body)
    m = body.modifiers.new('planar', 'DECIMATE'); m.decimate_type = 'DISSOLVE'; m.angle_limit = math.radians(2.0); m.delimit = {'MATERIAL', 'SHARP'}
    bpy.ops.object.modifier_apply(modifier=m.name)
for o in car:
    if o is not body and len(o.data.polygons) > 4000: decimate(o, 0.3)        # grilles, mirror heads, light bar
joinees = [o for o in car if o is not body and not re.match(r'^exhaust_\d+$', o.name)]
for x in scene.objects: x.select_set(x in joinees or x is body)
bpy.context.view_layer.objects.active = body
bpy.ops.object.join()
body.name = body.data.name = 'vertigo-gt_Body'
for o in scene.objects:
    if o.name.startswith('wheelwell_'):
        floor = -o.location.z + 0.004
        for v in o.data.vertices: v.co.z = max(v.co.z, floor)

keep = [o for o in scene.objects if o.type == 'MESH']
for o in scene.objects: o.select_set(o in keep)

# ---- the checks of build_game.py
problems = []
wheels = [o for o in keep if re.match(r'^wheel_[FR][LR]$', o.name)]
for w in wheels:
    if w.rotation_euler.to_quaternion().angle > 1e-6: problems.append(f'{w.name} has a rotation')
    if (w.scale - Vector((1, 1, 1))).length > 1e-6: problems.append(f'{w.name} has a scale')
    if w.children or w.parent: problems.append(f'{w.name} has a parent or children')
    vs = [v.co for v in w.data.vertices]
    r = max(math.hypot(v.x, v.z) for v in vs)
    if abs(w.location.z - r) > 2e-3: problems.append(f'{w.name} does not touch the ground')
    c = bpy.data.objects.get(w.name.replace('wheel_', 'caliper_'))
    if not c or (c.location - w.location).length > 1e-6: problems.append(f'{w.name} caliper missing or off the hub')
if len(wheels) != 4: problems.append(f'{len(wheels)} wheels')
for o in keep:
    if o not in wheels and re.match(r'^wheel_[FR][LR]', o.name, re.I): problems.append(f'{o.name} matches the wheel pattern')
    z = min((o.matrix_world @ v.co).z for v in o.data.vertices)
    if z < -1e-4: problems.append(f'{o.name} goes below the road ({z:.3f})')
mats = {m.name for o in keep for m in o.data.materials if m}
for need in ('TailLamp', 'CenterBrakeLamp', 'ReverseLamp', 'GT Paint'):
    if need not in mats: problems.append(f'no {need} material')
lips = [o.name for o in keep if re.search(r'exhaust_\d+$', o.name)]
if len(lips) != 2: problems.append(f'exhaust lips {lips}')
if problems:
    print('PROBLEMS', problems); raise SystemExit(1)

os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=out, use_selection=True, export_apply=True, export_yup=True,
                          export_cameras=False, export_lights=False, export_extras=False,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
tris = sum(sum(len(p.vertices) - 2 for p in o.data.polygons) for o in keep)
xs = [(o.matrix_world @ v.co).x for o in keep for v in o.data.vertices]
print('MATERIALS', sorted(mats))
print('LENGTH', round(max(xs) - min(xs), 4), 'lips', lips)
print('EXPORTED', out, os.path.getsize(out), 'bytes,', len(keep), 'objects,', tris, 'triangles')
