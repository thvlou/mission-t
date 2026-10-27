# Vertigo fleet: five original Mission T cars built with the same method as the Vertigo GT
# (lofted cross-sections with monotone PCHIP profiles, subdivision with creases, boolean wheel
# arches, ribbon details ray-cast onto the body). Run inside Blender with the Vertigo GT .blend
# open (it supplies the studio); each car lands in its own collection "Fleet_<id>".
#
#   exec(open(r"<repo>/blender/vertigo_fleet.py").read()); build_all()
#
# Body types are generic (coupe SUV, front-engine GT, mid-engine wedge, four-door fastback, track
# coupe); no real car's lamps, grille, badge or name is copied.
import bpy, bmesh, math
from mathutils import Vector, Matrix

M = bpy.data.materials
lerp = lambda a, b, t: a + (b - a) * t


# ---------------------------------------------------------------- materials
def material(name, base, metal=0.05, rough=0.16, coat=0.0, emit=None, strength=0.0, alpha=1.0):
    # base: '#rrggbb' (sRGB) or a linear (r, g, b) tuple
    m = M.get(name) or M.new(name)
    m.use_nodes = True
    nt = m.node_tree
    p = next((n for n in nt.nodes if n.type == 'BSDF_PRINCIPLED'), None)
    if p is None:
        nt.nodes.clear()
        p = nt.nodes.new('ShaderNodeBsdfPrincipled')
        out = nt.nodes.new('ShaderNodeOutputMaterial')
        nt.links.new(p.outputs[0], out.inputs[0])
    hexrgb = lambda h: [((int(h[i:i + 2], 16) / 255) ** 2.2) for i in (1, 3, 5)]
    rgb = hexrgb(base) if isinstance(base, str) else list(base)
    p.inputs['Base Color'].default_value = (*rgb, 1)
    p.inputs['Metallic'].default_value = metal
    p.inputs['Roughness'].default_value = rough
    p.inputs['Coat Weight'].default_value = coat
    if 'Coat Roughness' in p.inputs: p.inputs['Coat Roughness'].default_value = 0.02
    e = hexrgb(emit) if isinstance(emit, str) else (emit or (1, 1, 1))
    p.inputs['Emission Color'].default_value = (*e, 1)
    p.inputs['Emission Strength'].default_value = strength
    p.inputs['Alpha'].default_value = alpha
    if alpha < 1:
        if hasattr(m, 'surface_render_method'): m.surface_render_method = 'BLENDED'
        if hasattr(m, 'blend_method'):
            try: m.blend_method = 'BLEND'
            except Exception: pass
    m.diffuse_color = (*rgb, alpha)
    return m


def shared_materials():
    return {
        'Glass': material('Fleet Smoked Glass', (0.018, 0.032, 0.044), 0.05, 0.11, 1.0, alpha=0.58),
        'Trim': material('Fleet Trim', (0.012, 0.016, 0.021), 0.25, 0.32),
        'Cladding': material('Fleet Cladding', (0.02, 0.022, 0.026), 0.0, 0.62),
        'LampHousing': material('Fleet LampHousing', (0.004, 0.004, 0.005), 0.3, 0.15, 1.0),
        'HeadLamp': material('HeadLamp Fleet', (1, 1, 1), 0.0, 0.2, emit=(0.905, 0.939, 1.0), strength=6.0),
        'BrakeLamp': material('BrakeLamp Fleet', (0.55, 0.003, 0.008), 0.25, 0.18, emit=(1, 0.01, 0.016), strength=1.0),
        'CenterBrakeLamp': material('CenterBrakeLamp Fleet', (0.38, 0.002, 0.004), 0.15, 0.19),
        'ReverseLamp': material('ReverseLamp Fleet', (0.65, 0.72, 0.8), 0.1, 0.21),
        'Tire': material('Fleet Tire', (0.006, 0.006, 0.007), 0.0, 0.75),
        'RimFace': material('Fleet RimFace', (0.839, 0.839, 0.823), 0.3, 0.22, 0.6),
        'RimDark': material('Fleet RimDark', (0.012, 0.012, 0.014), 0.6, 0.35),
        'Disc': material('Fleet Disc', (0.068, 0.072, 0.08), 0.8, 0.45),
        'RimGraphite': material('Fleet RimGraphite', (0.06, 0.065, 0.072), 0.75, 0.3),
        'RimBlack': material('Fleet RimBlack', (0.012, 0.012, 0.014), 0.5, 0.35, 0.4),
        'RimTwoTone': material('Fleet RimTwoTone', (0.70, 0.71, 0.72), 0.9, 0.18, 0.6),
        'Caliper': material('Fleet Caliper', '#d23437', 0.1, 0.35),
        'RimLip': material('Fleet RimLip', (0.86, 0.86, 0.87), 1.0, 0.1, 0.8),
        'Lug': material('Fleet Lug', (0.55, 0.56, 0.58), 1.0, 0.24),
        'TireWall': material('Fleet TireWall', (0.016, 0.016, 0.018), 0.0, 0.58),
        'Hat': material('Fleet DiscHat', (0.03, 0.032, 0.036), 0.7, 0.4),
        'WheelWell': material('Fleet WheelWell', (0.003, 0.003, 0.004), 0.0, 0.9),
        'Interior': material('Fleet Interior', (0.024, 0.026, 0.03), 0.0, 0.48),
        'Accent': material('Fleet Accent', '#d23437', 0.05, 0.18, 1.0),
    }


# ---------------------------------------------------------------- profiles
def pchip(pts):
    """Monotone cubic (Fritsch-Carlson): smooth, no overshoot, no flat spots at the keys."""
    xs = sorted(pts); ys = [pts[x] for x in xs]
    n = len(xs); h = [xs[i + 1] - xs[i] for i in range(n - 1)]
    d = [(ys[i + 1] - ys[i]) / h[i] for i in range(n - 1)]
    m = [0.0] * n
    m[0], m[-1] = d[0], d[-1]
    for i in range(1, n - 1):
        if d[i - 1] * d[i] <= 0: m[i] = 0.0
        else:
            w1, w2 = 2 * h[i] + h[i - 1], h[i] + 2 * h[i - 1]
            m[i] = (w1 + w2) / (w1 / d[i - 1] + w2 / d[i])
    def f(x):
        if x <= xs[0]: return ys[0]
        if x >= xs[-1]: return ys[-1]
        i = max(k for k in range(n - 1) if xs[k] <= x)
        t = (x - xs[i]) / h[i]
        h00, h10, h01, h11 = 2*t**3 - 3*t**2 + 1, t**3 - 2*t**2 + t, -2*t**3 + 3*t**2, t**3 - t**2
        return h00 * ys[i] + h10 * h[i] * m[i] + h01 * ys[i + 1] + h11 * h[i] * m[i + 1]
    return f


# ---------------------------------------------------------------- the five cars
# x forward (front +), y to the left, z up, metres. Keys: zb underside, W half width, zbel rocker
# bulge, zsh shoulder line, ztop centre line (roof, glass, hood, deck), wcb half width of the roof.
SPECS = {
    'vertigo-apex': dict(
        name='Vertigo Apex', paint='#7d738d', paint_metal=0.35, paint_rough=0.2, paint_name='Lavender', length=4.50, wb=(-1.32, 1.30), R=0.355, track=0.86,
        flare=(0.045, 0.024), ride=0.115,
        zb={-2.25: 0.33, -2.15: 0.22, -1.95: 0.15, -1.75: 0.125, 0.0: 0.115, 1.80: 0.12, 2.08: 0.15, 2.25: 0.20},
        W={-2.25: 0.60, -2.18: 0.77, -2.05: 0.90, -1.80: 0.995, -1.35: 1.04, -0.90: 1.0, -0.40: 0.935, 0.20: 0.905, 0.80: 0.93, 1.30: 0.975, 1.80: 0.945, 2.05: 0.875, 2.18: 0.74, 2.25: 0.56},
        zbel={-2.25: 0.47, -1.80: 0.49, -1.35: 0.50, -0.30: 0.43, 1.30: 0.46, 2.25: 0.31},
        zsh={-2.25: 0.80, -2.10: 0.87, -1.75: 0.93, -1.35: 0.95, -0.85: 0.86, -0.25: 0.755, 0.45: 0.735, 0.95: 0.77, 1.30: 0.80, 1.80: 0.67, 2.10: 0.48, 2.25: 0.35},
        ztop={-2.25: 0.815, -2.15: 0.87, -1.85: 0.90, -1.35: 0.94, -0.85: 1.02, -0.45: 1.095, -0.05: 1.125, 0.30: 1.105, 0.62: 1.0, 1.0: 0.76, 1.35: 0.63, 1.85: 0.545, 2.10: 0.445, 2.25: 0.335},
        wcb={-2.25: 0.36, -1.80: 0.42, -1.25: 0.55, -0.65: 0.655, 0.0: 0.675, 0.55: 0.655, 1.0: 0.59, 1.40: 0.45, 2.25: 0.34},
        glass=(-0.78, 1.04),
        lamp=dict(y0=0.40, y1=0.82, z0=0.43, rise=0.075, width=0.085, drl=0.026, style='hook'), tail_style='split',
        intake_z=0.27, splitter=True, scoop=dict(x0=-0.48, x1=-0.98, z0=0.40, z1=0.74, width=0.12),
        shuts=[(0.98, -0.43)], mirror=(0.72, 0.76), tail=dict(z=0.70, y=0.66, width=0.07), diffuser_z=0.36, fins=5,
        vents=True, seat_x=-0.10, wheel=dict(windows=10, r_in=0.11, r_out=0.25, w_in=0.012, w_out=0.034, twist=0.22, face='RimFace'),
    ),
    'vertigo-arc': dict(
        name='Vertigo Arc', paint='#64a8c9', paint_metal=0.35, paint_rough=0.18, paint_name='Sky Blue', length=4.62, wb=(-1.30, 1.18), R=0.355, track=0.84,
        flare=(0.06, 0.02), ride=0.125,
        zb={-2.33: 0.34, -2.21: 0.24, -2.01: 0.16, -1.81: 0.135, 0.0: 0.125, 1.90: 0.13, 2.16: 0.16, 2.29: 0.21},
        W={-2.33: 0.60, -2.26: 0.76, -2.13: 0.89, -1.93: 0.98, -1.45: 1.03, -0.95: 0.97, -0.45: 0.92, 0.20: 0.905, 0.70: 0.925, 1.18: 0.96, 1.80: 0.93, 2.05: 0.86, 2.20: 0.74, 2.29: 0.56},
        zbel={-2.33: 0.50, -1.93: 0.51, -1.45: 0.52, -0.30: 0.46, 1.18: 0.48, 2.29: 0.33},
        zsh={-2.33: 0.73, -2.18: 0.81, -1.93: 0.885, -1.45: 0.93, -1.00: 0.88, -0.40: 0.82, 0.40: 0.81, 0.95: 0.83, 1.18: 0.85, 1.80: 0.74, 2.12: 0.56, 2.29: 0.42},
        ztop={-2.33: 0.76, -2.25: 0.82, -2.06: 0.865, -1.75: 0.905, -1.35: 0.94, -0.95: 0.955, -0.55: 0.95, -0.15: 0.93, 0.35: 0.905, 0.62: 0.87, 0.95: 0.79, 1.45: 0.735, 1.95: 0.645, 2.18: 0.52, 2.29: 0.42},
        wcb={-2.33: 0.40, -1.90: 0.52, -1.45: 0.62, -0.95: 0.70, -0.40: 0.72, 0.30: 0.71, 0.62: 0.66, 0.95: 0.55, 1.50: 0.46, 2.29: 0.38},
        glass=None, cabrio=dict(x0=-0.86, x1=0.58, hy=0.63, shield=0.36, rake=0.42),
        lamp=dict(y0=0.48, y1=0.78, z0=0.56, rise=0.04, width=0.08, drl=0.03, style='round'),
        intake_z=0.29, splitter=False, scoop=dict(x0=-0.95, x1=-1.20, z0=0.52, z1=0.70, width=0.06),
        shuts=[(0.66, -0.66)], mirror=(0.52, 0.86), tail=dict(z=0.70, y=0.66, width=0.06), diffuser_z=0.38, fins=0,
        seat_x=-0.22, wheel=dict(windows=5, r_in=0.10, r_out=0.25, w_in=0.012, w_out=0.03, pair=0.16, face='RimFace'),
    ),
    'vertigo-grand': dict(
        name='Vertigo Grand', paint='#063722', paint_metal=0.35, paint_rough=0.18, paint_name='Forest Green', length=4.96, wb=(-1.48, 1.50), R=0.37, track=0.86,
        flare=(0.03, 0.018), ride=0.13,
        zb={-2.48: 0.36, -2.36: 0.25, -2.15: 0.17, -1.95: 0.14, 0.0: 0.13, 2.02: 0.135, 2.30: 0.17, 2.48: 0.22},
        W={-2.48: 0.60, -2.40: 0.74, -2.28: 0.86, -2.05: 0.95, -1.60: 0.995, -1.10: 0.97, -0.50: 0.94, 0.30: 0.935, 0.90: 0.95, 1.50: 0.975, 2.0: 0.95, 2.25: 0.88, 2.38: 0.76, 2.48: 0.58},
        zbel={-2.48: 0.53, -2.0: 0.54, -1.55: 0.55, -0.30: 0.49, 1.50: 0.51, 2.48: 0.35},
        zsh={-2.48: 0.79, -2.30: 0.865, -2.0: 0.93, -1.60: 0.95, -1.10: 0.905, -0.40: 0.845, 0.40: 0.835, 1.0: 0.855, 1.50: 0.89, 2.0: 0.785, 2.30: 0.58, 2.48: 0.43},
        ztop={-2.48: 0.86, -2.40: 0.925, -2.25: 0.955, -2.05: 0.965, -1.85: 1.03, -1.55: 1.18, -1.15: 1.32, -0.70: 1.385, -0.20: 1.395, 0.25: 1.37, 0.55: 1.22, 0.85: 0.94, 1.15: 0.81, 1.70: 0.755, 2.20: 0.645, 2.40: 0.51, 2.48: 0.42},
        wcb={-2.48: 0.38, -2.0: 0.45, -1.60: 0.55, -1.10: 0.66, -0.50: 0.71, 0.30: 0.71, 0.75: 0.64, 1.05: 0.52, 1.60: 0.46, 2.48: 0.38},
        glass=(-1.80, 0.88), pillars=(-0.24, -1.26),
        lamp=dict(y0=0.30, y1=0.84, z0=0.55, rise=0.05, width=0.07, drl=0.022), front_bar=True,
        intake_z=0.31, splitter=False, scoop=None,
        shuts=[(0.88, -0.22), (-0.28, -1.20)], mirror=(0.80, 0.90), tail=dict(z=0.74, y=0.70, width=0.06), diffuser_z=0.40, fins=0,
        seat_x=-0.05, rear_seats=True, wheel=dict(windows=14, r_in=0.115, r_out=0.25, w_in=0.009, w_out=0.022, twist=0.42, face='RimGraphite'),
    ),
    'vertigo-terra': dict(
        name='Vertigo Terra', paint='#790113', paint_metal=0.35, paint_rough=0.18, paint_name='Crimson',
        length=4.80, wb=(-1.42, 1.45), R=0.40, track=0.88, flare=(0.035, 0.025), ride=0.30, cladding=True,
        zb={-2.40: 0.58, -2.30: 0.45, -2.12: 0.35, -1.90: 0.31, 0.0: 0.30, 1.90: 0.31, 2.15: 0.36, 2.40: 0.46},
        W={-2.40: 0.70, -2.34: 0.82, -2.22: 0.91, -2.0: 0.975, -1.55: 1.02, -1.05: 1.0, -0.50: 0.975, 0.30: 0.97, 0.90: 0.98, 1.45: 1.0, 1.95: 0.98, 2.20: 0.91, 2.33: 0.80, 2.40: 0.66},
        zbel={-2.40: 0.74, -1.90: 0.75, -1.45: 0.76, -0.30: 0.71, 1.45: 0.72, 2.40: 0.58},
        zsh={-2.40: 1.04, -2.25: 1.10, -2.0: 1.155, -1.55: 1.18, -1.10: 1.13, -0.40: 1.09, 0.40: 1.085, 1.0: 1.10, 1.45: 1.13, 1.95: 1.03, 2.25: 0.83, 2.40: 0.66},
        ztop={-2.40: 1.06, -2.34: 1.17, -2.24: 1.33, -2.08: 1.47, -1.80: 1.59, -1.40: 1.665, -0.90: 1.69, -0.30: 1.70, 0.25: 1.685, 0.55: 1.59, 0.88: 1.33, 1.15: 1.16, 1.70: 1.09, 2.15: 0.96, 2.32: 0.78, 2.40: 0.66},
        wcb={-2.40: 0.50, -2.10: 0.58, -1.70: 0.66, -1.10: 0.73, -0.50: 0.76, 0.30: 0.76, 0.75: 0.71, 1.10: 0.60, 1.60: 0.54, 2.40: 0.46},
        glass=(-2.02, 0.90), pillars=(-0.22, -1.22),
        lamp=dict(y0=0.42, y1=0.86, z0=0.93, rise=0.03, width=0.05, drl=0.018, style='twotier'), lower_lamp=dict(z=0.66, y0=0.55, y1=0.80),
        intake_z=0.50, splitter=False, scoop=None,
        shuts=[(0.92, -0.20), (-0.26, -1.18)], mirror=(0.86, 1.22), tail=dict(z=1.10, y=0.72, width=0.06), diffuser_z=0.64, fins=0,
        rails=True, seat_x=0.0, rear_seats=True, wheel=dict(windows=6, r_in=0.115, r_out=0.255, w_in=0.026, w_out=0.06, face='RimBlack'),
    ),
    'vertigo-r': dict(
        name='Vertigo R', paint='#979fac', paint_metal=0.6, paint_rough=0.2, paint_name='Cool Silver', length=4.68, wb=(-1.38, 1.38), R=0.355, track=0.88,
        flare=(0.06, 0.045), ride=0.10,
        zb={-2.34: 0.32, -2.22: 0.22, -2.02: 0.14, -1.82: 0.115, 0.0: 0.10, 1.87: 0.11, 2.14: 0.14, 2.34: 0.19},
        W={-2.34: 0.60, -2.27: 0.75, -2.14: 0.87, -1.92: 0.975, -1.50: 1.045, -1.0: 0.995, -0.50: 0.935, 0.20: 0.92, 0.75: 0.95, 1.38: 1.0, 1.85: 0.97, 2.05: 0.905, 2.20: 0.79, 2.34: 0.59},
        zbel={-2.34: 0.48, -1.92: 0.49, -1.45: 0.50, -0.30: 0.44, 1.38: 0.46, 2.34: 0.31},
        zsh={-2.34: 0.70, -2.20: 0.775, -1.97: 0.865, -1.55: 0.925, -1.10: 0.87, -0.40: 0.785, 0.40: 0.775, 1.0: 0.81, 1.38: 0.86, 1.85: 0.745, 2.12: 0.55, 2.34: 0.39},
        ztop={-2.34: 0.675, -2.26: 0.71, -2.12: 0.72, -1.87: 0.755, -1.55: 0.835, -1.20: 0.96, -0.80: 1.08, -0.40: 1.175, -0.05: 1.21, 0.25: 1.203, 0.55: 1.12, 0.97: 0.795, 1.30: 0.685, 1.85: 0.615, 2.12: 0.505, 2.34: 0.38},
        wcb={-2.34: 0.36, -1.90: 0.44, -1.55: 0.52, -1.0: 0.64, -0.25: 0.685, 0.50: 0.675, 0.97: 0.63, 1.30: 0.49, 1.90: 0.44, 2.34: 0.36},
        glass=(-1.42, 0.965),
        lamp=dict(y0=0.34, y1=0.81, z0=0.468, rise=0.115, width=0.115, drl=0.034),
        intake_z=0.26, splitter=True, scoop=dict(x0=-0.60, x1=-0.90, z0=0.40, z1=0.70, width=0.08),
        shuts=[(0.93, -0.58)], mirror=(0.74, 0.80), tail=dict(z=0.585, y=0.62, width=0.065), tail_style='double', diffuser_z=0.30, fins=6,
        vents=True, wing=True, stripe=True, projectors=True, seat_x=-0.25, wheel=dict(windows=5, r_in=0.10, r_out=0.25, w_in=0.014, w_out=0.036, pair=0.12, face='RimTwoTone'),
    ),
}


# ---------------------------------------------------------------- body
def half_profile(x, P):
    w, b, bel, sh, top, wc = (P[k](x) for k in ('W', 'zb', 'zbel', 'zsh', 'ztop', 'wcb'))
    t = max(0.0, min(1.0, (top - sh) / 0.15))
    t = t * t * (3 - 2 * t)
    p8 = (wc, lerp(top + 0.35 * (sh - top), sh + 0.012, t))
    p9 = (lerp(0.70 * wc, 0.92 * wc, t), lerp(top + 0.05 * (sh - top), sh + 0.55 * (top - sh), t))
    p10 = (lerp(0.35 * wc, 0.66 * wc, t), lerp(top, top - 0.05, t))
    return [(0.0, b), (0.78 * w, b), (0.90 * w, b + 0.05), (0.965 * w, b + 0.16), (w, bel), (0.98 * w, bel + 0.13),
            (0.92 * w, sh - 0.075), (0.83 * w, sh), p8, p9, p10, (0.0, top)]


def ring(x, P):
    h = half_profile(x, P)
    return [(-y, z) for (y, z) in h] + [(y, z) for (y, z) in reversed(h[1:-1])]


def build_body(cid, S, coll, mats):
    P = {k: pchip(S[k]) for k in ('W', 'zb', 'zbel', 'zsh', 'ztop', 'wcb')}
    x0, x1 = min(S['ztop']), max(S['ztop'])
    xs = [x0, x0 + 0.02, x0 + 0.05, x0 + 0.09, x0 + 0.14]
    x = x0 + 0.22
    while x < x1 - 0.18:
        xs.append(round(x, 3)); x += 0.1
    xs += [x1 - 0.14, x1 - 0.09, x1 - 0.05, x1 - 0.02, x1]
    N = len(ring(0, P))
    bm = bmesh.new()
    rings = [[bm.verts.new((x, y, z)) for (y, z) in ring(x, P)] for x in xs]
    crease = bm.edges.layers.float.get('crease_edge') or bm.edges.layers.float.new('crease_edge')
    CREASE = {7: 0.3, 15: 0.3, 5: 0.18, 17: 0.18, 8: 0.6, 14: 0.6}
    for a, b in zip(rings, rings[1:]):
        for i in range(N):
            j = (i + 1) % N
            bm.faces.new((a[i], a[j], b[j], b[i]))
        for k, c in CREASE.items():
            e = bm.edges.get((a[k], b[k]))
            if e: e[crease] = c
    def cap(r, dx, scale):
        cz = sum(v.co.z for v in r) / len(r)
        inner = [bm.verts.new((v.co.x + dx, v.co.y * scale, cz + (v.co.z - cz) * scale)) for v in r]
        for i in range(N):
            j = (i + 1) % N
            bm.faces.new((r[i], r[j], inner[j], inner[i]))
        bm.faces.new(inner)
    cap(rings[0], -0.05, 0.5)
    cap(rings[-1], 0.03, 0.5)
    xr, xf = S['wb']
    R = S['R']
    for v in bm.verts:
        vx, vy, vz = v.co
        for ax, flare, lift in ((xf, S['flare'][1], 0.022), (xr, S['flare'][0], 0.016)):
            d = math.hypot(vx - ax, vz - (R + 0.01))
            if abs(vy) > 0.72 and R + 0.02 < d < R + 0.49:
                u = (d - R - 0.02) / 0.47
                k = (1 - u) ** 2 * (1 + 2 * u)
                v.co.y += math.copysign(flare * k, vy)
                if vz > R + 0.24: v.co.z += lift * k
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f'{cid}_Body')
    bm.to_mesh(me); bm.free()
    for m in (mats['Paint'], mats['Glass'], mats['Trim'], mats['Cladding']): me.materials.append(m)
    GLASS = {8, 9, 10, 11, 12, 13}
    TRIM = {0, 1, 20, 21}
    g0, g1 = S['glass'] or (0.0, 0.0)
    bands = (len(xs) - 1) * N
    clad = S.get('cladding')
    for f, p in enumerate(me.polygons):
        p.use_smooth = True
        if f < bands:
            i = f % N
            cx = p.center.x
            glass = i in GLASS and g0 < cx < g1
            sill = i in {2, 19} and xr + 0.43 < cx < xf - 0.46
            if glass: p.material_index = 1
            elif clad and i in {1, 2, 3, 18, 19, 20}: p.material_index = 3
            elif i in TRIM or sill: p.material_index = 2
            else: p.material_index = 0
    me.update()
    body = bpy.data.objects.new(f'{cid}_Body', me)
    coll.objects.link(body)
    # Wheel arches: two cylinders cut from the subdivided shell; cut faces take the well material.
    cbm = bmesh.new()
    # One short cylinder per wheel, outboard only, so the cut never reaches the hood or deck.
    for ax in (xr, xf):
        for side in (1, -1):
            bmesh.ops.create_cone(cbm, cap_ends=True, segments=64, radius1=R + 0.07, radius2=R + 0.07, depth=0.9,
                                  matrix=Matrix.Translation((ax, side * 1.05, R + 0.01)) @ Matrix.Rotation(math.pi / 2, 4, 'X'))
    bmesh.ops.recalc_face_normals(cbm, faces=cbm.faces)
    cme = bpy.data.meshes.new(f'{cid}_ArchCutter'); cbm.to_mesh(cme); cbm.free()
    cme.materials.append(mats['WheelWell'])
    cutter = bpy.data.objects.new(f'{cid}_ArchCutter', cme)
    coll.objects.link(cutter)
    cutter.hide_render = True
    cutter.display_type = 'WIRE'
    sub = body.modifiers.new('Subdivision', 'SUBSURF'); sub.levels = 2; sub.render_levels = 2
    arch = body.modifiers.new('Arches', 'BOOLEAN'); arch.operation = 'DIFFERENCE'; arch.object = cutter
    arch.solver = 'EXACT'; arch.material_mode = 'TRANSFER'
    arch.use_self = True; arch.use_hole_tolerant = True  # self mode keeps the cut a cut on every body
    if S.get('cabrio'):
        cb = S['cabrio']
        top = pchip(S['ztop'])
        deck = min(top(cb['x0']), top(cb['x1']))
        outline = rounded_rect((cb['x0'] + cb['x1']) / 2, (cb['x1'] - cb['x0']) / 2, cb['hy'], 0.16)
        cockpit = bpy.data.objects.new(f'{cid}_CockpitCutter', prism_mesh(f'{cid}_CockpitCutter', outline, deck - 0.09, deck + 1.5, mats['Interior']))
        coll.objects.link(cockpit)
        cockpit.hide_render = True
        cockpit.display_type = 'WIRE'
        cut = body.modifiers.new('Cockpit', 'BOOLEAN'); cut.operation = 'DIFFERENCE'; cut.object = cockpit
        cut.solver = 'EXACT'; cut.material_mode = 'TRANSFER'; cut.use_self = True; cut.use_hole_tolerant = True
    return body, cutter


def rounded_rect(cx, hx, hy, r, n=10):
    pts = []
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ox, oy = cx + sx * (hx - r), sy * (hy - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90 * i / n)
            pts.append((ox + r * math.cos(a), oy + r * math.sin(a)))
    return pts


def prism_mesh(name, outline, z0, z1, mat, cap_top=True, inward=False):
    bm = bmesh.new()
    lo = [bm.verts.new((x, y, z0)) for x, y in outline]
    hi = [bm.verts.new((x, y, z1)) for x, y in outline]
    n = len(outline)
    for i in range(n):
        j = (i + 1) % n
        bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
    bm.faces.new(list(reversed(lo)))
    if cap_top: bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    if inward: bmesh.ops.reverse_faces(bm, faces=bm.faces)
    me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
    me.materials.append(mat)
    return me


def build_cabrio(cid, S, coll, mats):
    """Open cockpit: an interior tub, a raked windscreen in a slim frame, roll hoops and humps."""
    cb = S['cabrio']
    top = pchip(S['ztop'])
    zb0 = pchip(S['zb'])(0.0)
    deck = min(top(cb['x0']), top(cb['x1']))
    tub = rounded_rect((cb['x0'] + cb['x1']) / 2, (cb['x1'] - cb['x0']) / 2 - 0.02, cb['hy'] - 0.02, 0.14)
    ob = bpy.data.objects.new(f'{cid}_Tub', prism_mesh(f'{cid}_Tub', tub, zb0 + 0.10, deck - 0.05, mats['Interior'], cap_top=False, inward=True))
    coll.objects.link(ob)
    # Windscreen: a curved, raked panel (glass) with a slim frame band (trim) round its edge
    x0, z0 = cb['x1'] + 0.02, top(cb['x1'] + 0.02) - 0.01
    H, rake, half = cb['shield'], cb['rake'], cb['hy'] + 0.05
    rows, cols = 8, 18
    bm = bmesh.new()
    grid = []
    for i in range(rows + 1):
        u = i / rows
        row = []
        for j in range(cols + 1):
            v = j / cols * 2 - 1
            y = v * half * (1 - 0.10 * u)
            x = x0 - rake * u - 0.07 * v * v
            z = z0 + H * u + 0.02 * (1 - v * v) * u - 0.03 * v * v * (1 - u)
            row.append(bm.verts.new((x, y, z)))
        grid.append(row)
    for i in range(rows):
        for j in range(cols):
            f = bm.faces.new((grid[i][j], grid[i][j + 1], grid[i + 1][j + 1], grid[i + 1][j]))
            edge = i == rows - 1 or j in (0, cols - 1)
            f.material_index = 1 if edge else 0
            f.smooth = True
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f'{cid}_Windscreen'); bm.to_mesh(me); bm.free()
    me.materials.append(mats['Glass']); me.materials.append(mats['Trim'])
    ws = bpy.data.objects.new(f'{cid}_Windscreen', me); coll.objects.link(ws)
    sol = ws.modifiers.new('Thickness', 'SOLIDIFY'); sol.thickness = 0.012
    # Roll hoops behind the seats and two long humps on the rear deck
    for s in (1, -1):
        bm = bmesh.new()
        MAJ, MIN, NU, NV = 0.17, 0.022, 20, 8
        g = [[bm.verts.new((MIN * math.sin(b), s * 0.36 + (MAJ + MIN * math.cos(b)) * math.cos(a), deck - 0.02 + (MAJ + MIN * math.cos(b)) * math.sin(a)))
              for b in (k * math.tau / NV for k in range(NV))] for a in (i * math.pi / NU for i in range(NU + 1))]
        for i in range(NU):
            for k in range(NV):
                bm.faces.new((g[i][k], g[i + 1][k], g[i + 1][(k + 1) % NV], g[i][(k + 1) % NV]))
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        bmesh.ops.translate(bm, verts=bm.verts, vec=(S['seat_x'] - 0.34, 0, 0))
        me = bpy.data.meshes.new(f'{cid}_Hoop_{s}'); bm.to_mesh(me); bm.free()
        me.materials.append(mats['RimFace'])
        for p in me.polygons: p.use_smooth = True
        coll.objects.link(bpy.data.objects.new(f'{cid}_Hoop_{s}', me))
        bm = bmesh.new()
        bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
        for v in bm.verts:
            v.co.x *= 0.62; v.co.y *= 0.19; v.co.z *= 0.09
            v.co += Vector((S['seat_x'] - 0.95, s * 0.36, deck - 0.01))
        me = bpy.data.meshes.new(f'{cid}_Hump_{s}'); bm.to_mesh(me); bm.free()
        me.materials.append(mats['Paint'])
        for p in me.polygons: p.use_smooth = True
        coll.objects.link(bpy.data.objects.new(f'{cid}_Hump_{s}', me))


# ---------------------------------------------------------------- wheels
def build_wheels(cid, S, coll, mats):
    MATS = ['Tire', S['wheel'].get('face', 'RimFace'), 'RimDark', 'Disc', 'RimLip', 'Lug', 'TireWall', 'Hat', 'Caliper']
    SLOT = {'Tire': 0, 'RimFace': 1, 'RimDark': 2, 'Disc': 3, 'RimLip': 4, 'Lug': 5, 'TireWall': 6, 'Hat': 7, 'Caliper': 8}
    Wp = S['wheel']
    twist, pair = Wp.get('twist', 0.0), Wp.get('pair', 0.0)
    R_IN, R_OUT, W_IN, W_OUT, ROUND, POINTS = Wp['r_in'], Wp['r_out'], Wp['w_in'], Wp['w_out'], 4.0, 64
    count = Wp['windows']

    def window(axis):
        mid, half = (R_IN + R_OUT) / 2, (R_OUT - R_IN) / 2
        pts = []
        for i in range(POINTS):
            t = i / POINTS * math.tau
            c, s_ = math.cos(t), math.sin(t)
            u = math.copysign(abs(c) ** (2 / ROUND), c)
            v = math.copysign(abs(s_) ** (2 / ROUND), s_)
            r = mid + u * half
            w = W_IN + (W_OUT - W_IN) * (u + 1) / 2
            phi = axis + (v * w) / r + twist * (r - R_IN) / (R_OUT - R_IN)
            pts.append(Vector((r * math.cos(phi), r * math.sin(phi))))
        return pts

    def tmp(name, bm, slot):
        for f in bm.faces: f.material_index = slot
        me = bpy.data.meshes.new(name); bm.to_mesh(me); bm.free()
        for m in MATS: me.materials.append(mats[m])
        o = bpy.data.objects.new(name, me); bpy.context.scene.collection.objects.link(o)
        return o

    bm = bmesh.new()
    prof = [(0.082 + 0.176 * (i / 20), 0.058 + 0.072 * (i / 20) ** 1.4) for i in range(21)]
    loop = prof + [(r, y - 0.028) for (r, y) in reversed(prof)]
    vs = [bm.verts.new((0, y, r)) for (r, y) in loop]
    es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:] + vs[:1])]
    bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=math.tau, steps=120, use_merge=True)
    bmesh.ops.remove_doubles(bm, verts=bm.verts, dist=1e-6)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    disc = tmp('tmp_disc', bm, SLOT['RimFace'])
    bm = bmesh.new()
    axes = [math.pi / 2 + k * math.tau / count + d for k in range(count) for d in ((-pair / 2, pair / 2) if pair else (0.0,))]
    for axis in axes:
        outline = window(axis)
        lo = [bm.verts.new((p.x, -0.2, p.y)) for p in outline]
        hi = [bm.verts.new((p.x, 0.3, p.y)) for p in outline]
        n = len(outline)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((lo[i], lo[j], hi[j], hi[i]))
        bm.faces.new(list(reversed(lo))); bm.faces.new(hi)
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    cut = tmp('tmp_cut', bm, SLOT['RimDark'])
    mod = disc.modifiers.new('win', 'BOOLEAN'); mod.operation = 'DIFFERENCE'; mod.object = cut; mod.solver = 'EXACT'; mod.material_mode = 'TRANSFER'
    # The window prisms can overlap each other (paired spokes), so let the solver resolve the cutter's
    # own intersections; and evaluate after a scene update, or the result reads back empty.
    mod.use_self = True
    mod.use_hole_tolerant = True
    bpy.context.view_layer.update()
    face = bpy.data.meshes.new_from_object(disc.evaluated_get(bpy.context.evaluated_depsgraph_get()))
    print('STEP wheel face', len(face.polygons), 'faces', flush=True)
    for o in (disc, cut):
        m = o.data; bpy.data.objects.remove(o, do_unlink=True); bpy.data.meshes.remove(m)

    def wheel_bm():
        bm = bmesh.new()
        def lathe(profile, mat, steps=72):
            old = set(bm.faces)
            vs = [bm.verts.new((0, y, r)) for (r, y) in profile]
            es = [bm.edges.new((a, b)) for a, b in zip(vs, vs[1:])]
            bmesh.ops.spin(bm, geom=vs + es, cent=(0, 0, 0), axis=(0, 1, 0), angle=math.tau, steps=steps, use_merge=True)
            for f in bm.faces:
                if f not in old: f.material_index = SLOT[mat]
        # Tyre: rounded sidewalls (with a rim-protector bead on the outside) and a tread with three
        # circumferential grooves.
        lathe([(0.276, -0.124), (0.300, -0.134), (0.328, -0.136), (0.348, -0.124), (0.358, -0.100)], 'TireWall', 96)
        tread = [(0.358, -0.100), (0.3615, -0.088)]
        for gy in (-0.052, 0.0, 0.052):
            tread += [(0.3615, gy - 0.009), (0.3525, gy - 0.006), (0.3525, gy + 0.006), (0.3615, gy + 0.009)]
        tread += [(0.3615, 0.088), (0.358, 0.100)]
        lathe(tread, 'Tire', 128)
        lathe([(0.358, 0.100), (0.348, 0.124), (0.328, 0.136), (0.306, 0.138), (0.300, 0.143), (0.293, 0.139),
               (0.286, 0.133), (0.276, 0.128)], 'TireWall', 96)
        # Rim: dark barrel, a polished stepped lip, then the spoke face
        lathe([(0.276, 0.128), (0.273, 0.075), (0.273, -0.115), (0.24, -0.12)], 'RimDark', 96)
        lathe([(0.276, 0.128), (0.276, 0.136), (0.272, 0.142), (0.266, 0.143), (0.261, 0.138), (0.259, 0.128)], 'RimLip', 96)
        # Ventilated brake disc: two plates with a dark gap and a dark hat in the middle
        lathe([(0.232, -0.044), (0.234, -0.040), (0.234, -0.032), (0.232, -0.030), (0.125, -0.030), (0.125, -0.044), (0.232, -0.044)], 'Disc', 64)
        lathe([(0.232, -0.026), (0.234, -0.022), (0.234, -0.014), (0.232, -0.010), (0.125, -0.010), (0.125, -0.026), (0.232, -0.026)], 'Disc', 64)
        lathe([(0.229, -0.030), (0.229, -0.026)], 'Hat', 64)
        lathe([(0.125, -0.044), (0.118, -0.02), (0.11, 0.0), (0.0, 0.0)], 'Hat', 48)
        # Hub and a round centre cap with a red ring
        lathe([(0.0, 0.05), (0.083, 0.05), (0.086, 0.04), (0.086, 0.0)], 'RimDark', 36)
        lathe([(0.0, 0.100), (0.020, 0.099), (0.030, 0.095), (0.034, 0.090)], 'RimLip', 36)
        lathe([(0.034, 0.090), (0.040, 0.088), (0.040, 0.084)], 'Caliper', 36)
        lathe([(0.040, 0.084), (0.042, 0.076), (0.044, 0.05)], 'RimLip', 36)
        # Five lug nuts round the cap
        for k in range(5):
            a = math.pi / 2 + k * math.tau / 5
            old = set(bm.faces)
            res = bmesh.ops.create_cone(bm, cap_ends=True, segments=6, radius1=0.011, radius2=0.011, depth=0.024)
            vs = res['verts']
            bmesh.ops.rotate(bm, verts=vs, cent=(0, 0, 0), matrix=Matrix.Rotation(math.pi / 2, 3, 'X'))
            bmesh.ops.translate(bm, verts=vs, vec=(0.062 * math.cos(a), 0.084, 0.062 * math.sin(a)))
            for f in bm.faces:
                if f not in old: f.material_index = SLOT['Lug']
        bm.from_mesh(face)
        bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
        return bm

    scale = S['R'] / 0.362
    xr, xf = S['wb']
    out = []
    for name, x, y in (('wheel_FL', xf, 1), ('wheel_FR', xf, -1), ('wheel_RL', xr, 1), ('wheel_RR', xr, -1)):
        bm = wheel_bm()
        if y < 0:
            bmesh.ops.scale(bm, vec=(1, -1, 1), verts=bm.verts)
            bmesh.ops.reverse_faces(bm, faces=bm.faces)
        bmesh.ops.scale(bm, vec=(scale, scale, scale), verts=bm.verts)
        me = bpy.data.meshes.new(f'{cid}_{name}'); bm.to_mesh(me); bm.free()
        for m in MATS: me.materials.append(mats[m])
        for p in me.polygons: p.use_smooth = p.material_index in (SLOT['Tire'], SLOT['RimFace'], SLOT['TireWall'], SLOT['RimLip'], SLOT['Disc'])
        ob = bpy.data.objects.new(name, me)
        ob.location = (x, y * S['track'], S['R'])
        coll.objects.link(ob)
        out.append(ob)
        # Caliper: an arc block inside the rim, behind the spokes (stays put while the wheel spins)
        cb = bmesh.new()
        a0, a1, steps = math.radians(20), math.radians(95), 10
        r0, r1, d0, d1 = 0.16 * scale, 0.225 * scale, -0.07 * y, -0.005 * y
        rows = []
        for i in range(steps + 1):
            a = a0 + (a1 - a0) * i / steps
            c, s_ = math.cos(a), math.sin(a)
            rows.append([cb.verts.new((r * c, dd, r * s_)) for r in (r0, r1) for dd in (d0, d1)])
        for ra, rb in zip(rows, rows[1:]):
            for i0, i1 in ((0, 1), (1, 3), (3, 2), (2, 0)):
                cb.faces.new((ra[i0], ra[i1], rb[i1], rb[i0]))
        cb.faces.new((rows[0][0], rows[0][2], rows[0][3], rows[0][1])); cb.faces.new((rows[-1][0], rows[-1][1], rows[-1][3], rows[-1][2]))
        bmesh.ops.recalc_face_normals(cb, faces=cb.faces)
        cme = bpy.data.meshes.new(f'{cid}_caliper_{name[-2:]}'); cb.to_mesh(cme); cb.free()
        cme.materials.append(mats['Caliper'])
        cal = bpy.data.objects.new(f'caliper_{name[-2:]}', cme)
        cal.location = ob.location
        coll.objects.link(cal)
    bpy.data.meshes.remove(face)
    return out


# ---------------------------------------------------------------- details
def build_details(cid, S, coll, mats, body):
    deps = bpy.context.evaluated_depsgraph_get()
    ev = body.evaluated_get(deps)
    def hit(o, d):
        ok, loc, nor, _ = ev.ray_cast(Vector(o), Vector(d).normalized())
        return (loc, nor) if ok else None
    def along(fn, n):
        return [h for h in (fn(i / (n - 1)) for i in range(n)) if h]
    def new_obj(name, bm, ms):
        me = bpy.data.meshes.new(f'{cid}_{name}'); bm.to_mesh(me); bm.free()
        for m in (ms if isinstance(ms, (list, tuple)) else [ms]): me.materials.append(mats[m])
        for p in me.polygons: p.use_smooth = True
        ob = bpy.data.objects.new(f'{cid}_{name}', me); coll.objects.link(ob); return ob
    def smooth(seq, k):
        out = []
        for i in range(len(seq)):
            lo, hi = max(0, i - k), min(len(seq), i + k + 1)
            acc = Vector((0, 0, 0))
            for v in seq[lo:hi]: acc += v
            out.append(acc / (hi - lo))
        return out
    def ribbon(name, samples, width, mat, lift=0.008, taper=None, solid=0.0):
        if len(samples) < 3: return None
        pts = smooth([p for p, _ in samples], 2)
        nors = [n.normalized() for n in smooth([n for _, n in samples], 4)]
        bm = bmesh.new(); rows = []
        for i, (p, n) in enumerate(zip(pts, nors)):
            t = (pts[min(len(pts) - 1, i + 1)] - pts[max(0, i - 1)]).normalized()
            side = n.cross(t).normalized()
            k = taper(i / max(1, len(pts) - 1)) if taper else 1.0
            base = p + n * lift * 1.35
            rows.append((bm.verts.new(base + side * width * k / 2), bm.verts.new(base - side * width * k / 2)))
        for (a0, a1), (b0, b1) in zip(rows, rows[1:]):
            bm.faces.new((a0, b0, b1, a1))
        ob = new_obj(name, bm, mat)
        if solid:
            s = ob.modifiers.new('Thickness', 'SOLIDIFY'); s.thickness = solid
        return ob
    soft = lambda u: 0.35 + 0.65 * math.sin(math.pi * u) ** 0.5

    def round_lamp(T, h, mk):
        # A round lamp: dark housing, glowing ring, polished projector
        if not h: return
        p, n = h
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=36, radius1=0.105, radius2=0.098, depth=0.05)
        rot = Vector((0, 0, 1)).rotation_difference(n).to_matrix()
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=rot)
        bmesh.ops.translate(bm, verts=bm.verts, vec=p + n * 0.012)
        mk('LampRound_' + T, bm, 'LampHousing')
        bm = bmesh.new()
        MAJ, MIN, NU, NV = 0.078, 0.009, 36, 6
        g = [[bm.verts.new(((MAJ + MIN * math.cos(b)) * math.cos(a), (MAJ + MIN * math.cos(b)) * math.sin(a), MIN * math.sin(b)))
              for b in (k * math.tau / NV for k in range(NV))] for a in (i * math.tau / NU for i in range(NU))]
        for i in range(NU):
            for k in range(NV):
                bm.faces.new((g[i][k], g[(i + 1) % NU][k], g[(i + 1) % NU][(k + 1) % NV], g[i][(k + 1) % NV]))
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=rot)
        bmesh.ops.translate(bm, verts=bm.verts, vec=p + n * 0.04)
        mk('LampRing_' + T, bm, 'HeadLamp')
        bm = bmesh.new()
        bmesh.ops.create_cone(bm, cap_ends=True, segments=24, radius1=0.032, radius2=0.03, depth=0.02)
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=rot)
        bmesh.ops.translate(bm, verts=bm.verts, vec=p + n * 0.042)
        mk('LampLens_' + T, bm, 'RimFace')
    front, rear = max(S['ztop']) + 3, min(S['ztop']) - 3
    L = S['lamp']
    for s in (1, -1):
        T = 'L' if s > 0 else 'R'
        path = lambda u, dz=0.0: hit((front, s * (L['y0'] + (L['y1'] - L['y0']) * u), L['z0'] + L['rise'] * u ** 1.3 + dz), (-1, 0, 0))
        style = L.get('style', 'blade')
        if style == 'round':
            round_lamp(T, path(0.5, 0.02), new_obj)
        else:
            ribbon('LampHousing_' + T, along(lambda u: path(u), 40), L['width'], 'LampHousing', 0.006, soft)
            ribbon('LampDRL_' + T, along(lambda u: path(0.04 + 0.92 * u, L['drl'] * 0.9), 40), 0.011, 'HeadLamp', 0.012,
                   lambda u: 0.4 + 0.6 * math.sin(math.pi * u) ** 0.3)
        if style == 'hook':
            # the light line turns down at the outer corner
            ribbon('LampHook_' + T, along(lambda u: hit((front, s * (L['y1'] - 0.035), L['z0'] + L['rise'] + L['drl'] * 0.9 - 0.15 * u), (-1, 0, 0)), 16), 0.011, 'HeadLamp', 0.012)
        if style == 'twotier' and 'lower_lamp' in S:
            ribbon('LampLink_' + T, along(lambda u: hit((front, s * (L['y1'] - 0.03), L['z0'] - (L['z0'] - S['lower_lamp']['z']) * u), (-1, 0, 0)), 20), 0.01, 'HeadLamp', 0.011)
        if 'lower_lamp' in S:
            ll = S['lower_lamp']
            ribbon('LampLow_' + T, along(lambda u: hit((front, s * (ll['y0'] + (ll['y1'] - ll['y0']) * u), ll['z']), (-1, 0, 0)), 20), 0.05, 'LampHousing', 0.006, soft)
            ribbon('LampLowDRL_' + T, along(lambda u: hit((front, s * (ll['y0'] + 0.02 + (ll['y1'] - ll['y0'] - 0.04) * u), ll['z']), (-1, 0, 0)), 20), 0.01, 'HeadLamp', 0.011)
        for k, u in enumerate((0.38, 0.64) if S.get('projectors') else ()):
            h = path(u, -0.004)
            if not h: continue
            p, n = h
            bm = bmesh.new()
            bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.022, radius2=0.02, depth=0.016)
            lens = bmesh.ops.create_cone(bm, cap_ends=True, segments=20, radius1=0.014, radius2=0.014, depth=0.018)
            for f in {f for v in lens['verts'] for f in v.link_faces}: f.material_index = 1
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(n).to_matrix())
            bmesh.ops.translate(bm, verts=bm.verts, vec=p + n * 0.01)
            new_obj(f'Projector_{T}{k}', bm, ['RimFace', 'HeadLamp'])
        ribbon('IntakeCorner_' + T, along(lambda u: hit((front, s * 0.70, S['intake_z'] - 0.06 + 0.2 * u), (-1, 0, 0)), 16), 0.07, 'Trim', 0.006, soft)
        sc = S.get('scoop')
        if sc:
            ribbon('Scoop_' + T, along(lambda u: hit((sc['x0'] + (sc['x1'] - sc['x0']) * u, s * 3, sc['z0'] + (sc['z1'] - sc['z0']) * u), (0, -s, 0)), 24),
                   sc['width'], 'Trim', 0.006, lambda u: 0.3 + 0.7 * math.sin(math.pi * u * 0.9 + 0.1))
        zb0 = pchip(S['zb'])(0.0)
        for j, (xa, xb) in enumerate(S['shuts']):
            for xx in (xa, xb):
                ribbon(f'Shut{j}_{T}_{xx:+.2f}', along(lambda u: hit((xx - 0.05 * u, s * 3, zb0 + 0.14 + (pchip(S['zsh'])(xx) - zb0 - 0.17) * u), (0, -s, 0)), 24), 0.005, 'Trim', 0.003)
        # Mirror: a flattened wing on a short blade stalk
        mx, mz = S['mirror']
        root = hit((mx, s * 3, mz), (0, -s, 0))
        if root:
            rp, rn = root
            head_c = rp + Vector((-0.06, s * 0.085, 0.07))
            bm = bmesh.new()
            bmesh.ops.create_uvsphere(bm, u_segments=24, v_segments=12, radius=1.0)
            for v in bm.verts:
                v.co.x *= 0.11; v.co.y *= 0.085; v.co.z *= 0.05
                if v.co.x < 0: v.co.x *= 0.35
                v.co.x += 0.02 * (v.co.y * s) / 0.085
                v.co += head_c
            bm.normal_update()
            for f in bm.faces: f.material_index = 1 if f.normal.x < -0.7 else 0
            hd = new_obj('Mirror_' + T, bm, ['Paint', 'LampHousing'])
            a, b = rp - rn * 0.005, head_c + Vector((0.01, -s * 0.03, -0.022))
            d = b - a
            bm = bmesh.new()
            bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x *= 0.06; v.co.y *= 0.016; v.co.z *= d.length
            bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Vector((0, 0, 1)).rotation_difference(d.normalized()).to_matrix())
            bmesh.ops.translate(bm, verts=bm.verts, vec=(a + b) / 2)
            st = new_obj('MirrorStalk_' + T, bm, 'Paint')
            bev = st.modifiers.new('Bevel', 'BEVEL'); bev.width = 0.004; bev.segments = 2
    zsh_f, ztop_f = pchip(S['zsh']), pchip(S['ztop'])
    for xp in S.get('pillars', ()):
        for s in (1, -1):
            ribbon(f'Pillar_{s}_{xp:+.2f}', along(lambda u: hit((xp, s * 3, zsh_f(xp) + 0.02 + (ztop_f(xp) - zsh_f(xp) - 0.07) * u), (0, -s, 0)), 16),
                   0.075, 'Paint', 0.004)
    # Front: lower intake, optional splitter and a full-width light line
    ribbon('Intake', along(lambda u: hit((front, -0.56 + 1.12 * u, S['intake_z'] + 0.03), (-1, 0, 0)), 64), 0.11, 'Trim', 0.008, soft)
    if S.get('front_bar'):
        ribbon('FrontLightBar', along(lambda u: hit((front, -0.40 + 0.80 * u, L['z0'] + L['drl'] * 0.9), (-1, 0, 0)), 64), 0.008, 'HeadLamp', 0.012)
    if S.get('splitter'):
        lip = along(lambda u: hit((front, -0.9 + 1.8 * u, pchip(S['zb'])(max(S['ztop']) - 0.15) + 0.05), (-1, 0, 0)), 48)
        bm = bmesh.new(); top, bot = [], []
        for p, n in lip:
            flat = Vector((n.x, n.y, 0)).normalized()
            top.append(bm.verts.new(p + flat * 0.05 + Vector((0, 0, -0.035))))
            bot.append(bm.verts.new(p - flat * 0.28 + Vector((0, 0, -0.035))))
        for i in range(len(top) - 1):
            bm.faces.new((top[i], top[i + 1], bot[i + 1], bot[i]))
        sp = new_obj('Splitter', bm, 'Trim')
        sol = sp.modifiers.new('Thickness', 'SOLIDIFY'); sol.thickness = 0.018
    # Rear: housing, light bar (brake), centre brake strip, reverse lamps, diffuser
    tl = S['tail']
    arch_c = lambda y: 0.014 * (1 - min(1.0, (y / 0.75) ** 2))
    ribbon('TailHousing', along(lambda u: hit((rear, -tl['y'] + 2 * tl['y'] * u, tl['z'] + arch_c(-tl['y'] + 2 * tl['y'] * u)), (1, 0, 0)), 128),
           tl['width'], 'LampHousing', 0.012, lambda u: 0.45 + 0.55 * math.sin(math.pi * u) ** 0.25)
    ts = S.get('tail_style', 'bar')
    if ts == 'split':
        for s in (1, -1):
            ribbon(f'TailBar_{s}', along(lambda u: hit((rear, s * (0.12 + (tl['y'] - 0.14) * u), tl['z'] + 0.02 + 0.03 * u), (1, 0, 0)), 48),
                   0.018, 'BrakeLamp', 0.018, lambda u: 0.5 + 0.5 * math.sin(math.pi * u) ** 0.2)
    else:
        for k, dz in enumerate((0.0, -0.045) if ts == 'double' else (0.0,)):
            ribbon(f'TailBar{k}', along(lambda u: hit((rear, -(tl['y'] - 0.02) + 2 * (tl['y'] - 0.02) * u, tl['z'] + 0.02 + dz + arch_c(-(tl['y'] - 0.02) + 2 * (tl['y'] - 0.02) * u)), (1, 0, 0)), 128),
                   0.015, 'BrakeLamp', 0.018, lambda u: 0.5 + 0.5 * math.sin(math.pi * u) ** 0.2)
    gx = min(S['glass']) if S.get('glass') else min(S['ztop']) + 0.45
    cz = pchip(S['ztop'])(gx + 0.03)
    ribbon('CenterBrake', along(lambda u: hit((gx - 0.02, -0.22 + 0.44 * u, cz + 0.6), (0, 0, -1)), 24), 0.012, 'CenterBrakeLamp', 0.01)
    for s in (1, -1):
        ribbon('Reverse_' + ('L' if s > 0 else 'R'), along(lambda u: hit((rear, s * (0.30 + 0.12 * u), S['diffuser_z'] + 0.13), (1, 0, 0)), 12), 0.02, 'ReverseLamp', 0.016)
    ribbon('Diffuser', along(lambda u: hit((rear, -0.56 + 1.12 * u, S['diffuser_z']), (1, 0, 0)), 120), 0.16, 'Trim', 0.014,
           lambda u: 0.55 + 0.45 * math.sin(math.pi * u) ** 0.35)
    for k in range(S.get('fins', 0)):
        y = -0.42 + 0.84 * k / max(1, S['fins'] - 1)
        h = hit((rear, y, S['diffuser_z'] - 0.08), (1, 0, 0))
        if not h: continue
        p, n = h
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.26; v.co.y *= 0.01; v.co.z *= 0.085
        bmesh.ops.rotate(bm, verts=bm.verts, cent=(0, 0, 0), matrix=Matrix.Rotation(math.radians(-10), 3, 'Y'))
        bmesh.ops.translate(bm, verts=bm.verts, vec=p + Vector((0.13, 0, -0.06)))
        new_obj(f'Fin_{k}', bm, 'Trim')
    # Extras per car
    if S.get('vents'):
        for s in (1, -1):
            for j in range(3):
                xv = max(S['ztop']) - 0.75 - 0.09 * j
                ribbon(f'Vent_{s}_{j}', along(lambda u: hit((xv - 0.02 * u, s * (0.22 + 0.20 * u), 3), (0, 0, -1)), 16), 0.022, 'Trim', 0.004)
    if S.get('stripe'):
        for s in (1, -1):
            ribbon(f'Stripe_{s}', along(lambda u: hit((min(S['ztop']) + 0.05 + (max(S['ztop']) - min(S['ztop']) - 0.1) * u, s * 0.13, 3), (0, 0, -1)), 160), 0.07, 'Accent', 0.004)
    if S.get('rails'):
        for s in (1, -1):
            r = ribbon(f'Rail_{s}', along(lambda u: hit((-1.40 + 1.90 * u, s * 0.56, 3), (0, 0, -1)), 40), 0.035, 'Trim', 0.03, solid=0.025)
    if S.get('wing'):
        deck_x = min(S['ztop']) + 0.30
        dz = pchip(S['ztop'])(deck_x)
        bm = bmesh.new()
        chord, span, z = 0.30, 1.64, dz + 0.30
        prof = [(0, 0), (0.06, 0.022), (0.16, 0.026), (0.30, 0.008), (0.16, -0.004), (0.06, -0.006)]
        rows = []
        for y in (-span / 2, span / 2):
            rows.append([bm.verts.new((deck_x - 0.06 - px, y, z + pz)) for (px, pz) in prof])
        n = len(prof)
        for i in range(n):
            j = (i + 1) % n
            bm.faces.new((rows[0][i], rows[0][j], rows[1][j], rows[1][i]))
        bm.faces.new(list(reversed(rows[0]))); bm.faces.new(rows[1])
        new_obj('Wing', bm, 'Trim')
        for s in (1, -1):
            for yy in (s * 0.42,):
                base = hit((deck_x - 0.12, yy, 3), (0, 0, -1))
                if not base: continue
                p, _ = base
                bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
                hgt = z - p.z
                for v in bm.verts:
                    v.co.x *= 0.12; v.co.y *= 0.014; v.co.z *= hgt
                bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((p.x - 0.02, yy, p.z + hgt / 2)))
                new_obj(f'WingPost_{s}', bm, 'Trim')
        for s in (1, -1):
            bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
            for v in bm.verts:
                v.co.x *= 0.36; v.co.y *= 0.008; v.co.z *= 0.12
            bmesh.ops.translate(bm, verts=bm.verts, vec=Vector((deck_x - 0.17, s * span / 2, z + 0.02)))
            new_obj(f'WingEnd_{s}', bm, 'Trim')


# ---------------------------------------------------------------- interior
def build_interior(cid, S, coll, mats):
    """Low-poly cabin seen through the smoked glass: seats, dash and a steering wheel."""
    zb0 = pchip(S['zb'])(0.0)
    zsh = pchip(S['zsh'])
    sx = S['seat_x']
    def block(name, size, loc, mat='Interior', bevel=0.02):
        bm = bmesh.new(); bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= size[0]; v.co.y *= size[1]; v.co.z *= size[2]
        bmesh.ops.translate(bm, verts=bm.verts, vec=Vector(loc))
        me = bpy.data.meshes.new(f'{cid}_{name}'); bm.to_mesh(me); bm.free()
        me.materials.append(mats[mat])
        ob = bpy.data.objects.new(f'{cid}_{name}', me); coll.objects.link(ob)
        b = ob.modifiers.new('Bevel', 'BEVEL'); b.width = bevel; b.segments = 2
        return ob
    floor = zb0 + 0.12
    for row, x in ((0, sx),) + (((1, sx - 0.85),) if S.get('rear_seats') else ()):
        for s in (1, -1):
            block(f'SeatBase_{row}_{s}', (0.46, 0.44, 0.12), (x, s * 0.36, floor + 0.12))
            block(f'SeatBack_{row}_{s}', (0.12, 0.42, 0.52), (x - 0.24, s * 0.36, floor + 0.42), bevel=0.04)
    dash_x = (S['glass'][1] if S.get('glass') else S['cabrio']['x1']) - 0.18
    dash_z = zsh(dash_x) - 0.05
    block('Dash', (0.30, 1.30, 0.14), (dash_x - 0.05, 0, dash_z), bevel=0.04)
    # Steering wheel: a thin torus in the y-z plane (the rig turns it about x)
    bm = bmesh.new()
    MAJ, MIN, NU, NV = 0.17, 0.016, 32, 8
    grid = [[bm.verts.new((MIN * math.sin(b), (MAJ + MIN * math.cos(b)) * math.cos(a), (MAJ + MIN * math.cos(b)) * math.sin(a)))
             for b in (j * math.tau / NV for j in range(NV))] for a in (i * math.tau / NU for i in range(NU))]
    for i in range(NU):
        for j in range(NV):
            bm.faces.new((grid[i][j], grid[(i + 1) % NU][j], grid[(i + 1) % NU][(j + 1) % NV], grid[i][(j + 1) % NV]))
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    me = bpy.data.meshes.new(f'{cid}_steering'); bm.to_mesh(me); bm.free()
    me.materials.append(mats['Interior'])
    for p in me.polygons: p.use_smooth = True
    ring_ob = bpy.data.objects.new('steering_wheel', me)
    ring_ob.location = (dash_x - 0.30, 0.36, dash_z - 0.02)
    ring_ob.rotation_euler = (0, math.radians(-22), 0)
    coll.objects.link(ring_ob)


# ---------------------------------------------------------------- orchestration
def build(cid):
    S = SPECS[cid]
    name = f'Fleet_{cid}'
    old = bpy.data.collections.get(name)
    if old:
        for o in list(old.objects): bpy.data.objects.remove(o, do_unlink=True)
        bpy.data.collections.remove(old)
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    mats = dict(shared_materials())
    mats['Paint'] = material(f'Paint {S["name"]}', S.get('paint_linear', S['paint']), S.get('paint_metal', 0.05), S.get('paint_rough', 0.16), 1.0)
    body, cutter = build_body(cid, S, coll, mats)
    build_wheels(cid, S, coll, mats)
    bpy.context.view_layer.update()
    build_details(cid, S, coll, mats, body)
    build_interior(cid, S, coll, mats)
    if S.get('cabrio'): build_cabrio(cid, S, coll, mats)
    return coll


def build_all(ids=None):
    for cid in ids or SPECS:
        build(cid)


def show_only(cid):
    for c in bpy.data.collections:
        if c.name.startswith('Fleet_') or c.name in ('VertigoGT', 'Traffic'):
            vis = c.name == f'Fleet_{cid}'
            c.hide_render = not vis
            c.hide_viewport = not vis


def export(cid, path):
    show_only(cid)
    coll = bpy.data.collections[f'Fleet_{cid}']
    bpy.ops.object.select_all(action='DESELECT')
    for o in coll.objects:
        if 'Cutter' in o.name: continue
        o.select_set(True)
    bpy.context.view_layer.objects.active = next(o for o in coll.objects if o.name.endswith('_Body'))
    bpy.ops.export_scene.gltf(filepath=path, use_selection=True, export_apply=True, export_yup=True,
                              export_draco_mesh_compression_enable=True, export_draco_mesh_compression_level=6,
                              export_draco_position_quantization=14, export_draco_normal_quantization=10,
                              export_cameras=False, export_lights=False)


def look(cam, loc, target):
    cam.location = loc
    cam.rotation_euler = (Vector(target) - Vector(loc)).to_track_quat('-Z', 'Y').to_euler()


VIEWS = {
    'front': ((7.2, -5.4, 2.3), (0.15, 0, 0.55)),
    'side': ((0.0, -9.2, 1.0), (0, 0, 0.62)),
    'rear': ((-6.8, -4.9, 2.4), (0, 0, 0.6)),
}


def render(cid, folder, views=('front', 'side', 'rear'), pct=55, suffix=''):
    show_only(cid)
    sc = bpy.context.scene
    sc.render.resolution_percentage = pct
    cam = bpy.data.objects['Camera']
    cam.data.lens = 50
    files = []
    for v in views:
        look(cam, *VIEWS[v])
        sc.render.filepath = f'{folder}/{cid}_{v}{suffix}.png'
        bpy.ops.render.render(write_still=True)
        files.append(sc.render.filepath)
    return files
