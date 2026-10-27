// Pure course geometry shared by physics, multiplayer and offline track validation.
export const RUNOFF = 9;
const wrapA = a => Math.atan2(Math.sin(a), Math.cos(a));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

export class Circuit {
  constructor(data) {
    this.id = data.id;
    this.name = data.name;
    this.data = data;
    this.closed = true;
    const pts = data.points;
    const n = pts.length;
    // Centre the course on the origin so it never needs rebasing (it spans ~2–3 km).
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const [x, , z] of pts) { minX = Math.min(minX, x); maxX = Math.max(maxX, x); minZ = Math.min(minZ, z); maxZ = Math.max(maxZ, z); }
    const ox = (minX + maxX) / 2, oz = (minZ + maxZ) / 2;
    this.offset = { x: ox, z: oz };
    this.n = n;
    this.x = pts.map((p) => p[0] - ox);
    this.y = pts.map((p) => p[1]);
    this.z = pts.map((p) => p[2] - oz);
    this.wr = pts.map((p) => p[3]);
    this.wl = pts.map((p) => p[4]);
    this.cum = [0];
    for (let i = 1; i <= n; i++) {
      const a = i - 1, b = i % n;
      this.cum.push(this.cum[a] + Math.hypot(this.x[b] - this.x[a], this.z[b] - this.z[a]));
    }
    this.length = this.cum[n];
    // Heading and slope at each point, from its neighbours (smooth through the joins).
    this.h = []; this.sl = [];
    for (let i = 0; i < n; i++) {
      const a = (i - 1 + n) % n, b = (i + 1) % n;
      this.h.push(Math.atan2(-(this.z[b] - this.z[a]), this.x[b] - this.x[a]));
      const run = Math.hypot(this.x[b] - this.x[a], this.z[b] - this.z[a]);
      this.sl.push((this.y[b] - this.y[a]) / run);
    }
    this.cursor = 0;
    this.routes = (data.shortcuts || []).map(route => {
      const path = new Circuit({ id: route.id, name: route.name, points: route.points });
      // All branch coordinates share the main course's coordinate frame.
      const dx = path.offset.x - ox, dz = path.offset.z - oz;
      path.x = path.x.map(x => x + dx); path.z = path.z.map(z => z + dz);
      // Branches are open: exclude the synthetic final segment back to their entrance.
      path.length = path.cum[path.n - 1];
      path.h[0] = Math.atan2(-(path.z[1] - path.z[0]), path.x[1] - path.x[0]);
      path.h[path.n - 1] = Math.atan2(-(path.z.at(-1) - path.z.at(-2)), path.x.at(-1) - path.x.at(-2));
      return { ...route, path };
    });
  }

  // Point index and fraction for a (wrapped) distance.
  locate(s) {
    const u = ((s % this.length) + this.length) % this.length;
    let i = this.cursor;
    if (this.cum[i] > u || this.cum[i + 1] <= u) {
      let lo = 0, hi = this.n;
      while (hi - lo > 1) { const m = (lo + hi) >> 1; if (this.cum[m] <= u) lo = m; else hi = m; }
      i = lo;
    }
    this.cursor = i;
    return { i, j: (i + 1) % this.n, t: (u - this.cum[i]) / (this.cum[i + 1] - this.cum[i] || 1) };
  }

  frame(s, out = {}) {
    const { i, j, t } = this.locate(s);
    out.x = this.x[i] + (this.x[j] - this.x[i]) * t;
    out.y = this.y[i] + (this.y[j] - this.y[i]) * t;
    out.z = this.z[i] + (this.z[j] - this.z[i]) * t;
    out.h = this.h[i] + wrapA(this.h[j] - this.h[i]) * t;
    out.slope = this.sl[i] + (this.sl[j] - this.sl[i]) * t;
    out.fx = Math.cos(out.h);
    out.fz = -Math.sin(out.h);
    out.rx = Math.sin(out.h);
    out.rz = Math.cos(out.h);
    return out;
  }

  // Road edges and walls across the road at s (d is positive to the right).
  edges(s, routeId = null) {
    const route = this.routeAt(routeId);
    if (route) {
      const u = this.routeDistance(s, route), q = route.path.locateOpen(u);
      const wr = route.path.wr[q.i] + (route.path.wr[q.j] - route.path.wr[q.i]) * q.t;
      const wl = route.path.wl[q.i] + (route.path.wl[q.j] - route.path.wl[q.i]) * q.t;
      return { left: -wl, right: wr, wallL: -wl - 1, wallR: wr + 1 };
    }
    const { i, j, t } = this.locate(s);
    const wl = this.wl[i] + (this.wl[j] - this.wl[i]) * t, wr = this.wr[i] + (this.wr[j] - this.wr[i]) * t;
    return { left: -wl, right: wr, wallL: -wl - RUNOFF, wallR: wr + RUNOFF };
  }

  // World (x, z) → (s, d), searching near the hint; s comes back on the hint's lap.
  project(px, pz, sHint, routeId = null) {
    const { i: i0 } = this.locate(sHint);
    let best = Infinity, bi = i0, bt = 0, qx = 0, qz = 0;
    for (let k = -24; k <= 24; k++) {
      const i = (i0 + k + this.n) % this.n, j = (i + 1) % this.n;
      const ax = this.x[i], az = this.z[i], ex = this.x[j] - ax, ez = this.z[j] - az;
      const t = clamp(((px - ax) * ex + (pz - az) * ez) / (ex * ex + ez * ez || 1), 0, 1);
      const cx = ax + ex * t, cz = az + ez * t;
      const dd = (px - cx) ** 2 + (pz - cz) ** 2;
      if (dd < best) { best = dd; bi = i; bt = t; qx = cx; qz = cz; }
    }
    const local = this.cum[bi] + (this.cum[bi + 1] - this.cum[bi]) * bt;
    const lapBase = sHint - (((sHint % this.length) + this.length) % this.length);
    let s = lapBase + local;
    if (s - sHint > this.length / 2) s -= this.length;
    else if (sHint - s > this.length / 2) s += this.length;
    const h = this.h[bi] + wrapA(this.h[(bi + 1) % this.n] - this.h[bi]) * bt;
    let result = { s, d: (px - qx) * Math.sin(h) + (pz - qz) * Math.cos(h), h, route: null };
    let score = best;
    const lap = Math.floor(sHint / this.length), localHint = sHint - lap * this.length;
    for (const route of this.routes) {
      if (localHint < route.from - 35 || localHint > route.to + 35) continue;
      const p = route.path.projectOpen(px, pz);
      // A shortcut is entered at its fork, never by snapping to it from a nearby later corner.
      if (route.id !== routeId && (p.u > 75 || localHint > route.from + 90)) continue;
      const progress = route.from + p.u / route.path.length * (route.to - route.from);
      // At a merge the normal road wins; away from merges retain the active fork.
      const margin = route.id === routeId && p.u > 8 && p.u < route.path.length - 8 ? -1.5 : 1;
      if (p.dist2 + margin < score && Math.abs(p.d) < route.width / 2 + 7 && Math.abs(progress - localHint) < 150) {
        score = p.dist2 + margin;
        result = { s: lap * this.length + progress, d: p.d, h: p.h, route: route.id };
      }
    }
    return result;
  }

  locateOpen(u) {
    const x = clamp(u, 0, this.length - 1e-6);
    let lo = 0, hi = this.n - 1;
    while (hi - lo > 1) { const m = (lo + hi) >> 1; if (this.cum[m] <= x) lo = m; else hi = m; }
    return { i: lo, j: lo + 1, t: (x - this.cum[lo]) / (this.cum[lo + 1] - this.cum[lo]) };
  }

  projectOpen(px, pz) {
    let best = { dist2: Infinity };
    for (let i = 0; i < this.n - 1; i++) {
      const ex = this.x[i + 1] - this.x[i], ez = this.z[i + 1] - this.z[i];
      const t = clamp(((px - this.x[i]) * ex + (pz - this.z[i]) * ez) / (ex * ex + ez * ez), 0, 1);
      const x = this.x[i] + ex * t, z = this.z[i] + ez * t, dist2 = (px - x) ** 2 + (pz - z) ** 2;
      if (dist2 < best.dist2) {
        const h = this.h[i] + wrapA(this.h[i + 1] - this.h[i]) * t;
        best = { dist2, u: this.cum[i] + (this.cum[i + 1] - this.cum[i]) * t, d: (px - x) * Math.sin(h) + (pz - z) * Math.cos(h), h };
      }
    }
    return best;
  }

  routeAt(id) { return this.routes.find(r => r.id === id); }
  localS(s) { return ((s % this.length) + this.length) % this.length; }
  routeDistance(s, route) { return clamp((this.localS(s) - route.from) / (route.to - route.from), 0, 1) * route.path.length; }

  drivingFrame(s, routeId = null) {
    const route = this.routeAt(routeId);
    if (!route) return this.frame(s);
    const p = route.path, { i, j, t } = p.locateOpen(this.routeDistance(s, route));
    const h = p.h[i] + wrapA(p.h[j] - p.h[i]) * t;
    return { x: p.x[i] + (p.x[j] - p.x[i]) * t, y: p.y[i] + (p.y[j] - p.y[i]) * t, z: p.z[i] + (p.z[j] - p.z[i]) * t,
      h, slope: (p.y[j] - p.y[i]) / (p.cum[j] - p.cum[i]), fx: Math.cos(h), fz: -Math.sin(h), rx: Math.sin(h), rz: Math.cos(h) };
  }

  surfaceAt(s, d = 0, routeId = null) {
    const route = this.routeAt(routeId), u = route ? this.routeDistance(s, route) : this.localS(s);
    const gaps = route?.gaps || this.data.gaps || [], e = this.edges(s, routeId), f = this.drivingFrame(s, routeId);
    const gap = gaps.find(g => u >= g.from && u < g.to);
    return { exists: !gap && d >= e.wallL && d <= e.wallR, gap: !!gap, height: f.y, slope: f.slope };
  }

  safeRespawn(s, routeId) {
    const route = this.routeAt(routeId);
    const lapBase = s - this.localS(s);
    if (route) return lapBase + route.from - 55;
    const gap = (this.data.gaps || []).find(g => this.localS(s) >= g.from - 20 && this.localS(s) < g.to + 80);
    return gap ? lapBase + gap.from - 65 : s - 55;
  }

  curvature(s) {
    const a = this.frame(s - 10), b = this.frame(s + 10);
    return wrapA(b.h - a.h) / 20;
  }

  // One lap of centreline points for maps: { s, x, z, h }.
  outline(step = 8) {
    const out = [];
    for (let s = 0; s <= this.length; s += step) {
      const f = this.frame(s);
      out.push({ s, x: f.x, z: f.z, h: f.h });
    }
    return out;
  }

  height(s) { return this.frame(s).y; }
  kindAt() { return 'circuit'; }
  interchangesIn() { return []; }
  ensure() {}
  trim() {}
  rebase(dx, dz) {
    for (let i = 0; i < this.n; i++) { this.x[i] -= dx; this.z[i] -= dz; }
    for (const r of this.routes) r.path.rebase(dx, dz);
  }
}

