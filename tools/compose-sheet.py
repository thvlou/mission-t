"""Lay three transparent car renders (front 3/4, rear 3/4, side) on a studio backdrop in the same
layout as the design-target sheets, and build a side-by-side comparison with the target.

  python tools/compose-sheet.py <renders-dir> <car-id> <target-sheet.png> <out-dir> "<TITLE>" "<COLOUR>"
"""
import os
import sys

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageFilter

rdir, cid, target, out_dir, title, colour = sys.argv[1:7]
W, H = 1536, 1024


def backdrop():
    # Warm light grey sweep: a little darker at the top corners, brightest on the floor.
    bg = Image.new('RGB', (W, H), (236, 234, 230))
    px = bg.load()
    for y in range(H):
        for x in range(0, W, 2):
            dx = (x - W / 2) / (W / 2)
            v = 238 - 10 * dx * dx - 6 * max(0, (300 - y) / 300)
            c = (int(v), int(v - 2), int(v - 6))
            px[x, y] = c
            if x + 1 < W: px[x + 1, y] = c
    return bg


def font(size, bold=False):
    for name in (('seguisb.ttf' if bold else 'segoeui.ttf'), 'arial.ttf'):
        try:
            return ImageFont.truetype(os.path.join('C:/Windows/Fonts', name), size)
        except OSError:
            continue
    return ImageFont.load_default()


def place(sheet, path, box):
    img = Image.open(path).convert('RGBA')
    bx, by, bw, bh = box
    # Fit the car itself (alpha above the faint floor shadow) into the box; the shadow around it
    # fades out towards the edges of the render so it never shows a hard frame.
    solid = img.getchannel('A').point(lambda a: 255 if a > 140 else 0)
    l, t, r, b = solid.getbbox() or (0, 0, img.width, img.height)
    s = min(bw / (r - l), bh / (b - t))
    w, h = img.width, img.height
    fade = Image.new('L', (w, h), 0)
    m = int(min(w, h) * 0.12)
    fade.paste(255, (m, m, w - m, h - m))
    fade = fade.filter(ImageFilter.GaussianBlur(m * 0.6))
    a = ImageChops.multiply(img.getchannel('A'), ImageChops.lighter(fade, solid))
    img.putalpha(a)
    img = img.resize((int(w * s), int(h * s)), Image.LANCZOS)
    ox = int(bx + (bw - (r - l) * s) / 2 - l * s)
    oy = int(by + (bh - (b - t) * s) / 2 - t * s)
    layer = Image.new('RGBA', sheet.size, (0, 0, 0, 0))
    layer.paste(img, (ox, oy))
    sheet.alpha_composite(layer)


sheet = backdrop().convert('RGBA')
d = ImageDraw.Draw(sheet)
d.text((34, 26), title, font=font(30, True), fill=(30, 30, 32))
tw = d.textlength(title, font=font(30, True))
d.text((34 + tw + 14, 26), '/ ' + colour, font=font(30), fill=(30, 30, 32))
place(sheet, os.path.join(rdir, f'{cid}_front.png'), (20, 90, 740, 360))
place(sheet, os.path.join(rdir, f'{cid}_rear.png'), (776, 90, 740, 360))
place(sheet, os.path.join(rdir, f'{cid}_side.png'), (40, 520, 1456, 400))
for text, x, y in (('FRONT 3/4', 48, 462), ('REAR 3/4', 852, 462), ('SIDE', 744, 944)):
    d.text((x, y), text, font=font(15), fill=(60, 60, 62))
os.makedirs(out_dir, exist_ok=True)
sheet = sheet.convert('RGB')
sheet.save(os.path.join(out_dir, f'{cid}-sheet.png'))
tgt = Image.open(target).convert('RGB').resize((W, H))
pair = Image.new('RGB', (W * 2 + 20, H), (255, 255, 255))
pair.paste(tgt, (0, 0))
pair.paste(sheet, (W + 20, 0))
pair.save(os.path.join(out_dir, f'{cid}-compare.png'))
print('ok', os.path.join(out_dir, f'{cid}-compare.png'))
