// A 2D path in the side plane, stored as a dense table of samples.
// Each sample has arc length s, position (x, y), heading a and signed curvature k.
export class Track {
  constructor(pieces, origin = [0, 0], step = 0.1) {
    this.s = [];
    this.x = [];
    this.y = [];
    this.a = [];
    this.k = [];
    let x = origin[0], y = origin[1], a = 0, s = 0;
    const push = (k) => {
      this.s.push(s); this.x.push(x); this.y.push(y); this.a.push(a); this.k.push(k);
    };
    push(0);
    this.breaks = [];
    for (const piece of pieces) {
      const isArc = piece.arc !== undefined;
      const len = isArc ? piece.arc * Math.abs(piece.turn) * Math.PI / 180 : piece.line;
      const k = isArc ? Math.sign(piece.turn) / piece.arc : 0;
      const n = Math.max(1, Math.ceil(len / step));
      const ds = len / n;
      for (let i = 0; i < n; i++) {
        if (k) {
          const a2 = a + k * ds;
          x += (Math.sin(a2) - Math.sin(a)) / k;
          y += (Math.cos(a) - Math.cos(a2)) / k;
          a = a2;
        } else {
          x += Math.cos(a) * ds;
          y += Math.sin(a) * ds;
        }
        s += ds;
        push(k);
      }
      this.breaks.push(s);
    }
    this.length = s;
    this.curveStart = this.breaks[0];
    this.top = Math.max(...this.y);
    this.x0 = origin[0];
  }

  index(s) {
    let lo = 0, hi = this.s.length - 1;
    if (s <= 0) return 0;
    if (s >= this.length) return hi - 1;
    while (hi - lo > 1) {
      const mid = (lo + hi) >> 1;
      if (this.s[mid] <= s) lo = mid; else hi = mid;
    }
    return lo;
  }

  at(s) {
    const c = Math.min(this.length, Math.max(0, s));
    const i = this.index(c);
    const span = this.s[i + 1] - this.s[i];
    const t = span > 0 ? (c - this.s[i]) / span : 0;
    return {
      x: this.x[i] + (this.x[i + 1] - this.x[i]) * t,
      y: this.y[i] + (this.y[i + 1] - this.y[i]) * t,
      a: this.a[i] + (this.a[i + 1] - this.a[i]) * t,
      k: this.k[i + 1],
    };
  }

  // Closest point on the path at or beyond minS. d is the signed distance along the
  // left-hand normal (positive on the riding side of the deck).
  closest(px, py, minS = 0) {
    const first = this.index(minS);
    const last = this.s.length - 2;
    let best = null, bestDist = Infinity;
    for (let i = first; i <= last; i++) {
      const ax = this.x[i], ay = this.y[i];
      const ex = this.x[i + 1] - ax, ey = this.y[i + 1] - ay;
      const len2 = ex * ex + ey * ey;
      let t = ((px - ax) * ex + (py - ay) * ey) / len2;
      const inside = !((i === first && t < 0) || (i === last && t > 1));
      t = Math.min(1, Math.max(0, t));
      const qx = ax + ex * t, qy = ay + ey * t;
      const dist = Math.hypot(px - qx, py - qy);
      if (dist < bestDist) {
        bestDist = dist;
        const a = this.a[i] + (this.a[i + 1] - this.a[i]) * t;
        const nx = -Math.sin(a), ny = Math.cos(a);
        best = { s: this.s[i] + (this.s[i + 1] - this.s[i]) * t, x: qx, y: qy, a, nx, ny, d: (px - qx) * nx + (py - qy) * ny, inside };
      }
    }
    return best;
  }
}
