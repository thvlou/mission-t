"""Draw a fit's projected outline (green) over the target's 3/4 views with the extracted target
outline (red).  python tools/fit-overlay.py <car-id> <sheet.png> <out.png>"""
import json
import sys

import numpy as np
from PIL import Image, ImageDraw

cid, sheet, out = sys.argv[1:4]
fit = json.load(open(f'blender/v3_fit/{cid}.json'))
tg = np.load(f'blender/v3_fit/{sheet.split("/")[-1][:2]}-targets.npz')
full = Image.open(sheet).convert('RGB').resize((1536, 1024))
tiles = []
for v in ('front', 'rear'):
    x0, y0, x1, y1 = tg[v + '_box']
    im = full.crop((x0, y0, x1, y1))
    d = ImageDraw.Draw(im)
    for u, y in enumerate(tg[v + '_top']):
        if y >= 0: d.point((u, int(y)), fill=(255, 0, 0))
    pts = [(u, y) for u, y in enumerate(fit['outlines'][v]) if y is not None]
    for (a, b), (c, e) in zip(pts, pts[1:]):
        if c - a <= 2: d.line((a, b, c, e), fill=(0, 200, 0), width=2)
    tiles.append(im)
W = sum(t.width for t in tiles) + 8
canvas = Image.new('RGB', (W, max(t.height for t in tiles)), 'white')
canvas.paste(tiles[0], (0, 0)); canvas.paste(tiles[1], (tiles[0].width + 8, 0))
canvas.save(out)
