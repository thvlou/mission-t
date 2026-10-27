"""Put one view of the target sheet next to our render of the same view, both scaled to the same
car height, for close comparison.

  python tools/pair-view.py <target-sheet.png> <view: front|rear|side> <our-render.png> <out.png>
"""
import sys

from PIL import Image

# where each view sits on each target sheet (the six sheets do not share one layout)
LAYOUTS = {
    '01': {'front': (0, 80, 790, 450), 'rear': (780, 80, 1536, 450), 'side': (0, 500, 1536, 920)},
    '02': {'front': (20, 130, 850, 500), 'rear': (820, 130, 1530, 500), 'side': (60, 540, 1480, 940)},
    '03': {'front': (10, 90, 790, 480), 'rear': (800, 130, 1536, 460), 'side': (40, 540, 1500, 900)},
    '04': {'front': (20, 90, 790, 450), 'rear': (780, 100, 1530, 440), 'side': (40, 500, 1500, 920)},
    '05': {'front': (0, 70, 790, 420), 'rear': (790, 70, 1530, 420), 'side': (60, 470, 1400, 920)},
    '06': {'front': (10, 90, 780, 470), 'rear': (780, 90, 1536, 470), 'side': (40, 510, 1500, 900)},
}
import os
key = os.path.basename(sys.argv[1])[:2]
tgt = Image.open(sys.argv[1]).convert('RGB').resize((1536, 1024)).crop(LAYOUTS.get(key, LAYOUTS['01'])[sys.argv[2]])
ours = Image.open(sys.argv[3]).convert('RGBA')
solid = ours.getchannel('A').point(lambda a: 255 if a > 140 else 0)
bbox = solid.getbbox()
bg = Image.new('RGBA', ours.size, (236, 234, 230, 255))
bg.alpha_composite(ours)
pad = 20
ours = bg.convert('RGB').crop((bbox[0] - pad, bbox[1] - pad, bbox[2] + pad, bbox[3] + pad))
H = 520
tgt = tgt.resize((int(tgt.width * H / tgt.height), H), Image.LANCZOS)
ours = ours.resize((int(ours.width * H / ours.height), H), Image.LANCZOS)
out = Image.new('RGB', (tgt.width + ours.width + 10, H), (255, 255, 255))
out.paste(tgt, (0, 0))
out.paste(ours, (tgt.width + 10, 0))
out.save(sys.argv[4])
print('ok')
