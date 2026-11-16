# blender --factory-startup -b -P build_surface.py -- <hybrid dir> <tag> [kW]
# The surfaced GT v4 body, built from the drawing curves alone (profiles.json), no sampling of the old fitted body
# (NOTES 15: the voxel/membrane body cannot hold an edge under ~7 cm; NOTES 17: s1-s3 still sampled it below the
# shoulder and capped the ends with flat grid fills).
#   stations    every 4 cm along x between the two end caps; each is a half section (y >= 0) with a fixed number of
#               points, so that one row index runs the whole length of the car: rows are the car's lines
#   lower part  anchor rows: floor centre (0) -> floor edge (7) -> sill top after a 35 mm corner (11) -> widest point
#               (19) -> shoulder (27); widths from the plan half width (A5, x kW), heights from the side silhouette's
#               underside (A2) and a shoulder-height curve; tumble-under below and tumblehome above the widest point
#   upper part  anchor rows: shoulder (0) -> A1 (8) -> A2 (16) -> centre (26)
#                 front: fender crest at the side silhouette's top (A2), bonnet centre 2-5 cm below it (the dip)
#                 rear: haunch crest at ~0.9 m, deck / buttress rising to the side silhouette's top at the centre
#                 cabin: door top -> glass base (plan outer glass edge, sill height) -> roof edge (plan inner glass
#                 edge) -> roof crown; blended in over 30 cm (smoothstep) where the cabin starts and ends
#   end caps    the last ~45 cm at each end: every row runs on in plan along the drawn outline (A5, superellipse-like,
#               with the flat bumper face) and turns onto the centre plane at right angles, ending on the drawn
#               nose / tail profile (A2); so the bumper faces are part of the same quad grid (no fills, full length)
#   mesh        quads, mirrored across y = 0; Catmull-Clark x2 with creased rows (glass base, roof edge, crest);
#               the four arches cut with cylinders as in build_body.py and their edges rounded
# Writes gt-v4-body-<tag>.blend (object body_smooth4, as the detail chain expects) and body-<tag>.glb.
import bpy, bmesh, sys, os, json, math
import numpy as np

argv = sys.argv[sys.argv.index('--') + 1:]
hyb, TAG = argv[:2]
KW = float(argv[2]) if len(argv) > 2 else 0.955       # plan half width -> body half width (A5 vs A3/A4 scales)
OPTS = set(argv[3:])
SHARP = 'sharp' in OPTS                                # fender / haunch crest as a real ridge (NOTES 19)
FLARE = 'flare' in OPTS                                # fenders flared over the tyres (NOTES 19-6)
LOD1 = 'lod1' in OPTS                                  # one Catmull-Clark level instead of two: the game body (NOTES 19-7)
P = json.load(open(os.path.join(hyb, 'profiles.json')))
X = np.array(P['x'])
nanf = lambda k: np.array([np.nan if v is None else v for v in P[k]], float)
TOP, BOT, HALF = nanf('top'), nanf('bottom'), nanf('half')
GH_OUT, GH_IN, BELT = nanf('gh_out'), nanf('gh_in'), nanf('belt')
ZO, NOSE, TAIL = np.array(P['zo']), np.array(P['nose']), np.array(P['tail'])
ZF, FW = np.array(P['z']), np.array(P['front_w'])


def gsmooth(v, sigma):
    """Gaussian smoothing (sigma in metres, 2 cm samples) inside the curve's defined span, edges held."""
    v = v.copy(); ok = np.flatnonzero(~np.isnan(v))
    if len(ok) < 3: return v
    a, b = ok[0], ok[-1] + 1; seg = v[a:b]
    k = int(3 * sigma / 0.02); t = np.arange(-k, k + 1) * 0.02; w = np.exp(-0.5 * (t / sigma) ** 2); w /= w.sum()
    v[a:b] = np.convolve(np.pad(seg, k, mode='edge'), w, 'valid'); return v


# the drawn curves carry pixel noise: wavy zebra stripes along the sides; smoothed before use
HALF, BOT, TOP = gsmooth(HALF, 0.08), gsmooth(BOT, 0.06), gsmooth(TOP, 0.03)
GH_OUT, GH_IN, BELT = gsmooth(GH_OUT, 0.06), gsmooth(GH_IN, 0.06), gsmooth(BELT, 0.06)
TOPMAX = np.nanmax(TOP)
up = ZF > 0.86                                          # greenhouse in the front view: half width -> height
ZFW = lambda y: np.interp(-y, -FW[up], ZF[up]) + 0.015
NL, NU = 28, 27                     # points in the lower and upper parts of every half section (shoulder shared)
LA = (0, 7, 11, 19, 27)             # lower anchors
UA = (0, 8, 16, 26)                 # upper anchors
ROWS = NL + NU - 1
X0F, X0R = 1.92, -1.96              # where the end caps start
NC = 22                             # stations in each end cap
AXLE_X, TYRE_R = 1.435, 0.40
ARCH = {'F': (0.43, 0.45), 'R': (0.42, 0.55)}
L2 = 2.368


def f(arr, x):
    ok = ~np.isnan(arr); return np.interp(x, X[ok], arr[ok])


_CX = np.arange(-2.6, 2.6001, 0.01)


def ctrl(x, pts, sigma=0.15):
    """design curve through control points: piecewise linear, then Gaussian-smoothed (no slope breaks: a linear
    interpolation's kinks show as bent zebra stripes)"""
    a = np.array(pts); v = np.interp(_CX, a[:, 0], a[:, 1])
    k = int(3 * sigma / 0.01); t = np.arange(-k, k + 1) * 0.01; w = np.exp(-0.5 * (t / sigma) ** 2); w /= w.sum()
    v = np.convolve(np.pad(v, k, mode='edge'), w, 'valid'); return np.interp(x, _CX, v)


def smoothstep(t):
    t = np.clip(t, 0, 1); return t * t * (3 - 2 * t)


def unit(v):
    v = np.asarray(v, float); return v / np.linalg.norm(v)


def resample(pts, n):
    pts = np.asarray(pts, float)
    seg = np.linalg.norm(np.diff(pts, axis=0), axis=1)
    s = np.concatenate([[0], np.cumsum(seg)])
    if s[-1] < 1e-9: return np.repeat(pts[:1], n, 0)
    t = np.linspace(0, s[-1], n)
    return np.stack([np.interp(t, s, pts[:, k]) for k in range(pts.shape[1])], 1)


def hermite(p0, t0, p1, t1, n, k=1.0):
    """n points (ends included) on the cubic Hermite p0 -> p1 with unit tangents t0, t1 (scaled by chord * k),
    evenly spaced by arc length."""
    p0, p1 = np.asarray(p0, float), np.asarray(p1, float)
    c = np.linalg.norm(p1 - p0) * k
    m0, m1 = unit(t0) * c, unit(t1) * c
    s = np.linspace(0, 1, 200)[:, None]
    h00, h10, h01, h11 = 2 * s**3 - 3 * s**2 + 1, s**3 - 2 * s**2 + s, -2 * s**3 + 3 * s**2, s**3 - s**2
    return resample(h00 * p0 + h10 * m0 + h01 * p1 + h11 * m1, n)


def chaikin(pts, it=2):
    pts = np.asarray(pts, float)
    for _ in range(it):
        q = [pts[0]]
        for a, b in zip(pts[:-1], pts[1:]):
            q += [0.75 * a + 0.25 * b, 0.25 * a + 0.75 * b]
        q.append(pts[-1]); pts = np.array(q)
    return pts


# ---- design curves along x
cabin_x = X[~np.isnan(GH_OUT)]
CAB0, CAB1 = cabin_x.min(), cabin_x.max()


def wcab(x):
    return smoothstep(np.minimum(x - CAB0, CAB1 - x) / 0.36)


def W(x):
    """body half width: the plan outline (A5 x KW), held out over the tyres' front and rear ends (the plan drawing
    narrows ahead of the front and behind the rear wheels faster than the front/rear views allow: the tyres showed
    beside the bumpers). Smooth maximum, no slope breaks."""
    a = KW * f(HALF, x)
    t = np.where(np.asarray(x) > 0, 0.968 - 0.27 * smoothstep((np.asarray(x) - 1.86) / 0.30),
                 0.986 - 0.29 * smoothstep((-np.asarray(x) - 1.86) / 0.30))
    t = np.where(np.abs(x) > 1.2, t, 0.0)
    return 0.5 * (a + t + np.sqrt((a - t) ** 2 + 0.015 ** 2))
def ZB(x): return f(BOT, x)                              # underside (the splitter blade is a part of its own, below)
def DIP(x):                                              # bonnet centre below the fender crests, nothing on the glass
    return ctrl(x, [(0.95, 0.0), (1.22, 0.06), (1.45, 0.05), (1.9, 0.03), (2.4, 0.0)], 0.08)
def ZW(x): return ctrl(x, [(-2.4, 0.47), (-1.4, 0.47), (0.0, 0.43), (1.4, 0.42), (2.4, 0.40)])
TU, RS, TH = 0.04, 0.035, 0.018                         # tumble-under at the sill top, sill corner radius, tumblehome
def ZS_nom(x):                                           # shoulder (top of the vertical side) height
    return ctrl(x, [(-2.4, 0.63), (-1.9, 0.67), (-1.3, 0.69), (-0.9, 0.76), (-0.3, 0.76), (0.6, 0.745), (1.1, 0.71), (1.4, 0.68), (2.0, 0.64), (2.4, 0.57)])
FRONT_SPLIT = 0.0                                        # crest rules: front of this x the fender crest, behind the haunch


def crest(x):
    """fender / haunch crest (y, z) and the centre-line height of bonnet / deck (outside the cabin)."""
    top = f(TOP, x)
    wf = smoothstep((x - FRONT_SPLIT + 0.4) / 0.8)       # 1 at the front, 0 at the rear
    zc_f, yc_f, zcen_f = top + 0.012, 0.69 * W(x), top - DIP(x)   # + subdivision shrink of the crest ridge
    zc_r = min(ctrl(x, [(-2.4, 0.85), (-2.0, 0.875), (-1.5, 0.885), (-0.9, 0.91)]), top - 0.012)
    yc_r, zcen_r = 0.70 * W(x), top
    return wf * yc_f + (1 - wf) * yc_r, wf * zc_f + (1 - wf) * zc_r, wf * zcen_f + (1 - wf) * zcen_r


def section(x):
    """half section at station x: ROWS x (y, z), from the floor centre round to the top centre."""
    w, zb, zw = W(x), ZB(x), ZW(x)
    yc, zc, zcen = crest(x)
    zs = min(ZS_nom(x), zc - 0.06)
    shoulder_t = (-math.sin(math.radians(30)), math.cos(math.radians(30)))
    p_floor_e = (w - TU - RS, zb); p_sill = (w - TU, zb + RS); p_wide = (w, zw); p_sh = (w - TH, zs)
    low = [np.linspace((0.0, zb), p_floor_e, LA[1] + 1)]
    low.append(hermite(p_floor_e, (1, 0), p_sill, (0.25, 1), LA[2] - LA[1] + 1, 1.2)[1:])
    low.append(hermite(p_sill, (0.25, 1), p_wide, (0, 1), LA[3] - LA[2] + 1)[1:])
    low.append(hermite(p_wide, (0, 1), p_sh, shoulder_t, LA[4] - LA[3] + 1)[1:])
    lower = np.vstack(low)
    # outside the cabin: shoulder -> crest (round-over) -> centre (S-curve, horizontal at both ends)
    # sharp: the crest is a ridge (the round-over arrives rising, the bonnet / deck side leaves falling), creased fully
    t_in, t_out = ((-1, 0.38), (-1, -0.32)) if SHARP else ((-1, 0), (-1, 0))
    up_o = np.vstack([hermite(p_sh, shoulder_t, (yc, zc), t_in, UA[1] + 1, 0.9),
                      hermite((yc, zc), t_out, (0.0, zcen), (-1, 0), UA[3] - UA[1] + 1)[1:]])
    wc = float(wcab(x))
    if wc > 0:
        top = f(TOP, x) - DIP(x)
        go = KW * f(GH_OUT, x); zg = f(BELT, x) if not np.isnan(f(BELT, x)) else zs + 0.07
        go = min(go, w - TH - 0.06); zg = max(zg, zs + 0.035)
        # roof edge behind the header, A-pillar ahead of it: one smooth line in plan (the drawn inner glass edge is
        # erratic at the header corner, x 0.3..0.7, and switching rules there dented the windscreen)
        gi = KW * ctrl(x, [(-1.0, 0.58), (-0.6, 0.547), (0.1, 0.555), (0.45, 0.54), (0.8, 0.565), (1.2, 0.58)], 0.12)
        gi = min(gi, go - 0.04)
        zre = float(np.clip(ZFW(gi) - (TOPMAX - top), zg + 0.07, top - 0.03))
        yy = np.linspace(gi, 0, 120); roof = np.stack([yy, top - (top - zre) * (yy / gi) ** 4], 1)
        sl = 4 * (top - zre) / gi                       # roof slope at the roof edge, continued by the glass
        up_c = np.vstack([hermite(p_sh, shoulder_t, (go, zg), (-1, 0.22), UA[1] + 1, 0.9),
                          hermite((go, zg), (-1.0, 0.9), (gi, zre), (-1, sl), UA[2] - UA[1] + 1)[1:],
                          resample(roof, UA[3] - UA[2] + 1)[1:]])
        upper = wc * up_c + (1 - wc) * up_o
    else:
        upper = up_o
    return np.vstack([lower, upper[1:]])


# ---- 1. sections between the caps
xs = np.round(np.arange(X0R, X0F + 1e-6, 0.04), 4)
grid = np.array([section(x) for x in xs])                # (S, ROWS, 2)
g = grid.copy()                                          # along x: removes template switching kinks
for it in range(10):
    lo = slice(0, NL) if it < 3 else slice(0, 0)
    for sl in (lo, slice(NL - 1, ROWS)):
        g[1:-1, sl] = 0.25 * g[:-2, sl] + 0.5 * g[1:-1, sl] + 0.25 * g[2:, sl]
g[:, 0, 0] = 0.0; g[:, -1, 0] = 0.0
# smoothing lowered the roof's peak: put the centre row back on the drawn top, fading to nothing at the shoulder
dtop = grid[:, -1, 1] - g[:, -1, 1]
g[:, NL - 1:, 1] += dtop[:, None] * np.linspace(0, 1, NU)[None, :] ** 2
grid = g
G3 = np.concatenate([np.repeat(xs[:, None, None], ROWS, 1), grid], 2)   # (S, ROWS, 3) x, y, z


# ---- 1b. wheel arch flares: the plan outline narrows above the arches (shoulder round-over, tumblehome) while the
# tyres' outer faces stand at |y| 0.966 / 0.98 up to their tops, so from above three-quarter the tyre showed beside and
# over the fender. Around each arch, the side is pushed out until the lip (arch radius + 3 cm) is 1.2 cm outboard of the
# tyre; the push fades above the lip over 15 cm (a fender bulge rising into the crest) and fore and aft of the arch.
ZLIP_MAX, DMAX = 0.80, 0.12                            # lip covered up to the tyre's top (0.80 m); at most 12 cm


def flare(G):
    G = G.copy()
    T = np.gradient(G[:, :, 1:], axis=1)                                     # section tangents (y, z)
    ny = T[:, :, 1] / (np.linalg.norm(T, axis=2) + 1e-9)                      # outward normal's y component
    for ax, (rad, _), yreq in ((AXLE_X, ARCH['F'], 0.978), (-AXLE_X, ARCH['R'], 0.992)):
        lip = rad + 0.03
        dx = np.abs(G[:, 0, 0] - ax)
        wx = smoothstep((lip + 0.25 - dx) / 0.25)                             # full over the arch, fading 25 cm fore and aft
        zt = TYRE_R + (ZLIP_MAX - TYRE_R) * smoothstep((lip + 0.05 - dx) / 0.25)   # lip height, smooth along x
        y, z = G[:, :, 1], G[:, :, 2]
        deficit = np.clip(yreq - y, 0, DMAX)                                  # each point only as far as it falls short
        h = 1 - smoothstep((z - zt[:, None]) / 0.15)                          # up to the lip, fading over 15 cm above it
        push = deficit * h * wx[:, None] * np.clip(ny / 0.5, 0, 1) * (z > 0.2)
        G[:, :, 1] += push
        print('FLARE axle', ax, 'max push', round(float(push.max()), 3))
    return G


if FLARE: G3 = flare(G3)


# ---- 2. end caps
def cap(front):
    sgn = 1 if front else -1
    x0 = X0F if front else X0R
    sec = G3[-1] if front else G3[0]
    y0, z0 = sec[:, 1], sec[:, 2]
    # plan outline of the widest row: drawn half width, then the flat bumper face onto the centre plane
    xa = np.linspace(x0, sgn * 2.35, 40)
    pl = [(abs(xx), W(xx)) for xx in xa]
    yf = W(sgn * 2.36)
    pl += [(L2 - 0.010 * (yy / yf) ** 2, yy) for yy in np.linspace(yf, 0, 12)]
    pl = chaikin(np.array(pl), 3)
    pl = resample(pl, 400)
    s = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(pl, axis=0), axis=1))])
    u = (np.arange(1, NC + 1) / NC) ** 1.0
    px = np.interp(u * s[-1], s, pl[:, 0]); py = np.interp(u * s[-1], s, pl[:, 1])
    XH = (px - abs(x0)) / (L2 - abs(x0)); YH = py / pl[0, 1]
    XH[-1], YH[-1] = 1.0, 0.0
    # the face profile on the centre plane (A2), from the floor's end B up to the bonnet / deck's end T
    prof = NOSE if front else TAIL
    zB, zT = (0.16, 0.545) if front else (0.20, 0.78)
    # the drawn profile steps at the intake mouth, the lamp lip and the deck lip read as ripples across the whole face:
    # the recesses are filled (running max over +-3 cm, keeps the full length) and the result smoothed (sigma 4 cm);
    # those openings belong to the detail pass
    zq = np.arange(0.0, 1.2, 0.005); pq = np.interp(zq, ZO, np.abs(prof))
    pq = np.array([pq[max(0, i - 6):i + 7].max() for i in range(len(pq))])
    k = 24; wq = np.exp(-0.5 * (np.arange(-k, k + 1) * 0.005 / 0.04) ** 2); wq /= wq.sum()
    pmax = pq.max(); pq = np.convolve(np.pad(pq, k, mode='edge'), wq, 'valid'); pq += pmax - pq.max()
    zz = np.linspace(zB, zT, 200); seam = np.stack([np.interp(zz, zq, pq), zz], 1)
    ss = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(seam, axis=0), axis=1))])
    # row -> seam position: half section arc length, half cumulative height change (both monotone)
    arc = np.concatenate([[0], np.cumsum(np.linalg.norm(np.diff(sec[:, 1:], axis=0), axis=1))]); arc /= arc[-1]
    dzc = np.concatenate([[0], np.cumsum(np.abs(np.diff(z0)))]); dzc /= dzc[-1]
    phi = 0.5 * arc + 0.5 * dzc
    xe = np.interp(phi * ss[-1], ss, seam[:, 0]); ze = np.interp(phi * ss[-1], ss, seam[:, 1])
    topf = lambda xx: f(TOP, sgn * xx); botf = lambda xx: ZB(sgn * xx)
    out = np.zeros((NC, ROWS, 3))
    for j in range(ROWS):
        xj = abs(x0) + (xe[j] - abs(x0)) * XH
        zgen = z0[j] + (ze[j] - z0[j]) * XH ** 1.5
        ztop = topf(xj) + (z0[j] - topf(abs(x0))) * (1 - XH) + (ze[j] - topf(xe[j])) * XH
        zbot = botf(xj) + (z0[j] - botf(abs(x0))) * (1 - XH) + (ze[j] - botf(xe[j])) * XH
        wt = smoothstep((phi[j] - 0.40) / 0.30); wb = smoothstep((0.30 - phi[j]) / 0.25)
        out[:, j] = np.stack([sgn * xj, y0[j] * YH, wt * ztop + wb * zbot + (1 - wt - wb) * zgen], 1)
    return out


cf, cr = cap(True), cap(False)
G3 = np.concatenate([cr[::-1], G3, cf], 0)
# along each row in 3D across the cap junctions (not the end seams, not the centre rows' y)
nS = len(G3)
for _ in range(6):
    G3[1:-1] = 0.25 * G3[:-2] + 0.5 * G3[1:-1] + 0.25 * G3[2:]
G3[:, 0, 1] = 0.0; G3[:, -1, 1] = 0.0; G3[0, :, 1] = 0.0; G3[-1, :, 1] = 0.0
print('GRID', G3.shape, 'x', round(G3[..., 0].min(), 3), round(G3[..., 0].max(), 3), 'halfw', round(G3[..., 1].max(), 3),
      'z', round(G3[..., 2].min(), 3), round(G3[..., 2].max(), 3))
if os.environ.get('GRID_OUT'): np.save(os.environ['GRID_OUT'], G3)

# ---- 3. mesh: half shell, mirrored, creased rows, subdivided
wcs = np.array([float(wcab(x)) for x in G3[:, 0, 0]])
bm = bmesh.new()
V = [[bm.verts.new(tuple(G3[i, j])) for j in range(ROWS)] for i in range(nS)]
for i in range(nS - 1):
    for j in range(ROWS - 1):
        bm.faces.new((V[i][j], V[i + 1][j], V[i + 1][j + 1], V[i][j + 1]))
bmesh.ops.recalc_face_normals(bm, faces=bm.faces[:])
crease = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
r_a1, r_a2 = NL - 1 + UA[1], NL - 1 + UA[2]
for i in range(NC, nS - NC - 1):
    w = 0.5 * (wcs[i] + wcs[i + 1])
    for j, cval in ((r_a1, 0.75 * w + (1.0 if SHARP else 0.6) * (1 - w)), (r_a2, 0.15 * w), (LA[2], 0.3)):
        e = bm.edges.get((V[i][j], V[i + 1][j]))
        if e and cval > 0.02: e[crease] = cval
me = bpy.data.meshes.new('body_smooth4'); bm.to_mesh(me); bm.free()
scene = bpy.context.scene
for o in list(scene.objects): bpy.data.objects.remove(o, do_unlink=True)   # factory cube, camera, light
body = bpy.data.objects.new('body_smooth4', me); scene.collection.objects.link(body)


def activate(o):
    for x_ in scene.objects: x_.select_set(x_ == o)
    bpy.context.view_layer.objects.active = o


activate(body)
mi = body.modifiers.new('mirror', 'MIRROR'); mi.use_axis = (False, True, False); mi.use_clip = True
mi.use_mirror_merge = True; mi.merge_threshold = 1e-5
bpy.ops.object.modifier_apply(modifier=mi.name)
sd = body.modifiers.new('subd', 'SUBSURF'); sd.levels = sd.render_levels = 1 if LOD1 else 2
bpy.ops.object.modifier_apply(modifier=sd.name)
bm = bmesh.new(); bm.from_mesh(body.data)
print('SHELL faces', len(bm.faces), 'non-manifold edges', sum(1 for e in bm.edges if not e.is_manifold),
      'degenerate', sum(1 for f_ in bm.faces if f_.calc_area() < 1e-9))
bm.free()
cutters = []
for axle, x in (('F', AXLE_X), ('R', -AXLE_X)):
    rad, y_in = ARCH[axle]
    for side in (1, -1):
        bpy.ops.mesh.primitive_cylinder_add(vertices=128, radius=rad, depth=0.9, location=(x, side * (y_in + 0.45), TYRE_R),
                                            rotation=(math.pi / 2, 0, 0))
        cutters.append(bpy.context.active_object)
for c in cutters:
    activate(body)
    b = body.modifiers.new('arch', 'BOOLEAN'); b.operation = 'DIFFERENCE'; b.object = c; b.solver = 'MANIFOLD'
    bpy.ops.object.modifier_apply(modifier=b.name)
for c in cutters: bpy.data.objects.remove(c, do_unlink=True)
activate(body)
bv = body.modifiers.new('bevel', 'BEVEL'); bv.width = 0.008; bv.segments = 2; bv.limit_method = 'ANGLE'; bv.angle_limit = math.radians(55)
bpy.ops.object.modifier_apply(modifier=bv.name)
# front splitter blade (A3: a full-width black lip down to z 0.07; A2: under the nose): a flat 3 cm slab whose plan
# outline is the sill-top row's path, 1.5 cm in, cut straight across at x 2.22; joined into the body mesh
path = G3[:, LA[2], :2]
path = path[(path[:, 0] >= 1.90) & (path[:, 0] <= 2.22)]
yb = np.interp(np.linspace(1.90, 2.22, 33), path[:, 0], path[:, 1]) - 0.015
xb = np.linspace(1.90, 2.22, 33)
ring = [(x_, y_) for x_, y_ in zip(xb, yb)]
ring += [(2.22 + 0.03 * math.sin(a), yb[-1] * math.cos(a)) for a in np.linspace(0.15, math.pi - 0.15, 9)][1:-1]  # front edge
ring += [(x_, -y_) for x_, y_ in zip(xb[::-1], yb[::-1])]
ring = chaikin(np.array(ring + [ring[0]]), 2)[:-1]
bm = bmesh.new(); bm.from_mesh(body.data)
lo = [bm.verts.new((x_, y_, 0.072)) for x_, y_ in ring]
hi = [bm.verts.new((x_, y_, 0.104)) for x_, y_ in ring]
n_ = len(ring)
bm.faces.new(lo[::-1]); bm.faces.new(hi)
for k_ in range(n_):
    bm.faces.new((lo[k_], lo[(k_ + 1) % n_], hi[(k_ + 1) % n_], hi[k_]))
blade_edges = [e for e in bm.edges if e.verts[0] in set(lo) | set(hi) and e.verts[1] in set(lo) | set(hi)
               and abs(e.verts[0].co.z - e.verts[1].co.z) < 1e-6]
bmesh.ops.bevel(bm, geom=blade_edges, offset=0.006, segments=2, profile=0.5, affect='EDGES')
bm.to_mesh(body.data); bm.free()
for p in body.data.polygons: p.use_smooth = True
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))
Vt = np.array([v.co[:] for v in body.data.vertices])
print('BODY extent', np.round(Vt.max(0) - Vt.min(0), 3), 'faces', len(body.data.polygons))
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(hyb, f'gt-v4-body-{TAG}.blend'))
activate(body)
bpy.ops.export_scene.gltf(filepath=os.path.join(hyb, f'body-{TAG}.glb'), use_selection=True, export_apply=True, export_materials='NONE')
print('DONE')
