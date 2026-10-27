"""Picker thumbnails (renders/vehicles/<id>_front|rear|side.png, 900x495) from the v3 studio renders:
each transparent render laid on the warm studio backdrop, the car filling ~86% of the frame.

  python tools/make-thumbs.py <renders-dir> <car-id> [<car-id> ...]
"""
import os
import sys

from PIL import Image

W, H = 900, 495
rdir = sys.argv[1]
for cid in sys.argv[2:]:
    for view in ('front', 'rear', 'side'):
        img = Image.open(os.path.join(rdir, f'{cid}_{view}.png')).convert('RGBA')
        solid = img.getchannel('A').point(lambda a: 255 if a > 140 else 0)
        l, t, r, b = solid.getbbox()
        s = min(W * 0.86 / (r - l), H * 0.8 / (b - t))
        img = img.resize((int(img.width * s), int(img.height * s)), Image.LANCZOS)
        bg = Image.new('RGBA', (W, H), (0, 0, 0, 255))
        px = bg.load()
        for y in range(H):
            v = int(232 - 14 * max(0, (y - H * 0.55) / (H * 0.45)) - 6 * max(0, (H * 0.3 - y) / (H * 0.3)))
            for x in range(W):
                px[x, y] = (v, v - 2, v - 6, 255)
        ox = int((W - (r - l) * s) / 2 - l * s)
        oy = int((H - (b - t) * s) / 2 - t * s)
        layer = Image.new('RGBA', (W, H), (0, 0, 0, 0))
        layer.paste(img, (ox, oy))
        bg.alpha_composite(layer)
        out = os.path.join('renders', 'vehicles', f'{cid}_{view}.png')
        bg.convert('RGB').save(out)
        print('wrote', out)
