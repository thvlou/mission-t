# blender -b <body blend> -P silcheck.py -- <object> <out prefix>
# Silhouette of a body object in the side (A2) and front (A3) drawings' pixel grids, by rays (every 2 px), saved as
# <prefix>-A2.npy / -A3.npy, plus the share of drawing-car pixels it misses and of its pixels outside the drawing.
import bpy, sys, os, numpy as np
from mathutils import Vector
from mathutils.bvhtree import BVHTree
name, prefix = sys.argv[sys.argv.index('--') + 1:][:2]
o = bpy.data.objects[name]
bvh = BVHTree.FromObject(o, bpy.context.evaluated_depsgraph_get())
L = 4.736; K2 = L / 1483
hyb = os.path.dirname(bpy.data.filepath)
def img(n):
    im = bpy.data.images.load(os.path.join(hyb, 'tex', n)); w, h = im.size
    a = np.empty(w * h * 4, np.float32); im.pixels.foreach_get(a); return a.reshape(h, w, 4)[::-1, :, 0] > 0.5
for view, ray, ranges in (('A2', lambda c, r: ((764.5 - c) * K2, 3.0, (691 - r) * K2, (0, -1, 0)), (200, 760, 0, 1536)),
                          ('A3', lambda c, r: (4.0, (767.5 - c) / 721, (880 - r) / 585, (-1, 0, 0)), (100, 900, 0, 1536))):
    sil = np.zeros((1024, 1536), bool)
    r0, r1, c0, c1 = ranges
    for r in range(r0, r1, 2):
        for c in range(c0, c1, 2):
            x, y, z, d = ray(c, r)
            if abs(x) > 4.5 or abs(y) > 3.5: continue
            if bvh.ray_cast(Vector((x, y, z)), Vector(d))[0] is not None: sil[r:r + 2, c:c + 2] = True
    np.save(f'{prefix}-{view}.npy', sil)
    ref = img(f'sil-{view}.png')[:1024, :1536]
    sub = (slice(r0, r1), slice(c0, c1))
    miss = (ref[sub] & ~sil[sub]).sum() / max(ref[sub].sum(), 1); extra = (sil[sub] & ~ref[sub]).sum() / max(ref[sub].sum(), 1)
    print('SIL', view, 'missed', round(float(miss) * 100, 1), '% extra', round(float(extra) * 100, 1), '%')
