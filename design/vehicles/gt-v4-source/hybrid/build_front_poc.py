# blender --factory-startup -b -P build_front_poc.py -- <hybrid dir> <body blend> <body object> <out blend>
# Front-quarter proof of concept (NOTES 19): the clean surfaced body (s4) carved with real geometry where the drawings
# show features, instead of painting them on: crisp panel gaps, a headlamp pocket with lens and LED modules, the
# intakes as open pockets with a honeycomb grille, hood vents. The aim is the hard-surface read of a hand-built car
# model (separate shut lines with turned edges, recessed lamps, deep intakes), not a melted clay surface.
#   feature lines are traced off the drawings (pixel coordinates below) and projected onto the body along each view:
#     A5 top (rays down): hood shut lines, hood front edge, hood vents
#     A3 front (rays along -x): headlamp outline and LEDs, link line from hood corner to lamp, lamp brow line,
#                               central and corner intakes
#     A2 side (rays along -y): front fender / door cut, line from the lamp's rear tip to the arch
#   gaps: a 3.5 mm strip cutter following the surface (6 mm out .. 12 mm in along the normal), boolean-subtracted;
#   pockets: the outline on the surface down to a floor pushed in along the local inward normal; the cut faces take the
#   cutters' dark material; then a 1.6 mm bevel on every sharp new edge (crisp but not knife-thin), weighted normals.
# Everything is built for +y and mirrored. Materials are render materials for the review (GT Paint / Gap / Lens / LED
# / Grille / Glass); the game chain is not touched.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree

hyb, body_blend, body_name, out_blend = sys.argv[sys.argv.index('--') + 1:][:4]
# POC_GAME=1: the game build (NOTES 19-7): feature lines sampled every 4 px (~1.3 cm) instead of 1.5, one bevel segment,
# coarser honeycomb. The review build's grooves alone were ~200k triangles.
GAME = os.environ.get('POC_GAME') == '1'
STEP_PX = 4.0 if GAME else 1.5
L = 4.736; K2, K5 = L / 1483, L / 1466
scene = bpy.context.scene
for o in list(scene.objects): bpy.data.objects.remove(o, do_unlink=True)
with bpy.data.libraries.load(body_blend) as (src, dst):
    dst.objects = [body_name]
body = dst.objects[0]; scene.collection.objects.link(body)
body.name = 'body_front'
bpy.context.view_layer.update()
src_bvh = BVHTree.FromObject(body, bpy.context.evaluated_depsgraph_get())


def mat(name, rgb, rough, metal=0.0, emit=0.0, coat=0.0, alpha=1.0, transm=0.0):
    m = bpy.data.materials.get(name) or bpy.data.materials.new(name)
    m.use_nodes = True
    b = next(n for n in m.node_tree.nodes if n.type == 'BSDF_PRINCIPLED')
    b.inputs['Base Color'].default_value = (*rgb, 1); b.inputs['Roughness'].default_value = rough
    b.inputs['Metallic'].default_value = metal
    if coat: b.inputs['Coat Weight'].default_value = coat; b.inputs['Coat Roughness'].default_value = 0.03
    if emit: b.inputs['Emission Color'].default_value = (*rgb, 1); b.inputs['Emission Strength'].default_value = emit
    if transm: b.inputs['Transmission Weight'].default_value = transm
    if alpha < 1: b.inputs['Alpha'].default_value = alpha
    return m


M_PAINT = mat('GT Paint', (0.82, 0.82, 0.80), 0.32, coat=1.0)
M_GAP = mat('GT Gap', (0.012, 0.012, 0.014), 0.55)
M_POCKET = mat('GT Housing', (0.02, 0.022, 0.026), 0.35, metal=0.3)
M_LENS = mat('GT Lens', (0.9, 0.92, 0.95), 0.02, alpha=0.18, transm=1.0)
M_LED = mat('GT LED', (1.0, 0.98, 0.95), 0.2, emit=1.8)
M_BEZEL = mat('GT Bezel', (0.06, 0.065, 0.07), 0.18, metal=1.0)
M_GRILLE = mat('GT Grille', (0.015, 0.015, 0.017), 0.6)
M_GLASS = mat('GT Glass', (0.01, 0.012, 0.015), 0.05, metal=0.2)
M_TAIL = mat('GT TailLamp', (0.9, 0.03, 0.03), 0.25, emit=3.0)
M_TAIL_LENS = mat('GT Tail Lens', (0.45, 0.015, 0.02), 0.32, alpha=0.6, transm=0.5)
M_METAL = mat('GT Exhaust', (0.85, 0.85, 0.86), 0.12, metal=1.0)
body.data.materials.clear(); body.data.materials.append(M_PAINT)


# ---------------------------------------------------------------- drawing coordinates -> surface points
def ray_hit(o, d):
    h = src_bvh.ray_cast(Vector(o), Vector(d))
    return (None, None) if h[0] is None else (np.array(h[0][:]), np.array(h[1][:]))


def px_ray(view, c, r):
    if view == 'A3': return (4.0, (767.5 - c) / 721, (880 - r) / 585), (-1, 0, 0)
    if view == 'A5': return ((765 - c) * K5, (r - 493) * K5, 3.0), (0, 0, -1)
    if view == 'A2': return ((764.5 - c) * K2, 3.0, (691 - r) * K2), (0, -1, 0)
    if view == 'A4': return (-4.0, (767.5 - c) / 691, (865 - r) / 573), (1, 0, 0)   # left half of the rear view -> +y (mirrored anyway)


def to_px(view, p):
    if view == 'A3': return 767.5 - p[1] * 721, 880 - p[2] * 585
    if view == 'A4': return 767.5 - p[1] * 691, 865 - p[2] * 573


def dense(poly, step, closed=False):
    poly = np.asarray(poly, float)
    if closed: poly = np.vstack([poly, poly[:1]])
    seg = np.linalg.norm(np.diff(poly, axis=0), axis=1); s = np.concatenate([[0], np.cumsum(seg)])
    t = np.arange(0, s[-1], step) if closed else np.linspace(0, s[-1], max(2, int(s[-1] / step) + 1))
    return np.stack([np.interp(t, s, poly[:, k]) for k in range(2)], 1)


def chaikin(poly, it=2, closed=False):
    p = np.asarray(poly, float)
    for _ in range(it):
        q = [] if closed else [p[0]]
        pts = np.vstack([p, p[:1]]) if closed else p
        for a, b in zip(pts[:-1], pts[1:]): q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        if not closed: q.append(p[-1])
        p = np.array(q)
    return p


def project(view, poly, step_px=None, closed=False):
    step_px = step_px or STEP_PX
    P, N = [], []
    for c, r in dense(poly, step_px, closed):
        o, d = px_ray(view, c, r); p, n = ray_hit(o, d)
        if p is not None: P.append(p); N.append(n)
    return np.array(P), np.array(N)


# ---------------------------------------------------------------- cutters
def strip_cutter(P, N, width=0.0035, out=0.006, depth=0.012, name='gap', closed=False):
    """closed thin solid following surface points P (normals N): the panel gap (a ring when the line is closed)"""
    bm = bmesh.new(); rings = []
    T = (np.roll(P, -1, 0) - np.roll(P, 1, 0)) if closed else np.gradient(P, axis=0)
    for p, n, t in zip(P, N, T):
        b = np.cross(n, t); b /= np.linalg.norm(b) + 1e-12
        rings.append([bm.verts.new(tuple(p + n * out + b * width / 2)), bm.verts.new(tuple(p + n * out - b * width / 2)),
                      bm.verts.new(tuple(p - n * depth - b * width / 2)), bm.verts.new(tuple(p - n * depth + b * width / 2))])
    pairs = list(zip(rings[:-1], rings[1:])) + ([(rings[-1], rings[0])] if closed else [])
    for a, b_ in pairs:
        for k in range(4): bm.faces.new((a[k], a[(k + 1) % 4], b_[(k + 1) % 4], b_[k]))
    if not closed: bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    return finish(bm, name, M_GAP)


def pocket_cutter(P, N, depth, inward=None, name='pocket', material=None, out=0.05):
    """closed prism along the inward direction: outline ring pulled 5 cm out of the body, floor ring pushed in;
    caps fanned to the rings' centroids (a cap fanned to a point near a curved surface could dip into the body)"""
    bm = bmesh.new()
    nav = N.mean(0); nav /= np.linalg.norm(nav)
    d_in = -nav if inward is None else np.asarray(inward, float)
    top = [bm.verts.new(tuple(p - d_in * out)) for p in P]
    bot = [bm.verts.new(tuple(p + d_in * depth)) for p in P]
    k = len(P)
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((top[i], top[j], bot[j], bot[i]))
    ct = bm.verts.new(tuple(P.mean(0) - d_in * out)); cb = bm.verts.new(tuple(P.mean(0) + d_in * depth))
    for i in range(k):
        j = (i + 1) % k
        bm.faces.new((top[j], top[i], ct)); bm.faces.new((bot[i], bot[j], cb))
    return finish(bm, name, material or M_POCKET)


def pocket_filled(view, outline_px, depth, inward, name, material=None, out=0.05):
    d = np.asarray(inward, float) / np.linalg.norm(inward)
    poly = dense(chaikin(outline_px, 1, closed=True), 2.0, closed=True)
    bm = bmesh.new()
    f = bm.faces.new([bm.verts.new((c, r, 0.0)) for c, r in poly])
    bmesh.ops.triangulate(bm, faces=[f], quad_method='BEAUTY', ngon_method='BEAUTY')
    for _ in range(4):
        long_ = [e for e in bm.edges if e.calc_length() > 6.0]
        if not long_: break
        bmesh.ops.subdivide_edges(bm, edges=long_, cuts=1, use_grid_fill=True)
    for v in bm.verts:
        o_, dd = px_ray(view, v.co.x, v.co.y); p_, n_ = ray_hit(o_, dd)
        if p_ is None:                                        # off the body: keep it on the view plane behind the face
            p_ = np.array(o_) + np.array(dd) * 1.8
        v.co = Vector(p_ - d * out)
    ext = bmesh.ops.extrude_face_region(bm, geom=bm.faces[:])
    bmesh.ops.translate(bm, vec=Vector(d * (out + depth)), verts=[g for g in ext['geom'] if isinstance(g, bmesh.types.BMVert)])
    return finish(bm, name, material or M_POCKET)


def finish(bm, name, material):
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(material)
    o = bpy.data.objects.new(name, me); cutters.objects.link(o)
    return o


def mirror_obj(o):
    c = o.copy(); c.data = o.data.copy(); c.name = o.name + '_R'
    for v in c.data.vertices: v.co.y = -v.co.y
    c.data.flip_normals(); o.users_collection[0].objects.link(c); return c


cutters = bpy.data.collections.new('cutters'); scene.collection.children.link(cutters)


def load_mask(name):
    img = bpy.data.images.load(os.path.join(hyb, 'tex', f'mask-{name}.png'))
    w, h = img.size; a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a); bpy.data.images.remove(img)
    return np.rint(a.reshape(h, w, 4)[::-1, :, 0] * 255).astype(np.uint8)


def inside(poly, X, Y):
    """vectorised even-odd test of points (X, Y) against polygon poly (k x 2)"""
    X = np.asarray(X, float); Y = np.asarray(Y, float); c = np.zeros(X.shape, bool)
    for (x1, y1), (x2, y2) in zip(poly, np.roll(poly, -1, 0)):
        m = (y1 > Y) != (y2 > Y)
        xi = x1 + (Y - y1) * (x2 - x1) / (y2 - y1 + 1e-12)
        c ^= m & (X < xi)
    return c


def flood(m, seed):
    out = np.zeros_like(m); st = [seed]
    while st:
        i, j = st.pop()
        if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1]) or out[i, j] or not m[i, j]: continue
        out[i, j] = True; st += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    return out


m5, m2 = load_mask('A5'), load_mask('A2')
ws = flood(m5 == 2, (493, 560))
wcols = np.flatnonzero(ws.any(0))[::5]
WS_A5 = [(c, np.flatnonzero(ws[:, c])[0] + 2) for c in wcols] + [(c, np.flatnonzero(ws[:, c])[-1] - 2) for c in wcols[::-1]]
SIDE_PANE = [(700, 331), (760, 331), (830, 334), (892, 340), (897, 421), (760, 425), (617, 429)]   # masks.py
NOMIRROR = ('pocket_intake', 'gap_windscreen')

# A5 plan: hood shut line (front corner -> windscreen base), hood front edge (corner -> centre)
SHUT_A5 = [(120, 626), (150, 635), (200, 647.5), (250, 657.5), (300, 669), (350, 680), (400, 692.5), (452, 702)]
FRONT_A5 = [(120, 626), (112.5, 610), (107, 585), (104.5, 550), (104, 520), (104, 493)]
VENT_A5 = [(272, 603), (300, 609), (336, 622), (347, 633), (338, 638), (300, 630), (274, 616)]
# A3 front: headlamp outline, LEDs, central and corner intakes, lamp brow
LAMP_A3 = [(152.5, 512.5), (200, 526.5), (290, 555), (365, 572.5), (385, 587.5), (405, 605), (416, 619), (400, 620),
           (340, 602.5), (270, 590), (205, 580), (172.5, 575), (160, 545)]
LEDS_A3 = [((209, 544), (242, 561)), ((256, 557), (291, 573)), ((304, 570), (338, 586))]
BROW_A3 = [(86, 489), (120, 500), (152.5, 512.5)]
INTAKE_A3 = [(400, 703), (560, 699), (767.5, 697), (767.5, 792), (560, 792), (446, 792), (430, 760)]
CORNER_A3 = [(222, 662), (245, 656), (292, 690), (296, 705), (268, 785), (232, 798), (200, 798), (212, 712)]
# A2 side: fender / door cut, lamp rear tip to the arch
DOOR_A2 = [(500, 450), (484, 470), (476, 495), (472, 525), (472, 555), (476, 590), (480, 620)]
LAMPLINE_A2 = [(165, 467), (200, 462), (232, 459)]

parts = []
P, N = project('A5', chaikin(SHUT_A5, 2)); shut = P; parts.append(strip_cutter(P, N, name='gap_hood_shut'))
P, N = project('A5', chaikin(FRONT_A5, 2)); front_P = P; parts.append(strip_cutter(P, N, name='gap_hood_front'))
corner = shut[0]
lamp_P, lamp_N = project('A3', chaikin(LAMP_A3, 2, closed=True), closed=True)
# link line: hood corner -> lamp inner-top corner, in the front view's pixel space
c_px = to_px('A3', corner); lt = (365, 572.5)
P, N = project('A3', [c_px, ((c_px[0] + lt[0]) / 2, (c_px[1] + lt[1]) / 2 - 1.5), lt]); parts.append(strip_cutter(P, N, name='gap_lamp_link'))
P, N = project('A3', chaikin(BROW_A3, 1)); parts.append(strip_cutter(P, N, name='gap_lamp_brow'))
P, N = project('A2', chaikin(DOOR_A2, 2)); parts.append(strip_cutter(P, N, name='gap_door'))
P, N = project('A2', chaikin(LAMPLINE_A2, 1)); parts.append(strip_cutter(P, N, name='gap_lamp_rear'))
# the bumper's rear end on the side, from the brow line's end down to the sill (the bumper is a panel of its own)
BUMPER_X = 1.95
P, N = project('A2', [(764.5 - BUMPER_X / K2, 480), (764.5 - (BUMPER_X - 0.01) / K2, 560), (764.5 - (BUMPER_X - 0.03) / K2, 652)])
parts.append(strip_cutter(P, N, name='gap_bumper_side'))
# flush door handle: a shallow rounded slot on the door (A2 x 0.08 .. 0.25 m, z 0.775 m)
HANDLE_A2 = [(690, 447), (735, 445), (739, 449), (735, 453), (690, 451), (687, 449)]
P, N = project('A2', chaikin(HANDLE_A2, 2, closed=True), closed=True)
parts.append(pocket_cutter(P, N, 0.007, name='pocket_handle', material=M_GAP))
parts.append(pocket_cutter(lamp_P, lamp_N, 0.028, name='pocket_lamp'))
vent_P, vent_N = project('A5', chaikin(VENT_A5, 2, closed=True), closed=True)
parts.append(pocket_cutter(vent_P, vent_N, 0.030, name='pocket_vent', material=M_GRILLE))
INTAKE_FULL = INTAKE_A3[:2] + [(1535 - c, r) for c, r in INTAKE_A3[:2][::-1]] + [(1535 - c, r) for c, r in INTAKE_A3[4:][::-1]] + INTAKE_A3[4:]
in_P, in_N = project('A3', chaikin(INTAKE_FULL, 1, closed=True), closed=True)
parts.append(pocket_cutter(in_P, in_N, 0.11, inward=(-1, 0, 0), name='pocket_intake'))
P, N = project('A5', chaikin(WS_A5, 2, closed=True), closed=True); ws_poly = np.array([(p[0], p[1]) for p in P])
parts.append(strip_cutter(P, N, width=0.004, name='gap_windscreen', closed=True))
P, N = project('A2', chaikin(SIDE_PANE, 2, closed=True), closed=True); side_poly = np.array([(p[0], p[2]) for p in P])
parts.append(strip_cutter(P, N, width=0.004, name='gap_sideglass', closed=True))
co_P, co_N = project('A3', chaikin(CORNER_A3, 2, closed=True), closed=True)
parts.append(pocket_cutter(co_P, co_N, 0.09, inward=(-0.9, -0.43, 0) / np.linalg.norm((-0.9, -0.43, 0)), name='pocket_corner'))
# ---------------------------------------------------------------- side and rear (NOTES 19-4)
# A2 side: door rear cut (B-pillar line), slanted side intake behind the door, sill / skirt line, quarter glass
DOORREAR_A2 = [(972, 310), (945, 365), (922, 420), (917, 470), (914, 520), (905, 580), (878, 612)]
SIDEINTAKE_A2 = [(1010, 478), (1030, 474), (1040, 480), (1000, 525), (955, 572), (940, 574), (933, 568), (975, 520)]
SILL_A2 = [(470, 600), (600, 599), (800, 599), (1000, 599), (1088, 596)]
QUARTER_A2 = [(952, 325), (1030, 340), (1060, 385), (960, 392), (940, 360)]
# A5 top: engine lid outline, louvre panel, small vent, centre brake lamp
LID_A5 = [(1000, 362), (1290, 352), (1328, 400), (1338, 493), (1328, 586), (1290, 634), (1000, 624)]
LOUVRE_A5 = [(1064, 379), (1285, 395), (1300, 420), (1300, 566), (1285, 591), (1064, 605), (1060, 590), (1060, 394)]
SMALLVENT_A5 = [(1010, 474), (1043, 476), (1045, 513), (1010, 515)]
CHMSL_A5 = [(1333, 447), (1339, 447), (1339, 539), (1333, 539)]
# A4 rear: upper tail lamp, light bar, haunch line, rear bumper top edge, diffuser mesh, exhausts
TAIL_A4 = [(172, 442), (250, 445), (330, 448), (412, 452), (395, 465), (377, 477), (300, 478), (220, 476), (195, 470), (175, 458)]
BAR_A4 = [(275, 500), (767.5, 500), (1260, 500), (1273, 507), (1272, 527), (1265, 536), (767.5, 536), (270, 536), (262, 527), (263, 507)]
HAUNCH_A4 = [(355, 350), (390, 372), (415, 400), (415, 430), (412, 452)]
RBUMPER_A4 = [(340, 556), (500, 558), (767.5, 560)]
DIFF_A4 = [(300, 610), (420, 602), (767.5, 600), (1115, 602), (1235, 610), (1250, 690), (1115, 705), (767.5, 708), (420, 705), (285, 690)]
EXH_A4 = [(700, 667.5)]
RBUMPER_X = -1.97
P, N = project('A2', chaikin(DOORREAR_A2, 2)); parts.append(strip_cutter(P, N, name='gap_door_rear'))
P, N = project('A2', chaikin(SILL_A2, 1)); sill_P = P; parts.append(strip_cutter(P, N, name='gap_sill'))
P, N = project('A2', chaikin(SIDEINTAKE_A2, 2, closed=True), closed=True); parts.append(pocket_cutter(P, N, 0.07, name='pocket_sideintake', material=M_GRILLE))
P, N = project('A2', chaikin(QUARTER_A2, 2, closed=True), closed=True); quarter_poly = np.array([(p[0], p[2]) for p in P])
parts.append(strip_cutter(P, N, width=0.004, name='gap_quarter', closed=True))
P, N = project('A5', chaikin(LID_A5, 2, closed=True), closed=True); parts.append(strip_cutter(P, N, name='gap_enginelid', closed=True))
P, N = project('A5', chaikin(LOUVRE_A5, 2, closed=True), closed=True); louvre_P = P
parts.append(pocket_cutter(P, N, 0.035, inward=(0, 0, -1), name='pocket_louvre', material=M_GRILLE))
P, N = project('A5', chaikin(SMALLVENT_A5, 1, closed=True), closed=True); parts.append(pocket_cutter(P, N, 0.012, inward=(0, 0, -1), name='pocket_smallvent', material=M_GAP))
P, N = project('A5', chaikin(CHMSL_A5, 1, closed=True), closed=True); parts.append(pocket_cutter(P, N, 0.006, inward=(0, 0, -1), name='pocket_chmsl', material=M_TAIL))
tail_P, tail_N = project('A4', chaikin(TAIL_A4, 2, closed=True), closed=True); parts.append(pocket_filled('A4', TAIL_A4, 0.02, (1, 0, 0), 'pocket_tail'))
bar_P, bar_N = project('A4', chaikin(BAR_A4, 1, closed=True), closed=True); parts.append(pocket_filled('A4', BAR_A4, 0.018, (1, 0, 0), 'pocket_bar'))
P, N = project('A4', chaikin(HAUNCH_A4, 2)); parts.append(strip_cutter(P, N, name='gap_haunch'))
P, N = project('A4', chaikin(RBUMPER_A4, 1)); rbump_P = P; parts.append(strip_cutter(P, N, name='gap_rbumper'))
P, N = project('A2', [(764.5 - RBUMPER_X / K2, 470), (764.5 - (RBUMPER_X + 0.01) / K2, 560), (764.5 - (RBUMPER_X + 0.03) / K2, 640)])
parts.append(strip_cutter(P, N, name='gap_rbumper_side'))
diff_P, diff_N = project('A4', chaikin(DIFF_A4, 1, closed=True), closed=True); parts.append(pocket_cutter(diff_P, diff_N, 0.07, inward=(1, 0, 0), name='pocket_diffuser'))
NOMIRROR = NOMIRROR + ('pocket_bar', 'pocket_diffuser', 'gap_enginelid', 'pocket_louvre', 'pocket_smallvent', 'pocket_chmsl')
for o in list(parts):
    if o.name in NOMIRROR: continue          # spans the centre line already
    parts.append(mirror_obj(o))
print('CUTTERS', len(parts), 'lamp pts', len(lamp_P), 'intake pts', len(in_P))

# ---------------------------------------------------------------- carve
bpy.context.view_layer.objects.active = body
for o in scene.objects: o.select_set(o == body)
bo = body.modifiers.new('carve', 'BOOLEAN'); bo.operation = 'DIFFERENCE'; bo.operand_type = 'COLLECTION'
bo.collection = cutters; bo.solver = 'MANIFOLD'
if hasattr(bo, 'material_mode'): bo.material_mode = 'TRANSFER'
bpy.ops.object.modifier_apply(modifier=bo.name)
cutters.hide_render = True
for o in cutters.objects: o.hide_render = True; o.hide_viewport = True
bv = body.modifiers.new('edges', 'BEVEL'); bv.width = 0.0016; bv.segments = 1 if GAME else 2; bv.limit_method = 'ANGLE'
bv.angle_limit = math.radians(40); bv.harden_normals = False
bpy.ops.object.modifier_apply(modifier=bv.name)
# stepped bumper: everything below the hood front edge, lamp link and the lamps' lower edges (front view) and ahead of the
# side gap stands 3.5 mm proud of the bonnet and fenders, so every shut line around it reads as a shadow step; the strip
# above the central intake is pushed out a further 7 mm (fading over 3.5 cm) into a visor over the intake mouth
hood_px = [to_px('A3', p) for p in front_P][::-1]           # centre -> corner
lamp_low = [LAMP_A3[i] for i in (3, 4, 5, 6, 7, 8, 9, 10, 11, 12, 0)]
BUMPER_POLY = np.array([(800, hood_px[0][1])] + hood_px + [lt] + lamp_low + [(86, 489), (30, 489), (30, 905), (800, 905)])
bm = bmesh.new(); bm.from_mesh(body.data); bm.normal_update()
V = np.array([v.co[:] for v in bm.verts]); Nv = np.array([v.normal[:] for v in bm.verts])
col = 767.5 - np.abs(V[:, 1]) * 721; row = 880 - V[:, 2] * 585
inb = inside(BUMPER_POLY, col, row) & (V[:, 0] > BUMPER_X - 0.012 + 0.03 * (V[:, 2] < 0.2))
# ramp the step over 2.5 px (~3.5 mm, the gap width) from the boundary, so the groove floor slopes instead of tearing
seg_a = BUMPER_POLY; seg_b = np.roll(BUMPER_POLY, -1, 0); dist = np.full(len(V), 1e9)
for a_, b_ in zip(seg_a, seg_b):
    ab = b_ - a_; t = np.clip(((col - a_[0]) * ab[0] + (row - a_[1]) * ab[1]) / (ab @ ab + 1e-9), 0, 1)
    dist = np.minimum(dist, np.hypot(col - (a_[0] + t * ab[0]), row - (a_[1] + t * ab[1])))
ramp = np.clip(dist / 2.5, 0, 1); ramp = ramp * ramp * (3 - 2 * ramp)
# step direction: the original surface's normal (vertex normals at cut rims point into the pockets)
src_n = np.zeros_like(V)
for i in np.flatnonzero(inb):
    loc, n_, _, _ = src_bvh.find_nearest(Vector(V[i])); src_n[i] = n_[:] if n_ is not None else Nv[i]
z_top = (880 - 700) / 585
vis = (V[:, 0] > 2.1) & (np.abs(V[:, 1]) < (767.5 - 400) / 721) & (V[:, 2] > z_top - 0.002) & (V[:, 2] < z_top + 0.035) & (Nv[:, 0] > 0.3)
fall = np.clip(1 - (V[:, 2] - z_top) / 0.035, 0, 1) ** 1.5
bm.verts.ensure_lookup_table()
for i in np.flatnonzero(inb | vis):
    off = Vector(src_n[i]) * (0.0035 * ramp[i] if inb[i] else 0.0) + Vector((0.007 * fall[i] if vis[i] else 0.0, 0, 0))
    bm.verts[i].co += off
bm.to_mesh(body.data); bm.free()
print('BUMPER verts', int(inb.sum()), 'visor verts', int(vis.sum()))
# rear bumper: below its top edge (rear view) and behind the side gap, 3.5 mm proud, ramped the same way
rb_px = [tuple(to_px('A4', p)) for p in rbump_P]          # outer -> centre
RB_POLY = np.array([(800, rb_px[-1][1])] + rb_px[::-1] + [(20, rb_px[0][1]), (20, 905), (800, 905)])
bm = bmesh.new(); bm.from_mesh(body.data); bm.normal_update(); bm.verts.ensure_lookup_table()
V = np.array([v.co[:] for v in bm.verts])
col = 767.5 - np.abs(V[:, 1]) * 691; row = 865 - V[:, 2] * 573
inr = inside(RB_POLY, col, row) & (V[:, 0] < RBUMPER_X + 0.012)
dist = np.full(len(V), 1e9)
for a_, b_ in zip(RB_POLY, np.roll(RB_POLY, -1, 0)):
    ab = b_ - a_; t = np.clip(((col - a_[0]) * ab[0] + (row - a_[1]) * ab[1]) / (ab @ ab + 1e-9), 0, 1)
    dist = np.minimum(dist, np.hypot(col - (a_[0] + t * ab[0]), row - (a_[1] + t * ab[1])))
ramp = np.clip(dist / 2.5, 0, 1); ramp = ramp * ramp * (3 - 2 * ramp)
for i in np.flatnonzero(inr):
    loc, n_, _, _ = src_bvh.find_nearest(Vector(V[i]))
    if n_ is not None: bm.verts[i].co += Vector(n_) * 0.0035 * ramp[i]
bm.to_mesh(body.data); bm.free()
print('REAR BUMPER verts', int(inr.sum()))
for p in body.data.polygons: p.use_smooth = True
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(38))
wn = body.modifiers.new('wn', 'WEIGHTED_NORMAL'); wn.keep_sharp = True
bpy.ops.object.modifier_apply(modifier=wn.name)
print('BODY faces', len(body.data.polygons), 'materials', [m.name for m in body.data.materials])

# ---------------------------------------------------------------- headlamp unit (lens on the original surface, LEDs, bezel)
def fill_outline(view, outline_px, offset_in, material, name, grid_px=3.0, inset_px=0.0):
    """mesh the drawn outline (pixel polygon) on a grid, project it onto the original surface, push in by offset"""
    poly = chaikin(outline_px, 2, closed=True)
    if inset_px:
        cen = poly.mean(0); poly = cen + (poly - cen) * (1 - inset_px / np.linalg.norm(poly - cen, axis=1).mean())
    bm = bmesh.new()
    vs = []
    for c, r in dense(poly, grid_px, closed=True):
        o, d = px_ray(view, c, r); p, n = ray_hit(o, d)
        if p is not None: vs.append(bm.verts.new(tuple(p - n * offset_in)))
    f = bm.faces.new(vs)
    bmesh.ops.triangulate(bm, faces=[f], quad_method='BEAUTY', ngon_method='BEAUTY')
    for _ in range(3):
        bmesh.ops.subdivide_edges(bm, edges=[e for e in bm.edges if e.calc_length() > 0.012], cuts=1, use_grid_fill=True)
    for v in bm.verts:                       # back onto the original surface (minus offset), along the view direction
        c, r = to_px(view, v.co)
        o, d = px_ray(view, c, r); p, n = ray_hit(o, d)
        if p is not None: v.co = Vector(p - n * offset_in)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(material)
    for p in me.polygons: p.use_smooth = True
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o); return o


units = []
units.append(fill_outline('A3', LAMP_A3, 0.0015, M_LENS, 'lamp_lens'))
units.append(fill_outline('A3', LAMP_A3, 0.024, M_POCKET, 'lamp_back', inset_px=2.5))
# LED modules: rounded blocks standing on the lamp back, faces toward the lens
for k, ((c0, r0), (c1, r1)) in enumerate(LEDS_A3):
    o, d = px_ray('A3', (c0 + c1) / 2, (r0 + r1) / 2); p, n = ray_hit(o, d)
    w = (c1 - c0) / 721; h = (r1 - r0) / 585
    rot = Vector(n).to_track_quat('X', 'Z').to_euler()
    bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(p - n * 0.016))      # module body: dark chrome block
    bz = bpy.context.active_object; bz.name = f'lamp_bezel_{k}'
    bz.scale = (0.010, w * 1.08, h * 1.05); bz.rotation_euler = rot
    bv = bz.modifiers.new('r', 'BEVEL'); bv.width = 0.0022; bv.segments = 3
    bz.data.materials.append(M_BEZEL); units.append(bz)
    # a projector module, not a glowing card: black face plate, three small LED chips, a clear lens dome over them
    R = rot.to_matrix()
    def put(prim, local, scale, mat_, name, **kw):
        loc = Vector(p) + R @ Vector(local)
        getattr(bpy.ops.mesh, prim)(location=tuple(loc), **kw)
        ob = bpy.context.active_object; ob.name = name; ob.scale = scale; ob.rotation_euler = rot
        ob.data.materials.append(mat_); units.append(ob); return ob
    face = put('primitive_cube_add', (-0.0108, 0, 0), (0.0012, w * 0.80, h * 0.66), M_POCKET, f'lamp_face_{k}', size=1)
    for c in (-1, 0, 1):
        chip = put('primitive_cube_add', (-0.0099, c * w * 0.22, 0), (0.0008, w * 0.13, h * 0.26), M_LED, f'lamp_chip_{k}_{c + 1}', size=1)
    dome = put('primitive_uv_sphere_add', (-0.0098, 0, 0), (0.0028, w * 0.36, h * 0.30), M_LENS, f'lamp_dome_{k}', segments=24, ring_count=12, radius=1)
    dome.data.polygons.foreach_set('use_smooth', [True] * len(dome.data.polygons))


# ---------------------------------------------------------------- headlamp bezel: two stepped rings inside the pocket
def offset_poly(poly, d):
    """polygon offset inward by d pixels (poly counter-clockwise or not: the inward side is found from the area sign)"""
    poly = np.asarray(poly, float); n = len(poly)
    area = 0.5 * np.sum(poly[:, 0] * np.roll(poly[:, 1], -1) - np.roll(poly[:, 0], -1) * poly[:, 1])
    out = []
    for i in range(n):
        a, b, c = poly[i - 1], poly[i], poly[(i + 1) % n]
        t1 = (b - a) / (np.linalg.norm(b - a) + 1e-9); t2 = (c - b) / (np.linalg.norm(c - b) + 1e-9)
        nrm = np.array([-(t1[1] + t2[1]), t1[0] + t2[0]]); nrm /= np.linalg.norm(nrm) + 1e-9
        out.append(b + nrm * d * (1 if area > 0 else -1))
    return np.array(out)


def ring_strip(outline_px, inset0, inset1, depth0, depth1, material, name):
    return ring_strip_view('A3', outline_px, inset0, inset1, depth0, depth1, material, name)


def ring_strip_view(view, outline_px, inset0, inset1, depth0, depth1, material, name):
    """a sloped band inside the lamp pocket between two inset outlines at two depths (the stepped bezel of a lamp)"""
    base = dense(chaikin(outline_px, 2, closed=True), 2.0, closed=True)
    rings = []
    for inset, depth in ((inset0, depth0), (inset1, depth1)):
        ring = []
        for c, r in offset_poly(base, inset):
            o, d = px_ray(view, c, r); p, n = ray_hit(o, d)
            ring.append(None if p is None else p - n * depth)
        rings.append(ring)
    bm = bmesh.new(); k = len(base)
    va = [bm.verts.new(tuple(p)) if p is not None else None for p in rings[0]]
    vb = [bm.verts.new(tuple(p)) if p is not None else None for p in rings[1]]
    for i in range(k):
        j = (i + 1) % k
        q = (va[i], va[j], vb[j], vb[i])
        if all(v is not None for v in q): bm.faces.new(q)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(material)
    for p_ in me.polygons: p_.use_smooth = True
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    so = o.modifiers.new('so', 'SOLIDIFY'); so.thickness = 0.0012
    return o


units.append(ring_strip(LAMP_A3, 0.6, 2.6, 0.003, 0.006, M_BEZEL, 'lamp_bezel_outer'))
units.append(ring_strip(LAMP_A3, 2.6, 5.5, 0.006, 0.019, M_POCKET, 'lamp_bezel_inner'))

# ---------------------------------------------------------------- wipers (parked along the windscreen base) and washer jets
def surface_down(x, y):
    p, n = ray_hit((x, y, 3.0), (0, 0, -1)); return p, n


def wiper(y0, y1, name):
    ys = np.linspace(y0, y1, 40)
    base = []
    for y in ys:
        near = ws_poly[np.abs(np.abs(ws_poly[:, 1]) - abs(y)) < 0.03]
        xb = near[:, 0].max() if len(near) else ws_poly[:, 0].max()
        p, n = surface_down(xb - 0.045, y)
        if p is not None: base.append((p, n))
    bm = bmesh.new(); rings = []
    for i, (p, n) in enumerate(base):
        t = base[min(i + 1, len(base) - 1)][0] - base[max(i - 1, 0)][0]; t /= np.linalg.norm(t)
        b = np.cross(n, t); b /= np.linalg.norm(b)
        rings.append([bm.verts.new(tuple(p + n * h + b * w)) for h, w in ((0.006, -0.006), (0.006, 0.006), (0.016, 0.004), (0.016, -0.004))])
    for a_, b_ in zip(rings[:-1], rings[1:]):
        for k in range(4): bm.faces.new((a_[k], a_[(k + 1) % 4], b_[(k + 1) % 4], b_[k]))
    bm.faces.new(rings[0][::-1]); bm.faces.new(rings[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free(); me.materials.append(M_GAP)
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    bv_ = o.modifiers.new('r', 'BEVEL'); bv_.width = 0.0015; bv_.segments = 2
    return o


smalls = [wiper(-0.58, 0.02, 'wiper_driver'), wiper(0.06, 0.62, 'wiper_passenger')]
for y in (0.24, -0.24):
    p, n = surface_down(1.06, y)
    bpy.ops.mesh.primitive_uv_sphere_add(segments=16, ring_count=8, radius=1, location=tuple(p))
    j = bpy.context.active_object; j.name = f'washer_{"L" if y > 0 else "R"}'
    j.scale = (0.009, 0.006, 0.004); j.rotation_euler = Vector(n).to_track_quat('Z', 'X').to_euler()
    j.data.materials.append(M_GAP); j.data.polygons.foreach_set('use_smooth', [True] * len(j.data.polygons)); smalls.append(j)
print('SMALL PARTS', [o.name for o in smalls])

# ---------------------------------------------------------------- side mirrors (head measured as in build_parts.py: x 0.52 glass .. 0.70 nose,
# y 0.85 .. 1.02, z 0.824 .. 0.936; the outer end sweeps back), on a black stalk from the door top
M_MIRROR = mat('GT Mirror', (0.92, 0.93, 0.95), 0.02, metal=1.0)
def mirror_head():
    bm = bmesh.new(); secs = []
    ys = np.linspace(0.855, 1.02, 12)
    for y in ys:
        t = (y - 0.855) / (1.02 - 0.855)
        x0, x1 = 0.52 - 0.025 * t * t, 0.70 - 0.06 * t * t            # sweeps back toward the outer end
        zc, hz = 0.880 - 0.006 * t * t, 0.054 * (1 - 0.18 * t * t) * (0.82 + 0.18 * math.sin(math.pi * min(1, t * 1.6 + 0.2)))
        cap = 1 - 0.85 * max(0, (t - 0.86) / 0.14) ** 2 if t > 0.86 else 1
        ring = []
        for a_ in np.linspace(0, 2 * math.pi, 32, endpoint=False):
            ca, sa = math.cos(a_), math.sin(a_)
            ex = 0.45 if ca < 0 else 1.15                                  # full glass side, teardrop nose
            xx = (x0 + x1) / 2 + (x1 - x0) / 2 * np.sign(ca) * abs(ca) ** ex * cap
            zz = zc + hz * np.sign(sa) * abs(sa) ** 0.8 * cap
            ring.append(bm.verts.new((xx, y, zz)))
        secs.append(ring)
    for r0, r1 in zip(secs[:-1], secs[1:]):
        for i in range(32): bm.faces.new((r0[i], r0[(i + 1) % 32], r1[(i + 1) % 32], r1[i]))
    bm.faces.new(secs[0][::-1]); bm.faces.new(secs[-1])
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('mirror_head'); bm.to_mesh(me); bm.free(); me.materials.append(M_PAINT)
    o = bpy.data.objects.new('mirror_head', me); scene.collection.objects.link(o)
    sd = o.modifiers.new('sd', 'SUBSURF'); sd.levels = sd.render_levels = 2
    for p_ in me.polygons: p_.use_smooth = True
    # mirror glass: a superellipse plate just behind the flat side
    bm = bmesh.new(); ring = []
    for a_ in np.linspace(0, 2 * math.pi, 40, endpoint=False):
        ca, sa = math.cos(a_), math.sin(a_)
        ring.append(bm.verts.new((0.508, 0.94 + 0.072 * np.sign(ca) * abs(ca) ** 0.4, 0.882 + 0.046 * np.sign(sa) * abs(sa) ** 0.4)))
    bm.faces.new(ring)
    me = bpy.data.meshes.new('mirror_glass'); bm.to_mesh(me); bm.free(); me.materials.append(M_MIRROR)
    g = bpy.data.objects.new('mirror_glass', me); scene.collection.objects.link(g)
    # stalk: tapered blade from the door top to the head's inner end
    p, n = ray_hit((0.64, 3.0, 0.80), (0, -1, 0))
    root = Vector(p) if p is not None else Vector((0.64, 0.86, 0.80))
    bm = bmesh.new()
    pts = [(root + Vector((dx, -0.01, dz))) for dx, dz in ((-0.026, -0.003), (0.026, -0.003), (0.014, 0.009), (-0.014, 0.009))]
    top = [Vector((0.60 + dx, 0.862, 0.852 + dz)) for dx, dz in ((-0.016, -0.004), (0.016, -0.004), (0.010, 0.004), (-0.010, 0.004))]
    va = [bm.verts.new(tuple(v)) for v in pts]; vb = [bm.verts.new(tuple(v)) for v in top]
    for i in range(4): bm.faces.new((va[i], va[(i + 1) % 4], vb[(i + 1) % 4], vb[i]))
    bm.faces.new(va[::-1]); bm.faces.new(vb)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('mirror_stalk'); bm.to_mesh(me); bm.free(); me.materials.append(M_GAP)
    st = bpy.data.objects.new('mirror_stalk', me); scene.collection.objects.link(st)
    bv_ = st.modifiers.new('r', 'BEVEL'); bv_.width = 0.003; bv_.segments = 2
    return [o, g, st]


# ---------------------------------------------------------------- hood vent slats and splitter end plates
def slats_in(P, name, n_slats=3, depth=0.012):
    c = P.mean(0); Q = P - c
    u, sv, vt = np.linalg.svd(Q[:, :2], full_matrices=False); ax = np.array([*vt[0], 0.0]); ac = np.array([-ax[1], ax[0], 0.0])
    length = np.ptp(Q @ ax) * 0.85; width = np.ptp(Q @ ac)
    objs_ = []
    for k in range(n_slats):
        off = (k - (n_slats - 1) / 2) * width / (n_slats + 0.5)
        pc = Vector(c + ac * off - np.array((0, 0, depth)))
        bpy.ops.mesh.primitive_cube_add(size=1, location=tuple(pc))
        sl = bpy.context.active_object; sl.name = f'{name}_{k}'
        sl.scale = (length, 0.002, 0.016)
        sl.rotation_euler = (math.radians(-25), 0, math.atan2(ax[1], ax[0]))
        sl.data.materials.append(M_GRILLE); objs_.append(sl)
    return objs_


def endplate(side):
    V_ = np.array([v.co[:] for v in body.data.vertices]); bl = V_[(V_[:, 2] < 0.106) & (V_[:, 0] > 2.0) & (V_[:, 0] < 2.16)]
    y = np.abs(bl[:, 1]).max() - 0.004 if len(bl) else 0.80
    bm = bmesh.new()
    prof = [(2.00, 0.072), (2.17, 0.072), (2.17, 0.105), (2.06, 0.15), (2.00, 0.15)]
    a_ = [bm.verts.new((x, side * (y - 0.003), z)) for x, z in prof]; b_ = [bm.verts.new((x, side * (y + 0.003), z)) for x, z in prof]
    k = len(prof)
    for i in range(k): bm.faces.new((a_[i], a_[(i + 1) % k], b_[(i + 1) % k], b_[i]))
    bm.faces.new(a_[::-1]); bm.faces.new(b_)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('splitter_end'); bm.to_mesh(me); bm.free(); me.materials.append(M_GAP)
    o = bpy.data.objects.new(f'splitter_end_{"L" if side > 0 else "R"}', me); scene.collection.objects.link(o)
    bv_ = o.modifiers.new('r', 'BEVEL'); bv_.width = 0.0025; bv_.segments = 2
    return o


extra = mirror_head() + slats_in(vent_P, 'vent_slat')
for o in list(extra): extra.append(mirror_obj(o))
print('EXTRA PARTS', len(extra))


# ---------------------------------------------------------------- honeycomb grille plates in the intakes
def hex_plate(outline_px, x_plate, name, cell=None, bar=0.0026, thick=0.010, keep=None):
    cell = cell or (0.028 if GAME else 0.020)
    poly = chaikin(outline_px, 1, closed=True)
    Y = (767.5 - poly[:, 0]) / 721; Z = (880 - poly[:, 1]) / 585
    def inside(y, z):
        c = False; n = len(Y)
        for i in range(n):
            j = (i - 1) % n
            if (Z[i] > z) != (Z[j] > z) and y < (Y[j] - Y[i]) * (z - Z[i]) / (Z[j] - Z[i] + 1e-12) + Y[i]: c = not c
        return c
    bm = bmesh.new(); r = cell / math.sqrt(3)
    dz = cell * math.sqrt(3) / 2
    zs = np.arange(Z.min(), Z.max() + dz, dz)
    for i, z in enumerate(zs):
        for y in np.arange(Y.min() + (cell / 2 if i % 2 else 0), Y.max() + cell, cell):
            if not inside(y, z): continue
            if keep is not None and not keep(x_plate(y, z), y, z): continue
            ring = [bm.verts.new((x_plate(y, z), y + r * math.cos(a), z + r * math.sin(a))) for a in np.radians(np.arange(30, 390, 60))]
            bm.faces.new(ring)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    o = bpy.data.objects.new(name, me); scene.collection.objects.link(o)
    wf = o.modifiers.new('wf', 'WIREFRAME'); wf.thickness = bar; wf.use_even_offset = True
    so = o.modifiers.new('so', 'SOLIDIFY'); so.thickness = thick
    me.materials.append(M_GRILLE); return o


xi = in_P[:, 0].min() - 0.035
units.append(hex_plate(INTAKE_FULL, lambda y, z: xi, 'grille_intake'))
d_co = np.array((-0.9, -0.43, 0)) / np.linalg.norm((-0.9, -0.43, 0)); c_co = co_P.mean(0) + d_co * 0.065
def behind_face(x, y, z):                                  # a grille cell must sit at least 1.5 cm inside the bumper face
    p_, n_ = ray_hit((4.0, y, z), (-1, 0, 0)); return p_ is not None and x < p_[0] - 0.015
units.append(hex_plate([tuple(q) for q in offset_poly(chaikin(CORNER_A3, 1, closed=True), 4.0)], lambda y, z: c_co[0] - (d_co[1] * (y - c_co[1]) + d_co[2] * (z - c_co[2])) / d_co[0], 'grille_corner', keep=behind_face))
for o in list(units):
    if o.name.startswith('grille_intake'): continue
    bpy.context.view_layer.objects.active = o
    for x in scene.objects: x.select_set(x == o)
    for m in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
    units.append(mirror_obj(o))
print('UNITS', [o.name for o in units])

# ---------------------------------------------------------------- rear lamps, louvres, diffuser mesh and fins, exhausts
rear = [fill_outline('A4', TAIL_A4, 0.002, M_TAIL_LENS, 'tail_lens'), fill_outline('A4', TAIL_A4, 0.012, M_TAIL, 'tail_glow', inset_px=3.0),
        ring_strip_view('A4', TAIL_A4, 0.6, 2.4, 0.003, 0.008, M_BEZEL, 'tail_bezel')]
for o in list(rear):
    bpy.context.view_layer.objects.active = o
    for x in scene.objects: x.select_set(x == o)
    for m in list(o.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)
    rear.append(mirror_obj(o))
rear += [fill_outline('A4', BAR_A4, 0.0015, M_TAIL_LENS, 'bar_lens'), fill_outline('A4', BAR_A4, 0.006, M_TAIL, 'bar_glow', inset_px=1.0)]
# engine louvres: nine slats over the louvre pocket (A5 columns 1114 .. 1268 as build_parts.py), leaning to the tail
for i in range(9):
    x = (765 - (1114 + 19.25 * i)) * K5
    bm = bmesh.new(); rows_ = []
    for y in np.linspace(-0.33, 0.33, 23):
        p_, n_ = ray_hit((x, y, 3.0), (0, 0, -1))
        if p_ is None: continue
        zt = p_[2] - 0.010; zb = p_[2] - 0.032; lean = 0.015                     # top edge 1 cm under the deck, leaning to the tail
        rows_.append([bm.verts.new(v) for v in ((x, y, zt), (x - 0.006, y, zt), (x - 0.006 - lean, y, zb), (x - lean, y, zb))])
    for a_, b_ in zip(rows_[:-1], rows_[1:]):
        for k in range(4): bm.faces.new((a_[k], a_[(k + 1) % 4], b_[(k + 1) % 4], b_[k]))
    bm.faces.new(rows_[0][::-1]); bm.faces.new(rows_[-1]); bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('louvre'); bm.to_mesh(me); bm.free(); me.materials.append(M_GRILLE)
    sl = bpy.data.objects.new(f'louvre_{i}', me); scene.collection.objects.link(sl); rear.append(sl)
# diffuser: honeycomb plate in the mesh pocket (rear view outline, plate a little inside the pocket), four fins below it
def rear_face_x(y, z):
    p_, n_ = ray_hit((-4.0, y, z), (1, 0, 0)); return (p_[0] if p_ is not None else diff_P[:, 0].min()) + 0.04
rear.append(hex_plate([(1535 - c, r) for c, r in DIFF_A4], rear_face_x, 'grille_diffuser'))
for c in (347, 537, 998, 1188):
    y = (767.5 - c) / 691
    bm = bmesh.new()
    prof = [(-2.30, 0.115), (-1.95, 0.115), (-2.05, 0.30), (-2.30, 0.30)]
    a_ = [bm.verts.new((x, y - 0.004, z)) for x, z in prof]; b_ = [bm.verts.new((x, y + 0.004, z)) for x, z in prof]
    for i in range(4): bm.faces.new((a_[i], a_[(i + 1) % 4], b_[(i + 1) % 4], b_[i]))
    bm.faces.new(a_[::-1]); bm.faces.new(b_); bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
    me = bpy.data.meshes.new('fin'); bm.to_mesh(me); bm.free(); me.materials.append(M_GAP)
    fo = bpy.data.objects.new(f'diffuser_fin_{c}', me); scene.collection.objects.link(fo); rear.append(fo)
# exhausts: polished outer tube and a dark inner pipe, standing out of the diffuser pocket
for c, r in EXH_A4:
    for cc in (c, 1535 - c):
        y, z = (767.5 - cc) / 691, (865 - r) / 573
        p_, n_ = ray_hit((-4.0, y, z), (1, 0, 0)); x0 = (p_[0] if p_ is not None else -2.3)
        bpy.ops.mesh.primitive_cylinder_add(vertices=48, radius=0.069, depth=0.10, location=(x0 + 0.03, y, z), rotation=(0, math.pi / 2, 0))
        t = bpy.context.active_object; t.name = f'exhaust_tip_{cc:.0f}'; t.data.materials.append(M_METAL)
        bpy.ops.mesh.primitive_cylinder_add(vertices=32, radius=0.058, depth=0.11, location=(x0 + 0.025, y, z), rotation=(0, math.pi / 2, 0))
        ip = bpy.context.active_object; ip.name = f'exhaust_pipe_{cc:.0f}'; ip.data.materials.append(M_GAP)
        rear += [t, ip]
print('REAR UNITS', len(rear))

# ---------------------------------------------------------------- windows and blade (review only)
body.data.materials.append(M_GLASS); gi = len(body.data.materials) - 1
C = np.array([p.center[:] for p in body.data.polygons]); Nn = np.array([p.normal[:] for p in body.data.polygons])
MI = np.array([p.material_index for p in body.data.polygons])
g_ws = (MI == 0) & (Nn[:, 2] > 0.2) & (C[:, 2] > 0.8) & inside(ws_poly, C[:, 0], np.abs(C[:, 1]))
g_sd = (MI == 0) & (np.abs(Nn[:, 1]) > 0.12) & (C[:, 2] > 0.76) & inside(side_poly, C[:, 0], C[:, 2])
g_sd |= (MI == 0) & (np.abs(Nn[:, 1]) > 0.12) & (C[:, 2] > 0.78) & inside(quarter_poly, C[:, 0], C[:, 2])
sill_z = np.interp(C[:, 0], np.sort(sill_P[:, 0]), sill_P[np.argsort(sill_P[:, 0]), 2])
skirt = (MI == 0) & (C[:, 0] < sill_P[:, 0].max()) & (C[:, 0] > sill_P[:, 0].min()) & (C[:, 2] < sill_z - 0.002) & (np.abs(Nn[:, 1]) > 0.2)
for i in np.flatnonzero(skirt): body.data.polygons[i].material_index = 1
blade = (C[:, 2] < 0.106) & (C[:, 0] > 1.85)
for i in np.flatnonzero(g_ws | g_sd): body.data.polygons[i].material_index = gi
for i in np.flatnonzero(blade): body.data.polygons[i].material_index = 1
ng = int((g_ws | g_sd).sum())
print('GLASS faces', ng)
for o in cutters.objects: bpy.data.objects.remove(o, do_unlink=True)
bpy.data.collections.remove(cutters)
bpy.ops.wm.save_as_mainfile(filepath=out_blend)
print('DONE')
