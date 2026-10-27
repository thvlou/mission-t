"""Car silhouette masks from the design-target sheets, for fitting the 3D models to them.

Each view box on a sheet sits on a smooth warm-grey studio sweep. Per view: fit a quadratic
background surface to the box's border pixels, mark pixels that differ from it in colour or that
are much darker (tyres, trim), reject soft floor shadow (same hue as the floor, only somewhat
darker), keep the largest connected blob and fill its holes.

  python tools/target-mask.py <sheet.png> <out-dir>     # writes <id>-<view>-mask.png + overlay
"""
import os
import sys
from collections import deque

import numpy as np
from PIL import Image

LAYOUTS = {
    '01': {'front': (0, 80, 790, 450), 'rear': (780, 80, 1536, 450), 'side': (0, 500, 1536, 920)},
    '02': {'front': (20, 130, 850, 500), 'rear': (820, 130, 1530, 500), 'side': (60, 540, 1480, 940)},
    '03': {'front': (10, 90, 790, 480), 'rear': (800, 130, 1536, 460), 'side': (40, 540, 1500, 900)},
    '04': {'front': (20, 90, 790, 450), 'rear': (780, 100, 1530, 440), 'side': (40, 500, 1500, 920)},
    '05': {'front': (0, 70, 790, 420), 'rear': (790, 70, 1530, 420), 'side': (60, 470, 1400, 920)},
    '06': {'front': (10, 90, 780, 470), 'rear': (780, 90, 1536, 470), 'side': (40, 510, 1500, 900)},
}


def background(img):
    """Quadratic fit per channel to the box border (outer 6% each side, minus the bottom)."""
    h, w, _ = img.shape
    yy, xx = np.mgrid[0:h, 0:w]
    m = max(4, int(min(h, w) * 0.06))
    border = np.zeros((h, w), bool)
    border[:m, :] = True
    border[:, :m] = True
    border[:, -m:] = True
    u, v = xx / w, yy / h
    A = np.stack([np.ones_like(u), u, v, u * u, v * v, u * v], -1)
    bg = np.zeros_like(img)
    for c in range(3):
        coef, *_ = np.linalg.lstsq(A[border], img[..., c][border], rcond=None)
        bg[..., c] = A @ coef
    return bg


def largest_blob(mask):
    h, w = mask.shape
    seen = np.zeros_like(mask)
    best = []
    for y0 in range(0, h, 2):
        for x0 in range(0, w, 2):
            if not mask[y0, x0] or seen[y0, x0]: continue
            q = deque([(y0, x0)]); seen[y0, x0] = True; comp = []
            while q:
                y, x = q.popleft(); comp.append((y, x))
                for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                    ny, nx = y + dy, x + dx
                    if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not seen[ny, nx]:
                        seen[ny, nx] = True; q.append((ny, nx))
            if len(comp) > len(best): best = comp
    out = np.zeros_like(mask)
    if best:
        ys, xs = zip(*best); out[list(ys), list(xs)] = True
    return out


def fill_holes(mask):
    h, w = mask.shape
    outside = np.zeros_like(mask)
    q = deque()
    for y in range(h):
        for x in (0, w - 1):
            if not mask[y, x]: q.append((y, x)); outside[y, x] = True
    for x in range(w):
        for y in (0, h - 1):
            if not mask[y, x] and not outside[y, x]: q.append((y, x)); outside[y, x] = True
    while q:
        y, x = q.popleft()
        for dy, dx in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            ny, nx = y + dy, x + dx
            if 0 <= ny < h and 0 <= nx < w and not mask[ny, nx] and not outside[ny, nx]:
                outside[ny, nx] = True; q.append((ny, nx))
    return ~outside


def dilate(mask, r):
    out = mask.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            out |= np.roll(np.roll(mask, dy, 0), dx, 1)
    return out


def erode(mask, r):
    return ~dilate(~mask, r)


def car_mask(img):
    bg = background(img)
    lum = img.mean(-1) + 1e-3
    blum = bg.mean(-1) + 1e-3
    ratio = lum / blum
    # chroma: colour direction difference after normalising brightness
    chroma = np.abs(img / lum[..., None] - bg / blum[..., None]).sum(-1)
    diff = np.abs(img - bg).max(-1)
    # edges: car panels have hard edges, floor shadows are soft
    gy, gx = np.gradient(img.mean(-1))
    edge = np.hypot(gx, gy) > 9
    shadow = (ratio > 0.42) & (ratio < 0.985) & (chroma < 0.06) & ~edge
    cand = ((diff > 10) | (chroma > 0.06) | (ratio < 0.42) | edge) & ~shadow
    cand = erode(dilate(cand, 3), 3)  # close small gaps along low-contrast panel edges
    blob = largest_blob(cand)
    return fill_holes(erode(dilate(blob, 2), 2))


if __name__ == '__main__':
    sheet, out_dir = sys.argv[1], sys.argv[2]
    os.makedirs(out_dir, exist_ok=True)
    key = os.path.basename(sheet)[:2]
    full = np.asarray(Image.open(sheet).convert('RGB').resize((1536, 1024)), dtype=np.float32)
    for view, (x0, y0, x1, y1) in LAYOUTS[key].items():
        img = full[y0:y1, x0:x1]
        m = car_mask(img)
        Image.fromarray((m * 255).astype(np.uint8)).save(os.path.join(out_dir, f'{key}-{view}-mask.png'))
        ov = img.copy()
        edge = m ^ erode(m, 1)
        ov[edge] = (255, 0, 0)
        Image.fromarray(ov.astype(np.uint8)).save(os.path.join(out_dir, f'{key}-{view}-overlay.png'))
        print(key, view, int(m.sum()))


def top_profile(mask, keep=0.25):
    """Per column, the first car pixel from the top; columns with little car below are dropped
    (stray background speckle), as is everything outside the car's main span."""
    cnt = mask.sum(0)
    ok = cnt >= keep * cnt.max()
    top = np.where(ok, mask.argmax(0), -1)
    return top


def top_edge(img, thr=26, gap=3):
    """Per column, the first sharp top-to-bottom change from the top of the box: the car's upper
    outline. The studio sweep only changes gradually, so its vignette never trips it. Columns with
    no edge get -1; isolated outliers (speckle, reflections) are dropped against a running median."""
    k = np.ones(3) / 3
    sm = img.copy()
    for ax in (0, 1):
        sm = np.apply_along_axis(lambda a: np.convolve(a, k, 'same'), ax, sm)
    dy = np.abs(sm[2 * gap:] - sm[:-2 * gap]).sum(-1)
    hit = dy > thr
    hit[:8] = False  # the smoothing pads the box edge with zeros
    hit[:, :4] = hit[:, -4:] = False
    first = np.where(hit.any(0), hit.argmax(0) + gap, -1)
    out = first.copy()
    for u in range(len(first)):
        lo, hi = max(0, u - 6), min(len(first), u + 7)
        win = first[lo:hi][first[lo:hi] >= 0]
        if first[u] < 0 or len(win) < 5 or abs(first[u] - np.median(win)) > 12:
            out[u] = -1
    return out
