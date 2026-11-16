# blender -b <gt-v4-detail.blend> -P build_bake.py -- <hybrid dir> [size]
# Paints the detail body from the four blueprint class masks (masks.py) into a normal UV atlas for the game.
# Each atlas texel decides ONE class, with no colour blending:
#   Cycles bakes the surface position and normal of every texel (emission bakes into float images); then each view
#   votes with the class its mask shows there: side A2 (x, z), top A5 (x, y), front A3 (y, z), rear A4 (y, z),
#   weighted by the (smoothed) normal raised to the 8th power; faces pointing down vote trim; a view whose mask is background
#   there (the body and the drawing disagree) does not vote.
#   glass wins from 30 % of the vote, lamp and LED from 40 %, otherwise the largest share wins.
# The earlier version blended the four view colours by the normal: where side and top disagree (the side windows
# lean in, so A5 sees paint where A2 sees glass) that gave grey, half-tinted glass and grey smudges on the body.
# One 3x3 average over the result softens the texel steps at class edges.
# Front/rear image scales were measured from A3/A4 (car extents: rows 143..880 / 142..865 = 1.26 m tall,
# columns 75..1460 / 94..1441 = the 1.92 / 1.95 m wide body at tyre height).
# Writes tex/gt4-body-albedo.png, tex/gt4-body-rough.png and updates gt-v4-detail.blend, body-detail.glb.
import bpy, sys, os, math
import numpy as np

args = sys.argv[sys.argv.index('--') + 1:]
hyb = args[0]; SIZE = int(args[1]) if len(args) > 1 else 2048
tex = os.path.join(hyb, 'tex')
scene = bpy.context.scene
body = bpy.data.objects['body_detail']
L = 4.736
K2, K5 = L / 1483, L / 1466
PAINT, GLASS, TRIM, LAMP, LED, PILLAR, SIDEGLASS = 1, 2, 3, 4, 5, 6, 7   # PILLAR: A5, SIDEGLASS: A2 (masks.py)
# sRGB albedo, roughness per class (as build_detail.py LOOK)
# glass areas are a black frame on the body: the panes themselves are separate meshes (build_parts.py build_glass)
LOOK = {PAINT: ((232, 232, 228), 0.28), GLASS: ((12, 13, 15), 0.35), TRIM: ((26, 27, 29), 0.55),
        LAMP: ((176, 16, 24), 0.12), LED: ((236, 244, 255), 0.08), SIDEGLASS: ((12, 13, 15), 0.35)}
VIEWS = {  # mask, texel (x, y, z) -> (col, row), normal -> weight
    'A2': (lambda x, y, z: (764.5 - x / K2, 691 - z / K2), lambda n: np.abs(n[..., 1])),
    'A5': (lambda x, y, z: (765 - x / K5, 493 + y / K5), lambda n: np.maximum(n[..., 2], 0)),
    'A3': (lambda x, y, z: (767.5 - y * 721, 880 - z * 585), lambda n: np.maximum(n[..., 0], 0)),
    'A4': (lambda x, y, z: (767.5 + y * 691, 865 - z * 573), lambda n: np.maximum(-n[..., 0], 0)),
}


def load_mask(name):
    img = bpy.data.images.load(os.path.join(tex, f'mask-{name}.png'))
    w, h = img.size
    a = np.empty(w * h * 4, np.float32); img.pixels.foreach_get(a)
    bpy.data.images.remove(img)
    return np.rint(a.reshape(h, w, 4)[::-1, :, 0] * 255).astype(np.uint8)  # row 0 = top


def emitter(name, socket_of_geometry):
    """Emission material showing a geometry vector mapped to 0..1 (position (p + 4) / 8, normal (n + 1) / 2)."""
    m = bpy.data.materials.new(name); m.use_nodes = True
    nt = m.node_tree; N = nt.nodes
    for n in list(N):
        if n.type != 'OUTPUT_MATERIAL': N.remove(n)
    outn = next(n for n in N if n.type == 'OUTPUT_MATERIAL')
    geo = N.new('ShaderNodeNewGeometry')
    k, b = (1 / 8, 0.5) if socket_of_geometry == 'Position' else (0.5, 0.5)
    ma = N.new('ShaderNodeVectorMath'); ma.operation = 'MULTIPLY_ADD'
    nt.links.new(geo.outputs[socket_of_geometry], ma.inputs[0])
    ma.inputs[1].default_value = (k, k, k); ma.inputs[2].default_value = (b, b, b)
    em = N.new('ShaderNodeEmission'); nt.links.new(ma.outputs[0], em.inputs['Color'])
    nt.links.new(em.outputs[0], outn.inputs['Surface'])
    return m


# bake UVs (re-runs start clean: old atlas images and bake UVs go)
me = body.data
for im in [i for i in bpy.data.images if i.name.startswith(('gt4-body-albedo', 'gt4-body-rough', 'gt4-body-orm', 'bake-'))]:
    bpy.data.images.remove(im)
for uvl in [u for u in me.uv_layers if u.name.startswith('bake')]: me.uv_layers.remove(uvl)
for o in scene.objects: o.select_set(o == body)
bpy.context.view_layer.objects.active = body
bake_uv = me.uv_layers.new(name='bake')
me.uv_layers.active = bake_uv
bpy.ops.object.mode_set(mode='EDIT'); bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.uv.smart_project(angle_limit=math.radians(60), island_margin=0.003)
bpy.ops.object.mode_set(mode='OBJECT')

scene.render.engine = 'CYCLES'
scene.cycles.samples = 1
scene.cycles.device = 'CPU'
geo = {}
for sock in ('Position', 'Normal'):
    target = bpy.data.images.new(f'bake-{sock}', SIZE, SIZE, alpha=False, float_buffer=True)
    target.colorspace_settings.name = 'Non-Color'
    m = emitter(f'emit-{sock}', sock)
    t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = target
    for n in m.node_tree.nodes: n.select = False
    t.select = True; m.node_tree.nodes.active = t
    me.materials.clear(); me.materials.append(m)
    bpy.ops.object.bake(type='EMIT', margin=6, use_clear=True)
    a = np.empty(SIZE * SIZE * 4, np.float32); target.pixels.foreach_get(a)
    geo[sock] = a.reshape(SIZE, SIZE, 4)[..., :3]          # row 0 = bottom, as Blender stores it
    bpy.data.images.remove(target); bpy.data.materials.remove(m)
    print('BAKED', sock, SIZE)

P = geo['Position'] * 8 - 4
Nn = geo['Normal'] * 2 - 1
nl = np.linalg.norm(Nn, axis=-1)
valid = np.abs(nl - 1) < 0.25                               # unbaked texels are (0,0,0) -> |(-1,-1,-1)| = 1.73
Nn = Nn / np.maximum(nl, 1e-6)[..., None]
x, y, z = P[..., 0], P[..., 1], P[..., 2]


def smooth3d(data, cell=0.015, passes=2):
    """Average a per-texel field (vote shares, normals) over the SURFACE in 3D (a sparse voxel grid, [1 2 1] blurs,
    trilinear read back, normalised by the texel count). For the shares (~1.5 cm) this means votes that flip from texel to texel at grazing angles (bumper corners,
    sills) stop leaving black specks, while shapes larger than a few cm keep their edges. Texel neighbours in the
    atlas are not surface neighbours across island seams; 3D is."""
    pv = P[valid]
    lo = pv.min(0) - 3 * cell
    dims = tuple(np.ceil((pv.max(0) - lo) / cell).astype(int) + 4)
    g = (pv - lo) / cell
    i = np.floor(g).astype(int)
    flat = np.ravel_multi_index((i[:, 0], i[:, 1], i[:, 2]), dims)
    n = int(np.prod(dims))
    cnt = np.bincount(flat, minlength=n).astype(np.float32).reshape(dims)
    ch = data.shape[-1]
    acc = np.stack([np.bincount(flat, data[valid][:, c], minlength=n).astype(np.float32).reshape(dims) for c in range(ch)], -1)
    for _ in range(passes):
        for ax in range(3):
            cnt = (np.roll(cnt, 1, ax) + 2 * cnt + np.roll(cnt, -1, ax)) / 4
            acc = (np.roll(acc, 1, ax) + 2 * acc + np.roll(acc, -1, ax)) / 4
    u = g - 0.5
    i0 = np.floor(u).astype(int); f = u - i0
    sa = np.zeros((len(pv), ch), np.float32); sc = np.zeros(len(pv), np.float32)
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                w = (f[:, 0] if dx else 1 - f[:, 0]) * (f[:, 1] if dy else 1 - f[:, 1]) * (f[:, 2] if dz else 1 - f[:, 2])
                a, b, c = i0[:, 0] + dx, i0[:, 1] + dy, i0[:, 2] + dz
                sa += w[:, None] * acc[a, b, c]; sc += w * cnt[a, b, c]
    out = data.copy()
    out[valid] = sa / np.maximum(sc, 1e-9)[:, None]
    return out


# The views are weighted by a normal smoothed over ~3.5 cm, raised to the 8th power: with the raw normal (and the 4th
# power) the line where one view hands over to the next followed every small dent of the surface, and where two views
# disagree (the bumper-corner intake is drawn in both A2 and A3, and does not line up on this rounder corner) the
# surface got black flames. Now each surface follows the one view it faces, with a smooth boundary.
Nw = smooth3d(Nn, cell=0.02, passes=6)
nw = np.linalg.norm(Nw, axis=-1)
Nw = np.where((nw > 0.3)[..., None], Nw / np.maximum(nw, 1e-6)[..., None], Nn)   # thin parts: both faces cancel
votes = np.zeros((SIZE, SIZE, 8), np.float32)
view_w = {}
for view, (to_px, weight) in VIEWS.items():
    mask = load_mask(view)
    c, r = to_px(x, y, z)
    wv = weight(Nw) ** 8
    # Ahead of the front arches and behind the rear ones the nose and tail corners are round, so a wide band faces
    # half forward, half sideways. A2 maps those points by (x, z) and stretched its corner intake into black flames
    # across them; there the front/rear drawing wins up to ~57 deg off its axis (30 ** (1/8) = 1.53).
    if view == 'A3': wv = wv * np.where(x > 1.9, 30.0, 1.0)
    if view == 'A4': wv = wv * np.where(x < -1.9, 30.0, 1.0)
    # the top view cannot see into the grille or the diffuser: the up-facing ledges of those recesses took its paint
    # and showed as white strokes inside the black openings
    if view == 'A5': wv = wv * np.where((np.abs(x) > 1.85) & (z < 0.45), 0.0, 1.0)
    view_w[view] = wv
    # bilinear: the four mask pixels round the texel each vote with their share of it, so class edges fall between
    # pixels instead of stepping along them (the saw-tooth on the screen frame)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    for dr, dc in ((0, 0), (0, 1), (1, 0), (1, 1)):
        ri, ci = r0 + dr, c0 + dc
        inside = (ri >= 0) & (ri < mask.shape[0]) & (ci >= 0) & (ci < mask.shape[1])
        cls = np.zeros((SIZE, SIZE), np.uint8)
        cls[inside] = mask[ri[inside], ci[inside]]
        cls[cls == PILLAR] = PAINT   # the top view's A-pillar strip votes as plain paint (see the pillar rule below)
        w = wv * (fr if dr else 1 - fr) * (fc if dc else 1 - fc) * (cls > 0)
        np.add.at(votes.reshape(-1, 8), (np.arange(SIZE * SIZE), cls.ravel()), w.ravel())
votes[..., TRIM] += np.maximum(-Nw[..., 2], 0) ** 8         # underbody: only faces that really point down
votes[..., 0] = 0
total = votes.sum(-1)
share = votes / np.maximum(total, 1e-9)[..., None]
share[total <= 1e-6, PAINT] = 1
# Pillars and frames. The panes are separate meshes (build_parts.py build_glass: the A5 windscreen and the A2 side
# pane, each cast 1 cm inside its outline). Under a pane the body stays dark, so that centimetre reads as the frame;
# every other glass-class texel of the cabin, ahead of the B-pillar line (x > -0.45), is body colour: the A-pillars,
# the strip between pane and roof, the door below. Their edges follow the panes' outlines, not texel votes.
def flood(m, seed):
    out = np.zeros_like(m); stack = [seed]
    while stack:
        i, j = stack.pop()
        if not (0 <= i < m.shape[0] and 0 <= j < m.shape[1]) or out[i, j] or not m[i, j]: continue
        out[i, j] = True
        stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    return out


def bilinear(img, view):
    """img (float, row 0 = top) read at every texel's position in the view, between pixels."""
    c, r = VIEWS[view][0](x, y, z)
    c0, r0 = np.floor(c).astype(int), np.floor(r).astype(int)
    fc, fr = c - c0, r - r0
    out = np.zeros(valid.shape, np.float32)
    for dr, dc in ((0, 0), (0, 1), (1, 0), (1, 1)):
        ri, ci = r0 + dr, c0 + dc
        ok = (ri >= 0) & (ri < img.shape[0]) & (ci >= 0) & (ci < img.shape[1])
        out[ok] += img[ri[ok], ci[ok]] * ((fr if dr else 1 - fr) * (fc if dc else 1 - fc))[ok]
    return out


def under(mask, view, extra):
    return (bilinear(mask.astype(np.float32), view) > 0.5) & extra


m5, m2 = load_mask('A5'), load_mask('A2')
shield = flood(m5 == GLASS, (493, 560))
covered = under(shield, 'A5', Nw[..., 2] > 0.40) | under(m2 == SIDEGLASS, 'A2', np.abs(Nw[..., 1]) > 0.3)   # screen kept from n.z 0.45
pillar = valid & (share[..., GLASS] + share[..., SIDEGLASS] > 0.3) & ~covered & (x > -0.45) & (z > 0.7)
share[pillar] = 0; share[pillar, PAINT] = 1


share = smooth3d(share)
cls = share.argmax(-1)
cls = np.where(share[..., LED] >= 0.4, LED, cls)
cls = np.where(share[..., LAMP] >= 0.4, LAMP, cls)
# glass wins from 30 % of the vote; the side pane (lighter, the cabin shows through) and the dark glass/frames split it
glassy = share[..., GLASS] + share[..., SIDEGLASS]
cls = np.where(glassy >= 0.3, np.where(share[..., SIDEGLASS] > share[..., GLASS], SIDEGLASS, GLASS), cls)
print('TEXELS', {k: int(((cls == v) & valid).sum()) for k, v in (('paint', PAINT), ('glass', GLASS), ('sideglass', SIDEGLASS), ('trim', TRIM), ('lamp', LAMP), ('led', LED))})

albedo = np.zeros((SIZE, SIZE, 3), np.float32); rough = np.zeros((SIZE, SIZE), np.float32)
for c, (rgb, rg) in LOOK.items():
    albedo[cls == c] = np.array(rgb) / 255.0; rough[cls == c] = rg


def box3(a, wgt):
    """3x3 average of a over the valid texels only (invalid ones neither give nor take)."""
    pad = lambda q: np.pad(q, [(1, 1), (1, 1)] + [(0, 0)] * (q.ndim - 2), mode='edge')
    aw, ww = pad(a * (wgt[..., None] if a.ndim == 3 else wgt)), pad(wgt)
    s = sum(aw[i:i + SIZE, j:j + SIZE] for i in range(3) for j in range(3))
    n = sum(ww[i:i + SIZE, j:j + SIZE] for i in range(3) for j in range(3))
    return s / np.maximum(n, 1e-6)[..., None] if a.ndim == 3 else s / np.maximum(n, 1e-6)


vf = valid.astype(np.float32)
albedo = np.where(valid[..., None], box3(albedo, vf), np.array(LOOK[PAINT][0]) / 255.0)
rough = np.where(valid, box3(rough, vf), LOOK[PAINT][1])

# Panel lines (masks.py line-*.png: shut lines and seams traced off the drawings), each view weighted as in the vote,
# darken the paint along them: door, bonnet, wings, engine cover and bumper seams read as cut panels, not one skin.
wsum = sum(view_w.values()) + 1e-9
lines = np.zeros(valid.shape, np.float32)
for view in VIEWS:
    img = bpy.data.images.load(os.path.join(tex, f'line-{view}.png'))
    w_, h_ = img.size
    a = np.empty(w_ * h_ * 4, np.float32); img.pixels.foreach_get(a); bpy.data.images.remove(img)
    li = a.reshape(h_, w_, 4)[::-1, :, 0]                                   # row 0 = top, 0..1
    lines += bilinear(li, view) * view_w[view] / wsum
lines = np.clip(lines * 1.6, 0, 1) * (cls == PAINT)
albedo = albedo * (1 - 0.72 * lines)[..., None]
rough = rough + 0.25 * lines
print('LINE texels', int((lines > 0.3).sum()))


# Mesh in the openings: the drawings show a honeycomb behind the grille, the bumper-corner intakes, the side intakes and
# the diffuser. Trim texels there get a 22 mm hex grid (plane of the view): light rims round black cells.
def hex_rim(u, v, size=0.022):
    cx = (np.sqrt(3) / 3 * u - v / 3) / size; cz = (2 / 3 * v) / size; cy = -cx - cz
    rx, ry, rz = np.rint(cx), np.rint(cy), np.rint(cz)
    dx, dy, dz = np.abs(rx - cx), np.abs(ry - cy), np.abs(rz - cz)
    fx = (dx > dy) & (dx > dz); fz = ~fx & (dz > dy)
    rx = np.where(fx, -ry - rz, rx); rz = np.where(fz, -rx - ry, rz)
    cu = size * np.sqrt(3) * (rx + rz / 2); cv = size * 1.5 * rz          # cell centre
    lu, lv = np.abs(u - cu), np.abs(v - cv)
    m = np.maximum(lv * np.sqrt(3) / 2 + lu / 2, lu)                       # pointy-top hex metric
    return np.clip((m - size * np.sqrt(3) / 2 * 0.78) / (size * 0.12), 0, 1)   # 1 on the rim, 0 in the cell


zones = [((x > 1.85) & (z < 0.55) & (Nw[..., 0] > 0.5), y, z), ((x < -1.85) & (z < 0.5) & (Nw[..., 0] < -0.5), y, z),
         ((x > -1.0) & (x < -0.4) & (z > 0.3) & (z < 0.78) & (np.abs(Nw[..., 1]) > 0.6), x, z)]   # facing the view
mesh = np.zeros(valid.shape, np.float32); in_zone = np.zeros(valid.shape, bool)
for zone, u, v in zones:
    mesh = np.where(zone, hex_rim(u, v), mesh); in_zone |= zone
mesh *= (cls == TRIM) & valid
# the mesh is matte plastic: the creased floors of the 3 cm recesses had caught the light as white strokes
rough = np.where(in_zone & (cls == TRIM), 0.85, rough)
albedo = albedo + (mesh[..., None] * (np.array([58, 60, 64]) / 255.0 - albedo)) * 0.85
print('MESH texels', int((mesh > 0.5).sum()))

# Ambient occlusion within 15 cm (wheels, liners and the body itself occlude), multiplied into the albedo: a flat white
# atlas read as clay in the game; the darkening in the arches, round the intakes, under the mirrors and along the sill
# gives the shape back. 60 % floor so open panels stay white.
AO_DIST, AO_FLOOR = 0.15, 0.6
if scene.world is None: scene.world = bpy.data.worlds.new('bake')
scene.world.light_settings.distance = AO_DIST
scene.cycles.samples = 48
target = bpy.data.images.new('bake-ao', SIZE, SIZE, alpha=False, float_buffer=True)
target.colorspace_settings.name = 'Non-Color'
m = bpy.data.materials.new('bake-ao'); m.use_nodes = True
t = m.node_tree.nodes.new('ShaderNodeTexImage'); t.image = target
for n in m.node_tree.nodes: n.select = False
t.select = True; m.node_tree.nodes.active = t
me.materials.clear(); me.materials.append(m)
for o in scene.objects: o.select_set(o == body)
bpy.ops.object.bake(type='AO', margin=6, use_clear=True)
a = np.empty(SIZE * SIZE * 4, np.float32); target.pixels.foreach_get(a)
ao = np.clip(a.reshape(SIZE, SIZE, 4)[..., 0], 0, 1)
bpy.data.images.remove(target); bpy.data.materials.remove(m)
ao = np.where(valid, box3(ao, vf), 1.0)
albedo = albedo * ((AO_FLOOR + (1 - AO_FLOOR) * ao) ** (1 / 2.2))[..., None]   # linear factor, albedo is stored as sRGB
print('AO mean', round(float(ao[valid].mean()), 3), '5% low', round(float(np.percentile(ao[valid], 5)), 3))

results = {}
for name, arr, colorspace in (('gt4-body-albedo', albedo, 'sRGB'), ('gt4-body-rough', np.repeat(rough[..., None], 3, -1), 'Non-Color')):
    img = bpy.data.images.new(name, SIZE, SIZE, alpha=False)
    img.colorspace_settings.name = colorspace
    rgba = np.concatenate([arr, np.ones((SIZE, SIZE, 1), np.float32)], -1)  # albedo stored as sRGB bytes, tagged sRGB
    img.pixels.foreach_set(rgba.astype(np.float32).ravel())
    img.filepath_raw = os.path.join(tex, name + '.png'); img.file_format = 'PNG'; img.save()
    img.source = 'FILE'; img.reload()
    results[name] = img

# final material: baked albedo + roughness on the bake UVs, nothing else
for uvl in list(me.uv_layers):
    if uvl.name != 'bake': me.uv_layers.remove(uvl)
me.uv_layers['bake'].active_render = True
mat = bpy.data.materials.get('GT4 Paint') or bpy.data.materials.new('GT4 Paint')
mat.name = 'GT4 Paint'; mat.use_nodes = True
nt = mat.node_tree
for n in list(nt.nodes):
    if n.type not in ('OUTPUT_MATERIAL', 'BSDF_PRINCIPLED'): nt.nodes.remove(n)
bsdf = next(n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED')
ta = nt.nodes.new('ShaderNodeTexImage'); ta.image = results['gt4-body-albedo']
tr = nt.nodes.new('ShaderNodeTexImage'); tr.image = results['gt4-body-rough']
nt.links.new(ta.outputs['Color'], bsdf.inputs['Base Color'])
nt.links.new(tr.outputs['Color'], bsdf.inputs['Roughness'])
bsdf.inputs['Metallic'].default_value = 0.0
bsdf.inputs['Coat Weight'].default_value = 0.6
# Trim, grille, window frames: same atlas, own material without clear coat, so the game does not tune them as paint
# (clear coat and flakes made the black areas glossy plastic).
trim = bpy.data.materials.get('GT4 Trim Body') or bpy.data.materials.new('GT4 Trim Body')
trim.use_nodes = True
tn = trim.node_tree
for n in list(tn.nodes):
    if n.type not in ('OUTPUT_MATERIAL', 'BSDF_PRINCIPLED'): tn.nodes.remove(n)
tb = next(n for n in tn.nodes if n.type == 'BSDF_PRINCIPLED')
t1 = tn.nodes.new('ShaderNodeTexImage'); t1.image = results['gt4-body-albedo']
t2 = tn.nodes.new('ShaderNodeTexImage'); t2.image = results['gt4-body-rough']
tn.links.new(t1.outputs['Color'], tb.inputs['Base Color']); tn.links.new(t2.outputs['Color'], tb.inputs['Roughness'])
tb.inputs['Metallic'].default_value = 0.0; tb.inputs['Coat Weight'].default_value = 0.0
me.materials.clear(); me.materials.append(mat); me.materials.append(trim)
uvd = me.uv_layers['bake'].data
dark = np.isin(cls, (TRIM, GLASS, SIDEGLASS))
n_trim = 0
# a face is trim when its centre or any corner is on a dark class: by the centre alone, faces along the grille and
# intake edges stayed paint, and their clear coat drew white streaks over the black texture
pix = lambda uv: (min(SIZE - 1, max(0, int(uv.y * SIZE))), min(SIZE - 1, max(0, int(uv.x * SIZE))))
for p in me.polygons:
    u = sum(uvd[i].uv.x for i in p.loop_indices) / p.loop_total; v = sum(uvd[i].uv.y for i in p.loop_indices) / p.loop_total
    hit = dark[min(SIZE - 1, max(0, int(v * SIZE))), min(SIZE - 1, max(0, int(u * SIZE)))]
    hit = hit or any(dark[pix(uvd[i].uv)] for i in p.loop_indices)
    p.material_index = 1 if hit else 0; n_trim += p.material_index
print('TRIM faces', n_trim, 'of', len(me.polygons))
scene.render.engine = 'BLENDER_EEVEE'
bpy.ops.wm.save_as_mainfile(filepath=os.path.join(hyb, 'gt-v4-detail.blend'))
for o in scene.objects: o.select_set(o == body)
bpy.ops.export_scene.gltf(filepath=os.path.join(hyb, 'body-detail.glb'), use_selection=True, export_apply=True)
print('DONE')
