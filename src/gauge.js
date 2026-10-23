// The dashboard speedometer. Each car brings its own design (theme.gauge in src/vehicles.js); the
// whole dial is drawn into one 220×160 SVG and rebuilt when the car changes.
//
// While boosting the dial switches to the car's more saturated palette, shakes like a body at full
// thrust and the dashboard eases smaller (CSS: .dash.boosting) so the boost flame stays in view.
const NS = 'http://www.w3.org/2000/svg';

// Angles in degrees, counter-clockwise from +x; the dial sweeps clockwise from a0 = 90 + sweep / 2.
//   cuts: gaps cut through the band · segments: an LED bar · outer: fine ticks outside the ring
//   labels: numbered majors inside the arc · redline: share of the arc marked as the redline
const STYLES = {
  classic: { cy: 96, r: 70, sweep: 240, width: 16, cuts: 12, cutW: 2, needle: 'line' },
  ring: { cy: 94, r: 66, sweep: 270, width: 5, round: true, outer: 36, needle: 'bead', unitY: 76, speedY: 110, endsY: 152 },
  segments: { cy: 96, r: 70, sweep: 240, width: 14, segments: 24, needle: 'none' },
  minimal: { cy: 98, r: 72, sweep: 220, width: 3, track: 1, labels: 4, minor: 16, needle: 'hand', ends: false, unitY: 70, speedY: 106 },
  rugged: { cy: 98, r: 64, sweep: 240, width: 22, cuts: 8, cutW: 4.5, needle: 'pointer' },
  track: { cy: 112, r: 80, sweep: 180, width: 12, segments: 40, redline: 0.86, needle: 'bar', unitY: 62, speedY: 104, endsY: 132 },
};

const el = (tag, attrs = {}, parent = null) => {
  const n = document.createElementNS(NS, tag);
  for (const k in attrs) n.setAttribute(k, attrs[k]);
  parent?.appendChild(n);
  return n;
};
const f2 = (v) => v.toFixed(2);
let instances = 0; // gradient and mask ids must be unique in the document

export class Gauge {
  constructor(root, dash) {
    this.root = root; // .gauge
    this.dash = dash; // .dash, shrinks while boosting
    this.max = 240;
    this.kmh = 0;
    this.level = 0; // smoothed 0..1 boost intensity
    this.offAt = 0;
    this.t = 0;
    this.uid = `g${++instances}`;
    this.setTheme({ gauge: 'classic', accent: '#d23437', grad: ['#ffe2a8', '#ff9a5c', '#f05a3a', '#d23437'], boost: ['#ff9e57', '#ff4d2e', '#ff1a3c', '#c8001e'] });
  }

  setTheme(theme) {
    this.theme = theme;
    this.s = { cx: 110, unitY: 74, speedY: 112, endsY: null, ends: true, ...STYLES[theme.gauge] || STYLES.classic };
    this.dash.dataset.gauge = theme.gauge;
    this.dash.style.setProperty('--g-accent', theme.accent);
    this.dash.style.setProperty('--g-boost', theme.boost[3]);
    this.dash.style.setProperty('--g-fill', `linear-gradient(90deg, ${theme.grad[3]}, ${theme.grad[1]})`);
    this.dash.style.setProperty('--g-fill-boost', `linear-gradient(90deg, ${theme.boost[3]}, ${theme.boost[1]})`);
    this.build();
  }

  setMax(max) {
    this.max = max;
    this.build();
  }

  polar(r, deg) {
    const a = (deg * Math.PI) / 180;
    return [this.s.cx + r * Math.cos(a), this.s.cy - r * Math.sin(a)];
  }

  build() {
    const s = this.s, th = this.theme;
    const a0 = 90 + s.sweep / 2;
    this.a0 = a0;
    this.root.textContent = '';
    const svg = el('svg', { viewBox: '0 0 220 160', 'aria-hidden': 'true' }, this.root);
    this.svg = svg;
    const defs = el('defs', {}, svg);
    const grad = (id, stops) => {
      const g = el('linearGradient', { id, x1: 0, y1: 0, x2: 1, y2: 0 }, defs);
      stops.forEach((c, i) => el('stop', { offset: f2(i / (stops.length - 1)), 'stop-color': c }, g));
    };
    const id = this.uid;
    grad(`${id}Grad`, th.grad);
    grad(`${id}Boost`, th.boost);

    const arcD = (r, from = 0, to = 1) => {
      const [x0, y0] = this.polar(r, a0 - s.sweep * from);
      const [x1, y1] = this.polar(r, a0 - s.sweep * to);
      const large = s.sweep * (to - from) > 180 ? 1 : 0;
      return `M ${f2(x0)} ${f2(y0)} A ${r} ${r} 0 ${large} 1 ${f2(x1)} ${f2(y1)}`;
    };
    const d = arcD(s.r);

    // A mask turns the band into steps or segments with real gaps, so the road shows through.
    let mask = null;
    if (s.cuts || s.segments) {
      const m = el('mask', { id: `${id}Mask`, maskUnits: 'userSpaceOnUse', x: -20, y: -20, width: 260, height: 200 }, defs);
      if (s.segments) {
        const step = 100 / s.segments;
        el('path', { d, fill: 'none', stroke: '#fff', 'stroke-width': s.width + 4, pathLength: 100, 'stroke-dasharray': `${f2(step * 0.78)} ${f2(step * 0.22)}`, 'stroke-dashoffset': f2(-step * 0.11) }, m);
      } else {
        el('rect', { x: -20, y: -20, width: 260, height: 200, fill: '#fff' }, m);
        for (let i = 0; i <= s.cuts; i++) {
          const a = a0 - (s.sweep * i) / s.cuts;
          const [xa, ya] = this.polar(s.r - s.width / 2 - 2, a);
          const [xb, yb] = this.polar(s.r + s.width / 2 + 2, a);
          el('line', { x1: f2(xa), y1: f2(ya), x2: f2(xb), y2: f2(yb), stroke: '#000', 'stroke-width': s.cutW }, m);
        }
      }
      mask = `url(#${id}Mask)`;
    }

    const band = el('g', mask ? { mask } : {}, svg);
    const cap = s.round ? 'round' : 'butt';
    el('path', { d, class: 'g-track', fill: 'none', stroke: th.accent, 'stroke-opacity': s.track ? 0.35 : 0.12, 'stroke-width': s.track || s.width, 'stroke-linecap': cap }, band);
    if (s.redline) {
      el('path', { d: arcD(s.r, s.redline, 1), fill: 'none', stroke: '#ff2d3d', 'stroke-opacity': 0.32, 'stroke-width': s.width }, band);
    }
    this.fill = el('path', { d, class: 'g-fill', fill: 'none', stroke: `url(#${id}Grad)`, 'stroke-width': s.width, 'stroke-linecap': cap, pathLength: 100, 'stroke-dasharray': '0 100' }, band);
    this.boostFill = el('path', { d, class: 'g-fill g-boost', fill: 'none', stroke: `url(#${id}Boost)`, 'stroke-width': s.width, 'stroke-linecap': cap, pathLength: 100, 'stroke-dasharray': '0 100' }, band);

    if (s.outer) {
      const g = el('g', { class: 'g-minor' }, svg);
      for (let i = 0; i <= s.outer; i++) {
        const a = a0 - (s.sweep * i) / s.outer;
        const major = i % 6 === 0;
        const [xa, ya] = this.polar(s.r + 7, a);
        const [xb, yb] = this.polar(s.r + (major ? 14 : 10), a);
        el('line', { x1: f2(xa), y1: f2(ya), x2: f2(xb), y2: f2(yb), class: major ? 'major' : '' }, g);
      }
    }
    if (s.minor) {
      const g = el('g', { class: 'g-minor' }, svg);
      for (let i = 0; i <= s.minor; i++) {
        const a = a0 - (s.sweep * i) / s.minor;
        const major = i % (s.minor / s.labels) === 0;
        const [xa, ya] = this.polar(s.r - 5, a);
        const [xb, yb] = this.polar(s.r - (major ? 12 : 8), a);
        el('line', { x1: f2(xa), y1: f2(ya), x2: f2(xb), y2: f2(yb), class: major ? 'major' : '' }, g);
      }
    }
    if (s.labels) {
      for (let i = 0; i <= s.labels; i++) {
        const a = a0 - (s.sweep * i) / s.labels;
        const [x, y] = this.polar(s.r - 23, a);
        el('text', { x: f2(x), y: f2(y + 3.5), class: 'end' }, svg).textContent = String(Math.round((this.max * i) / s.labels));
      }
    }

    // Needles are drawn pointing straight up and rotated about the dial centre.
    const cx = s.cx, cy = s.cy, r = s.r, w = s.width;
    const needle = el('g', { class: `g-needle ${s.needle}` }, svg);
    if (s.needle === 'line') {
      el('line', { x1: cx, y1: cy - (r - 18), x2: cx, y2: cy - (r + 11) }, needle);
    } else if (s.needle === 'bead') {
      el('circle', { cx, cy: cy - r, r: 10, class: 'halo' }, needle);
      el('circle', { cx, cy: cy - r, r: 5 }, needle);
    } else if (s.needle === 'hand') {
      el('line', { x1: cx, y1: cy - (r - 17), x2: cx, y2: cy - (r + 7) }, needle);
      el('circle', { cx, cy: cy - (r - 17), r: 2.4 }, needle);
    } else if (s.needle === 'pointer') {
      const tip = cy - (r + w / 2 + 2), base = cy - (r + w / 2 + 13);
      el('path', { d: `M ${cx} ${tip} L ${cx - 6} ${base} L ${cx + 6} ${base} Z` }, needle);
    } else if (s.needle === 'bar') {
      el('rect', { x: cx - 2.5, y: cy - (r + w / 2 + 5), width: 5, height: w + 10, rx: 1.5 }, needle);
    }
    this.needle = s.needle === 'none' ? null : needle;

    el('text', { x: cx, y: s.unitY, class: 'unit' }, svg).textContent = 'km/h';
    this.speed = el('text', { x: cx, y: s.speedY, class: 'speed' }, svg);
    this.speed.textContent = '0';
    this.speedText = '0';
    if (s.ends) {
      const [x0, y0] = this.polar(r, a0);
      const [x1, y1] = this.polar(r, a0 - s.sweep);
      el('text', { x: f2(x0 + 10), y: s.endsY ?? f2(y0 + 19), class: 'end' }, svg).textContent = '0';
      el('text', { x: f2(x1 - 10), y: s.endsY ?? f2(y1 + 19), class: 'end' }, svg).textContent = String(this.max);
    }
    this.pct = -1;
  }

  // boosting: the jets are on this frame. Speed eases toward kmh like a real needle.
  update(dt, kmh, boosting) {
    this.t += dt;
    if (boosting) this.offAt = this.t;
    // A short hold so feathering the boost doesn't make the dashboard pump.
    const on = this.t - this.offAt < 0.3;
    this.level += ((on ? 1 : 0) - this.level) * (1 - Math.exp(-dt * (on ? 10 : 5)));
    if (this.dash.classList.contains('boosting') !== on) this.dash.classList.toggle('boosting', on);

    this.kmh += (kmh - this.kmh) * (1 - Math.exp(-dt * 16));
    const pct = Math.min(1, Math.max(0, this.kmh / this.max));
    const text = String(Math.round(kmh));
    if (text !== this.speedText) {
      this.speedText = text;
      this.speed.textContent = text;
    }
    if (Math.abs(pct - this.pct) > 0.0005) {
      this.pct = pct;
      const dash = `${f2(pct * 100)} 100`;
      this.fill.setAttribute('stroke-dasharray', dash);
      this.boostFill.setAttribute('stroke-dasharray', dash);
    }

    // The shake: a fast buzz on top of a slower body judder, stronger the faster you go.
    const k = this.level;
    let wobble = 0;
    if (k > 0.01) {
      const amp = k * (1.1 + 1.9 * pct);
      const x = Math.sin(this.t * 47) * amp * 0.55 + (Math.random() - 0.5) * amp * 0.9;
      const y = Math.sin(this.t * 61 + 1.3) * amp * 0.35 + (Math.random() - 0.5) * amp * 0.5;
      const rot = (Math.random() - 0.5) * amp * 0.45;
      this.svg.style.transform = `translate(${f2(x)}px, ${f2(y)}px) rotate(${f2(rot)}deg)`;
      wobble = (Math.random() - 0.5) * k * 3.2;
    } else if (this.svg.style.transform) {
      this.svg.style.transform = '';
    }
    if (this.needle) {
      const a = this.a0 - this.s.sweep * pct;
      this.needle.setAttribute('transform', `rotate(${f2(90 - a + wobble)} ${this.s.cx} ${this.s.cy})`);
    }
  }
}
