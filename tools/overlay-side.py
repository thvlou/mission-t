"""Overlay an orthographic side render (sheet scale) on the target sheet's side view.

  python tools/overlay-side.py <target-sheet.png> <ortho.png> <out.png>
Target in its own colours, our car's silhouette edge in red and a 50% ghost of our render.
"""
import sys

from PIL import Image, ImageChops, ImageFilter

tgt = Image.open(sys.argv[1]).convert('RGB').resize((1536, 1024)).crop((0, 512, 1536, 1024))
ours = Image.open(sys.argv[2]).convert('RGBA')
alpha = ours.getchannel('A').point(lambda a: 255 if a > 140 else 0)
edge = alpha.filter(ImageFilter.FIND_EDGES).filter(ImageFilter.MaxFilter(3))
ghost = Image.new('RGB', tgt.size, (255, 255, 255))
ghost.paste(ours.convert('RGB'), mask=alpha)
out = Image.blend(tgt, ghost, 0.45)
red = Image.new('RGB', tgt.size, (230, 0, 0))
out.paste(red, mask=edge)
out.save(sys.argv[3])
print('ok')
