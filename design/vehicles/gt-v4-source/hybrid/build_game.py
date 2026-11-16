# blender -b <gt-v4-parts.blend> -P build_game.py -- <out.glb> [body decimate ratio]
# Packs the GT v4 working file into the layout the game loads (src/car-model.js, src/vehicle-rig.js, src/rover.js):
#   vertigo-gt_Body          the detail body (build_detail/build_bake), material "GT4 Paint" (tuned as paint by the game),
#                            decimated for the game (default ratio 0.35, about 65k triangles)
#   wheelwell_FL/FR/RL/RR    black arch liners, part of the body (not matched by /^wheel_[FR][LR]/); trimmed at the
#                            road, since the game stands the model on its lowest point
#   wheel_FL/FR/RL/RR        one node each, origin at the hub, no rotation, no scale, no children:
#                            the game spins it about its local Z (glTF) = the axle, and plants it on a hub group
#   caliper_FL/FR/RL/RR      origin at the same hub; the game re-parents it onto the hub, so it steers but never spins
#   parts (build_parts.py)   window panes (glass_*), mirrors, lamps (TailLamp / CenterBrakeLamp / ReverseLamp materials drive the rig's lamps),
#                            exhaust_N lip rings (the boost flames sit at their centres), fins, splitter, louvres
# Everything else in the working file (AI reference, voxel copies, blueprints) stays out. GLB is +Y up, metres, Draco.
# Prints a check of every rule above and fails if one is broken.
import bpy, sys, os, math, re
from mathutils import Vector

args = sys.argv[sys.argv.index('--') + 1:]
out = args[0]
RATIO = float(args[1]) if len(args) > 1 else 0.35
scene = bpy.context.scene


def activate(o):
    for x in scene.objects: x.select_set(x == o)
    bpy.context.view_layer.objects.active = o


def decimate(o, ratio):
    activate(o)
    m = o.modifiers.new('decimate', 'DECIMATE'); m.ratio = ratio; m.use_collapse_triangulate = True
    bpy.ops.object.modifier_apply(modifier=m.name)


body = bpy.data.objects['body_detail']
body.name = body.data.name = 'vertigo-gt_Body'
assert body.data.materials[0].name == 'GT4 Paint'
decimate(body, RATIO)
parts = [o for o in scene.objects if o.get('gt4_part')]
for o in parts:
    if o.name.startswith(('lamps_rear_', 'headlamp_')): decimate(o, 0.5)   # dense decal grids, flat enough to halve
    if o.name.startswith('glass_'): decimate(o, 0.3)                       # window panes: smooth, gently curved
for o in scene.objects:
    if o.name.startswith('wheelwell_'):
        floor = -o.location.z + 0.004
        for v in o.data.vertices: v.co.z = max(v.co.z, floor)

keep = [body] + parts + [o for o in scene.objects if re.match(r'^(wheel_|caliper_|wheelwell_)[FR][LR]$', o.name)]
for o in scene.objects:
    o.hide_set(False); o.hide_viewport = False
    o.select_set(o in keep)
bpy.context.view_layer.objects.active = body

problems = []
wheels = [o for o in keep if re.match(r'^wheel_[FR][LR]$', o.name)]
for w in wheels:
    if w.rotation_euler.to_quaternion().angle > 1e-6: problems.append(f'{w.name} has a rotation')
    if (w.scale - Vector((1, 1, 1))).length > 1e-6: problems.append(f'{w.name} has a scale')
    if w.children: problems.append(f'{w.name} has children')
    if w.parent: problems.append(f'{w.name} has a parent')
    # the hub is the origin: the tyre must be centred on it (axle along Blender Y)
    vs = [v.co for v in w.data.vertices]
    cx = (max(v.x for v in vs) + min(v.x for v in vs)) / 2
    cz = (max(v.z for v in vs) + min(v.z for v in vs)) / 2
    if abs(cx) > 1e-3 or abs(cz) > 1e-3: problems.append(f'{w.name} is not centred on its origin ({cx:.4f}, {cz:.4f})')
    r = max(math.hypot(v.x, v.z) for v in vs)
    if abs(w.location.z - r) > 2e-3: problems.append(f'{w.name} does not touch the ground (hub z {w.location.z:.3f}, radius {r:.3f})')
    c = bpy.data.objects.get(w.name.replace('wheel_', 'caliper_'))
    if not c: problems.append(f'{w.name} has no caliper')
    elif (c.location - w.location).length > 1e-6: problems.append(f'{c.name} origin is not at the hub')
    print('CHECK', w.name, 'hub', tuple(round(x, 3) for x in w.location), 'radius', round(r, 4), 'tris',
          sum(len(p.vertices) - 2 for p in w.data.polygons))
for o in keep:
    if o.name.startswith('wheelwell_') and re.match(r'^wheel_[FR][LR]', o.name, re.I): problems.append(f'{o.name} matches the wheel pattern')
    if o is not body and re.match(r'^wheel_[FR][LR]', o.name, re.I) and o not in wheels: problems.append(f'{o.name} matches the wheel pattern')
if len(wheels) != 4: problems.append(f'{len(wheels)} wheels')
lows = {o.name: min((o.matrix_world @ v.co).z for v in o.data.vertices) for o in keep}
for name, z in lows.items():
    if z < -1e-4: problems.append(f'{name} goes below the road ({z:.3f})')
mats = {m.name for o in keep for m in o.data.materials if m}
for need in ('TailLamp', 'CenterBrakeLamp', 'ReverseLamp'):
    if need not in mats: problems.append(f'no {need} material')
lips = [o.name for o in parts if re.search(r'exhaust_\d+$', o.name)]
if not lips: problems.append('no exhaust_N lips')
if problems:
    print('PROBLEMS', problems); raise SystemExit(1)

os.makedirs(os.path.dirname(out), exist_ok=True)
bpy.ops.export_scene.gltf(filepath=out, use_selection=True, export_apply=True, export_yup=True,
                          export_cameras=False, export_lights=False, export_extras=False,
                          export_image_format='JPEG', export_jpeg_quality=90,
                          export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6)
tris = 0
dg = bpy.context.evaluated_depsgraph_get()
for o in keep:
    me = o.evaluated_get(dg).to_mesh()
    tris += sum(len(p.vertices) - 2 for p in me.polygons)
xs = [(o.matrix_world @ v.co).x for o in keep for v in o.data.vertices]
print('LENGTH', round(max(xs) - min(xs), 4), 'exhaust lips', lips)
print('EXPORTED', out, os.path.getsize(out), 'bytes,', len(keep), 'objects,', tris, 'triangles')
