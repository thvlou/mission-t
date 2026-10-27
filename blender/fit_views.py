# Fit a v3 car's nose, tail and cabin to all three target views:
#
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/fit_views.py -- <car-id> [rounds]
#
# fit_v3.py matched the upper outline of the 3/4 views with plan widths along the whole car. That
# leaves the ends loose: in each 3/4 view the near end is the right-hand side of the silhouette,
# which an upper outline barely touches. Here each 3/4 camera is re-solved with the wheel hubs as
# landmarks (TARGETS[...]['hubs'], view-box pixels) on top of the upper outline. Then, with the
# cameras held, the body is fitted to both views' upper and right-hand outlines
# (blender/v3_fit/<sheet>-right.npz, from tools/target-mask.py car_mask) through:
#   - plan width and shoulder height at stations in from the nose (front fenders) and from the
#     tail (rear haunches), easing back to the spec shape further in (vertigo_v3.apply_regions);
#     widths never drop below the spec over the wheels (the tyres stay covered) or 12% elsewhere
#   - the cabin width
# while the side view's measured silhouette holds the shoulders to their measured height.
# Result: 'regions', 'wcb_mult' and the cameras in blender/v3_fit/<car-id>.json, which spec() reads.
import json, os, sys
import numpy as np

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_argv = sys.argv[sys.argv.index('--') + 1:]
src = open(os.path.join(REPO, 'blender', 'fit_v3.py'), encoding='utf-8').read()
__file__ = os.path.join(REPO, 'blender', 'fit_v3.py')
exec(src[:src.rindex('try:')])  # fit_v3's targets, projection, optimiser and body rebuild
ROUNDS = int(_argv[1]) if len(_argv) > 1 else 3
pchip = ns['pchip']

RIGHT = np.load(os.path.join(FIT, f'{KEY}-right.npz'))
for v in VIEWS:
    r = RIGHT[v + '_right'].astype(np.float64)
    rows = T['right_rows'][v]  # rows where the right-hand outline is car, not floor shadow or the box edge
    keep = np.zeros_like(r, bool)
    if rows: keep[rows[0]:rows[1]] = True
    TGT[v]['right'] = np.where(keep & (r >= 0), r, -1.0)
# stations (m in from each end) with free width and shoulder height; spec shape from d_fix on
REGIONS = {'front': dict(d=[0.0, 0.12, 0.3, 0.55, 0.85], d_fix=1.3),
           'rear': dict(d=[0.0, 0.15, 0.4, 0.7, 1.0, 1.3], d_fix=1.7)}
SPEC_K = ns['spec'](CID)['_k']  # metres per sheet pixel


def right_outline(P, cam, w, h):
    u, v = project(P, cam, w, h)
    vi = np.round(v).astype(np.int64)
    keep = (vi >= 0) & (vi < h)
    out = np.full(h, -np.inf)
    np.maximum.at(out, vi[keep], u[keep])
    env = out.copy()
    for k in (1, 2):
        env = np.maximum(env, np.maximum(np.roll(out, k), np.roll(out, -k)) - 0.3 * k)
    return env


def loss_right(P, cam, view):
    t = TGT[view]
    o = right_outline(P, cam, t['w'], t['h'])
    tt = t['right']
    both = (tt >= 0) & np.isfinite(o)
    if not (tt >= 0).any(): return 0.0  # no usable right-hand outline in this view
    if not both.any(): return 50.0
    r = np.abs(o[both] - tt[both])
    hub = np.where(r < 8, r, 8 + (r - 8) * 0.3)
    miss = ((tt >= 0) & ~np.isfinite(o)).sum()
    return hub.mean() + 30.0 * miss / max(1, both.sum())


def loss_hubs(cam, view):
    w, h = TGT[view]['w'], TGT[view]['h']
    err = []
    for name, (u0, v0) in T['hubs'][view].items():
        u, v = project(HUB[name][None, :], cam, w, h)
        err.append(np.hypot(u[0] - u0, v[0] - v0))
    return float(np.mean(err))


def loss_cam(P, cam, view):
    return loss_view(P, cam, view) + loss_right(P, cam, view) + 2.0 * loss_hubs(cam, view)


def side_loss(P):
    """Upper side silhouette against the measured one (TARGETS top), in sheet pixels."""
    xm = (T['front'] + T['rear']) / 2
    px = xm - P[:, 0] / SPEC_K
    py = T['ground'] - P[:, 2] / SPEC_K
    res = []
    for x0, y0 in np.array(T['top'], float)[1:-1]:
        near = np.abs(px - x0) < 3
        if near.any():
            res.append(abs(y0 - py[near].min()))  # the orthographic side view is the most trustworthy: hold it both ways
    return float(np.mean(res)) if res else 0.0


def regions_of(x):
    """Parameter vector -> {'front': ..., 'rear': ...} and the cabin multiplier."""
    out, i = {}, 0
    for end, r in REGIONS.items():
        n = len(r['d'])
        out[end] = dict(r, W_mult=[float(v) for v in x[i:i + n]], zsh_dz=[float(v) for v in x[i + n:i + 2 * n]])
        i += 2 * n
    return out, float(x[i])


def rebuild(x):
    coll = bpy.data.collections[f'Fleet_{CID}']
    for o in list(coll.objects):
        if o.name.startswith(f'{CID}_Body') or o.name.startswith(f'{CID}_ArchCutter'):
            bpy.data.objects.remove(o, do_unlink=True)
    regions, cab = regions_of(x)
    S = ns['spec'](CID, dict(BASE_FIT, regions=regions, wcb_mult=cab))  # on top of fit_v3's plan widths
    ns['SLAB']['g'] = lambda x, sl=T.get('slab', 0.0), xr=S['wb'][0], x_lo=min(S['ztop']): sl * max(0.25, min(1.0, (x - x_lo) / max(0.1, xr - x_lo)))
    ns['SLAB']['rail'] = T.get('roof_rail', 0.016)
    ns['SLAB']['valley'] = T.get('valley', False)
    ns['SLAB']['ledge'] = T.get('ledge', 0.0)
    mats = ns['v3_materials'](S)
    body, cutter = ns['build_body_v3'](CID, S, coll, mats)
    bpy.context.view_layer.update()
    return mesh_points([body])


def main():
    global HUB
    np.random.seed(11)
    ns['build'](CID)
    coll = bpy.data.collections[f'Fleet_{CID}']
    R = ns['spec'](CID)['R']
    HUB = {}
    for o in coll.objects:
        name = o.name.split('.')[0]
        if name in ('wheel_FL', 'wheel_FR', 'wheel_RL', 'wheel_RR'):
            side = 1 if name[-1] == 'L' else -1  # the centre cap sits 0.1 m (base wheel) outboard of the wheel centre
            HUB[name] = np.array(o.matrix_world.translation) + np.array((0, side * 0.1 * R / 0.362, 0))
    static = [o for o in coll.objects if o.type == 'MESH' and not o.hide_render and not o.name.endswith('_Body')
              and 'steering' not in o.name and 'Interior' not in o.name]
    PS = mesh_points(static)
    global BASE_FIT
    fit = json.load(open(os.path.join(FIT, f'{CID}.json')))
    BASE_FIT = fit
    cams = {v: np.array(fit['cams'][v], float) for v in VIEWS}
    # start from the previous fit where there is one
    prev = fit.get('regions', {})
    x = []
    for end, r in REGIONS.items():
        p = prev.get(end, {})
        same = list(p.get('d', [])) == list(r['d'])
        x += list(p['W_mult']) if same else [1.0] * len(r['d'])
        x += list(p['zsh_dz']) if same else [0.0] * len(r['d'])
    x.append(fit.get('wcb_mult', 1.0))
    x = np.array(x, float)
    # Width floors: the body has to cover the tyres near each axle; elsewhere it may pinch in a little
    S0 = ns['spec'](CID)
    x_lo, x_hi = min(S0['ztop']), max(S0['ztop'])
    w_lo = []
    for end, r in REGIONS.items():
        for d in r['d']:
            xs = x_hi - d if end == 'front' else x_lo + d
            w_lo.append(1.0 if min(abs(xs - a) for a in S0['wb']) < 0.4 else 0.88)
        w_lo += [None] * len(r['d'])
    w_lo.append(None)
    x = np.array([max(v, lo) if lo else v for v, lo in zip(x, w_lo)])
    PB = rebuild(x)
    P = np.concatenate([PB, PS])
    for v in VIEWS:
        best = None
        for k in range(3):
            x0 = cams[v] if best is None else best[0] + np.random.normal(0, 1, 7) * np.array([0.3, 0.3, 0.15, 0.08, 0.08, 0.04, 30])
            c, fv = nelder_mead(lambda c: loss_cam(P, c, v), x0, [0.6, 0.6, 0.3, 0.15, 0.15, 0.08, 90], iters=350)
            if best is None or fv < best[1]: best = (c, fv)
        cams[v] = best[0]
        print('STEP camera', v, 'top', round(loss_view(P, cams[v], v), 2), 'right', round(loss_right(P, cams[v], v), 2), 'hubs', round(loss_hubs(cams[v], v), 2), flush=True)

    # (the side silhouette is checked on the body alone: lamps and mirrors stay where the spec body put them)
    def total(PB, P):
        return sum(loss_view(P, cams[v], v) + 1.5 * loss_right(P, cams[v], v) for v in VIEWS) + 2.0 * side_loss(PB)

    def report(tag):
        print('STEP', tag, round(cur, 3), ' '.join(f'{v} top {loss_view(P, cams[v], v):.2f} right {loss_right(P, cams[v], v):.2f}' for v in VIEWS),
              'side', round(side_loss(PB), 2), flush=True)
    cur = total(PB, P)
    report('shape start')
    kinds = []
    for end, r in REGIONS.items():
        kinds += [('W', end)] * len(r['d']) + [('dz', end)] * len(r['d'])
    kinds.append(('cab', None))
    for rnd in range(ROUNDS):
        step = 0.08 / (rnd + 1)
        for i, (kind, end) in enumerate(kinds):
            for sgn in (1, -1):
                x2 = x.copy()
                if kind == 'W': x2[i] = min(1.25, max(w_lo[i], x2[i] + sgn * step))
                elif kind == 'dz': x2[i] = min(0.15, max(-0.15, x2[i] + sgn * step * 0.6))
                else: x2[i] = min(1.25, max(0.8, x2[i] + sgn * step * 0.5))
                PB2 = rebuild(x2)
                P2 = np.concatenate([PB2, PS])
                l2 = total(PB2, P2)
                if l2 < cur - 1e-3:
                    x, cur, P, PB = x2, l2, P2, PB2
                    break
        regions, cab = regions_of(x)
        report(f'round {rnd}')
        print('STEP   ', {e: (np.round(r['W_mult'], 3).tolist(), np.round(r['zsh_dz'], 3).tolist()) for e, r in regions.items()}, 'cab', round(cab, 3), flush=True)
    regions, cab = regions_of(x)
    fit['cams'] = {v: [float(c) for c in cams[v]] for v in VIEWS}
    fit['regions'] = regions
    fit['wcb_mult'] = cab
    fit.pop('front', None)
    fit['views_loss'] = float(cur)
    with open(os.path.join(FIT, f'{CID}.json'), 'w') as fh:
        json.dump(fit, fh, indent=1)
    print('STEP wrote', CID, flush=True)


try:
    main()
except Exception:
    import traceback; traceback.print_exc(); sys.exit(1)
