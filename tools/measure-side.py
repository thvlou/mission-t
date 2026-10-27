"""Measure a target sheet's side view: car extents, wheel centres and radii, ground line, and the
top/bottom silhouette every 20 px. Car pixels are told from the warm grey backdrop by colour
distance (works for saturated and dark paints; check silver cars by eye).

  python tools/measure-side.py <sheet.png> <y0> <y1> [threshold]
"""
import sys

from PIL import Image

im = Image.open(sys.argv[1]).convert('RGB')
px = im.load()
y0, y1 = int(sys.argv[2]), int(sys.argv[3])
thr = float(sys.argv[4]) if len(sys.argv) > 4 else 38
W = im.width

def bg(x):  # backdrop colour at this column, sampled above the car
    return px[x, y0]

def car(x, y):
    r, g, b = px[x, y]
    br, bgc, bb = bg(x)
    return abs(r - br) + abs(g - bgc) + abs(b - bb) > thr

def dark(p): return max(p) < 60

cols = {}
for x in range(0, W, 2):
    ys = [y for y in range(y0, y1) if car(x, y)]
    if len(ys) > 8: cols[x] = (ys[0], ys[-1])
xs = sorted(cols)
print('extent', xs[0], xs[-1])
# tyres: the darkest pixels; find two wheel blobs from dark columns near the bottom
darkcols = [x for x in range(0, W) if sum(1 for y in range(y1 - 260, y1) if dark(px[x, y])) > 60]
blobs = []
for x in darkcols:
    if blobs and x - blobs[-1][1] <= 4: blobs[-1][1] = x
    else: blobs.append([x, x])
blobs = [b for b in blobs if b[1] - b[0] > 80]
for a, b in blobs:
    c = (a + b) // 2
    col = [y for y in range(y1 - 300, y1) if dark(px[c, y])]
    print('wheel', a, b, 'centre x', c, 'tyre y', col[0], col[-1], 'r', (col[-1] - col[0]) / 2, 'cy', (col[0] + col[-1]) / 2)
print('top/bottom every 20px:')
print([(x, cols[x][0]) for x in xs[::10]])
