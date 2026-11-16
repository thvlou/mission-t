# blender -b -P probe.py -- <mesh.glb>
# Loads an AI mesh, puts it on game axes (length on X, ground z=0, centred) at the GT length, and prints
# where its wheels touch the ground and which end is the nose, so build_base.py can orient and scale it.
import bpy, sys, math
import numpy as np
from mathutils import Matrix, Vector

glb = sys.argv[sys.argv.index('--') + 1]
L = 4.736
bpy.ops.wm.read_factory_settings(use_empty=True)
bpy.ops.import_scene.gltf(filepath=glb)
meshes = [o for o in bpy.context.scene.objects if o.type == 'MESH']
for o in bpy.context.scene.objects:
    o.select_set(o.type == 'MESH')
bpy.context.view_layer.objects.active = meshes[0]
if len(meshes) > 1:
    bpy.ops.object.join()
car = bpy.context.view_layer.objects.active
bpy.ops.object.transform_apply(location=True, rotation=True, scale=True)
me = car.data


def verts():
    a = np.empty(len(me.vertices) * 3); me.vertices.foreach_get('co', a); return a.reshape(-1, 3)


V = verts()
ext = V.max(0) - V.min(0)
if ext[1] > ext[0]:
    me.transform(Matrix.Rotation(math.pi / 2, 4, 'Z'))
V = verts()
lo, hi = V.min(0), V.max(0)
V = (V - [(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]]) * (L / (hi[0] - lo[0]))
print('EXTENT', np.round(V.max(0) - V.min(0), 3))

# ground contact: vertices within 4 cm of the floor, outboard of the body centre
g = V[(V[:, 2] < 0.04) & (np.abs(V[:, 1]) > 0.4)]
xs = np.sort(g[:, 0])
gaps = np.where(np.diff(xs) > 0.3)[0]
groups = np.split(xs, gaps + 1)
for grp in groups:
    sel = g[(g[:, 0] >= grp[0]) & (g[:, 0] <= grp[-1])]
    print('CONTACT x %.3f..%.3f centre %.3f  |y| %.3f..%.3f  n=%d' % (grp[0], grp[-1], (grp[0] + grp[-1]) / 2,
          np.abs(sel[:, 1]).min(), np.abs(sel[:, 1]).max(), len(sel)))

# wheel radius: highest point of the wheel disc seen from the side in a 1 cm slab at each contact centre,
# measured on the outermost 5 cm of the tyre (where only wheel geometry is)
for grp in groups:
    cx = (grp[0] + grp[-1]) / 2
    for side in (1, -1):
        yo = (V[:, 1] * side).max()
        s = V[(np.abs(V[:, 0] - cx) < 0.01) & (V[:, 1] * side > yo - 0.6)]
        print('SLICE x %.3f side %+d  outer y %.3f' % (cx, side, yo))

# nose: the end whose top surface is lower over its last 0.6 m
for name, m in (('+X', V[:, 0] > L / 2 - 0.6), ('-X', V[:, 0] < -L / 2 + 0.6)):
    print('END', name, 'max z %.3f  mean top %.3f' % (V[m, 2].max(), np.percentile(V[m, 2], 95)))
print('ROOF x at max z %.3f' % V[V[:, 2].argmax(), 0])
