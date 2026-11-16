# python silhouettes.py <gt-v4-source dir>
# Filled car silhouettes of blueprints A2/A5/A3/A4 for the visual hull (build_body.py, HULL mode).
# Car pixels: not near-white; small gaps in the white paint closed (5 px), then everything the background
# flood fill cannot reach is car. Mirrors are removed (the body is fitted without them, they are separate
# parts): A5 by bridging the plan width across the mirror columns, A3/A4 by clipping the mirror rows.
# Writes hybrid/tex/sil-<view>.png (255 = car).
import sys, os, numpy as np
from PIL import Image, ImageFilter, ImageDraw
d = sys.argv[1]
out = os.path.join(d, 'hybrid', 'tex')


def silhouette(name):
    a = np.asarray(Image.open(os.path.join(d, 'blueprint', name)).convert('RGB')).astype(int)
    car = ((a.mean(2) < 244) | ((a.max(2) - a.min(2)) > 25)).astype(np.uint8) * 255
    im = Image.fromarray(car).filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))
    im = im.convert('L')
    ImageDraw.floodfill(im, (0, 0), 128)
    m = np.asarray(im) != 128
    return m


def bridge_columns(m, c0, c1):
    """Replace each column in c0..c1 by the extent interpolated between columns c0 and c1 (plan view)."""
    def ext(c):
        r = np.flatnonzero(m[:, c]); return r[0], r[-1]
    (t0, b0), (t1, b1) = ext(c0), ext(c1)
    for c in range(c0, c1 + 1):
        f = (c - c0) / (c1 - c0)
        t, b = int(round(t0 + f * (t1 - t0))), int(round(b0 + f * (b1 - b0)))
        m[:, c] = False; m[t:b + 1, c] = True


def clip_rows(m, r0, r1, c0, c1):
    m[r0:r1, :c0] = False; m[r0:r1, c1:] = False


views = {}
m = silhouette('gt-A2-side.png')
# the ground shadow under the car reads as car: below the sill (row 655, z 0.11 m) only the tyres are real
k2 = 4.736 / 1483
yy, xx = np.mgrid[:m.shape[0], :m.shape[1]]
tyres = np.zeros_like(m)
for cx in (315, 1214):
    tyres |= (xx - cx) ** 2 + (yy - (691 - 0.40 / k2)) ** 2 < (0.40 / k2) ** 2
m[(yy > 655) & ~tyres] = False
views['A2'] = m
m = silhouette('gt-A5-top.png'); bridge_columns(m, 505, 640); views['A5'] = m
m = silhouette('gt-A3-front.png'); clip_rows(m, 270, 400, 296, 1240); views['A3'] = m
m = silhouette('gt-A4-rear.png'); clip_rows(m, 250, 345, 330, 1206); views['A4'] = m
for k, m in views.items():
    Image.fromarray(m.astype(np.uint8) * 255).save(os.path.join(out, f'sil-{k}.png'))
    print(k, 'car px', int(m.sum()))
