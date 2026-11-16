# blender -b -P build_base.py -- <hunyuan21.glb> <out_dir>
# Turns the Hunyuan3D-2.1 mesh into the GT v4 modelling base:
#   ref_hunyuan21  the AI mesh fitted to blueprint A2/A5 (length 4.736, width 2.07, height 1.26, wheel
#                  centres moved onto A2's +-1.435 m), kept as the shrinkwrap/snapping reference
#   body_src       a watertight voxel copy with the four wheel arches cut out (wheels get modelled apart)
#   body_retopo    a clean quad cage (QuadriFlow) shrinkwrapped onto body_src, smoothed by subdivision
#   bp_side/bp_top blueprint A2 and A5 as reference images behind and under the car
# Game axes: nose +X, up +Z, ground z=0, metres. Writes gt-v4-base.blend and body-v1.glb.
import bpy, sys, os, math
import numpy as np
from mathutils import Matrix

glb, out = sys.argv[sys.argv.index('--') + 1:][:2]
BP = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'blueprint')
L, W, H = 4.736, 2.07, 1.26
AXLE_X = 1.435          # A2: wheel centres at +-1.435 m, 0.93 m overhangs front and rear
TRACK_Y = 0.86          # wheel centre |y|
TYRE_R = 0.40           # A2 tyre (0.797 m across)
ARCH_R = {'F': 0.43, 'R': 0.42}   # arch cut radius: the tyre plus 2 cm, plus 1 cm at the front for the steering sweep
ARCH_IN = {'F': 0.45, 'R': 0.55}  # |y| where the cut starts: a steered front tyre's inner corner swings to 0.55
SMOOTH_ITERS = 25       # Laplacian passes that take the AI mesh's ripples out of the shrinkwrap target
VOXEL = 0.012
CAGE_FACES = 6000

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
bpy.ops.import_scene.gltf(filepath=glb)
meshes = [o for o in scene.objects if o.type == 'MESH']
for o in scene.objects:
    o.select_set(o.type == 'MESH')
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
ref = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
for o in list(scene.objects):
    if o != ref: bpy.data.objects.remove(o, do_unlink=True)
ref.name = ref.data.name = 'ref_hunyuan21'
for slot in ref.material_slots: slot.material = None


def get(me):
    a = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', a); return a.reshape(-1, 3)


def put(me, V):
    me.vertices.foreach_set('co', V.ravel()); me.update()


V = get(ref.data)
ext = V.max(0) - V.min(0)
if ext[1] > ext[0]:
    V = V[:, [1, 0, 2]] * [-1, 1, 1]
lo, hi = V.min(0), V.max(0)
V = (V - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) * (L / (hi[0] - lo[0]))
if np.percentile(V[V[:, 0] > L / 2 - 0.6, 2], 95) > np.percentile(V[V[:, 0] < -L / 2 + 0.6, 2], 95):
    V[:, :2] *= -1  # the nose is the lower end; turn it to +X

# where the AI mesh's tyres touch the ground
g = V[(V[:, 2] < 0.04) & (np.abs(V[:, 1]) > 0.4)]
xs = np.sort(g[:, 0])
groups = np.split(xs, np.where(np.diff(xs) > 0.3)[0] + 1)
centres = sorted((grp[0] + grp[-1]) / 2 for grp in groups)
rear_x, front_x = centres[0], centres[-1]
print('AI AXLES', round(rear_x, 3), round(front_x, 3))

# smooth monotone warp along X: ends stay at +-L/2, axles move onto A2 (PCHIP through 4 knots)
src = np.array([-L / 2, rear_x, front_x, L / 2]); dst = np.array([-L / 2, -AXLE_X, AXLE_X, L / 2])


def pchip(x, xk, yk):
    h = np.diff(xk); d = np.diff(yk) / h
    m = np.zeros_like(yk)
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, len(xk) - 1):
        if d[i - 1] * d[i] > 0:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    i = np.clip(np.searchsorted(xk, x) - 1, 0, len(xk) - 2)
    t = (x - xk[i]) / h[i]
    h00, h10, h01, h11 = 2 * t**3 - 3 * t**2 + 1, t**3 - 2 * t**2 + t, -2 * t**3 + 3 * t**2, t**3 - t**2
    return h00 * yk[i] + h10 * h[i] * m[i] + h01 * yk[i + 1] + h11 * h[i] * m[i + 1]


V[:, 0] = pchip(V[:, 0], src, dst)
ext = V.max(0) - V.min(0)
V[:, 1] *= W / ext[1]
V[:, 2] *= H / ext[2]
put(ref.data, V)
print('REF EXTENT', np.round(V.max(0) - V.min(0), 3))


def dup(o, name):
    c = o.copy(); c.data = o.data.copy(); c.name = c.data.name = name
    scene.collection.objects.link(c); return c


def activate(o):
    for x in scene.objects: x.select_set(False)
    o.select_set(True); bpy.context.view_layer.objects.active = o


def apply_all(o):
    activate(o)
    for m in list(o.modifiers):
        bpy.ops.object.modifier_apply(modifier=m.name)


# watertight copy with the wheels and arches carved out
src_o = dup(ref, 'body_src')
rm = src_o.modifiers.new('voxel', 'REMESH'); rm.mode = 'VOXEL'; rm.voxel_size = VOXEL
apply_all(src_o)
cutters = []
for axle, x in (('F', AXLE_X), ('R', -AXLE_X)):
    for side in (1, -1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=96, radius=ARCH_R[axle], depth=0.9,
                                            location=(x, side * (ARCH_IN[axle] + 0.45), TYRE_R), rotation=(math.pi / 2, 0, 0))
        cutters.append(bpy.context.active_object)
for c in cutters:
    b = src_o.modifiers.new('arch', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.object = c; b.solver = 'EXACT'
    apply_all(src_o)
for c in cutters: bpy.data.objects.remove(c, do_unlink=True)
rm = src_o.modifiers.new('voxel', 'REMESH'); rm.mode = 'VOXEL'; rm.voxel_size = VOXEL
apply_all(src_o)
print('BODY_SRC faces', len(src_o.data.polygons))

# smoothed copy for the cage to wrap onto: keeps the volume, drops the centimetre-scale ripples
smooth_o = dup(src_o, 'body_smooth')
ls = smooth_o.modifiers.new('laplacian', 'LAPLACIANSMOOTH'); ls.iterations = SMOOTH_ITERS; ls.lambda_factor = 0.5
ls.use_volume_preserve = True; ls.use_normalized = True
apply_all(smooth_o)

# quad cage: QuadriFlow refuses the fine voxel mesh (it reports a non-manifold mesh although bmesh finds
# none), so it runs on a 6 cm voxel copy; the shrinkwrap below puts the cage back on the fine surface
cage = dup(src_o, 'body_retopo')
rm = cage.modifiers.new('coarse', 'REMESH'); rm.mode = 'VOXEL'; rm.voxel_size = 0.06
apply_all(cage)
activate(cage)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
shells = sorted(bpy.context.selected_objects, key=lambda p: -len(p.data.vertices))
for p in shells[1:]: bpy.data.objects.remove(p, do_unlink=True)  # stray inner shells
activate(cage)
res = bpy.ops.object.quadriflow_remesh(target_faces=CAGE_FACES, use_mesh_symmetry=False, mode='FACES', seed=1)
print('CAGE', res, 'faces', len(cage.data.polygons))
assert res == {'FINISHED'}, 'QuadriFlow failed'
# mirror-symmetric: keep the +Y half and mirror it, so left and right match exactly
import bmesh
bm = bmesh.new(); bm.from_mesh(cage.data)
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, 1, 0),
                       clear_inner=True)
for v in bm.verts:
    if abs(v.co.y) < 1e-4: v.co.y = 0
bm.to_mesh(cage.data); bm.free()
mi = cage.modifiers.new('mirror', 'MIRROR'); mi.use_axis = (False, True, False); mi.use_clip = True; mi.use_mirror_merge = True
sw = cage.modifiers.new('shrinkwrap', 'SHRINKWRAP'); sw.target = smooth_o; sw.wrap_method = 'NEAREST_SURFACEPOINT'
sd = cage.modifiers.new('subd', 'SUBSURF'); sd.levels = 2; sd.render_levels = 2
activate(cage); bpy.ops.object.shade_smooth()

# blueprints: A2 behind the car (seen from -Y), A5 under it (seen from +Z); both have the nose on the left
k2 = L / 1483
bpy.ops.object.empty_add(type='IMAGE', location=(-(768 - (23 + 1506) / 2) * k2, 2.5, (691 - 512) * k2), rotation=(math.pi / 2, 0, 0))
bs = bpy.context.active_object; bs.name = 'bp_side'
bs.data = bpy.data.images.load(os.path.join(BP, 'gt-A2-side.png')); bs.empty_display_size = 1536 * k2; bs.scale.x = -1
k5 = L / 1466
bpy.ops.object.empty_add(type='IMAGE', location=(-(768 - (32 + 1498) / 2) * k5, -(512 - 493) * k5, -0.05))
bt = bpy.context.active_object; bt.name = 'bp_top'
bt.data = bpy.data.images.load(os.path.join(BP, 'gt-A5-top.png')); bt.empty_display_size = 1536 * k5; bt.scale.x = -1
for o in (bs, bt): o.empty_image_side = 'FRONT'; o.color[3] = 0.5; o.use_empty_image_alpha = True

ref.hide_set(True); ref.hide_render = True
src_o.hide_set(True); src_o.hide_render = True
smooth_o.hide_set(True); smooth_o.hide_render = True

os.makedirs(out, exist_ok=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'gt-v4-base.blend'))
for o in scene.objects: o.select_set(o == cage)
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'body-v3.glb'), use_selection=True, export_apply=True, export_materials='NONE')
print('DONE')
