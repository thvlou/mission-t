# blender -b <gt-v4-wheels.blend> -P check_motion.py
# Sweeps the tyres through the game's motion limits and reports how far they enter the body or the liner.
# The game keeps the wheels on the road and moves the body over them (src/rover.js pose3d, src/highway/car.js):
#   steer   front wheels about the vertical through the hub, |angle| <= 0.5 rad (car.js wheelAngle)
#   lean    body roll about the long axis, |lean| <= 0.065 rad
#   squat   body pitch, -0.035 .. +0.03 rad
# Both body rotations pivot on the car origin, 0.6 m above the road (car-model.js groundOffset).
# Equivalent here: keep the body still and move the tyre points by the inverse body rotation.
import bpy, math, itertools
from mathutils import Vector, Matrix
from mathutils.bvhtree import BVHTree

dg = bpy.context.evaluated_depsgraph_get()
PIVOT = Vector((0, 0, 0.6))
R_TYRE = 0.40


def bvh_of(names):
    objs = [bpy.data.objects[n] for n in names]
    verts, polys = [], []
    for o in objs:
        me = o.evaluated_get(dg).to_mesh()
        off = len(verts)
        verts += [o.matrix_world @ v.co for v in me.vertices]
        polys += [[off + i for i in p.vertices] for p in me.polygons]
        o.evaluated_get(dg).to_mesh_clear()
    return BVHTree.FromPolygons(verts, polys)


body = bvh_of(['body_retopo'])


def tyre_points(w):
    """Tyre surface samples in the wheel's local frame (rubber only: radius > lip)."""
    me = w.data
    tyre = {i for p in me.polygons if me.materials[p.material_index].name.startswith(('GT4 Tire', 'GT4 TireWall'))
            for i in p.vertices}
    return [me.vertices[i].co.copy() for i in tyre]


def inside(bvh, p):
    hit = bvh.find_nearest(p)
    if hit[0] is None: return 0.0
    d = p - hit[0]
    return hit[3] if d.dot(hit[1]) < 0 else 0.0


LINER_R = {'F': 0.425, 'R': 0.413}   # build_wheels LINER


def liner_hit(w, p):
    """How far a point (body frame) is outside the liner: past the tube radius inside its span, or behind
    the back plate. The liner is an open shell, so it is tested against its own shape, not by normals."""
    hub = w.matrix_world.translation
    side = 1 if hub.y > 0 else -1
    lo = bpy.data.objects[w.name.replace('wheel_', 'wheelwell_')]
    ys = [side * (lo.matrix_world @ v.co).y for v in lo.data.vertices]
    inner, outer = min(ys), max(ys)
    d = p - hub
    y = side * p.y
    if y < inner: return inner - y                      # through the back plate
    r = math.hypot(d.x, d.z)
    ang = math.degrees(math.atan2(d.z, d.x))
    rw = LINER_R[w.name[6]]
    if -15 <= ang <= 195 and y <= outer and r > rw: return r - rw
    return 0.0


cases = {'rest': [(0, 0, 0)], 'steer only': [(s, 0, 0) for s in (-0.5, 0.5)],
         'lean only': [(0, l, 0) for l in (-0.065, 0.065)], 'squat only': [(0, 0, q) for q in (-0.035, 0.03)],
         'all limits': list(itertools.product((-0.5, 0, 0.5), (-0.065, 0.065), (-0.035, 0.03)))}
for name in ('wheel_FL', 'wheel_RL'):
    w = bpy.data.objects[name]
    pts = tyre_points(w)
    front = name[6] == 'F'
    hub = w.matrix_world.translation
    for label, combos in cases.items():
        wb = wl = 0.0
        for steer, lean, squat in combos:
            if not front: steer = 0
            S = Matrix.Rotation(steer, 4, 'Z')
            B = Matrix.Translation(PIVOT) @ (Matrix.Rotation(squat, 4, 'Y') @ Matrix.Rotation(lean, 4, 'X')).inverted() @ Matrix.Translation(-PIVOT)
            for co in pts[::2]:
                local = hub + (S @ co.to_4d()).to_3d()
                p = B @ local
                wb = max(wb, inside(body, p))
                wl = max(wl, liner_hit(w, p))           # the liner is part of the body, so it moves with it
        print('MOTION', name, f'{label:11s}', 'into body', round(wb * 1000, 1), 'mm', ' through liner', round(wl * 1000, 1), 'mm')

# With the game's suspension (settleHubs in src/car-model.js): the hub stays on the road until the body over
# its tyre top has come down by TRAVEL, then moves down with the body. Residual = what still overlaps.
TRAVEL = 0.02
for name in ('wheel_FL', 'wheel_RL'):
    w = bpy.data.objects[name]
    pts = tyre_points(w)
    front = name[6] == 'F'
    hub = w.matrix_world.translation
    wb, sink = 0.0, 0.0
    for steer, lean, squat in cases['all limits'] + cases['lean only'] + cases['squat only']:
        if not front: steer = 0
        S = Matrix.Rotation(steer, 4, 'Z')
        fwd = Matrix.Translation(PIVOT) @ Matrix.Rotation(squat, 4, 'Y') @ Matrix.Rotation(lean, 4, 'X') @ Matrix.Translation(-PIVOT)
        top = hub + Vector((0, 0, R_TYRE))
        drop = top.z - (fwd @ top).z
        shift = max(0.0, drop - TRAVEL)
        sink = max(sink, shift)
        for co in pts[::2]:
            road = hub + (S @ co.to_4d()).to_3d() - Vector((0, 0, shift))
            wb = max(wb, inside(body, fwd.inverted() @ road))
    print('SUSPENSION', name, 'travel', TRAVEL, 'into body', round(wb * 1000, 1), 'mm,', 'tyre pushed below the road up to', round(sink * 1000, 1), 'mm')
