"""Trace a car's side silhouette from a design-target sheet (side view in the lower half).

The studio background is fitted per row as a straight line between the far-left and far-right
strips (it darkens toward the corners), a pixel belongs to the car where it differs from that, and
only the region connected to the middle of the car is kept, so stray edges of the upper views, the
floor shadow and the label are ignored. Outputs the top line per column, the extent, and an
overlay PNG for checking.

Also finds the two wheels from the dark tyre rings (centre and outer radius, in sheet pixels).

  python tools/trace-silhouette.py <sheet.png> <out-prefix> [crop-from-y] [threshold]
"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

src, out = sys.argv[1], sys.argv[2]
img = Image.open(src).convert('RGB')
W, H = img.size
y_off = int(sys.argv[3]) if len(sys.argv) > 3 else int(H * 0.52)
thr = float(sys.argv[4]) if len(sys.argv) > 4 else 16
side = img.crop((0, y_off, W, H))
a = np.asarray(side.filter(ImageFilter.GaussianBlur(1.0))).astype(np.float32)
h, w, _ = a.shape
left = np.median(a[:, 4:30], axis=1)
right = np.median(a[:, -30:-4], axis=1)
t = np.linspace(0, 1, w)[None, :, None]
bg = left[:, None, :] * (1 - t) + right[:, None, :] * t
diff = np.abs(a - bg).max(axis=2)
m = Image.fromarray(((diff > thr) * 255).astype(np.uint8))
m = m.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))  # close small gaps
mask = np.asarray(m) > 0
# Seed: the busiest row near the middle of the image, at the centre column of that row's car run.
rows = mask[:, w // 4: 3 * w // 4].sum(axis=1)
seed_y = int(np.argmax(rows[: int(h * 0.75)]))
xs = np.where(mask[seed_y])[0]
seed_x = int(np.median(xs))
filled = m.convert('L')
ImageDraw.floodfill(filled, (seed_x, seed_y), 128)
comp = np.asarray(filled) == 128
cols = np.where(comp.any(axis=0))[0]
x0, x1 = int(cols.min()), int(cols.max())
top = [int(np.where(comp[:, x])[0].min()) if comp[:, x].any() else None for x in range(w)]
# Wheels: the dark tyre pixels in the lower part of the car, split at the middle of the car.
luma = a @ np.array([0.299, 0.587, 0.114])
dark = (luma < 70) & comp
wheels = []
mid = (x0 + x1) // 2
for lo, hi in ((x0, mid), (mid, x1)):
    ys, xs = np.where(dark[:, lo:hi])
    lowest = ys.max()
    keep = ys > lowest - (x1 - x0) * 0.17   # the ring spans about a sixth of the car's length
    ys, xs = ys[keep], xs[keep] + lo
    cx, cy = (xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2
    r = ((xs.max() - xs.min()) + (ys.max() - ys.min())) / 4
    wheels.append({'cx': round(float(cx), 1), 'cy': round(float(cy) + y_off, 1), 'r': round(float(r), 1)})
res = {'size': [W, H], 'y_off': y_off, 'x0': x0, 'x1': x1, 'top': top, 'wheels': wheels}
json.dump(res, open(out + '.json', 'w'))
ov = side.copy()
d = ImageDraw.Draw(ov)
for x in range(w):
    if top[x] is not None:
        d.rectangle((x, top[x] - 1, x, top[x] + 1), fill=(255, 0, 0))
d.line((x0, 0, x0, h), fill=(0, 160, 0))
d.line((x1, 0, x1, h), fill=(0, 160, 0))
for wh in wheels:
    cy = wh['cy'] - y_off
    d.ellipse((wh['cx'] - wh['r'], cy - wh['r'], wh['cx'] + wh['r'], cy + wh['r']), outline=(0, 120, 255), width=2)
ov.save(out + '-overlay.png')
print(json.dumps({'x0': x0, 'x1': x1, 'length_px': x1 - x0, 'wheels': wheels}))
