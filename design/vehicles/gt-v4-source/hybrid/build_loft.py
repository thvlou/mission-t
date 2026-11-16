# blender -b <gt-v4-base.blend> -P build_loft.py -- <out_dir>
# A smooth GT v4 body lofted through cross-sections of the fitted AI mesh, instead of shrinkwrapping onto it.
# The AI surface ripples at a few centimetres; a cage that follows it point by point keeps those ripples. Here only
# the volume is taken: at N stations along the car, M rays from a point on the centre plane measure the half
# section (from straight down, round the side, to straight up). The radii are median-filtered (mirror stalks,
# AI spikes) and Gaussian-smoothed along the car and round the section, then a quad grid is lofted through
# them, mirrored, and smoothed by subdivision. Wheel arches are cut as in build_base.py.
# Writes gt-v4-loft.blend (object body_loft, plus everything from the base file) and body-loft.glb.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

out = sys.argv[sys.argv.index('--') + 1]
scene = bpy.context.scene
L = 4.736
N, M = 76, 41                  # stations along the car, rays round the half section
SIG_X, SIG_A = 1.6, 1.1        # Gaussian smoothing, in stations and in rays
AXLE_X, TYRE_R = 1.435, 0.40
ARCH = {'F': (0.43, 0.45), 'R': (0.42, 0.55)}   # cut radius, |y| where the cut starts (build_base.py)

ref = bpy.data.objects['ref_hunyuan21']
# watertight copy of the fitted AI mesh to cast against
vox = ref.copy(); vox.data = ref.data.copy(); scene.collection.objects.link(vox)
for o in scene.objects: o.select_set(o == vox)
bpy.context.view_layer.objects.active = vox
vox.hide_set(False)
rm = vox.modifiers.new('v', 'REMESH'); rm.mode = 'VOXEL'; rm.voxel_size = 0.015
bpy.ops.object.modifier_apply(modifier='v')
bvh = BVHTree.FromObject(vox, bpy.context.evaluated_depsgraph_get())

# stations: cosine spacing so the nose and tail, where sections change fast, get more of them
xs = -L / 2 * np.cos(np.linspace(0.02, math.pi - 0.02, N))
thetas = np.radians(np.linspace(-90, 90, M))


def cast(o, d):
    hit = bvh.ray_cast(Vector(o), Vector(d))
    return hit[0]


zc = np.full(N, np.nan)
for i, x in enumerate(xs):
    top, bot = cast((x, 0, 3), (0, 0, -1)), cast((x, 0, -1), (0, 0, 1))
    if top and bot: zc[i] = (top.z + bot.z) / 2
ok = ~np.isnan(zc)
zc = np.interp(np.arange(N), np.flatnonzero(ok), zc[ok])


def gauss1d(a, sig, axis):
    k = np.arange(-int(3 * sig) - 1, int(3 * sig) + 2)
    w = np.exp(-k ** 2 / (2 * sig ** 2)); w /= w.sum()
    pad = [(0, 0)] * a.ndim; pad[axis] = (len(k) // 2, len(k) // 2)
    ap = np.pad(a, pad, mode='edge')
    return np.apply_along_axis(lambda v: np.convolve(v, w, mode='valid'), axis, ap)


zc = gauss1d(zc, 2.5, 0)
r = np.full((N, M), np.nan)
for i, x in enumerate(xs):
    o = Vector((x, 0, zc[i]))
    for j, t in enumerate(thetas):
        h = cast(o, (0, math.cos(t), math.sin(t)))
        if h: r[i, j] = (h - o).length
# holes (rays that escaped through an intake) -> neighbours
for i in range(N):
    row = r[i]; bad = np.isnan(row)
    if bad.all(): row[:] = 0.02
    elif bad.any(): row[bad] = np.interp(np.flatnonzero(bad), np.flatnonzero(~bad), row[~bad])
# median 3x3 knocks out mirror stalks and single-ray spikes, then the Gaussian takes the ripples
pad = np.pad(r, 1, mode='edge')
r = np.median(np.stack([pad[1 + di:N + 1 + di, 1 + dj:M + 1 + dj] for di in (-1, 0, 1) for dj in (-1, 0, 1)]), axis=0)
r = gauss1d(gauss1d(r, SIG_X, 0), SIG_A, 1)

# loft: half grid (y >= 0), rows = stations, columns = rays; the first and last columns lie on y = 0
bm = bmesh.new()
grid = [[bm.verts.new((x, r[i, j] * math.cos(t), zc[i] + r[i, j] * math.sin(t))) for j, t in enumerate(thetas)]
        for i, x in enumerate(xs)]
for i in range(N - 1):
    for j in range(M - 1):
        bm.faces.new((grid[i][j], grid[i + 1][j], grid[i + 1][j + 1], grid[i][j + 1]))
for i, end in ((0, -L / 2), (N - 1, L / 2)):  # round caps: a fan to a pole on the centre plane at the tip
    pole = bm.verts.new((end, 0, zc[i]))
    for j in range(M - 1):
        bm.faces.new((grid[i][j], grid[i][j + 1], pole) if i == 0 else (grid[i][j + 1], grid[i][j], pole))
for v in bm.verts:
    if abs(v.co.y) < 1e-6: v.co.y = 0
bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
me = bpy.data.meshes.new('body_loft'); bm.to_mesh(me); bm.free()
body = bpy.data.objects.new('body_loft', me); scene.collection.objects.link(body)
for p in me.polygons: p.use_smooth = True
mi = body.modifiers.new('mirror', 'MIRROR'); mi.use_axis = (False, True, False); mi.use_clip = True; mi.use_mirror_merge = True
sd = body.modifiers.new('subd', 'SUBSURF'); sd.levels = sd.render_levels = 2
print('LOFT', N, 'x', M, 'half grid,', len(me.polygons), 'faces')

# wheel arches, cut from the subdivided body
for o in scene.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
for m in list(body.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
cutters = []
for axle, x in (('F', AXLE_X), ('R', -AXLE_X)):
    rad, y_in = ARCH[axle]
    for side in (1, -1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=rad, depth=0.9, location=(x, side * (y_in + 0.45), TYRE_R),
                                            rotation=(math.pi / 2, 0, 0))
        cutters.append(bpy.context.active_object)
bpy.context.view_layer.objects.active = body
for c in cutters:
    b = body.modifiers.new('arch', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.object = c; b.solver = 'EXACT'
    for o in scene.objects: o.select_set(o == body)
    bpy.ops.object.modifier_apply(modifier=b.name)
for c in cutters: bpy.data.objects.remove(c, do_unlink=True)
bpy.data.objects.remove(vox, do_unlink=True)
for o in scene.objects: o.select_set(o == body)
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(40))
V = np.array([v.co[:] for v in body.data.vertices])
print('BODY extent', np.round(V.max(0) - V.min(0), 3), 'faces', len(body.data.polygons))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'gt-v4-loft.blend'))
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'body-loft.glb'), use_selection=True, export_apply=True, export_materials='NONE')
print('DONE')
