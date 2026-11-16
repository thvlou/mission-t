# blender -b <gt-v4-base.blend> -P build_body.py -- <out_dir>
# Smooth GT v4 body: a quad cage fitted to the AI volume as a relaxed membrane, arches cut afterwards.
# Why not shrinkwrap: a cage snapped vertex by vertex onto the AI surface copies its few-centimetre ripples, and
# subdivision keeps them (body-v1..v3). Here the cage alternates a half step towards the surface with Taubin
# smoothing (lambda/mu, no shrinkage), so it settles where it fits the big forms and cannot follow the ripples.
#   1. the fitted AI mesh WITH its wheels (arches filled) -> 4 cm voxel (closes the hood hole) as the target
#   2. QuadriFlow cage on a 6 cm voxel copy, cut to the +Y half (mirror modifier makes the other side)
#   3. 80 rounds: project half-way, Taubin smooth; the mirror pods are not projected, so they relax flat
#   4. subdivide twice, cut the four arches (radius, depth as in build_base.py), round the arch edge
# Writes gt-v4-body.blend (object body_smooth4) and body-v4.glb.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

args = sys.argv[sys.argv.index('--') + 1:]
out = args[0]
TAG = args[1] if len(args) > 1 else 'v4'
scene = bpy.context.scene
ROUNDS, PULL, LAM, MU, PASSES, TARGET_SMOOTH = 80, 0.5, 0.55, -0.58, 1, 4
if len(args) > 2: PULL, PASSES, TARGET_SMOOTH = float(args[2]), int(args[3]), int(args[4])
# HULL (optional 6th arg, 0..1): fit to a blend of the AI volume and the visual hull of the four blueprint silhouettes
# (tex/sil-*.png from silhouettes.py). The AI volume is rounder than the drawn car at the nose and tail corners;
# the target surface is f = max(hull, (1 - HULL) * ai + HULL * hull) = 0, so the cage moves out towards the hull's
# squarer corners where the AI is inside it, and can never end up outside any silhouette.
HULL = float(args[5]) if len(args) > 5 else None
# FENDERS (optional 7th arg, 1 = on): the body must wrap a rounded drum round each tyre, so after the arch cut a
# fender lip of at least 4.5 cm stays above the tyre and the arch edge sits outboard of the tyre's outer face.
# Without it the cut took the top off the low fenders (tyre showing through from above) and the tyres stood
# 2..12 cm proud of the narrower body sides (gt-v4-wheels.blend: tyre faces at |y| 0.966 front, 0.98 rear).
# RELAX (8th arg, default 0): extra rounds at the end with a weak pull, which irons out the last ripples.
FENDERS = len(args) > 6 and args[6] == '1'
RELAX = int(args[7]) if len(args) > 7 else 0
# FAIR (9th arg, default 0): a last fairing solve, (I + FAIR * L'L) V = V_fit, which takes out the 10..30 cm lumps
# the AI target itself has (Taubin only damps the shortest ripples, and every pull brings the lumps back).
FAIR = float(args[8]) if len(args) > 8 else 0.0
# DOOR (10th arg, bit flags: 1 pod fill, 2 flank taper, 3 both): the door between the front arch and the A-pillar base.
#   - the mirror-pod vertices (never projected) kept the AI mirror's bump: Taubin does not shrink, so a 3.5 cm bulge
#     stayed at shoulder height. Now they are filled from their neighbours each round (plain Laplacian steps).
#   - each drum's flank (tyre face + 15 mm) stood 5 cm proud of the door within 25 cm, a crease in the reflections.
#     Beyond the drum the side now has to clear three wider, shallower rings (TAPER_RINGS).
DOOR = int(args[9]) if len(args) > 9 else 0
TAPER_RINGS = ((0.15, 0.02), (0.30, 0.04), (0.45, 0.06))   # (radius added, flank drop) m
CAGE_FACES = 7000
AXLE_X, TYRE_R = 1.435, 0.40
ARCH = {'F': (0.43, 0.45), 'R': (0.42, 0.55)}
DRUM = {'F': dict(r=0.475, y_out=0.981), 'R': dict(r=0.465, y_out=0.995)}   # tyre face + 15 mm
DRUM_ROUND = 0.05
MIRROR_ZONE = dict(x=(0.30, 1.00), z=(0.78, 1.08), y=0.86)   # A2: mirror pods just behind the A-pillar


def activate(o):
    for x in scene.objects: x.select_set(x == o)
    bpy.context.view_layer.objects.active = o
    o.hide_set(False)


def apply(o, kind, **kw):
    activate(o)
    m = o.modifiers.new(kind, kind)
    for k, v in kw.items(): setattr(m, k, v)
    bpy.ops.object.modifier_apply(modifier=m.name)


def dup(o, name):
    c = o.copy(); c.data = o.data.copy(); c.name = c.data.name = name
    for m in list(c.modifiers): c.modifiers.remove(m)
    scene.collection.objects.link(c); return c


ref = bpy.data.objects['ref_hunyuan21']
target = dup(ref, 'body4_target')
apply(target, 'REMESH', mode='VOXEL', voxel_size=0.04)
apply(target, 'LAPLACIANSMOOTH', iterations=TARGET_SMOOTH, lambda_factor=0.5, use_volume_preserve=True, use_normalized=True)
bvh = BVHTree.FromObject(target, bpy.context.evaluated_depsgraph_get())

cage = dup(ref, 'body_smooth4')
cage.hide_render = False   # ref is hidden in renders; its copies must not be
apply(cage, 'REMESH', mode='VOXEL', voxel_size=0.06)
activate(cage)
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.separate(type='LOOSE'); bpy.ops.object.mode_set(mode='OBJECT')
for p in sorted(bpy.context.selected_objects, key=lambda p: -len(p.data.vertices))[1:]:
    bpy.data.objects.remove(p, do_unlink=True)
activate(cage)
res = bpy.ops.object.quadriflow_remesh(target_faces=CAGE_FACES, use_mesh_symmetry=False, mode='FACES', seed=3)
assert res == {'FINISHED'}, 'QuadriFlow failed'
bm = bmesh.new(); bm.from_mesh(cage.data)
bmesh.ops.bisect_plane(bm, geom=bm.verts[:] + bm.edges[:] + bm.faces[:], plane_co=(0, 0, 0), plane_no=(0, 1, 0), clear_inner=True)
bm.to_mesh(cage.data); bm.free()
me = cage.data
print('CAGE half faces', len(me.polygons))

V = np.array([v.co[:] for v in me.vertices])
E = np.array([e.vertices[:] for e in me.edges])
deg = np.bincount(E.ravel(), minlength=len(V)).astype(float)
seam = np.abs(V[:, 1]) < 2e-3
V[seam, 1] = 0
mz = MIRROR_ZONE
pod = (V[:, 0] > mz['x'][0]) & (V[:, 0] < mz['x'][1]) & (V[:, 2] > mz['z'][0]) & (V[:, 2] < mz['z'][1]) & (V[:, 1] > mz['y'])


def laplace(P):
    acc = np.zeros_like(P)
    np.add.at(acc, E[:, 0], P[E[:, 1]]); np.add.at(acc, E[:, 1], P[E[:, 0]])
    return acc / deg[:, None] - P


def project_ai(P):
    Q = P.copy()
    for k in np.flatnonzero(~pod):
        hit = bvh.find_nearest(Vector(P[k]))
        if hit[0] is not None: Q[k] = hit[0][:]
    return Q


project = project_ai
if HULL is not None:
    from mathutils.kdtree import KDTree
    L = 4.736
    k2, k5 = L / 1483, L / 1466
    # view: (u metres per px, v metres per px), point -> (col, row), plane-gradient (gu, gv) -> 3D gradient
    VIEWS = {
        'A2': ((k2, k2), lambda p: (764.5 - p[0] / k2, 691 - p[2] / k2), lambda gu, gv: (-gu, 0.0, -gv)),
        'A5': ((k5, k5), lambda p: (765 - p[0] / k5, 493 + p[1] / k5), lambda gu, gv: (-gu, gv, 0.0)),
        'A3': ((1 / 721, 1 / 585), lambda p: (767.5 - p[1] * 721, 880 - p[2] * 585), lambda gu, gv: (0.0, -gu, -gv)),
        'A4': ((1 / 691, 1 / 573), lambda p: (767.5 + p[1] * 691, 865 - p[2] * 573), lambda gu, gv: (0.0, gu, -gv)),
    }
    sil = {}
    for name, ((su, sv), to_px, to3) in VIEWS.items():
        img = bpy.data.images.load(os.path.join(out, 'tex', f'sil-{name}.png'))
        w, h = img.size
        a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); bpy.data.images.remove(img)
        m = a.reshape(h, w, 4)[::-1, :, 0] > 0.5                       # row 0 = top
        inner = m.copy()
        inner[1:-1, 1:-1] = m[1:-1, 1:-1] & m[:-2, 1:-1] & m[2:, 1:-1] & m[1:-1, :-2] & m[1:-1, 2:]
        rows, cols = np.nonzero(m & ~inner)
        kd = KDTree(len(rows))
        for i, (r, c) in enumerate(zip(rows, cols)): kd.insert((c * su, r * sv, 0.0), i)
        kd.balance()
        sil[name] = (m, kd, su, sv, to_px, to3)
        print('HULL view', name, 'boundary px', len(rows))

    def sdf_view(p, view):
        m, kd, su, sv, to_px, to3 = sil[view]
        c, r = to_px(p)
        q = Vector((c * su, r * sv, 0.0))
        b, _, d = kd.find(q)
        ci, ri = int(round(c)), int(round(r))
        inside = 0 <= ri < m.shape[0] and 0 <= ci < m.shape[1] and m[ri, ci]
        g = (q - b) / max(d, 1e-9)
        if inside: d, g = -d, -g
        return d, np.array(to3(g.x, g.y))

    def project_hull(P):
        Q = P.copy()
        for k in np.flatnonzero(~pod):
            p = P[k]
            hull = [sdf_view(p, v) for v in VIEWS]
            sh, gh = max(hull, key=lambda t: t[0])
            hit = bvh.find_nearest(Vector(p))
            dv = p - np.array(hit[0][:]); da = np.linalg.norm(dv)
            nrm = np.array(hit[1][:])
            sa = da if dv.dot(nrm) >= 0 else -da
            ga = dv / da * np.sign(sa) if da > 1e-6 else nrm
            blend = (1 - HULL) * sa + HULL * sh
            f, g = (sh, gh) if sh >= blend else (blend, (1 - HULL) * ga + HULL * gh)
            gg = g.dot(g)
            if gg > 1e-9: Q[k] = p - f * g / gg
        return Q

    project = project_hull


F = np.array([p.vertices[:] for p in me.polygons], dtype=object)


def normals(P):
    acc = np.zeros_like(P)
    for f in F:
        n = np.cross(P[f[1]] - P[f[0]], P[f[2]] - P[f[0]])
        for i in f: acc[i] += n
    return acc / np.maximum(np.linalg.norm(acc, axis=1, keepdims=True), 1e-12)


def drum_push(P):
    """Push vertices out of the rounded tyre drums (capped cylinders along y), along the vertex normal."""
    if not FENDERS: return P
    N = normals(P)
    Q = P.copy()
    for axle, hx in (('F', AXLE_X), ('R', -AXLE_X)):
        r, y0, y1 = DRUM[axle]['r'], ARCH[axle][1], DRUM[axle]['y_out']
        yc, hy = (y0 + y1) / 2, (y1 - y0) / 2
        qx = np.hypot(P[:, 0] - hx, P[:, 2] - TYRE_R) - (r - DRUM_ROUND)
        qy = np.abs(P[:, 1] - yc) - (hy - DRUM_ROUND)
        sd = np.minimum(np.maximum(qx, qy), 0) + np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) - DRUM_ROUND
        inside = (sd < 0) & (P[:, 2] > 0.08) & (N[:, 2] > -0.3)   # not the floor
        Q[inside] += N[inside] * (-sd[inside])[:, None]
        if DOOR & 2 and axle == 'F':   # behind the door the side intake scoop sits ahead of the rear arch: rings dimpled it
            # the flank between the drum and the doors: three wider, shallower rings (a stepped taper the smoothing rounds off),
            # pushed along the normal like the drum itself. Only the outer shell takes part (y within 12 cm of the
            # ring's face, normal sideways, below the shoulder), so walls deeper inside are left alone.
            for grow, drop in TAPER_RINGS:
                yo = y1 - drop
                yc2, hy2 = yo - 0.06, 0.06
                qx = np.hypot(P[:, 0] - hx, P[:, 2] - TYRE_R) - (r + grow - DRUM_ROUND)
                qy = np.abs(P[:, 1] - yc2) - (hy2 - DRUM_ROUND)
                sd = np.minimum(np.maximum(qx, qy), 0) + np.hypot(np.maximum(qx, 0), np.maximum(qy, 0)) - DRUM_ROUND
                cabin = (P[:, 0] - hx) * np.sign(hx) < 0           # only towards the doors, not the nose or tail
                shell = cabin & (sd < 0) & (N[:, 1] > 0.5) & (P[:, 2] > 0.12) & (P[:, 2] < TYRE_R + r * 0.8)
                Q[shell] += N[shell] * (-sd[shell])[:, None]
    return Q


for it in range(ROUNDS + RELAX):
    pull = PULL if it < ROUNDS else PULL * 0.2
    V += pull * (project(V) - V)
    for f in (LAM, MU) * PASSES:
        V += f * laplace(V)
        V[seam, 1] = 0
    V = drum_push(V)
    if DOOR & 1:
        for _ in range(5): V[pod] += 0.5 * laplace(V)[pod]
    if it % 20 == 19:
        d = np.linalg.norm(project(V)[~pod] - V[~pod], axis=1)
        print(f'ROUND {it + 1}: distance to the target surface mean {d.mean() * 1000:.1f} mm, 95% {np.percentile(d, 95) * 1000:.1f} mm')
def laplace_t(P):
    """L' P for L = D^-1 A - I (laplace above)."""
    Q = P / deg[:, None]
    acc = np.zeros_like(P)
    np.add.at(acc, E[:, 0], Q[E[:, 1]]); np.add.at(acc, E[:, 1], Q[E[:, 0]])
    return acc - P


def fair(V0):
    """(I + FAIR L'L) V = V0 by conjugate gradients on the sparse system (a dense L'L product is minutes in Blender's numpy)."""
    op = lambda X: X + FAIR * laplace_t(laplace(X))
    X = V0.copy(); R = V0 - op(X); Pd = R.copy(); rr = (R * R).sum(0)
    for _ in range(500):
        Ap = op(Pd); a = rr / (Pd * Ap).sum(0)
        X += a * Pd; R -= a * Ap
        rr2 = (R * R).sum(0)
        if rr2.max() < 1e-14: break
        Pd = R + (rr2 / rr) * Pd; rr = rr2
    X[seam, 1] = 0   # the seam's mirror twins would cancel its pull off the plane
    return X


if FAIR > 0:
    # fair and re-apply the fender drums in turn: one fair then one push left a step where the drums took over again
    # (a zig-zag ahead of the rear arch at FAIR 100+); each fair now rounds off the previous push
    V0 = V.copy()
    for _ in range(3): V = drum_push(fair(V))
    d = np.linalg.norm(V - V0, axis=1)
    print(f'FAIR {FAIR}: moved mean {d.mean() * 1000:.1f} mm, max {d.max() * 1000:.1f} mm')
for _ in range(3): V = drum_push(V)   # the subdivision below pulls convex corners in by a few mm; the drums have 15 mm to spare
me.vertices.foreach_set('co', V.ravel()); me.update()

# mirror, subdivide, then the arches
mi = cage.modifiers.new('mirror', 'MIRROR'); mi.use_axis = (False, True, False); mi.use_clip = True; mi.use_mirror_merge = True
sd = cage.modifiers.new('subd', 'SUBSURF'); sd.levels = sd.render_levels = 2
activate(cage)
for m in list(cage.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
cutters = []
for axle, x in (('F', AXLE_X), ('R', -AXLE_X)):
    rad, y_in = ARCH[axle]
    for side in (1, -1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=rad, depth=0.9, location=(x, side * (y_in + 0.45), TYRE_R),
                                            rotation=(math.pi / 2, 0, 0))
        cutters.append(bpy.context.active_object)
for c in cutters:
    activate(cage)
    b = cage.modifiers.new('arch', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.object = c; b.solver = 'EXACT'
    bpy.ops.object.modifier_apply(modifier=b.name)
for c in cutters: bpy.data.objects.remove(c, do_unlink=True)
apply(cage, 'BEVEL', width=0.008, segments=2, limit_method='ANGLE', angle_limit=math.radians(55))  # soft arch edge
for p in cage.data.polygons: p.use_smooth = True
activate(cage); bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
bpy.data.objects.remove(target, do_unlink=True)
V = np.array([v.co[:] for v in cage.data.vertices])
print('BODY extent', np.round(V.max(0) - V.min(0), 3), 'faces', len(cage.data.polygons))
for name in ('body_loft',):
    if name in bpy.data.objects: bpy.data.objects.remove(bpy.data.objects[name], do_unlink=True)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, f'gt-v4-body-{TAG}.blend'))
activate(cage)
bpy.ops.export_scene.gltf(filepath=os.path.join(out, f'body-{TAG}.glb'), use_selection=True, export_apply=True, export_materials='NONE')
print('DONE')
