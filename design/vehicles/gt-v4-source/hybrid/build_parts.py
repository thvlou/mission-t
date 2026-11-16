# blender -b <gt-v4-detail.blend> -P build_parts.py -- <hybrid dir>
# Detail pass 2: separate part meshes on the smooth GT v4 body, measured from the blueprints.
#   mirrors     side mirror heads (lofted superellipse sections, flat glass back) on a black stalk; A2/A5
#   lamps       decals: the lamp shapes of A3 (front) / A4 (rear) traced at sub-pixel accuracy, laid onto the body
#               along the view direction and lifted 1.5-3 mm. Game material names: TailLamp (brake glow),
#               CenterBrakeLamp, ReverseLamp (src/vehicle-rig.js), HeadLamp LED (tuned brighter in car-model.js)
#   exhaust_N   two polished lip rings (src/car-model.js keeps model pipes named exhaust_N, flames at their centre)
#   fins        five rear diffuser fins (A4 columns 345/535/767/1000/1190), front splitter blade (A2, A3)
#   louvres     nine engine deck slats over the recessed louvre panel (A5 columns 1114..1268)
# Everything is mirrored across y = 0, like the body. Writes gt-v4-parts.blend and parts.glb (parts only).
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

hyb = sys.argv[sys.argv.index('--') + 1:][0]
bp = os.path.join(os.path.dirname(hyb), 'blueprint')
scene = bpy.context.scene
body = bpy.data.objects['body_detail']
bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())
L = 4.736
K2, K5 = L / 1483, L / 1466
for o in [o for o in bpy.data.objects if o.get('gt4_part')]: bpy.data.objects.remove(o, do_unlink=True)


def srgb(c): c = c / 255; return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4


def material(name, rgb, rough, metal=0.0, emit=None, coat=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (*[srgb(c) for c in rgb], 1)
    b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    b.inputs['Coat Weight'].default_value = coat
    if emit:
        b.inputs['Emission Color'].default_value = (*[srgb(c) for c in emit[0]], 1)
        b.inputs['Emission Strength'].default_value = emit[1]
    return m


M = dict(
    paint=material('GT4 Paint Parts', (232, 232, 228), 0.28, coat=0.6),
    trim=material('GT4 Trim', (22, 23, 25), 0.5),
    carbon=material('GT4 Carbon', (30, 31, 34), 0.38, coat=0.3),
    mglass=material('GT4 Mirror Glass', (150, 156, 162), 0.04, metal=1.0),
    chrome=material('GT4 Exhaust Chrome', (222, 223, 226), 0.14, metal=1.0),
    soot=material('GT4 Exhaust Soot', (14, 14, 16), 0.7, metal=0.3),
    tail=material('TailLamp', (120, 6, 12), 0.12, emit=((255, 7, 20), 1.0)),
    center=material('CenterBrakeLamp', (110, 6, 12), 0.12, emit=((255, 7, 20), 1.0)),
    reverse=material('ReverseLamp', (215, 218, 222), 0.1, emit=((230, 242, 255), 1.0)),
    taillens=material('GT4 Tail Lens', (34, 6, 9), 0.05, coat=1.0),
    headlens=material('GT4 HeadLamp Lens', (16, 18, 22), 0.05, coat=1.0),
    led=material('GT4 HeadLamp LED', (240, 246, 255), 0.1, emit=((235, 244, 255), 2.0)),
    # windows: not named *glass*, so the game's glass tune (roughness 0.04, env x1.7) leaves them alone; that mirror
    # finish turned the light boxes of the environment into hard white blots that read as spilled paint
    # and satin (roughness 0.28, no coat): the game's environment has very bright light boxes overhead, and these
    # panes lean up a lot on this body, so a mirror finish turned them white from any raised camera
    glass=material('GT4 Window Screen', (12, 14, 17), 0.28),
    sideglass=material('GT4 Window Side', (24, 27, 32), 0.28),
)


def new_object(name, bm, mats, smooth=40):
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    for m in mats: me.materials.append(m)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o); o['gt4_part'] = 1
    for p in me.polygons: p.use_smooth = True
    if smooth:
        for x in scene.objects: x.select_set(x == o)
        bpy.context.view_layer.objects.active = o
        bpy.ops.object.shade_smooth_by_angle(angle=math.radians(smooth))
    return o


def mirrored(o, name):
    """Copy of o reflected across y = 0 (winding flipped so normals stay outward)."""
    me = o.data.copy(); me.name = name
    bm = bmesh.new(); bm.from_mesh(me)
    for v in bm.verts: v.co.y = -v.co.y
    bmesh.ops.reverse_faces(bm, faces=bm.faces[:])
    bm.to_mesh(me); bm.free()
    c = bpy.data.objects.new(name, me); scene.collection.objects.link(c); c['gt4_part'] = 1
    return c


def loft(bm, rings, cap0=None, cap1=None):
    """Faces between consecutive vertex rings (equal length, closed). cap: material index for an n-gon cap, or None."""
    vs = [[bm.verts.new(p) for p in r] for r in rings]
    n = len(rings[0])
    for a, b in zip(vs, vs[1:]):
        for i in range(n):
            bm.faces.new((a[i], a[(i + 1) % n], b[(i + 1) % n], b[i]))
    caps = []
    if cap0 is not None: f = bm.faces.new(vs[0][::-1]); f.material_index = cap0; caps.append(f)
    if cap1 is not None: f = bm.faces.new(vs[-1]); f.material_index = cap1; caps.append(f)
    return vs, caps


def superellipse(a, b, n=40, e=2.6):
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    c, s = np.cos(t), np.sin(t)
    return np.abs(c) ** (2 / e) * np.sign(c) * a, np.abs(s) ** (2 / e) * np.sign(s) * b


def ray(o, d):
    h = bvh.ray_cast(Vector(o), Vector(d))
    return (None, None) if h[0] is None else (np.array(h[0][:]), np.array(h[1][:]))


# ---------------------------------------------------------------- mirrors (A2 side, A5 top)
# head: x 0.52 (glass) .. 0.70 (nose), y 0.85 .. 1.02, z 0.824 .. 0.936; the outer end sweeps back.
# stalk: from the door shoulder (x 0.62..0.70, z 0.775) up to the head's lower inner side; black.
def build_mirror():
    bm = bmesh.new()
    XB, XF, YC, ZC, A, B, SWEEP = 0.52, 0.705, 0.935, 0.880, 0.085, 0.056, -0.15
    stations = [0, 0.012, 0.04, 0.09, 0.16, 0.26, 0.38, 0.5, 0.62, 0.73, 0.83, 0.91, 0.96, 0.99]
    rings = []
    for s in stations:
        if s < 0.04: k = 0.86 + 0.14 * math.sin(s / 0.04 * math.pi / 2)        # rolled rim round the glass
        else: k = (1 - ((s - 0.04) / 0.96) ** 2.2) ** (1 / 2.2)                  # rounded nose
        u, v = superellipse(A * k, B * k)
        x = XB + s * (XF - XB)
        rings.append([(x + SWEEP * uu, YC + uu, ZC + vv - 0.012 * s) for uu, vv in zip(u, v)])
    vs, caps = loft(bm, rings, cap0=1)
    tip = bm.verts.new((XF + 0.004, YC, ZC - 0.012))
    for i in range(len(vs[-1])):
        bm.faces.new((vs[-1][i], vs[-1][(i + 1) % len(vs[-1])], tip))
    for f in bm.faces:                                        # black lower shell, as drawn in A2
        if f.material_index == 0 and f.calc_center_median().z < ZC - 0.62 * B: f.material_index = 2
    # stalk: four elliptical sections, flared foot sunk into the door top
    st = []
    for (cx, cy, cz, rx, ry) in ((0.672, 0.828, 0.745, 0.058, 0.032), (0.668, 0.834, 0.776, 0.05, 0.027),
                                 (0.652, 0.857, 0.806, 0.034, 0.019), (0.635, 0.88, 0.842, 0.03, 0.017)):
        t = np.linspace(0, 2 * np.pi, 24, endpoint=False)
        st.append([(cx + rx * math.cos(a), cy + ry * math.sin(a), cz) for a in t])
    loft(bm, st)
    for f in bm.faces[-24 * 3:]: f.material_index = 2
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = new_object('mirror_L', bm, [M['paint'], M['mglass'], M['trim']])
    mirrored(o, 'mirror_R')


# ---------------------------------------------------------------- lamp decals (A3 front, A4 rear)
def load_rgb(name):
    img = bpy.data.images.load(os.path.join(bp, name))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); bpy.data.images.remove(img)
    return a.reshape(h, w, 4)[::-1, :, :3] * 255          # row 0 = top, sRGB 0..255


VIEW = {  # plane (u, v) -> (col, row), inverse, (axis of u, axis of v, ray axis), ray origin, ray direction
    'A3': (lambda y, z: (767.5 - y * 721, 880 - z * 585), lambda c, r: ((767.5 - c) / 721, (880 - r) / 585), (1, 2, 0), 4.0, -1.0),
    'A4': (lambda y, z: (767.5 + y * 691, 865 - z * 573), lambda c, r: ((c - 767.5) / 691, (865 - r) / 573), (1, 2, 0), -4.0, 1.0),
    'A2': (lambda x, z: (764.5 - x / K2, 691 - z / K2), lambda c, r: ((764.5 - c) * K2, (691 - r) * K2), (0, 2, 1), 3.0, -1.0),
    'A5': (lambda x, y: (765 - x / K5, 493 + y / K5), lambda c, r: ((765 - c) * K5, (r - 493) * K5), (0, 1, 2), 3.0, -1.0),
}


def shift_max(m, k):
    out = m.copy()
    for dy in range(-k, k + 1):
        for dx in range(-k, k + 1):
            out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


def close(m, k): return ~shift_max(~shift_max(m, k), k)


def fill_holes(m):
    """m plus every pixel not connected to the zone border through ~m."""
    free = ~m; seen = np.zeros_like(m)
    stack = [(i, j) for i in range(m.shape[0]) for j in (0, m.shape[1] - 1)] + [(i, j) for j in range(m.shape[1]) for i in (0, m.shape[0] - 1)]
    while stack:
        i, j = stack.pop()
        if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1]) or seen[i, j] or not free[i, j]: continue
        seen[i, j] = True
        stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    return ~seen


def blur(m, sigma=1.0):
    r = int(3 * sigma) + 1
    g = np.exp(-np.arange(-r, r + 1) ** 2 / (2 * sigma ** 2)); g /= g.sum()
    m = np.apply_along_axis(lambda v: np.convolve(v, g, 'same'), 0, m)
    return np.apply_along_axis(lambda v: np.convolve(v, g, 'same'), 1, m)


def decal(bm, view, zone, ind, mat_index, lift, step=0.004):
    """Lay the zone pixels where ind is True onto the body as a surface patch (sub-pixel outline). The patch is a grid
    in the drawing's plane; each vertex is cast onto the body along the view and lifted along the surface normal."""
    to_px, from_px, (iu, iv, iw), ox, dx = VIEW[view]
    c0, r0, c1, r1 = zone
    F = blur(ind.astype(float), 0.8)

    def Fs(y, z):
        c, r = to_px(y, z); c -= c0; r -= r0
        i, j = int(math.floor(r)), int(math.floor(c))
        if not (0 <= i < F.shape[0] - 1 and 0 <= j < F.shape[1] - 1): return 0.0
        fr, fc = r - i, c - j
        return (F[i, j] * (1 - fr) * (1 - fc) + F[i, j + 1] * (1 - fr) * fc + F[i + 1, j] * fr * (1 - fc) + F[i + 1, j + 1] * fr * fc)

    ya, za = from_px(c0, r1); yb, zb = from_px(c1, r0)
    ys = np.arange(min(ya, yb), max(ya, yb) + step, step); zs = np.arange(min(za, zb), max(za, zb) + step, step)
    inc = np.array([[Fs(y + step / 2, z + step / 2) > 0.5 for z in zs[:-1]] for y in ys[:-1]])
    if not inc.any(): return 0
    nb = np.zeros((len(ys), len(zs)), int)                 # included cells around each grid vertex
    for di in (0, 1):
        for dj in (0, 1):
            nb[di:di + inc.shape[0], dj:dj + inc.shape[1]] += inc
    pts = {}
    h = 0.25 / 691
    d = np.zeros(3); d[iw] = dx
    for i, j in zip(*np.nonzero(nb)):
        y, z = ys[i], zs[j]
        if nb[i, j] < 4:                                   # outline vertex: slide onto the 0.5 iso line
            y0, z0 = y, z
            for _ in range(6):
                f = Fs(y, z) - 0.5
                gy = (Fs(y + h, z) - Fs(y - h, z)) / (2 * h); gz = (Fs(y, z + h) - Fs(y, z - h)) / (2 * h)
                gg = gy * gy + gz * gz
                if gg < 1e-6: break
                y -= f * gy / gg; z -= f * gz / gg
                dd = math.hypot(y - y0, z - z0)
                if dd > 0.7 * step: y, z = y0 + (y - y0) * 0.7 * step / dd, z0 + (z - z0) * 0.7 * step / dd
        o = np.zeros(3); o[iu] = y; o[iv] = z; o[iw] = ox
        p, n = ray(o, d)
        if p is None: continue
        if n.dot(d) > 0: n = -n
        pts[i, j] = bm.verts.new(p + n * lift)
    count = 0
    for i, j in zip(*np.nonzero(inc)):
        q = [pts.get(k) for k in ((i, j), (i + 1, j), (i + 1, j + 1), (i, j + 1))]
        if None in q: continue
        f = bm.faces.new(q); f.material_index = mat_index; count += 1
        f.normal_update()
        if np.dot(f.normal, d) > 0: f.normal_flip()          # face the viewer of this drawing
    return count


def build_lamps():
    A3, A4 = load_rgb('gt-A3-front.png'), load_rgb('gt-A4-rear.png')

    def kinds(img, zone):
        c0, r0, c1, r1 = zone
        a = img[r0:r1, c0:c1]
        r, g, b = a[..., 0], a[..., 1], a[..., 2]
        lum = a.mean(2)
        return dict(red=(r > 110) & (r - g > 55) & (r - b > 45), dark=(lum < 110), bright=(lum > 175), lum=lum)

    # rear (A4, the +y half is left of column 767.5... mapping y = (col - 767.5) / 691, so take the right half)
    bm = bmesh.new()
    n = {}
    zone = (767, 432, 1375, 540)                            # upper tail lamp and the full-width bar
    k = kinds(A4, zone)
    lens = close(k['dark'] | k['red'], 3)
    rows = np.arange(zone[1], zone[3])[:, None]
    lens &= (rows < 482) | (rows > 489)                     # paint gap between the two lamps
    n['tail'] = decal(bm, 'A4', zone, k['red'], 1, 0.003, 0.003)
    n['taillens'] = decal(bm, 'A4', zone, lens & ~k['red'], 0, 0.0018, 0.004)
    zone = (767, 356, 870, 378)                             # centre brake lamp on the deck lid
    n['center'] = decal(bm, 'A4', zone, kinds(A4, zone)['red'], 2, 0.002, 0.002)
    zone = (1050, 632, 1132, 664)                           # reverse lamps in the diffuser mesh
    n['reverse'] = decal(bm, 'A4', zone, close(kinds(A4, zone)['lum'] > 105, 2), 3, 0.002, 0.003)   # grey-white, lum 120..190
    o = new_object('lamps_rear_L', bm, [M['taillens'], M['tail'], M['center'], M['reverse']], smooth=None)
    mirrored(o, 'lamps_rear_R')
    # front (A3: y = (767.5 - col) / 721, the +y half is the left of the image)
    bm = bmesh.new()
    zone = (140, 500, 430, 632)
    k = kinds(A3, zone)
    lens = fill_holes(close(k['dark'], 4))
    led = shift_max(~shift_max(~(k['bright'] & lens), 2), 2)          # opening: the three LED blocks, not glints
    n['headlens'] = decal(bm, 'A3', zone, lens, 0, 0.0018, 0.004)
    n['led'] = decal(bm, 'A3', zone, led, 1, 0.0032, 0.002)
    o = new_object('headlamp_L', bm, [M['headlens'], M['led']], smooth=None)
    mirrored(o, 'headlamp_R')
    print('LAMP faces', n)


# ---------------------------------------------------------------- exhaust (A4: centres col 702/832, row 665)
def build_exhaust():
    for idx, y in ((1, -0.095), (2, 0.095)):
        z = (865 - 665) / 573
        p, _ = ray((-4, y, z), (1, 0, 0))
        xt = p[0] - 0.018                                    # the lip stands 18 mm proud of the bumper
        lip = [(0.06, 0.066), (0.012, 0.0665), (0.003, 0.065), (0.0, 0.062), (0.001, 0.058), (0.006, 0.0555), (0.03, 0.055)]
        soot = [(0.03, 0.055), (0.09, 0.054), (0.09, 0.0)]
        for name, prof, mi in ((f'exhaust_{idx}', lip, 0), (f'exhaust_{idx}_soot', soot, 0)):
            bm = bmesh.new()
            t = np.linspace(0, 2 * np.pi, 40, endpoint=False)
            rings = [[(xt + dx, y + r * math.cos(a), z + r * math.sin(a)) for a in t] for dx, r in prof if r > 0]
            vs, _ = loft(bm, rings, cap1=0 if name.endswith('soot') else None)
            bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
            if name.endswith('soot'): bmesh.ops.reverse_faces(bm, faces=bm.faces[:])   # seen from inside the pipe
            new_object(name, bm, [M['chrome'] if mi == 0 and not name.endswith('soot') else M['soot']], smooth=60)


# ---------------------------------------------------------------- diffuser fins and splitter
def under(x, y, cap):
    p, _ = ray((x, y, 0.0), (0, 0, 1))
    return cap if p is None else min(p[2], cap)


def build_fins():
    bm = bmesh.new()
    # thin plates with a level bottom at floor height: the underside ramps up behind them, so they read as
    # vanes in the diffuser tunnel (a bottom dipping below the floor read as teeth from behind, in game)
    for y, x0, t_top, t_bot in ((0.0, -1.70, 0.014, 0.012), (0.336, -1.72, 0.014, 0.012), (0.611, -1.95, 0.016, 0.014)):
        x1 = -2.29
        xs = np.linspace(x0, x1, 14)
        z_bot0 = under(x0, y, 0.3) - 0.004
        rings = []
        for x in xs:
            top = under(x, y, 0.34) + 0.012
            bot = min(z_bot0, top - 0.006)
            rings.append([(x, y - t_top / 2, top), (x, y - t_bot / 2, bot), (x, y + t_bot / 2, bot), (x, y + t_top / 2, top)])
        loft(bm, rings, cap0=0, cap1=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    o = new_object('diffuser_fins_L', bm, [M['carbon']], smooth=30)
    m = mirrored(o, 'diffuser_fins_R')
    # the centre fin is on both halves: drop it from the mirror copy
    bm = bmesh.new(); bm.from_mesh(m.data)
    bmesh.ops.delete(bm, geom=[v for v in bm.verts if abs(v.co.y) < 0.03], context='VERTS')
    bm.to_mesh(m.data); bm.free()


def build_splitter():
    # blade under the front bumper: z 0.12 .. 0.165, 30 mm ahead of the bumper face at z 0.17, back to x 1.86
    # the surfaced body (build_surface.py, NOTES 18) carries its own blade at z 0.072 .. 0.104: then none here
    p, _ = ray((2.05, 0.3, 0.0), (0, 0, 1))
    if p is not None and p[2] < 0.112:
        print('SPLITTER on the body already: skipped'); return
    ys = np.linspace(0, 0.93, 32)
    xf = []
    for y in ys:
        p, _ = ray((4, y, 0.17), (-1, 0, 0))
        xf.append(p[0] + 0.03 if p is not None and p[0] > 1.9 else None)
    last = max(i for i, v in enumerate(xf) if v is not None)
    xf = np.array([v if v is not None else 1.95 for v in xf[:last + 1]]); ys = ys[:last + 1]
    xf = np.convolve(np.pad(xf, 2, mode='edge'), np.ones(5) / 5, 'valid')
    rings = []
    for y, x in zip(ys, xf):
        x = max(x, 1.93)
        rings.append([(1.86, y, 0.165), (x - 0.014, y, 0.165), (x, y, 0.146), (x - 0.006, y, 0.12), (1.86, y, 0.12)])
    # rounded outer end
    y_end, x_end = ys[-1], xf[-1]
    rings.append([(1.86, y_end + 0.02, 0.16), (x_end - 0.03, y_end + 0.02, 0.16), (x_end - 0.022, y_end + 0.02, 0.145),
                  (x_end - 0.026, y_end + 0.02, 0.125), (1.86, y_end + 0.02, 0.125)])
    rings = [[(p[0], -p[1], p[2]) for p in r] for r in rings[:0:-1]] + rings
    bm = bmesh.new()
    loft(bm, rings, cap0=0, cap1=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    new_object('splitter', bm, [M['carbon']], smooth=35)


# ---------------------------------------------------------------- engine deck louvres (A5)
def build_louvres():
    bm = bmesh.new()
    H, T, TILT = 0.028, 0.006, math.radians(35)            # slat height, thickness, lean towards the tail
    ys = np.linspace(-0.355, 0.355, 25)
    for i in range(9):
        x = (765 - (1114 + 19.25 * i)) * K5
        rings = []
        for y in ys:
            p, _ = ray((x, y, 3), (0, 0, -1))
            top = p[2] + 0.011                               # flush with the deck around the 14 mm recess
            bx = -math.sin(TILT) * H; bz = -math.cos(TILT) * H
            rings.append([(x - T / 2, y, top), (x + T / 2, y, top), (x + T / 2 + bx, y, top + bz), (x - T / 2 + bx, y, top + bz)])
        loft(bm, rings, cap0=0, cap1=0)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    new_object('louvres', bm, [material('GT4 Louvre', (12, 12, 14), 0.62)], smooth=30)


def refit_liners():
    """The arch liners (build_wheels.py) were fitted to the old placeholder body: move each liner tube's outer rim
    to 6 mm inside this body's surface, on a line through the fender just outside the arch cut (as build_wheels)."""
    for o in [o for o in scene.objects if o.name.startswith('wheelwell_')]:
        ys = [abs(v.co.y) for v in o.data.vertices]
        inner = min(ys); s = 1 if o.data.vertices[0].co.y > 0 else -1
        hx, hz = o.location.x, o.location.z
        moved = 0
        for v in o.data.vertices:
            if abs(v.co.y) < inner + 0.0015: continue
            a = math.atan2(v.co.z, v.co.x)
            p, _ = ray((hx + 0.437 * math.cos(a), s * 3.0, hz + 0.437 * math.sin(a)), (0, -s, 0))
            y = abs(p[1]) - 0.006 if p is not None else inner + 0.001
            v.co.y = s * max(inner + 0.001, y); moved += 1
        o.data.update()
        print('LINER', o.name, 'outer rim', moved, 'verts, |y| up to', round(max(abs(v.co.y) for v in o.data.vertices), 3))


def load_mask(name):
    img = bpy.data.images.load(os.path.join(hyb, 'tex', f'mask-{name}.png'))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); bpy.data.images.remove(img)
    return np.rint(a.reshape(h, w, 4)[::-1, :, 0] * 255).astype(np.uint8)   # row 0 = top, class ids (masks.py)


def component(m, seed):
    """The 4-connected part of m that holds seed (row, col)."""
    out = np.zeros_like(m); stack = [seed]
    while stack:
        i, j = stack.pop()
        if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1]) or out[i, j] or not m[i, j]: continue
        out[i, j] = True
        stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    return out


# ---------------------------------------------------------------- glazing (A5 windscreen, A2 side windows)
# The windows were only texture classes on the body, so their edges followed texel votes over a fitted surface and
# ran like wet paint, and the glass took the paint's clearcoat and flake. Now each pane is its own mesh cast from the
# drawing's clean outline (sub-pixel, like the lamps), 3 mm proud of the body, in a glass material the game tunes as
# glass. The body under it stays dark, so the 1 cm the panes are inset shows as a black frame (frit).
GLASS_INSET = 3   # px, ~1 cm
SHIELD_NZ = 0.45  # windscreen faces must look up this much (build_bake.py frames it from 0.40)
def build_glass():
    m5 = load_mask('A5')
    glass5 = m5 == 2
    shield = component(glass5, (493, 560))                       # the windscreen, between the pillar strips
    shield = ~shift_max(~shield, GLASS_INSET)
    rows, cols = np.nonzero(shield)
    zone = (cols.min() - 4, rows.min() - 4, cols.max() + 5, rows.max() + 5)
    bm = bmesh.new()
    n_front = decal(bm, 'A5', zone, shield[zone[1]:zone[3], zone[0]:zone[2]], 0, 0.003, 0.012)
    new_object('glass_front', bm, [M['glass']], smooth=None)
    m2 = load_mask('A2')
    pane = ~shift_max(~(m2 == 7), GLASS_INSET)                   # sideglass (masks.py SIDE_PANE)
    rows, cols = np.nonzero(pane)
    zone = (cols.min() - 4, rows.min() - 4, cols.max() + 5, rows.max() + 5)
    bm = bmesh.new()
    n_side = decal(bm, 'A2', zone, pane[zone[1]:zone[3], zone[0]:zone[2]], 0, 0.003, 0.012)
    o = new_object('glass_side_L', bm, [M['sideglass']], smooth=None)
    mirrored(o, 'glass_side_R')
    # Cast straight down, the windscreen's wrap-round corners get long, steep cells that cut under the curved body (a
    # white wedge showed through). Subdivide once and shrinkwrap 4 mm outside the body: every pane rides on it.
    for name in ('glass_front', 'glass_side_L', 'glass_side_R'):
        g = bpy.data.objects[name]
        for x in scene.objects: x.select_set(x == g)
        bpy.context.view_layer.objects.active = g
        sd = g.modifiers.new('subd', 'SUBSURF'); sd.subdivision_type = 'SIMPLE'; sd.levels = 1
        sw = g.modifiers.new('wrap', 'SHRINKWRAP'); sw.target = body; sw.wrap_method = 'NEAREST_SURFACEPOINT'
        sw.wrap_mode = 'OUTSIDE_SURFACE'; sw.offset = 0.004
        for mname in ('subd', 'wrap'): bpy.ops.object.modifier_apply(modifier=mname)
    # this body's windscreen wraps further round than the drawing: from above, the screen also caught a strip of the
    # cabin's side face, and between the two the pillar showed as an oval. The screen keeps only faces that look up
    # (normal z > SHIELD_NZ); the corner becomes one A-pillar (build_bake.py paints it, with a frame band below 0.45).
    g = bpy.data.objects['glass_front']
    bm = bmesh.new(); bm.from_mesh(g.data)
    bmesh.ops.delete(bm, geom=[f for f in bm.faces if f.normal.z < SHIELD_NZ], context='FACES')
    bm.to_mesh(g.data); bm.free()
    # Snapped to the body, the side panes took its last few millimetres of waviness, and the environment's light boxes
    # ran down them in streaks. Real panes are smooth: each is fitted to a quadratic y = f(x, z) and then lifted along that surface's mean normal until no vertex is within
    # 3 mm of the body. The body under a pane is the dark frame, so a slightly floating edge does not show.
    # (the screen stays snapped: its double curvature needs more than a low-order fit, 10 mm rms, and its reflections
    # were already clean in the game)
    for name, terms, axis in (('glass_side_L', lambda a, b: [a ** 0, a, b, a * a, a * b, b * b], 1),):
        o = bpy.data.objects[name]; me = o.data
        P = np.array([v.co[:] for v in me.vertices])
        uv = [0, 1] if axis == 2 else [0, 2]
        A = np.stack(terms(P[:, uv[0]], P[:, uv[1]]), 1)
        coef, *_ = np.linalg.lstsq(A, P[:, axis], rcond=None)
        rms = float(np.sqrt(np.mean((A @ coef - P[:, axis]) ** 2)))
        P[:, axis] = A @ coef
        me.vertices.foreach_set('co', P.ravel()); me.update()
        nrm = np.mean([p.normal[:] for p in me.polygons], 0); nrm /= np.linalg.norm(nrm)
        worst = 0.0
        for v in P:
            loc, n, _, _ = bvh.find_nearest(Vector(v))
            if loc is None: continue
            d = (Vector(v) - loc).dot(n)
            worst = max(worst, 0.003 - d)
        P += nrm * worst
        me.vertices.foreach_set('co', P.ravel()); me.update()
        print('GLASS fit', name, 'rms', round(rms * 1000, 2), 'mm, lifted', round(worst * 1000, 1), 'mm')
    bpy.data.objects.remove(bpy.data.objects['glass_side_R'], do_unlink=True)
    mirrored(bpy.data.objects['glass_side_L'], 'glass_side_R')
    print('GLASS faces', n_front, n_side, 'windscreen kept', len(g.data.polygons))


refit_liners()
build_glass()
build_mirror()
build_lamps()
build_exhaust()
build_fins()
build_splitter()
build_louvres()
parts = [o for o in scene.objects if o.get('gt4_part')]
print('PARTS', {o.name: len(o.data.polygons) for o in parts})
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(hyb, 'gt-v4-parts.blend'))
for o in scene.objects: o.select_set(o in parts)
bpy.ops.export_scene.gltf(filepath=os.path.join(hyb, 'parts.glb'), use_selection=True, export_apply=True)
print('DONE')
