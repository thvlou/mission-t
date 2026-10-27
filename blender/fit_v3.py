# Fit a v3 car's plan shape to its design-target sheet (photogrammetry-lite):
#
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/fit_v3.py -- <car-id> [rounds]
#
# The side silhouette is already measured off the side view (vertigo_v3.TARGETS). The two 3/4
# views carry the plan: how wide the body is at each station and how the cabin narrows. For each
# 3/4 view we recover the camera (position, aim point, focal length) by fitting the projected model
# to the sheet's upper outline (tools/target-mask.py -> blender/v3_fit/<sheet>-targets.npz), then
# adjust plan-width multipliers along the car and the cabin width so both views' outlines match,
# re-solving the cameras between rounds. Result: blender/v3_fit/<car-id>.json, which spec() reads.
import bpy, json, math, os, sys
import numpy as np
from mathutils import Vector

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index('--') + 1:]
CID = argv[0]
ROUNDS = int(argv[1]) if len(argv) > 1 else 3
ns = {'__file__': os.path.join(REPO, 'blender', 'vertigo_v3.py')}
exec(open(ns['__file__'], encoding='utf-8').read(), ns)
ns['USE_FIT'] = False  # fit from the measured spec, not a previous fit
T = ns['TARGETS'][CID]
KEY = T['sheet'][:2]
FIT = os.path.join(REPO, 'blender', 'v3_fit')
tg = np.load(os.path.join(FIT, f'{KEY}-targets.npz'))
VIEWS = ('front', 'rear')
STATIONS = 7


def main_run(top, gap=10):
    """Keep only the longest run of valid columns (drops label text and neighbouring views)."""
    ok = top >= 0
    best, cur, start = (0, 0), 0, None
    runs, s0, last = [], None, -100
    for u in np.nonzero(ok)[0]:
        if u - last > gap:
            if s0 is not None: runs.append((s0, last))
            s0 = u
        last = u
    if s0 is not None: runs.append((s0, last))
    a, b = max(runs, key=lambda r: r[1] - r[0])
    out = np.full_like(top, -1)
    out[a:b + 1] = np.where(ok[a:b + 1], top[a:b + 1], -1)
    return out, a, b


TGT = {}
for v in VIEWS:
    box = tg[v + '_box']
    top, a, b = main_run(tg[v + '_top'].astype(np.int64))
    TGT[v] = dict(top=top.astype(np.float64), a=a, b=b, w=int(box[2] - box[0]), h=int(box[3] - box[1]))


# ---------------------------------------------------------------- geometry
def mesh_points(objs):
    """Dense surface samples: every triangle's corners plus points spread across it, so the
    projected top outline is continuous instead of vertex-spiky."""
    dg = bpy.context.evaluated_depsgraph_get()
    W = np.array([(1, 0, 0), (1/3, 1/3, 1/3)])  # corners repeat across neighbours, so one corner + centre
    pts = []
    for o in objs:
        ev = o.evaluated_get(dg)
        me = ev.to_mesh()
        me.calc_loop_triangles()
        co = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', co); co = co.reshape(-1, 3)
        tri = np.empty(len(me.loop_triangles) * 3, dtype=np.int64); me.loop_triangles.foreach_get('vertices', tri); tri = tri.reshape(-1, 3)
        M = np.array(o.matrix_world)
        co = co @ M[:3, :3].T + M[:3, 3]
        A, B, C = co[tri[:, 0]], co[tri[:, 1]], co[tri[:, 2]]
        for w in W:
            pts.append(A * w[0] + B * w[1] + C * w[2])
        ev.to_mesh_clear()
    return np.concatenate(pts) if pts else np.zeros((0, 3))


def project(P, cam, w, h):
    pos, tgt, f = np.array(cam[:3]), np.array(cam[3:6]), cam[6]
    fwd = tgt - pos; fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, (0, 0, 1)); right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    d = P - pos
    zc = d @ fwd
    u = w / 2 + f * (d @ right) / zc
    v = h / 2 - f * (d @ up) / zc
    return u, v


def outline(P, cam, w, h):
    u, v = project(P, cam, w, h)
    ui = np.round(u).astype(np.int64)
    keep = (ui >= 0) & (ui < w)
    top = np.full(w, np.inf)
    np.minimum.at(top, ui[keep], v[keep])
    # upper envelope over a few columns: bridges columns no sample landed in
    env = top.copy()
    for k in (1, 2, 3):
        env = np.minimum(env, np.minimum(np.roll(top, k), np.roll(top, -k)) + 0.3 * k)
    return env


def loss_view(P, cam, view):
    t = TGT[view]
    o = outline(P, cam, t['w'], t['h'])
    tt = t['top']
    both = (tt >= 0) & np.isfinite(o)
    r = np.abs(o[both] - tt[both])
    hub = np.where(r < 8, r, 8 + (r - 8) * 0.3)  # robust to mirrors, hoops and edge noise
    only_t = ((tt >= 0) & ~np.isfinite(o)).sum()
    span = np.zeros_like(tt, bool); span[t['a']:t['b'] + 1] = True
    only_o = (np.isfinite(o) & ~span).sum()
    return hub.mean() + 30.0 * (only_t + only_o) / max(1, both.sum())


# ---------------------------------------------------------------- optimiser
def nelder_mead(fn, x0, step, iters=400):
    n = len(x0)
    pts = [np.array(x0, float)]
    for i in range(n):
        x = np.array(x0, float); x[i] += step[i]; pts.append(x)
    vals = [fn(p) for p in pts]
    for _ in range(iters):
        order = np.argsort(vals); pts = [pts[i] for i in order]; vals = [vals[i] for i in order]
        c = np.mean(pts[:-1], 0)
        xr = c + (c - pts[-1]); fr = fn(xr)
        if fr < vals[0]:
            xe = c + 2 * (c - pts[-1]); fe = fn(xe)
            pts[-1], vals[-1] = (xe, fe) if fe < fr else (xr, fr)
        elif fr < vals[-2]:
            pts[-1], vals[-1] = xr, fr
        else:
            xc = c + 0.5 * (pts[-1] - c); fc = fn(xc)
            if fc < vals[-1]:
                pts[-1], vals[-1] = xc, fc
            else:
                pts = [pts[0] + 0.5 * (p - pts[0]) for p in pts]
                vals = [fn(p) for p in pts]
    i = int(np.argmin(vals))
    return pts[i], vals[i]


def solve_camera(P, view, cam0):
    best = None
    for k in range(3):
        x0 = np.array(cam0, float) if best is None else best[0] + np.random.normal(0, 1, 7) * np.array([0.4, 0.4, 0.2, 0.1, 0.1, 0.05, 40])
        x, f = nelder_mead(lambda c: loss_view(P, c, view), x0, [0.8, 0.8, 0.4, 0.2, 0.2, 0.1, 120], iters=300)
        if best is None or f < best[1]: best = (x, f)
    return best


def initial_camera(P, view):
    t = TGT[view]
    cams = T.get('cams', {})
    dirv, height = ns['SHEET_VIEWS'][view][0], ns['SHEET_VIEWS'][view][1]
    if view in cams:
        (cx, cy), height = cams[view]; dirv = Vector((cx, cy, 0))
    d = np.array(dirv.normalized()) * 8.0
    centre = P.mean(0)
    cam = [centre[0] + d[0], centre[1] + d[1], height, centre[0], centre[1], centre[2] - 0.15, 1000.0]
    # scale focal length so the car spans the target's column run
    u, _ = project(P, cam, t['w'], t['h'])
    cam[6] *= (t['b'] - t['a']) / max(1.0, u.max() - u.min())
    return cam


# ---------------------------------------------------------------- shape
def apply_shape(S, mult, cab, dz=None):
    xs = sorted(S['ztop'])
    x_lo, x_hi = xs[0], xs[-1]
    st = {round(x_lo + (x_hi - x_lo) * i / (STATIONS - 1), 4): m for i, m in enumerate(mult)}
    mf = ns['pchip'](st)
    S['W'] = {x: v * mf(x) for x, v in S['W'].items()}
    S['wcb'] = {x: v * cab for x, v in S['wcb'].items()}
    if dz is not None:  # fender / haunch height (shoulder line outside the greenhouse)
        df = ns['pchip']({round(x_lo + (x_hi - x_lo) * i / (STATIONS - 1), 4): d for i, d in enumerate(dz)})
        g0, g1 = S['glass'] or (S['cabrio']['x0'], S['cabrio']['x1'])
        for x in list(S['zsh']):
            if not (g0 - 0.05 <= x <= g1 + 0.05):
                S['zsh'][x] = S['zsh'][x] + df(x)
    return S


def rebuild_body(mult, cab, dz=None):
    coll = bpy.data.collections[f'Fleet_{CID}']
    for o in list(coll.objects):
        if o.name.startswith(f'{CID}_Body') or o.name.startswith(f'{CID}_ArchCutter'):
            bpy.data.objects.remove(o, do_unlink=True)
    S = apply_shape(ns['spec'](CID), mult, cab, dz)
    ns['SLAB']['g'] = lambda x, sl=T.get('slab', 0.0), xr=S['wb'][0], x_lo=min(S['ztop']): sl * max(0.25, min(1.0, (x - x_lo) / max(0.1, xr - x_lo)))
    mats = ns['v3_materials'](S)
    body, cutter = ns['build_body_v3'](CID, S, coll, mats)
    bpy.context.view_layer.update()
    return mesh_points([body])


def main():
    np.random.seed(7)
    ns['build'](CID)
    coll = bpy.data.collections[f'Fleet_{CID}']
    static = [o for o in coll.objects if o.type == 'MESH' and not o.hide_render and not o.name.endswith('_Body')
              and 'steering' not in o.name and 'Interior' not in o.name]
    PS = mesh_points(static)
    mult, cab = [1.0] * STATIONS, 1.0
    PB = rebuild_body(mult, cab)
    P = np.concatenate([PB, PS])
    cams = {}
    for v in VIEWS:
        cams[v], f = solve_camera(P, v, initial_camera(P, v))
        print('STEP camera', v, round(f, 2), [round(c, 3) for c in cams[v]], flush=True)
    total = lambda P: sum(loss_view(P, cams[v], v) for v in VIEWS)
    cur = total(P)
    print('STEP start loss', round(cur, 3), flush=True)
    dz = [0.0] * STATIONS
    names = [('W', i) for i in range(STATIONS)] + [('cab', 0)] + [('dz', i) for i in range(STATIONS)]
    for rnd in range(ROUNDS):
        step = 0.06 / (rnd + 1)
        for kind, i in names:
            for sgn in (1, -1):
                m2, c2, d2 = list(mult), cab, list(dz)
                if kind == 'W': m2[i] = min(1.25, max(0.6, m2[i] + sgn * step))
                elif kind == 'cab': c2 = min(1.2, max(0.7, c2 + sgn * step))
                else: d2[i] = min(0.12, max(-0.12, d2[i] + sgn * step * 0.6))
                P2 = np.concatenate([rebuild_body(m2, c2, d2), PS])
                l2 = total(P2)
                if l2 < cur - 1e-3:
                    mult, cab, dz, cur, P = m2, c2, d2, l2, P2
                    print('STEP accept', rnd, kind, i, round(cur, 3), flush=True)
                    break
        for v in VIEWS:
            cams[v], f = solve_camera(P, v, cams[v])
        cur = total(P)
        print('STEP round', rnd, 'loss', round(cur, 3), 'mult', [round(m, 3) for m in mult], 'cab', round(cab, 3), 'dz', [round(d, 3) for d in dz], flush=True)
    out = dict(W_mult=mult, stations=STATIONS, wcb_mult=cab, zsh_dz=dz, cams={v: [float(c) for c in cams[v]] for v in VIEWS},
               boxes={v: [TGT[v]['w'], TGT[v]['h']] for v in VIEWS}, loss=float(cur),
               outlines={v: [None if not np.isfinite(y) else float(y) for y in outline(P, cams[v], TGT[v]['w'], TGT[v]['h'])] for v in VIEWS})
    with open(os.path.join(FIT, f'{CID}.json'), 'w') as fh:
        json.dump(out, fh, indent=1)
    print('STEP wrote', os.path.join(FIT, f'{CID}.json'), flush=True)


try:
    main()
except Exception:
    import traceback; traceback.print_exc(); sys.exit(1)
