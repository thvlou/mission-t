import { getVehicle } from '../vehicles.js';

// Course map for a race room (left of the screen): the whole course from the start line to the
// finish, with a dot per driver in the colour of their car and a legend in race order. The highway
// is traced from the road's curvature (so drawing it never touches the streamed road samples); a
// closed circuit is drawn once round, north up, with the lap count in the header.
const TRACE = 8;     // m between traced points
const SPREAD = 2.5;  // lateral positions drawn this much wider, so cars side by side don't merge
const PAD = 14;      // px around the course
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

export class Minimap {
  constructor(el) {
    this.el = el;
    el.innerHTML = `<div class="mm-core">
        <div class="mm-head"><span class="eyebrow">Course</span><b class="mm-len"></b></div>
        <canvas aria-hidden="true"></canvas>
        <ol class="mm-legend"></ol>
      </div>`;
    this.canvas = el.querySelector('canvas');
    this.ctx = this.canvas.getContext('2d');
    this.legend = el.querySelector('.mm-legend');
    this.key = '';
    this.size = '';
    this.drawnAt = 0;
    this.legendHtml = '';
  }

  show(on) {
    if (this.el.hidden === !on) return;
    this.el.hidden = !on;
    if (on) this.key = ''; // the canvas may have been resized while hidden
  }

  // players: [{ id, s, d, car, name, me }]; laps: { lap, laps } on a circuit
  draw(road, seed, s0, s1, players, laps = null) {
    const closed = !!road.closed;
    const L = closed ? road.length : 0;
    if (closed) { s0 = 0; s1 = L; }
    const lapS = (s) => (closed ? ((s % L) + L) % L : s);
    const now = performance.now();
    if (now - this.drawnAt < 33) return;
    this.drawnAt = now;
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    const dpr = Math.min(2, window.devicePixelRatio || 1);
    const size = `${w}x${h}@${dpr}`;
    const key = `${seed}:${s0}:${s1}:${size}`;
    if (key !== this.key) {
      this.key = key;
      if (size !== this.size) {
        this.size = size;
        this.canvas.width = Math.round(w * dpr);
        this.canvas.height = Math.round(h * dpr);
      }
      this.trace(road, s0, s1, w, h, dpr);
      this.lenText = '';
    }
    const lenText = laps ? `Lap ${laps.lap}/${laps.laps} · ${(L / 1000).toFixed(1)} km` : `${((s1 - s0) / 1000).toFixed(1)} km`;
    if (lenText !== this.lenText) {
      this.lenText = lenText;
      this.el.querySelector('.mm-len').textContent = lenText;
    }
    const ctx = this.ctx;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    ctx.drawImage(this.base, 0, 0);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // Our progress so far, in the accent colour.
    const me = players.find((p) => p.me);
    if (me && (!closed || me.s > 0)) {
      ctx.beginPath();
      const end = Math.min(s1, Math.max(s0, lapS(me.s)));
      for (let s = s0; s <= end; s += TRACE) {
        const q = this.at(s, 0);
        if (s === s0) ctx.moveTo(q.x, q.y); else ctx.lineTo(q.x, q.y);
      }
      const q = this.at(end, 0);
      ctx.lineTo(q.x, q.y);
      ctx.strokeStyle = '#d23437';
      ctx.lineWidth = 2.5;
      ctx.lineCap = 'round';
      ctx.lineJoin = 'round';
      ctx.stroke();
    }

    // Drivers: others first, ours on top with a ring that breathes.
    const order = [...players].sort((a, b) => (a.me ? 1 : 0) - (b.me ? 1 : 0));
    for (const p of order) {
      let q = this.at(lapS(p.s), p.d);
      if (p.route && road.drivingFrame) {
        const f = road.drivingFrame(p.s, p.route);
        q = this.worldMap(f.x + f.rx * p.d * SPREAD, f.z + f.rz * p.d * SPREAD);
      }
      const hex = getVehicle(p.car).hex;
      if (p.me) {
        const k = 0.5 + 0.5 * Math.sin(now / 320);
        ctx.beginPath();
        ctx.arc(q.x, q.y, 10 + k * 2.5, 0, Math.PI * 2);
        ctx.fillStyle = `rgba(210, 52, 55, ${0.12 + 0.1 * (1 - k)})`;
        ctx.fill();
      }
      const r = p.me ? 6.5 : 5;
      ctx.beginPath();
      ctx.arc(q.x, q.y + 0.8, r + 1.5, 0, Math.PI * 2);
      ctx.fillStyle = 'rgba(18, 19, 22, 0.18)';
      ctx.fill();
      ctx.beginPath();
      ctx.arc(q.x, q.y, r, 0, Math.PI * 2);
      ctx.fillStyle = hex;
      ctx.fill();
      ctx.lineWidth = p.me ? 2.5 : 2;
      ctx.strokeStyle = p.me ? '#d23437' : '#ffffff';
      ctx.stroke();
    }

    // Legend in race order.
    const rows = [...players].sort((a, b) => b.s - a.s).map((p, i) => {
      const car = getVehicle(p.car);
      return `<li class="${p.me ? 'me' : ''}"><b>${i + 1}</b><i style="background:${esc(car.hex)}"></i><span>${esc(p.name)}</span><small>${esc(car.name)}</small></li>`;
    }).join('');
    if (rows !== this.legendHtml) {
      this.legendHtml = rows;
      this.legend.innerHTML = rows;
    }
  }

  // Trace the course in a frame where the start-to-finish line runs straight up, fit it to the
  // canvas, and paint the static parts (road, start line, finish flag) once.
  trace(road, s0, s1, w, h, dpr) {
    let raw = [];
    if (road.closed) {
      raw = road.outline(TRACE);
    } else {
      let x = 0, z = 0, hd = 0;
      // The road starts at s = 0 heading along +x; integrate its curvature like Road.extend does.
      for (let s = 0; s <= s1 + TRACE; s += TRACE) {
        if (s >= s0 - TRACE) raw.push({ s, x, z, h: hd });
        const k = road.curvature(s + TRACE / 2);
        const hm = hd + (k * TRACE) / 2;
        x += Math.cos(hm) * TRACE;
        z -= Math.sin(hm) * TRACE;
        hd += k * TRACE;
      }
    }
    const a = raw[0], b = raw[raw.length - 1];
    // A sprint runs start-to-finish straight up; a circuit keeps north up.
    const turnBy = road.closed ? 0 : -Math.PI / 2 - Math.atan2(b.z - a.z, b.x - a.x);
    const c = Math.cos(turnBy), sn = Math.sin(turnBy);
    const pts = raw.map((p) => ({
      s: p.s,
      x: c * p.x - sn * p.z, y: sn * p.x + c * p.z,
      // the road's right-hand normal in map terms
      rx: c * Math.sin(p.h) - sn * Math.cos(p.h), ry: sn * Math.sin(p.h) + c * Math.cos(p.h),
    }));
    let minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    for (const p of pts) {
      minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x);
      minY = Math.min(minY, p.y); maxY = Math.max(maxY, p.y);
    }
    const scale = Math.min((w - PAD * 2) / Math.max(1, maxX - minX), (h - PAD * 2) / Math.max(1, maxY - minY));
    const ox = w / 2 - ((minX + maxX) / 2) * scale, oy = h / 2 - ((minY + maxY) / 2) * scale;
    this.worldMap = (x, z) => ({ x: ox + (c * x - sn * z) * scale, y: oy + (sn * x + c * z) * scale });
    this.pts = pts.map((p) => ({ ...p, x: ox + p.x * scale, y: oy + p.y * scale }));
    this.s0 = pts[0].s;
    this.scale = scale;

    const base = this.base || (this.base = document.createElement('canvas'));
    base.width = this.canvas.width;
    base.height = this.canvas.height;
    const g = base.getContext('2d');
    g.setTransform(dpr, 0, 0, dpr, 0, 0);
    g.clearRect(0, 0, w, h);
    const path = () => {
      g.beginPath();
      for (let s = s0; s <= s1; s += TRACE) {
        const q = this.at(s, 0);
        if (s === s0) g.moveTo(q.x, q.y); else g.lineTo(q.x, q.y);
      }
    };
    g.lineCap = 'round';
    g.lineJoin = 'round';
    path();
    g.strokeStyle = 'rgba(18, 19, 22, 0.1)';
    g.lineWidth = 9;
    g.stroke();
    path();
    g.strokeStyle = '#fbfaf8';
    g.lineWidth = 4;
    g.stroke();
    for (const route of road.routes || []) {
      g.beginPath();
      route.path.x.forEach((x,i) => { const p = this.worldMap(x, route.path.z[i]); if (!i) g.moveTo(p.x,p.y); else g.lineTo(p.x,p.y); });
      g.strokeStyle = '#6ca99c'; g.lineWidth = 3; g.setLineDash([3, 3]); g.stroke(); g.setLineDash([]);
    }
    // Start: a short bar across the road (a circuit's start is its finish too).
    const st = this.at(s0, 0), n0 = this.normal(s0);
    if (!road.closed) {
      g.beginPath();
      g.moveTo(st.x - n0.x * 7, st.y - n0.y * 7);
      g.lineTo(st.x + n0.x * 7, st.y + n0.y * 7);
      g.strokeStyle = '#121316';
      g.lineWidth = 2;
      g.stroke();
    }
    // Finish: a small chequered square.
    const fin = this.at(s1, 0);
    const cell = 3.2;
    for (let i = 0; i < 3; i++) {
      for (let j = 0; j < 3; j++) {
        g.fillStyle = (i + j) % 2 ? '#fbfaf8' : '#121316';
        g.fillRect(fin.x - cell * 1.5 + i * cell, fin.y - cell * 1.5 + j * cell, cell, cell);
      }
    }
    g.strokeStyle = 'rgba(18, 19, 22, 0.35)';
    g.lineWidth = 1;
    g.strokeRect(fin.x - cell * 1.5, fin.y - cell * 1.5, cell * 3, cell * 3);
  }

  // Map position of road coordinates (s along, d across).
  at(s, d) {
    const pts = this.pts;
    const f = Math.max(0, Math.min(pts.length - 1.001, (s - this.s0) / TRACE));
    const i = Math.floor(f), t = f - i;
    const a = pts[i], b = pts[i + 1];
    const dd = d * this.scale * SPREAD;
    return {
      x: a.x + (b.x - a.x) * t + (a.rx + (b.rx - a.rx) * t) * dd,
      y: a.y + (b.y - a.y) * t + (a.ry + (b.ry - a.ry) * t) * dd,
    };
  }

  normal(s) {
    const pts = this.pts;
    const p = pts[Math.max(0, Math.min(pts.length - 1, Math.round((s - this.s0) / TRACE)))];
    return { x: p.rx, y: p.ry };
  }
}
