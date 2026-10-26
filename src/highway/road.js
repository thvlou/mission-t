// An endless highway centreline, infinite in both directions, laid out piece by piece: straights,
// long sweepers, tight corners, S-bends and interchanges. Curvature blends between pieces so every
// bend eases in. Each direction away from s = 0 has its own plan, and the heading is kept within
// ±75° of the start, so the road always runs onward and never crosses itself. Samples are kept in
// world space for a window around the car; the rest is regenerated on demand, and the whole thing
// can be shifted back toward the origin to keep float precision on the GPU.

export const STEP = 2;          // m between centreline samples
const HILL = 11;                // height amplitude, m (grades up to ~8%: climbs and descents you feel)
const H_MAX = 1.3;              // rad, furthest the road may wander from its starting heading
export const INTERCHANGE = 460; // half-length of an interchange: straight, ramps and an overpass

// Cross-section, measured along the road's right-hand normal (positive = driver's right).
export const LAYOUT = {
  lane: 3.7,
  fwdLanes: [-3.7, 0, 3.7],
  oncLanes: [-10.9, -14.6, -18.3],
  roadL: -6.6, roadR: 8.6,      // our carriageway incl. shoulders
  oncL: -23.2, oncR: -8.0,      // oncoming carriageway
  median: -7.3,
  guardR: 9.1, guardL: -23.7,
  driveMin: -5.55, driveMax: 7.55,
};

export function rng(seed) {
  let s = (seed >>> 0) || 1;
  return () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296;
}

function wave(rand, periods, weights) {
  const terms = periods.map((p, i) => ({ f: (2 * Math.PI) / (p * (0.75 + 0.5 * rand())), ph: rand() * Math.PI * 2, a: weights[i] }));
  const norm = terms.reduce((t, w) => t + w.a, 0);
  return (x) => terms.reduce((t, w) => t + w.a * Math.sin(x * w.f + w.ph), 0) / norm;
}

const ease = (s, a, b) => {
  const t = Math.min(1, Math.max(0, (s - a) / (b - a)));
  return t * t * (3 - 2 * t);
};
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// One direction's plan: pieces of constant curvature { start, len, k, kind } along u ≥ 0.
class Layout {
  constructor(rand, wiggle) {
    this.rand = rand;
    this.wiggle = wiggle;
    this.pieces = [{ start: 0, len: 700, k: 0, kind: 'straight' }];
    this.interchanges = [];
    this.planEnd = 700;
    this.planH = 0;
    this.lastInterchange = -1200;
    this.lastKind = 'straight';
    this.cursor = 0;
  }

  add(len, k, kind) {
    const start = this.planEnd;
    this.pieces.push({ start, len, k, kind });
    this.planEnd += len;
    for (let u = start; u < this.planEnd; u += STEP) {
      const du = Math.min(STEP, this.planEnd - u);
      this.planH += this.curvature(u + du / 2) * du;
    }
  }

  // Choose the next stretch of road.
  plan() {
    const r = this.rand;
    const sinceIc = this.planEnd - this.lastInterchange;
    // Turn back toward the original heading when the road has wandered.
    const pick = () => (Math.abs(this.planH) > 0.45 ? -Math.sign(this.planH) : r() < 0.5 ? -1 : 1);
    const fit = (dir, angle) => Math.max(0.15, Math.min(angle, H_MAX - dir * this.planH));
    const corner = (radius, angle, kind) => {
      const dir = pick();
      this.add(Math.max(120, fit(dir, angle) * radius), dir / radius, kind);
    };
    if (sinceIc > 2400 && this.lastKind !== 'corner' && r() < 0.55) {
      // Interchange: dead straight so the ramps and the bridge line up.
      const start = this.planEnd;
      this.add(INTERCHANGE * 2, 0, 'interchange');
      this.interchanges.push(start + INTERCHANGE);
      this.lastInterchange = start + INTERCHANGE;
      this.lastKind = 'interchange';
      return;
    }
    const roll = r();
    if (this.lastKind !== 'straight' && roll < 0.35) {
      this.add(250 + r() * 450, 0, 'straight');
      this.lastKind = 'straight';
    } else if (roll < 0.6) {
      corner(560 + r() * 420, 0.3 + r() * 0.35, 'sweeper');
      this.lastKind = 'sweeper';
    } else if (roll < 0.85) {
      corner(230 + r() * 150, 0.7 + r() * 0.5, 'corner');
      this.add(120 + r() * 160, 0, 'straight');
      this.lastKind = 'corner';
    } else {
      // S-bend: two quick opposite corners.
      const radius = 260 + r() * 140, a = 0.45 + r() * 0.3;
      const dir = pick();
      this.add(fit(dir, a) * radius, dir / radius, 'corner');
      this.add(40 + r() * 60, 0, 'straight');
      this.add(Math.max(0.15, Math.min(a, H_MAX + dir * this.planH)) * radius, -dir / radius, 'corner');
      this.add(150 + r() * 150, 0, 'straight');
      this.lastKind = 'corner';
    }
  }

  piece(u) {
    while (this.planEnd <= u) this.plan();
    let i = Math.min(this.cursor, this.pieces.length - 1);
    while (i > 0 && this.pieces[i].start > u) i--;
    while (i < this.pieces.length - 1 && this.pieces[i + 1].start <= u) i++;
    this.cursor = i;
    return i;
  }

  // Curvature along u; each piece eases in from the one before.
  curvature(u) {
    const i = this.piece(u);
    const p = this.pieces[i];
    const own = (q) => q.k + (q.kind === 'straight' || q.kind === 'sweeper' ? this.wiggle(u) / 4000 : 0);
    const k = own(p);
    if (i === 0) return k;
    const ramp = Math.min(110, p.len * 0.45);
    const t = (u - p.start) / ramp;
    if (t >= 1) return k;
    const prev = own(this.pieces[i - 1]);
    return prev + (k - prev) * t * t * (3 - 2 * t);
  }
}

export class Road {
  constructor(seed) {
    const rand = rng(seed);
    const wiggle = wave(rand, [1400, 600], [1, 0.4]);
    this.hill = wave(rand, [1600, 700, 330], [1, 0.5, 0.2]);
    // Driving toward +s follows `ahead`; toward −s follows `behind` (u = −s). Going backward from
    // s = 0 the heading is minus behind's own heading, so it stays in range the same way.
    this.ahead = new Layout(rand, wiggle);
    this.behind = new Layout(rng(seed ^ 0x5bd1e995), wave(rng(seed + 7), [1400, 600], [1, 0.4]));
    this.s0 = 0;
    this.x = [0];
    this.z = [0];
    this.h = [0];
    this.y = [this.height(0)];
  }

  // Curvature (1/m, positive = left) at arc length s.
  curvature(s) {
    return s >= 0 ? this.ahead.curvature(s) : this.behind.curvature(-s);
  }

  kindAt(s) {
    const L = s >= 0 ? this.ahead : this.behind;
    return L.pieces[L.piece(Math.abs(s))].kind;
  }

  // Interchange centres between a and b.
  interchangesIn(a, b) {
    const out = [];
    if (b > -INTERCHANGE) {
      this.ahead.piece(Math.max(0, b) + INTERCHANGE);
      out.push(...this.ahead.interchanges);
    }
    if (a < INTERCHANGE) {
      this.behind.piece(Math.max(0, -a) + INTERCHANGE);
      out.push(...this.behind.interchanges.map((c) => -c));
    }
    return out.filter((c) => c + INTERCHANGE > a && c - INTERCHANGE < b);
  }

  height(s) {
    return HILL * this.hill(s) * ease(Math.abs(s), 100, 600);
  }

  get sEnd() {
    return this.s0 + (this.x.length - 1) * STEP;
  }

  // Make sure samples exist out to s, in either direction.
  ensure(s) {
    while (this.sEnd < s) this.extend();
    if (s < this.s0) this.extendBack(s);
  }

  extend() {
    const i = this.x.length - 1;
    const s = this.sEnd;
    const k = this.curvature(s + STEP / 2);
    const h = this.h[i] + k * STEP;
    const hm = (this.h[i] + h) / 2;
    this.x.push(this.x[i] + Math.cos(hm) * STEP);
    this.z.push(this.z[i] - Math.sin(hm) * STEP);
    this.h.push(h);
    this.y.push(this.height(s + STEP));
  }

  // Grow the sample window backward (toward −s) past s, a batch at a time.
  extendBack(s) {
    const n = Math.max(32, Math.ceil((this.s0 - s) / STEP));
    const xs = [], zs = [], hs = [], ys = [];
    let x = this.x[0], z = this.z[0], h = this.h[0], sc = this.s0;
    for (let k = 0; k < n; k++) {
      const hp = h - this.curvature(sc - STEP / 2) * STEP;
      const hm = (h + hp) / 2;
      x -= Math.cos(hm) * STEP;
      z += Math.sin(hm) * STEP;
      h = hp;
      sc -= STEP;
      xs.push(x); zs.push(z); hs.push(h); ys.push(this.height(sc));
    }
    this.x = xs.reverse().concat(this.x);
    this.z = zs.reverse().concat(this.z);
    this.h = hs.reverse().concat(this.h);
    this.y = ys.reverse().concat(this.y);
    this.s0 = sc;
  }

  // Keep only the samples between lo and hi so memory stays bounded; the layout plan is kept, so
  // anything dropped regenerates identically when the car comes back.
  trim(lo, hi) {
    const n = Math.floor((lo - this.s0) / STEP) - 4;
    if (n > 0 && n < this.x.length - 8) {
      for (const arr of [this.x, this.z, this.h, this.y]) arr.splice(0, n);
      this.s0 += n * STEP;
    }
    const m = Math.floor((this.sEnd - hi) / STEP) - 4;
    if (m > 0 && m < this.x.length - 8) {
      for (const arr of [this.x, this.z, this.h, this.y]) arr.length -= m;
    }
  }

  // Road frame at arc length s: position, heading, slope, forward and right vectors.
  frame(s, out = {}) {
    this.ensure(s + STEP);
    this.ensure(s - STEP);
    const f = Math.max(0, (s - this.s0) / STEP);
    const i = Math.min(this.x.length - 2, Math.floor(f));
    const t = f - i;
    out.x = this.x[i] + (this.x[i + 1] - this.x[i]) * t;
    out.z = this.z[i] + (this.z[i + 1] - this.z[i]) * t;
    out.y = this.y[i] + (this.y[i + 1] - this.y[i]) * t;
    out.h = this.h[i] + (this.h[i + 1] - this.h[i]) * t;
    out.slope = (this.y[i + 1] - this.y[i]) / STEP;
    out.fx = Math.cos(out.h);
    out.fz = -Math.sin(out.h);
    out.rx = Math.sin(out.h);
    out.rz = Math.cos(out.h);
    return out;
  }

  // World (x, z) → road coordinates (s along, d across), searching near a hint.
  project(px, pz, sHint) {
    this.ensure(sHint + 70);
    this.ensure(sHint - 70);
    const last = this.x.length - 2;
    const i0 = clamp(Math.round((sHint - this.s0) / STEP), 0, last);
    let bestJ = i0, bestT = 0, bestD = Infinity, qx = 0, qz = 0;
    for (let j = Math.max(0, i0 - 30); j <= Math.min(last, i0 + 30); j++) {
      const ax = this.x[j], az = this.z[j];
      const ex = this.x[j + 1] - ax, ez = this.z[j + 1] - az;
      const t = clamp(((px - ax) * ex + (pz - az) * ez) / (ex * ex + ez * ez), 0, 1);
      const cx = ax + ex * t, cz = az + ez * t;
      const dd = (px - cx) ** 2 + (pz - cz) ** 2;
      if (dd < bestD) { bestD = dd; bestJ = j; bestT = t; qx = cx; qz = cz; }
    }
    const h = this.h[bestJ] + (this.h[bestJ + 1] - this.h[bestJ]) * bestT;
    return { s: this.s0 + (bestJ + bestT) * STEP, d: (px - qx) * Math.sin(h) + (pz - qz) * Math.cos(h), h };
  }

  rebase(dx, dz) {
    for (let i = 0; i < this.x.length; i++) {
      this.x[i] -= dx;
      this.z[i] -= dz;
    }
  }
}
