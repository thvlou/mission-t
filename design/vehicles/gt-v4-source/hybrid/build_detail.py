# blender -b <gt-v4-wheels.blend> -P build_detail.py -- <hybrid dir> <body blend> <body object>
# Detail pass 1 on the smooth GT v4 body: the blueprint masks (masks.py) are projected onto it.
#   class per vertex/face: side-facing surfaces read blueprint A2 at (x, z), upward ones A5 at (x, y),
#   downward ones are underbody (trim). Front/rear faces take whichever of side/top they lean to.
#   recesses: the surface is pushed in along its normal where the masks say glass (6 mm), the side intakes
#   (35 mm), deck louvre panel (14 mm), hood vents (16 mm) and headlamp pods (8 mm), so they read as real
#   openings and frames, not paint; one smoothing pass of the depth field softens the edges.
#   colour: one material "GT4 Paint" with an albedo + roughness/metal atlas (A2 left half, A5 right half), so
#   window and trim edges are as sharp as the blueprint (3 mm/px), not stepped by the mesh.
# The old body_retopo is replaced in the scene by the new one (named body_detail). Wheels/liners are kept.
# Writes tex/gt4-body-albedo.png, tex/gt4-body-orm.png, gt-v4-detail.blend, body-detail.glb.
import bpy, bmesh, sys, os, math
import numpy as np
from mathutils import Vector

hyb, body_blend, body_name = sys.argv[sys.argv.index('--') + 1:][:3]
tex = os.path.join(hyb, 'tex')
scene = bpy.context.scene
L = 4.736
K2, K5 = L / 1483, L / 1466                      # metres per pixel, A2 and A5
PAINT, GLASS, TRIM, LAMP, LED = 1, 2, 3, 4, 5
# flat looks per class: sRGB albedo, roughness, metallic
LOOK = {0: ((28, 29, 31), 0.6, 0.0), PAINT: ((232, 232, 228), 0.28, 0.0), GLASS: ((16, 21, 27), 0.04, 0.0),
        TRIM: ((26, 27, 29), 0.55, 0.0), LAMP: ((176, 16, 24), 0.12, 0.0), LED: ((236, 244, 255), 0.08, 0.0)}


def load_mask(name):
    img = bpy.data.images.load(os.path.join(tex, f'mask-{name}.png'))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return np.rint(a.reshape(h, w, 4)[::-1, :, 0] * 255).astype(np.uint8)  # row 0 = top


A2, A5, A3, A4 = load_mask('A2'), load_mask('A5'), load_mask('A3'), load_mask('A4')
H, W = A2.shape


def a2_px(x, z): return 764.5 - x / K2, 691 - z / K2
def a5_px(x, y): return 765 - x / K5, 493 + y / K5
def a3_px(y, z): return 767.5 - y * 721, 880 - z * 585      # front view, scales from build_bake.py
def a4_px(y, z): return 767.5 + y * 691, 865 - z * 573      # rear view


def sample(mask, px, row):
    c, r = int(round(px)), int(round(row))
    if 0 <= r < mask.shape[0] and 0 <= c < mask.shape[1]: return int(mask[r, c])
    return 0


def view_of(n):
    if n.z < -0.35: return 'under'
    if abs(n.x) > max(abs(n.y), abs(n.z)): return 'front' if n.x > 0 else 'rear'
    return 'side' if abs(n.y) >= abs(n.z) else 'top'


def classify(co, n):
    v = view_of(n)
    if v == 'under': return TRIM, v
    if v == 'front':
        c = sample(A3, *a3_px(co.y, co.z))
    elif v == 'rear':
        c = sample(A4, *a4_px(co.y, co.z))
    elif v == 'side':
        c = sample(A2, *a2_px(co.x, co.z))
    else:
        c = sample(A5, *a5_px(co.x, co.y))
    return (c if c else PAINT), v


# --- the body: bring in the smooth one, retire the old placeholder
with bpy.data.libraries.load(body_blend) as (src, dst):
    dst.objects = [body_name]
body = dst.objects[0]
scene.collection.objects.link(body)
body.name = body.data.name = 'body_detail'
body.hide_render = False; body.hide_viewport = False   # it is a copy of the hidden AI reference
old = bpy.data.objects.get('body_retopo')
if old: bpy.data.objects.remove(old, do_unlink=True)
for o in scene.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
for m in list(body.modifiers): bpy.ops.object.modifier_apply(modifier=m.name)

me = body.data
me.calc_normals() if hasattr(me, 'calc_normals') else None
nv = len(me.vertices)
cls = np.zeros(nv, np.uint8)
depth = np.zeros(nv)
for v in me.vertices:
    c, view = classify(v.co, v.normal)
    cls[v.index] = c
    x, y, z = v.co
    d = 0.0
    if c == GLASS: d = 0.006
    if view == 'side' and c == TRIM and -0.95 < x < -0.45 and 0.33 < z < 0.72: d = 0.035      # side intake (C5)
    if view == 'top' and c == GLASS and -1.75 < x < -0.9 and abs(y) < 0.45: d = 0.014        # louvre panel
    if view == 'top' and c == GLASS and 1.25 < x < 1.65 and 0.35 < abs(y) < 0.62: d = 0.016  # hood vents
    if view == 'side' and c in (GLASS, TRIM, LED) and x > 1.85 and 0.45 < z < 0.65: d = 0.008  # headlamp pods
    if view == 'front' and c == TRIM and z < 0.5: d = 0.015       # grille and front intakes (A3)
    if view == 'rear' and c == TRIM and z < 0.55: d = 0.015        # diffuser and rear mesh (A4)
    depth[v.index] = d
# three averaging passes over the mesh soften each recess edge over ~3 faces. With one pass and 3 cm, the grille and
# diffuser floors crumpled into up-facing ledges that the game's overhead light turned into white streaks (now 15 mm).
E = np.array([e.vertices[:] for e in me.edges])
cnt = np.zeros(nv); np.add.at(cnt, E[:, 0], 1); np.add.at(cnt, E[:, 1], 1)
for _ in range(3):
    acc = np.zeros(nv)
    np.add.at(acc, E[:, 0], depth[E[:, 1]]); np.add.at(acc, E[:, 1], depth[E[:, 0]])
    depth = 0.5 * depth + 0.5 * acc / np.maximum(cnt, 1)
co = np.array([v.co[:] for v in me.vertices]); nrm = np.array([v.normal[:] for v in me.vertices])
co -= nrm * depth[:, None]
me.vertices.foreach_set('co', co.ravel()); me.update()
print('CLASSES', {k: int((cls == v).sum()) for k, v in (('paint', PAINT), ('glass', GLASS), ('trim', TRIM), ('lamp', LAMP), ('led', LED))},
      'recessed', int((depth > 0.001).sum()))

# --- atlas: A2 classes on the left half, A5 on the right, one flat colour per class
AW = 2 * W
albedo = np.zeros((H, AW, 4), np.float32); orm = np.zeros((H, AW, 4), np.float32)
albedo[..., 3] = orm[..., 3] = 1


def srgb_to_linear(c):
    c = c / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


for half, mask in ((0, A2), (1, A5)):
    sl = slice(half * W, half * W + W)
    for c, (rgb, rough, metal) in LOOK.items():
        sel = mask == c
        albedo[:, sl][sel, :3] = np.array(rgb) / 255.0        # stored as sRGB bytes; the image is tagged sRGB
        orm[:, sl][sel, 0] = 1.0; orm[:, sl][sel, 1] = rough; orm[:, sl][sel, 2] = metal
# underbody swatch: the top-left corner pixel block of A2 is background -> trim colour (class 0 look)


def save(name, arr, colorspace):
    img = bpy.data.images.new(name, AW, H, alpha=False)
    img.colorspace_settings.name = colorspace
    img.pixels.foreach_set(arr[::-1].ravel())
    img.filepath_raw = os.path.join(tex, name + '.png'); img.file_format = 'PNG'; img.save()
    return img


img_albedo = save('gt4-body-albedo', albedo, 'sRGB')
img_orm = save('gt4-body-orm', orm, 'Non-Color')

# --- UVs: each face projected from the view its normal faces
for old_uv in list(me.uv_layers): me.uv_layers.remove(old_uv)   # leftovers from the AI mesh would win at render
uv = me.uv_layers.new(name='blueprint')
me.uv_layers.active = uv; uv.active_render = True
for p in me.polygons:
    view = view_of(p.normal)
    for li in p.loop_indices:
        c = me.vertices[me.loops[li].vertex_index].co
        if view == 'top':
            px, row = a5_px(c.x, c.y); px += W
        elif view == 'side':
            px, row = a2_px(c.x, c.z)
        else:
            px, row = 4, 4                       # underbody/front/rear: replaced by the bake (build_bake.py)
        uv.data[li].uv = (px / AW, 1 - row / H)

if 'GT4 Paint' in bpy.data.materials: bpy.data.materials['GT4 Paint'].name = 'GT4 Paint (old body)'
mat = bpy.data.materials.new('GT4 Paint'); mat.use_nodes = True
nt = mat.node_tree
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = img_albedo; ta.interpolation = 'Linear'
to = nt.nodes.new('ShaderNodeTexImage'); to.image = img_orm; to.interpolation = 'Linear'
sep = nt.nodes.new('ShaderNodeSeparateColor')
nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
nt.links.new(to.outputs['Color'], sep.inputs['Color'])
nt.links.new(sep.outputs['Green'], bsdf.inputs['Roughness'])
nt.links.new(sep.outputs['Blue'], bsdf.inputs['Metallic'])
bsdf.inputs['Coat Weight'].default_value = 0.6
me.materials.clear(); me.materials.append(mat)
for p in me.polygons: p.use_smooth = True
bpy.ops.object.shade_smooth_by_angle(angle=math.radians(50))

bpy.ops.wm.save_as_mainfile(filepath=os.path.join(hyb, 'gt-v4-detail.blend'))
for o in scene.objects: o.select_set(o == body)
bpy.ops.export_scene.gltf(filepath=os.path.join(hyb, 'body-detail.glb'), use_selection=True, export_apply=True)
print('DONE')
