# python masks.py <gt-v4-source dir>
# Splits blueprints A2 (side) and A5 (top) into flat classes for the GT v4 body texture:
#   paint (pearl white), glass (dark tint), trim (satin black), lamp (tail red), led (headlamp white)
# Wheels are cut out of A2 (they are separate meshes). Writes hybrid/tex/mask-A2.png, mask-A5.png (class ids)
# and preview-A2.png / preview-A5.png (flat colours) for checking.
import sys, os, numpy as np
from PIL import Image, ImageFilter
d = sys.argv[1]
CLASS = {'bg': 0, 'paint': 1, 'glass': 2, 'trim': 3, 'lamp': 4, 'led': 5, 'pillar': 6, 'sideglass': 7}
COL = {0: (255, 255, 255), 1: (232, 232, 228), 2: (18, 24, 30), 3: (28, 29, 31), 4: (190, 20, 28), 5: (235, 245, 255), 6: (210, 120, 120), 7: (58, 64, 72)}


def classify(path, wheels=None, belt_row=None, greenhouse=None):
    a = np.asarray(Image.open(path).convert('RGB')).astype(int)
    r, g, b = a[..., 0], a[..., 1], a[..., 2]
    lum, sat = a.mean(2), a.max(2) - a.min(2)
    car = (lum < 244) | (sat > 25)
    # close the car mask (white paint touching the white background): fill rows between first/last car pixel
    filled = np.zeros_like(car)
    for y in range(car.shape[0]):
        xs = np.flatnonzero(car[y])
        if len(xs) > 10: filled[y, xs[0]:xs[-1] + 1] = True
    m = np.where(filled, CLASS['paint'], CLASS['bg'])
    dark = filled & (lum < 120) & (sat < 70)
    m[dark] = CLASS['glass'] if belt_row is None else CLASS['trim']
    if belt_row is not None:
        rows = np.arange(m.shape[0])[:, None]
        m[dark & (rows < belt_row)] = CLASS['glass']
    if belt_row is not None and greenhouse:
        # the side glass shows the grey cabin through it: inside the greenhouse span, anything not bright paint is glass
        x0, x1, top = greenhouse
        cols = np.arange(m.shape[1])[None, :]
        rows = np.arange(m.shape[0])[:, None]
        zone = filled & (rows < belt_row) & (rows > top) & (cols > x0) & (cols < x1)
        m[zone & (lum < 200) & (sat < 45)] = CLASS['glass']
    m[filled & (r > 120) & (r - g > 60) & (r - b > 50)] = CLASS['lamp']
    led = filled & (lum > 225) & (b > r + 8)
    m[led] = CLASS['led']
    if wheels:
        yy, xx = np.mgrid[:m.shape[0], :m.shape[1]]
        for cx, cy, rad in wheels:
            m[(xx - cx) ** 2 + (yy - cy) ** 2 < rad ** 2] = CLASS['bg']
    # tidy: majority filter removes single-pixel speckle
    im = Image.fromarray(m.astype(np.uint8)).filter(ImageFilter.ModeFilter(5))
    return np.asarray(im)


k2 = 4.736 / 1483
wheel_px = [(315, 691 - 0.40 / k2, 0.405 / k2), (1214, 691 - 0.40 / k2, 0.405 / k2)]
belt = int(691 - 0.80 / k2)   # dark above ~0.8 m in the side view is glass; below it is trim (intake, sill, splitter)
mA2 = classify(os.path.join(d, 'blueprint', 'gt-A2-side.png'), wheels=wheel_px, belt_row=belt, greenhouse=(560, 1070, 320))
# the side window: in A2 it shows the light grey cabin through it, framed by the black A-pillar, the black B-pillar line
# and the black quarter window. Kept as its own lighter class ('sideglass') so the greenhouse reads as framed panes, not
# one dark mass. The pane outline is measured off A2 (the cabin behind it is too busy to threshold: seats, reflections).
from PIL import ImageDraw
SIDE_PANE = [(700, 331), (760, 331), (830, 334), (892, 340), (897, 421), (760, 425), (617, 429)]
pane = Image.new('L', (mA2.shape[1], mA2.shape[0]), 0)
ImageDraw.Draw(pane).polygon(SIDE_PANE, fill=1)
mA2 = np.where((np.asarray(pane) > 0) & (mA2 == CLASS['glass']), CLASS['sideglass'], mA2).astype(np.uint8)
mA5 = classify(os.path.join(d, 'blueprint', 'gt-A5-top.png'))
# the headlamps are separate meshes traced from A3 (build_parts.py); the top view's copy of them would land higher up the
# nose on the AI-derived body and show twice, so it is painted over (the splitter edge at the very front stays)
rows, cols = np.mgrid[:mA5.shape[0], :mA5.shape[1]]
lampzone = (cols > 85) & (cols < 215) & ((rows < 330) | (rows > 660)) & np.isin(mA5, (2, 4, 5))
mA5 = np.where(lampzone, CLASS['paint'], mA5).astype(np.uint8)


def shift_or(m, r):
    out = m.copy()
    for dy in range(-r, r + 1):
        for dx in range(-r, r + 1):
            if dx * dx + dy * dy <= r * r: out |= np.roll(np.roll(m, dy, 0), dx, 1)
    return out


# the A-pillars: in the top view they are thin white strips (5..6 cm) between the windscreen and the side glass. On the
# body they lean out more than up, so the side view (which sees windscreen there) out-voted them and the greenhouse
# became one dark mass. Paint pixels that a 14 px closing of the glass would fill, in the cabin span, are class
# 'pillar': build_bake.py paints them body colour whatever way the surface faces.
# the windscreen: the cabin seen through it has light reflections on one side, which came out as paint islands (a
# hole in the glass on one side only). Fill it from the outline and make it symmetric about the centre line (row 493).
glass5 = mA5 == CLASS['glass']
seen = np.zeros_like(glass5); stack = [(493, 560)]
while stack:
    i, j = stack.pop()
    if not (0 <= i < glass5.shape[0] and 0 <= j < glass5.shape[1]) or seen[i, j] or not glass5[i, j]: continue
    seen[i, j] = True
    stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
outside = np.zeros_like(seen); stack = [(0, 0)]
while stack:
    i, j = stack.pop()
    if not (0 <= i < seen.shape[0] and 0 <= j < seen.shape[1]) or outside[i, j] or seen[i, j]: continue
    outside[i, j] = True
    stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
screen = ~outside
screen[:, :380] = False; screen[:, 720:] = False
mirror_rows = 2 * 493 - np.arange(screen.shape[0])
ok = (mirror_rows >= 0) & (mirror_rows < screen.shape[0])
sym = screen.copy(); sym[ok] |= screen[mirror_rows[ok]]
mA5 = np.where(sym, CLASS['glass'], mA5).astype(np.uint8)
glass5 = mA5 == CLASS['glass']
closed = ~shift_or(~shift_or(glass5, 14), 14)
pillar = closed & ~glass5 & (mA5 == CLASS['paint']) & (cols > 450) & (cols < 900)
mA5 = np.where(pillar, CLASS['pillar'], mA5).astype(np.uint8)
# front and rear views (A3/A4, slight perspective): dark above the bonnet line is glass, below it trim
def belt_of(path, frac):
    a = np.asarray(Image.open(path).convert('L')).astype(int)
    rows = np.flatnonzero((a < 244).sum(1) > 20)
    return int(rows[0] + frac * (rows[-1] - rows[0]))


def drop_outer_dark(m, px_per_m, centre_col, zero_row, row_per_m, tyre_y, tyre_z, strip=0.035):
    """Front/rear views: the tyres and the shaded flanks curving away at the car's left and right edges are dark, so
    they came out as trim. The body is wider than the drawing at the fenders (build_body.py drums), so its bumper
    corners landed on them as black flames. Those pixels become background (no vote; the side view decides there):
    dark below tyre_z m outside |y| tyre_y m (the tyres), and dark within `strip` of the row's silhouette edge.
    Measured, not flood-filled: the corner intakes and the grille join the tyres through the splitter line."""
    m = m.copy()
    rows, cols = np.mgrid[:m.shape[0], :m.shape[1]]
    y = np.abs(cols - centre_col) / px_per_m
    z = (zero_row - rows) / row_per_m
    dark = m == CLASS['trim']
    car = m > 0
    xs = [np.flatnonzero(r) for r in car]
    left = np.array([x[0] if len(x) else 0 for x in xs])[:, None]
    right = np.array([x[-1] if len(x) else 0 for x in xs])[:, None]
    edge = (cols < left + strip * (right - left)) | (cols > right - strip * (right - left))
    m[dark & (((y > tyre_y) & (z < tyre_z)) | edge)] = CLASS['bg']
    return m


A3p, A4p = os.path.join(d, 'blueprint', 'gt-A3-front.png'), os.path.join(d, 'blueprint', 'gt-A4-rear.png')
def fill_specks(m, limit=400):
    """Paint islands enclosed by trim and smaller than limit px (light glints on grille slats and mesh in the front and
    rear drawings) become trim: on the car they were white smears inside the black openings."""
    m = m.copy(); seen = np.zeros(m.shape, bool)
    for i, j in zip(*np.nonzero(m == CLASS['paint'])):
        if seen[i, j]: continue
        comp, stack, touches = [], [(i, j)], set(); seen[i, j] = True
        while stack and len(comp) <= limit:
            p, q = stack.pop(); comp.append((p, q))
            for u, v in ((p + 1, q), (p - 1, q), (p, q + 1), (p, q - 1)):
                if not (0 <= u < m.shape[0] and 0 <= v < m.shape[1]): continue
                if m[u, v] == CLASS['paint']:
                    if not seen[u, v]: seen[u, v] = True; stack.append((u, v))
                else: touches.add(int(m[u, v]))
        if len(comp) <= limit and not stack and touches == {CLASS['trim']}:
            for p, q in comp: m[p, q] = CLASS['trim']
    return m


mA3 = drop_outer_dark(classify(A3p, belt_row=belt_of(A3p, 0.36), greenhouse=(300, 1236, 170)),  # seats through the windscreen = glass
                      721, 767.5, 880, 585, tyre_y=0.70, tyre_z=0.15)
mA4 = drop_outer_dark(classify(A4p, belt_row=belt_of(A4p, 0.36)), 691, 767.5, 865, 573, tyre_y=0.68, tyre_z=0.35)
mA3, mA4 = fill_specks(mA3), fill_specks(mA4)
out = os.path.join(d, 'hybrid', 'tex')
ROUGH = {0: 0.55, 1: 0.28, 2: 0.04, 3: 0.55, 4: 0.12, 5: 0.08, 6: 0.28, 7: 0.05}
for name, m in (('A2', mA2), ('A5', mA5), ('A3', mA3), ('A4', mA4)):
    Image.fromarray(m).save(os.path.join(out, f'mask-{name}.png'))
    rgb = np.zeros(m.shape + (3,), np.uint8)
    for c, col in COL.items(): rgb[m == c] = col
    Image.fromarray(rgb).save(os.path.join(out, f'preview-{name}.png'))
    rough = np.zeros(m.shape, np.uint8)
    for c, v in ROUGH.items(): rough[m == c] = int(v * 255)
    Image.fromarray(rough).save(os.path.join(out, f'rough-{name}.png'))
    print(name, {k: int((m == v).sum()) for k, v in CLASS.items()})


# Panel lines: the drawings show shut lines and seams (door, bonnet, front wings, engine cover, bumpers) as thin dark
# curves 1..3 px wide. A black-hat (5 px closing minus the image) finds them; only on paint, away from the silhouette
# edge (where shading also darkens), and only in runs of 25 px or more. build_bake.py darkens the paint along them.
def panel_lines(name, m):
    g = Image.open(os.path.join(d, 'blueprint', f'gt-{name}.png')).convert('L')
    a = np.asarray(g).astype(float)
    cl = np.asarray(g.filter(ImageFilter.MaxFilter(5)).filter(ImageFilter.MinFilter(5))).astype(float)
    line = (np.clip(cl - a, 0, 255) > 28) & (m == CLASS['paint'])
    near_edge = np.asarray(Image.fromarray(((m == CLASS['bg']) * 255).astype(np.uint8)).filter(ImageFilter.MaxFilter(13))) > 0
    line &= ~near_edge
    seen = np.zeros_like(line); keep = np.zeros_like(line)
    for i, j in zip(*np.nonzero(line)):
        if seen[i, j]: continue
        comp, stack = [], [(i, j)]; seen[i, j] = True
        while stack:
            p, q = stack.pop(); comp.append((p, q))
            for dp in (-1, 0, 1):
                for dq in (-1, 0, 1):
                    u, v = p + dp, q + dq
                    if 0 <= u < line.shape[0] and 0 <= v < line.shape[1] and line[u, v] and not seen[u, v]:
                        seen[u, v] = True; stack.append((u, v))
        if len(comp) >= 25:
            for p, q in comp: keep[p, q] = True
    Image.fromarray((keep * 255).astype(np.uint8)).save(os.path.join(out, f'line-{name.split("-")[0]}.png'))
    print('LINES', name, int(keep.sum()))


for name, m in (('A2-side', mA2), ('A5-top', mA5), ('A3-front', mA3), ('A4-rear', mA4)):
    panel_lines(name, m)

