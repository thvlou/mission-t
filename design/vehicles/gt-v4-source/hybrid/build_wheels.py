# blender -b <gt-v4-base.blend> -P build_wheels.py -- <out_dir>
# Models the GT v4 wheel from detail image C3 and fits four of them to body_retopo:
#   wheel_FL/FR/RL/RR   tyre, rim, spoke face, rotor, hub, lugs: one mesh each, origin at the hub, no rotation,
#                       axle along Y (the game spins the GLB node about its local Z, which is Blender Y)
#   caliper_FL/..       red fixed calipers, separate so they steer but don't spin
# C3 measured at 0.40 m tyre radius (492 px, rays at the window and spoke centres): rim lip r 0.322,
# spoke face r 0.296, windows r 0.12..0.288 and about +-21 deg wide all the way (19.5 at the hub end, 23 in
# the middle, 19 at the rim), lugs on the spokes at r 0.092, black centre ring r 0.077, silver cap r 0.042. Tyres: 255 front, 305 rear, outer faces 1 cm inside the body side.
# Writes gt-v4-wheels.blend, wheels-v12.glb and clearance numbers.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

out = sys.argv[sys.argv.index('--') + 1]
scene = bpy.context.scene
R = 0.40                          # tyre outer radius (A2 / C3)
BEAD = 0.2667                     # 21 in bead seat
LIP, FACE_R = 0.322, 0.296
HUB_R = 0.077                     # spoke face inner edge = black centre ring
AXLE_X = 1.435
WIDTH = {'F': 0.255, 'R': 0.305}
INSET = 0.01                      # tyre outer face inside the body side
CALIPER_DEG = 165                 # caliper centre angle in the side view, 0 = towards the nose, 90 = up

MATS = {}


def mat(name, rgb, metal, rough, coat=0.0, spec=0.5):
    m = bpy.data.materials.new('GT4 ' + name); m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')  # node names follow the UI language
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Metallic'].default_value = metal
    b.inputs['Roughness'].default_value = rough
    if coat: b.inputs['Coat Weight'].default_value = coat
    b.inputs['Specular IOR Level'].default_value = spec
    MATS[name] = m
    return m


mat('Tire', (0.005, 0.005, 0.006), 0.0, 0.92, spec=0.15)
mat('TireWall', (0.006, 0.006, 0.007), 0.0, 0.86, spec=0.2)
mat('Well', (0.006, 0.006, 0.007), 0.0, 0.95)
mat('RimFace', (0.88, 0.89, 0.90), 1.0, 0.34)             # satin silver (C3): rough enough to read bright, not mirror-dark
mat('RimLip', (0.90, 0.90, 0.91), 1.0, 0.24)              # outer lip, a touch smoother than the face
mat('RimDark', (0.02, 0.02, 0.022), 0.4, 0.5)
mat('Disc', (0.45, 0.45, 0.46), 1.0, 0.3)
mat('Hat', (0.06, 0.06, 0.065), 0.6, 0.5)
mat('Lug', (0.55, 0.55, 0.57), 1.0, 0.2)
mat('Cap', (0.82, 0.83, 0.84), 1.0, 0.22)
mat('Caliper', (0.60, 0.012, 0.016), 0.0, 0.25, coat=1.0)
mat('Paint', (0.80, 0.80, 0.78), 0.0, 0.32, coat=1.0)
# The game's tune() (src/car-model.js) forces any /rim/ material to roughness <= 0.2, which reads as dark chrome
# under its room light; the spoke face keeps its satin 0.34 under a name that rule doesn't match.
MATS['RimFace'].name = 'GT4 Alloy'
ORDER = ['Tire', 'TireWall', 'RimFace', 'RimDark', 'Disc', 'Hat', 'Lug', 'Cap', 'RimLip']
SLOT = {n: i for i, n in enumerate(ORDER)}


def to_object(name, bm, materials, coll):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in materials: me.materials.append(MATS[m])
    o = bpy.data.objects.new(name, me); coll.objects.link(o)
    return o


def lathe(bm, profile, slot, steps):
    """Spin an open (radius, axial) polyline about the Y axle."""
    old = set(bm.faces)
    vs = [bm.verts.new((0, a, r)) for (r, a) in profile]
    es = [bm.edges.new((p, q)) for p, q in zip(vs, vs[1:])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=math.tau, steps=steps, use_merge=True)
    new = [f for f in bm.faces if f not in old]
    for f in new: f.material_index = slot
    return new


W_IN, W_OUT = 0.12, 0.288                         # window radial span (C3)
W_HALF = (19.5, 23.0, 19.0)                       # window angular half width at hub end, middle, rim end (deg)
W_ROUND = 3.2                                     # superellipse exponent of the window ends
DISH, THICK, CROWN = 0.058, 0.03, 0.012           # face dish depth, plate thickness, spoke crown height


def dish(r):
    """Axial height of the face (0 at the hub edge, DISH at the rim edge)."""
    return DISH * min(1.0, max(0.0, (r - HUB_R) / (FACE_R - HUB_R))) ** 1.6


def window_half(r):
    """Window half width (radians) at radius r; 0 outside the window, closing round at both ends."""
    if r <= W_IN or r >= W_OUT: return 0.0
    u = (2 * r - W_IN - W_OUT) / (W_OUT - W_IN)              # -1 hub end .. +1 rim end
    hw = W_HALF[1] + (W_HALF[2] - W_HALF[1]) * u if u > 0 else W_HALF[1] + (W_HALF[0] - W_HALF[1]) * -u
    return math.radians(hw) * (1 - abs(u) ** W_ROUND) ** (1 / W_ROUND)


def crown(r, x):
    """Raised spoke surface. x: -1..1 across the spoke. One ridge along the spoke, splitting into two creases
    that run to the window corners over the last 7 cm before the rim (the C3 'forked' tips)."""
    if r <= W_IN - 0.02: return 0.0
    fade = min(1.0, (r - (W_IN - 0.02)) / 0.04)
    t = min(1.0, max(0.0, (r - 0.215) / 0.07)); t = t * t * (3 - 2 * t)
    single = 1 - x * x
    double = max(0.0, 1 - ((abs(x) - 0.55) / 0.45) ** 2)
    out = min(1.0, max(0.0, (W_OUT + 0.002 - r) / 0.022))  # flatten into the rim ring: past the window ends the
    return CROWN * fade * out * ((1 - t) * single + t * double)  # ridges would be bumps across the closed ring


def spoke_face():
    """Quad-meshed five-spoke face, no boolean: every ring has M+1 points across each spoke, placed between the
    two neighbouring window edges, so the window outlines are the mesh's own edges. Where a ring is outside the
    window span the edge points of neighbouring spokes are the same vertex and the face is closed."""
    M = 8                                                  # 5 x 8 = 40 segments round the rim edge, every other lip vertex
    us = [-math.cos(math.pi * i / 12) for i in range(13)]    # cosine spacing: dense at the round window ends
    rings = [HUB_R, HUB_R + 0.02, W_IN - 0.012] + [(W_IN + W_OUT) / 2 + u * (W_OUT - W_IN) / 2 for u in us] + [FACE_R - 0.004, FACE_R - 0.0015]  # 1.5 mm inside the lip wall (same radius z-fights)
    bm = bmesh.new()
    F, B = [], []  # per ring: list over spokes of M+1 front / back verts
    for r in rings:
        h = window_half(r)
        fr, br = [], []
        for k in range(5):
            a0 = math.radians(90 + 72 * k) + h            # this spoke runs from window k ...
            a1 = math.radians(90 + 72 * (k + 1)) - h      # ... to window k+1
            frow, brow = [], []
            for j in range(M + 1):
                if h == 0 and j == 0 and k > 0:           # closed ring: share the seam with the previous spoke
                    frow.append(fr[k - 1][M]); brow.append(br[k - 1][M]); continue
                if h == 0 and j == M and k == 4:
                    frow.append(fr[0][0]); brow.append(br[0][0]); continue
                a = a0 + (a1 - a0) * j / M
                x = 2 * j / M - 1
                cx, cz = r * math.cos(a), r * math.sin(a)
                frow.append(bm.verts.new((cx, dish(r) + crown(r, x), cz)))
                brow.append(bm.verts.new((cx, dish(r) - THICK, cz)))
            fr.append(frow); br.append(brow)
        F.append(fr); B.append(br)
    def quad(vs, flip=False):
        vs = list(dict.fromkeys(vs))                       # drop repeats where a window end closes to a point
        if len(vs) >= 3: bm.faces.new(vs[::-1] if flip else vs)
    for i in range(len(rings) - 1):
        for k in range(5):
            for j in range(M):
                quad((F[i][k][j], F[i][k][j + 1], F[i + 1][k][j + 1], F[i + 1][k][j]))
                quad((B[i][k][j], B[i][k][j + 1], B[i + 1][k][j + 1], B[i + 1][k][j]), flip=True)
            for j in (0, M):                               # window walls
                if F[i][k][j] is not F[i][(k + (1 if j == M else -1)) % 5][0 if j == M else M] or                    F[i + 1][k][j] is not F[i + 1][(k + (1 if j == M else -1)) % 5][0 if j == M else M]:
                    quad((F[i][k][j], F[i + 1][k][j], B[i + 1][k][j], B[i][k][j]), flip=(j == M))
    for i in (0, len(rings) - 1):                          # hub and rim edge walls
        for k in range(5):
            for j in range(M):
                quad((F[i][k][j], F[i][k][j + 1], B[i][k][j + 1], B[i][k][j]), flip=(i == 0))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-7)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    for f in bm.faces: f.material_index = SLOT['RimFace']; f.smooth = True
    # 2.5 mm rounded chamfer on every window and rim edge: it catches a thin highlight like C3's machined edges
    # (window edges only: chamfering the rim ring too makes broken glints where it meets the window ends)
    sharp = [e for e in bm.edges if len(e.link_faces) == 2 and e.calc_face_angle(0) > math.radians(40)
             and min(math.hypot(v.co.x, v.co.z) for v in e.verts) < FACE_R - 0.003]
    bmesh.ops.bevel(bm, geom=sharp, offset=0.0025, offset_type='OFFSET', segments=2, profile=0.5, affect='EDGES')
    for f in bm.faces: f.material_index = SLOT['RimFace']; f.smooth = True
    me = bpy.data.meshes.new('spoke_face'); bm.to_mesh(me); bm.free()
    return me


FACE = spoke_face()
print('FACE faces', len(FACE.polygons))


def wheel_bm(width):
    """One wheel, face towards +Y, hub at the origin. width: tyre section width."""
    hw = width / 2
    face_a = hw - 0.012 - DISH           # axial position of the face's deepest (hub) surface
    bm = bmesh.new()
    sw = R - 0.022                       # where sidewall turns into the shoulder
    # tyre: blank rounded sidewalls, rim protector, shoulder, tread with three grooves
    wall_in = [(BEAD, -(hw - 0.012)), (BEAD + 0.012, -hw), (sw - 0.02, -hw - 0.002), (sw, -hw + 0.004), (R - 0.006, -hw + 0.016)]
    lathe(bm, wall_in, SLOT['TireWall'], 56)
    tread = [(R - 0.006, -hw + 0.016), (R, -hw + 0.03)]
    for g in (-hw * 0.28, hw * 0.28):
        tread += [(R, g - 0.008), (R - 0.009, g - 0.006), (R - 0.009, g + 0.006), (R, g + 0.008)]
    tread += [(R, hw - 0.03), (R - 0.006, hw - 0.016)]
    TREAD_STEPS = 96
    for f in lathe(bm, tread, SLOT['Tire'], TREAD_STEPS):
        pass
    # shoulder notches (C3): every other step, the shoulder ring is pulled in 5 mm -> 48 short lateral slots
    for v in bm.verts:
        r = math.hypot(v.co.x, v.co.z)
        if abs(v.co.y) > hw - 0.034 and r > R - 0.0065 and abs(v.co.y) < hw:
            step = round(math.atan2(v.co.z, v.co.x) / (math.tau / TREAD_STEPS))
            if step % 2 == 0:
                k = (r - 0.005) / r; v.co.x *= k; v.co.z *= k
    # outer sidewall: 81 mm of rubber from the shoulder down to the silver lip (C3), with a rim-protector rib
    wall_out = [(R - 0.006, hw - 0.016), (sw, hw - 0.004), (sw - 0.02, hw + 0.002), (LIP + 0.016, hw + 0.004),
                (LIP + 0.009, hw + 0.010), (LIP + 0.003, hw + 0.008), (LIP, hw + 0.002)]
    lathe(bm, wall_out, SLOT['TireWall'], 64)
    # rim: silver lip and its step down to the spoke face, dark barrel behind
    lathe(bm, [(LIP, hw + 0.002), (LIP, hw + 0.010), (LIP - 0.006, hw + 0.014), (FACE_R + 0.006, hw + 0.010),
               (FACE_R, hw + 0.002), (FACE_R, face_a + DISH - THICK)], SLOT['RimLip'], 80)
    lathe(bm, [(LIP, hw + 0.002), (BEAD, hw - 0.012), (BEAD - 0.004, hw - 0.03), (BEAD - 0.004, -(hw - 0.012)), (BEAD, -(hw - 0.012))],
          SLOT['RimDark'], 36)
    # rotor: two plates around a dark vane gap, dark hat; drilled holes as dark plugs on the outer plate
    dr, ri = 0.205, 0.10
    da = face_a - 0.075
    lathe(bm, [(ri, da + 0.032), (dr - 0.003, da + 0.032), (dr, da + 0.029), (dr, da + 0.003), (dr - 0.003, da), (ri, da)], SLOT['Disc'], 48)
    lathe(bm, [(dr - 0.004, da + 0.022), (dr - 0.004, da + 0.010)], SLOT['Hat'], 48)
    lathe(bm, [(0.0, face_a - 0.005), (ri - 0.012, face_a - 0.005), (ri, face_a - 0.02), (ri, da + 0.032)], SLOT['Hat'], 36)
    for ring, n, phase in ((0.135, 12, 0.0), (0.160, 12, 0.5), (0.185, 12, 0.25)):
        for k in range(n):
            a = (k + phase) * math.tau / n
            old = set(bm.faces)
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.0042, radius2=0.0042, depth=0.002)
            bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
            bmesh.ops.translate(bm, verts=res['verts'], vec=(ring * math.cos(a), da + 0.0322, ring * math.sin(a)))
            for f in bm.faces:
                if f not in old: f.material_index = SLOT['RimDark']
    # centre: black ring, domed silver cap, five lugs on the spokes
    lathe(bm, [(0.042, face_a + 0.012), (0.070, face_a + 0.008), (0.074, face_a + 0.002), (HUB_R, face_a - 0.004)], SLOT['RimDark'], 36)
    lathe(bm, [(0.0, face_a + 0.024), (0.024, face_a + 0.021), (0.038, face_a + 0.015), (0.042, face_a + 0.012)], SLOT['Cap'], 36)
    for k in range(5):
        a = math.radians(90 + 36 + 72 * k)
        old = set(bm.faces)
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.0115, radius2=0.0095, depth=0.016)
        bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
        r_l = 0.092
        bmesh.ops.translate(bm, verts=res['verts'], vec=(r_l * math.cos(a), face_a + 0.006 + dish(r_l), r_l * math.sin(a)))
        for f in bm.faces:
            if f not in old: f.material_index = SLOT['Lug']
    # spoke face, moved so its rim edge meets the lip step
    fm = FACE.copy()
    fm.transform(Matrix.Translation((0, face_a, 0)))
    bm.from_mesh(fm); bpy.data.meshes.remove(fm)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm, face_a, da


LINER = {  # tube radius between the tyre's swept radius and the arch cut (build_base ARCH_R), back plate depth
    'F': dict(rw=0.425, back=0.31),  # steered +-0.5 rad, the tyre sweeps r 0.42 and its inner corner 0.28 m inboard
    'R': dict(rw=0.413, back=None),  # rear: just behind the tyre's inner face
}


def well_bm(inner, outer, rw):
    """Black wheel-well liner: a back plate behind the tyre and a tube round its upper 210 deg, out to the body
    side, so the windows show black instead of the white arch walls. y from inner to outer (both > 0); outer is
    a number or a function of the angle (the fender tucks in above the arch, so the tube must stop short of it)."""
    bm = bmesh.new()
    res = bmesh.ops.create_circle(bm, cap_ends=True, segments=64, radius=rw)
    bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
    bmesh.ops.translate(bm, verts=res['verts'], vec=(0, inner, 0))
    a0, a1 = math.radians(-15), math.radians(195)
    n = 40
    ring = lambda y: [bm.verts.new((rw * math.cos(a0 + (a1 - a0) * i / n), y, rw * math.sin(a0 + (a1 - a0) * i / n))) for i in range(n + 1)]
    lo = ring(inner)
    hi = [bm.verts.new((rw * math.cos(a), outer(a) if callable(outer) else outer, rw * math.sin(a)))
          for a in (a0 + (a1 - a0) * i / n for i in range(n + 1))]
    for i in range(n):
        bm.faces.new((lo[i], lo[i + 1], hi[i + 1], hi[i]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


def caliper_bm(face_a, da):
    """Fixed caliper straddling the rotor edge behind the spokes: a rounded curved block over 56 deg with two
    piston housings standing out of its outer face, like C3's two-lobed caliper."""
    bm = bmesh.new()
    r0, r1 = 0.142, 0.232
    a0, a1 = da - 0.022, da + 0.045  # clear of the spoke face's back
    prof = [(r0, a0), (r1, a0), (r1, a1), (r0, a1)]
    vs = [bm.verts.new((r, a, 0)) for r, a in prof]  # in the XY plane at angle 0, spun about Y
    es = [bm.edges.new((p, q)) for p, q in zip(vs, vs[1:] + vs[:1])]
    span = math.radians(56)
    bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(-span / 2, 3, 'Y'))
    res = bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=span, steps=14)
    bmesh.ops.contextual_create(bm, geom=vs + es)
    last = [e for e in res['geom_last'] if isinstance(e, bmesh.types.BMEdge)]
    bmesh.ops.contextual_create(bm, geom=last)
    for deg in (-13, 13):
        c = Matrix.Rotation(math.radians(deg), 3, 'Y') @ Vector(((r0 + r1) / 2, 0, 0))
        res = bmesh.ops.create_cone(bm, cap_ends=True, segments=16, radius1=0.031, radius2=0.027, depth=0.016)
        bmesh.ops.rotate(bm, verts=res['verts'], cent=(0, 0, 0), matrix=Matrix.Rotation(-math.pi / 2, 3, 'X'))
        bmesh.ops.translate(bm, verts=res['verts'], vec=(c.x, a1 + 0.004, c.z))
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    return bm


wcoll = bpy.data.collections.new('wheels'); scene.collection.children.link(wcoll)
body = bpy.data.objects['body_retopo']
src = bpy.data.objects['body_src']
dg = bpy.context.evaluated_depsgraph_get()
body_bvh = BVHTree.FromObject(body.evaluated_get(dg), dg)  # body is at the origin, unrotated
sv = np.array([v.co[:] for v in src.data.vertices])
results = {}
for axle, x in (('F', AXLE_X), ('R', -AXLE_X)):
    # body side at this axle: widest body point beside the arch, between sill and shoulder height
    near = sv[(np.abs(sv[:, 0] - x) < R + 0.15) & (sv[:, 2] > 0.25) & (sv[:, 2] < 0.75)]
    side = np.abs(near[:, 1]).max()
    w = WIDTH[axle]
    yc = side - INSET - w / 2
    results[axle] = dict(body_side=round(float(side), 3), centre_y=round(float(yc), 3))
    for lr, s in (('L', 1), ('R', -1)):
        name = f'wheel_{axle}{lr}'
        bm, face_a, da = wheel_bm(w)
        if s < 0:
            bmesh.ops.scale(bm, vec=(1, -1, 1), verts=bm.verts)
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
        o = to_object(name, bm, ORDER, wcoll)
        o.location = (x, s * yc, R)
        cb = caliper_bm(face_a, da)
        bmesh.ops.rotate(cb, verts=cb.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(-math.radians(CALIPER_DEG), 3, 'Y'))
        if s < 0:
            bmesh.ops.scale(cb, vec=(1, -1, 1), verts=cb.verts)
            bmesh.ops.reverse_faces(cb, faces=cb.faces)
        for f in cb.faces: f.material_index = 0
        c = to_object(f'caliper_{axle}{lr}', cb, ['Caliper'], wcoll)
        c.location = o.location
        L = LINER[axle]
        inner_y = yc - (L['back'] or w / 2 + 0.03)

        def outer_y(a, x=x, side=side, inner_y=inner_y):
            # the body's outermost surface on a line through the fender just outside the arch cut, minus 6 mm
            p = Vector((x + 0.437 * math.cos(a), 3.0, R + 0.437 * math.sin(a)))
            hit = body_bvh.ray_cast(p, Vector((0, -1, 0)))
            y = hit[0].y - 0.006 if hit[0] is not None else inner_y
            return max(inner_y + 0.001, min(side - 0.004, y))
        wb = well_bm(inner_y, outer_y, L['rw'])
        if s < 0:
            bmesh.ops.scale(wb, vec=(1, -1, 1), verts=wb.verts)
            bmesh.ops.reverse_faces(wb, faces=wb.faces)
        for f in wb.faces: f.material_index = 0
        wl = to_object(f'wheelwell_{axle}{lr}', wb, ['Well'], wcoll)
        wl.location = (x, 0, R)
        wl.data.materials[0].use_backface_culling = False
        bv = c.modifiers.new('bevel', 'BEVEL'); bv.width = 0.01; bv.segments = 3
        for ob in (o, c):
            for p in ob.data.polygons: p.use_smooth = True
            bpy.context.view_layer.objects.active = ob
            for x2 in scene.objects: x2.select_set(x2 == ob)
            bpy.ops.object.shade_smooth_by_angle(angle=math.radians(35))

# clearance: tyre surface to the body, per wheel
bpy.context.view_layer.update()
dg = bpy.context.evaluated_depsgraph_get()
be = body.evaluated_get(dg)
bvh = BVHTree.FromObject(be, dg)
for name in ('wheel_FL', 'wheel_RL'):
    o = bpy.data.objects[name]
    pts = [o.matrix_world @ v.co for v in o.data.vertices if v.co.length > R - 0.03]
    d = [bvh.find_nearest(p)[3] for p in pts[::3]]
    inside = 0
    for p in pts[::6]:
        hit = bvh.ray_cast(p, Vector((0, 0, 1)))
        # inside the body if the first upward hit faces up (we are under a back face)
        if hit[0] is not None and hit[1].z > 0: inside += 1
    results[name] = dict(min_gap=round(min(d), 4), tyre_pts_inside_body=inside)
print('FIT', results)

pm = MATS['Paint']
body.data.materials.clear(); body.data.materials.append(pm)
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(out, 'gt-v4-wheels.blend'))
for o in scene.objects: o.select_set(o.name.startswith(('wheel_', 'caliper_', 'wheelwell_')))
bpy.ops.export_scene.gltf(filepath=os.path.join(out, 'wheels-v12.glb'), use_selection=True, export_apply=True)
print('DONE')
