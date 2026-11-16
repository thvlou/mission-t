# python profiles.py <gt-v4-source dir>
# 1D design curves of the GT v4 body, measured off the blueprint silhouettes (silhouettes.py) and class masks
# (masks.py), for the surfaced body (build_surface.py). Every curve is sampled at stations x (metres, +x = nose) and
# smoothed, so the body built from them has no lumps of its own:
#   top(x), bottom(x)      side silhouette A2: roof / bonnet / deck line, and the underside (tyre spans bridged)
#   half(x)                plan half width, A5 (mirrors already bridged by silhouettes.py)
#   gh_out(x), gh_in(x)    greenhouse in plan, A5 glass: outer edge of the side glass (its base) and inner edge (roof)
#   belt(x)                window sill line, lowest A2 glass row inside the cabin span
#   front_w(z), rear_w(z)  A3 / A4 half width at each height (the body's section envelope at its ends)
#   nose(zo), tail(zo)     A2 front-most / rear-most x at each height (the bumper faces' centre-plane profile)
# Writes hybrid/profiles.json and hybrid/renders/profiles.png (the curves drawn over the drawings).
import sys, os, json, numpy as np
from PIL import Image, ImageDraw

d = sys.argv[1]
tex = os.path.join(d, 'hybrid', 'tex')
L = 4.736
K2, K5 = L / 1483, L / 1466


def img(name): return np.asarray(Image.open(os.path.join(tex, name)))
def mask(name):
    m = img(f'mask-{name}.png'); return m[..., 0] if m.ndim == 3 else m


sil2, sil5 = img('sil-A2.png') > 127, img('sil-A5.png') > 127
sil3, sil4 = img('sil-A3.png') > 127, img('sil-A4.png') > 127
m2, m5 = mask('A2'), mask('A5')


def flood(m, seed):
    out = np.zeros_like(m); stack = [seed]
    while stack:
        i, j = stack.pop()
        if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1]) or out[i, j] or not m[i, j]: continue
        out[i, j] = True
        stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    return out


# the cabin in plan: windscreen + A-pillar strips + side glass, one connected region (bonnet vents, intakes and deck
# louvres are glass-dark too, but not part of it)
cabin_px = np.isin(m5, (2, 6))
cabin = flood(cabin_px, (493, 560))
side_seed = next((r, 765) for r in range(493, 1024) if m5[r, 765] == 2)
cabin |= flood(cabin_px, side_seed)


def smooth(v, k=7, it=3):
    """Moving average (k samples), repeated; NaNs filled by interpolation first."""
    v = np.asarray(v, float); ok = ~np.isnan(v)
    if ok.sum() < 2: return v
    idx = np.arange(len(v)); v = np.interp(idx, idx[ok], v[ok])
    w = np.ones(k) / k
    for _ in range(it):
        v = np.convolve(np.pad(v, k // 2, mode='edge'), w, 'valid')
    return v


xs = np.round(np.arange(-2.36, 2.3601, 0.02), 4)
top, bottom, half, gh_out, gh_in, belt = [], [], [], [], [], []
WHEELS = [(1.435, 0.44), (-1.435, 0.44)]               # tyre spans to bridge for the underside
for x in xs:
    c2 = int(round(764.5 - x / K2)); c5 = int(round(765 - x / K5))
    col = np.flatnonzero(sil2[:, c2]) if 0 <= c2 < sil2.shape[1] else []
    top.append((691 - col[0]) * K2 if len(col) else np.nan)
    in_wheel = any(abs(x - wx) < r for wx, r in WHEELS)
    bottom.append(np.nan if in_wheel or not len(col) else (691 - col[-1]) * K2)
    rows = np.flatnonzero(sil5[:, c5]) if 0 <= c5 < sil5.shape[1] else []
    half.append(max(rows[-1] - 493, 493 - rows[0]) * K5 if len(rows) else np.nan)
    g = np.flatnonzero(cabin[493:, c5])                   # +y half of the plan: cabin rows below the centre line
    if len(g):
        gh_out.append(g[-1] * K5)
        # side glass sliver: the run of cabin rows ending at the outer edge; its inner end is the roof edge
        gs = set(g.tolist()); run = g[-1]
        while run - 1 in gs: run -= 1
        gh_in.append(run * K5 if run > 3 else np.nan)       # the windscreen spans the centre line: no roof there
    else:
        gh_out.append(np.nan); gh_in.append(np.nan)
    gl = np.flatnonzero(np.isin(m2[:, c2], (2, 7))) if 0 <= c2 < m2.shape[1] else []
    belt.append((691 - gl[-1]) * K2 if len(gl) and -0.95 < x < 1.25 else np.nan)

front_w, rear_w, zs = [], [], np.round(np.arange(0.0, 1.30, 0.01), 3)
for z in zs:
    r3, r4 = int(round(880 - z * 585)), int(round(865 - z * 573))
    c = np.flatnonzero(sil3[r3]) if 0 <= r3 < sil3.shape[0] else []
    front_w.append(max(767.5 - c[0], c[-1] - 767.5) / 721 if len(c) else 0.0)
    c = np.flatnonzero(sil4[r4]) if 0 <= r4 < sil4.shape[0] else []
    rear_w.append(max(767.5 - c[0], c[-1] - 767.5) / 691 if len(c) else 0.0)

zo = np.round(np.arange(0.10, 1.0001, 0.005), 4)
nose, tail = [], []
for z in zo:
    c = np.flatnonzero(sil2[int(round(691 - z / K2))])
    nose.append((764.5 - c[0]) * K2 if len(c) else np.nan); tail.append((764.5 - c[-1]) * K2 if len(c) else np.nan)

prof = dict(x=xs.tolist(), zo=zo.tolist(), nose=smooth(nose, 5, 2).tolist(), tail=smooth(tail, 5, 2).tolist(), top=smooth(top).tolist(), bottom=smooth(bottom, 9).tolist(), half=smooth(half).tolist(),
            gh_out=[float(v) for v in np.asarray(gh_out, float)], gh_in=[float(v) for v in np.asarray(gh_in, float)],
            belt=[float(v) for v in np.asarray(belt, float)],
            z=zs.tolist(), front_w=smooth(front_w, 5).tolist(), rear_w=smooth(rear_w, 5).tolist())
# the greenhouse curves only exist over the cabin: smooth within their span, keep NaN outside
for k in ('gh_out', 'gh_in', 'belt'):
    v = np.array(prof[k]); ok = ~np.isnan(v)
    if ok.any():
        i0, i1 = np.flatnonzero(ok)[[0, -1]]
        v[i0:i1 + 1] = smooth(v[i0:i1 + 1], 7)
    prof[k] = [None if np.isnan(a) else float(a) for a in v]
json.dump(prof, open(os.path.join(d, 'hybrid', 'profiles.json'), 'w'))

# check sheet: side curves on A2, plan curves on A5
a2 = Image.open(os.path.join(d, 'blueprint', 'gt-A2-side.png')).convert('RGB'); dr = ImageDraw.Draw(a2)
a5 = Image.open(os.path.join(d, 'blueprint', 'gt-A5-top.png')).convert('RGB'); d5 = ImageDraw.Draw(a5)
for key, colr in (('top', (220, 30, 40)), ('bottom', (30, 90, 220)), ('belt', (20, 160, 60))):
    pts = [(764.5 - x / K2, 691 - v / K2) for x, v in zip(xs, prof[key]) if v is not None and not np.isnan(v)]
    dr.line(pts, fill=colr, width=2)
for key, colr in (('half', (220, 30, 40)), ('gh_out', (20, 160, 60)), ('gh_in', (30, 90, 220))):
    pts = [(765 - x / K5, 493 + v / K5) for x, v in zip(xs, prof[key]) if v is not None and not np.isnan(v)]
    if pts: d5.line(pts, fill=colr, width=2)
sheet = Image.new('RGB', (1536, 2048), (255, 255, 255)); sheet.paste(a2, (0, 0)); sheet.paste(a5, (0, 1024))
sheet.save(os.path.join(d, 'hybrid', 'renders', 'profiles.png'))
print('PROFILES', {k: int(np.sum([v is not None and not (isinstance(v, float) and np.isnan(v)) for v in prof[k]])) for k in ('top', 'bottom', 'half', 'gh_out', 'gh_in', 'belt')})
