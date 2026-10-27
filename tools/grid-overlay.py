"""Overlay a labelled pixel grid on part of an image, for reading off coordinates by eye.

  python tools/grid-overlay.py <image> <out.png> <x0> <y0> <x1> <y1> [step]
"""
import sys

from PIL import Image, ImageDraw

src, out = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = (int(v) for v in sys.argv[3:7])
step = int(sys.argv[7]) if len(sys.argv) > 7 else 50
img = Image.open(src).convert('RGB').crop((x0, y0, x1, y1))
d = ImageDraw.Draw(img)
for x in range((x0 // step + 1) * step, x1, step):
    major = x % (step * 2) == 0
    d.line((x - x0, 0, x - x0, y1 - y0), fill=(0, 140, 255) if major else (150, 200, 255), width=1)
    if major:
        d.text((x - x0 + 2, 2), str(x), fill=(0, 90, 200))
for y in range((y0 // step + 1) * step, y1, step):
    major = y % (step * 2) == 0
    d.line((0, y - y0, x1 - x0, y - y0), fill=(255, 60, 60) if major else (255, 170, 170), width=1)
    if major:
        d.text((2, y - y0 + 2), str(y), fill=(200, 0, 0))
img.save(out)
