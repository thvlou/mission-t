"""Target view box next to the matching render through the fitted camera, plus a blend of the two.

  python tools/match-compare.py <sheet.png> <render-dir> <car-id> <out.png>

The renders come from `run_v3.py ... match` (blender/vertigo_v3.py render_match), which uses the
cameras blender/fit_v3.py recovered, so both images share one pixel frame."""
import importlib.util
import os
import sys

from PIL import Image, ImageChops, ImageFilter

spec = importlib.util.spec_from_file_location('tm', os.path.join(os.path.dirname(__file__), 'target-mask.py'))
tm = importlib.util.module_from_spec(spec); spec.loader.exec_module(tm)

sheet, rdir, cid, out = sys.argv[1:5]
full = Image.open(sheet).convert('RGB').resize((1536, 1024))
box = tm.LAYOUTS[os.path.basename(sheet)[:2]]
rows = []
for view in ('front', 'rear'):
    x0, y0, x1, y1 = box[view]
    tgt = full.crop((x0, y0, x1, y1))
    r = Image.open(os.path.join(rdir, f'{cid}_match_{view}.png')).convert('RGBA').resize(tgt.size, Image.LANCZOS)
    bg = Image.new('RGBA', tgt.size, (226, 224, 220, 255))
    bg.alpha_composite(r)
    ren = bg.convert('RGB')
    # blend: target in the red channel's edges over the render, so misaligned lines show doubled
    edges = tgt.convert('L').filter(ImageFilter.FIND_EDGES).point(lambda v: 255 if v > 28 else 0)
    blend = Image.blend(ren, tgt, 0.5)
    red = Image.new('RGB', tgt.size, (220, 30, 40))
    blend.paste(red, mask=edges)
    rows.append([tgt, ren, blend])
w = sum(i.width for i in rows[0]) + 12
h = sum(r[0].height for r in rows) + 6
sheet_out = Image.new('RGB', (w, h), 'white')
y = 0
for r in rows:
    x = 0
    for im in r:
        sheet_out.paste(im, (x, y)); x += im.width + 6
    y += r[0].height + 6
sheet_out.save(out)
print('ok', out)
