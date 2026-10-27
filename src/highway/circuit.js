import * as THREE from 'three';
import { buildStuntScenery } from './stunt-scenery.js';

// A closed race circuit built from assets/tracks/<id>.json (see tools/build-track.mjs), with the
// same interface as the endless Road (frame, project, rebase…) so the highway car, camera, race
// and minimap run on it unchanged. Arc length s is unwrapped: it keeps counting up lap after lap
// (frame() wraps it), so progress, standings and the finish are plain distances.
//
// CircuitScenery draws the whole course once in the game's look: terrain that follows the road,
// asphalt with edge lines, red-and-white kerbs through corners, gravel run-off, low walls, trees
// and a start gantry. It is cached per course, so racing again doesn't rebuild it.
import { Circuit, RUNOFF } from './circuit-path.js';
export { Circuit, RUNOFF };

const tracks = new Map(); // id → Promise<data>
export function loadCircuit(id) {
  if (!tracks.has(id)) {
    const p = fetch(`assets/tracks/${id}.json`).then((r) => {
      if (!r.ok) throw new Error(`${r.status} for track ${id}`);
      return r.json();
    });
    p.catch(() => tracks.delete(id));
    tracks.set(id, p);
  }
  return tracks.get(id);
}

const wrapA = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

// ---------- scenery ----------
const PALETTE = {
  asphalt: '#a8a6a1', line: '#fbfbf9', ground: '#e6e3dc', gravel: '#d6d2ca',
  concrete: '#e4e1db', canopy: '#d4d7c9', trunk: '#b5ad9f', red: '#d23437', ink: '#121316',
};

function canvasTex(w, h, draw, repeat = true) {
  const c = document.createElement('canvas');
  c.width = w; c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 16;
  if (repeat) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}
function speckle(ctx, w, h, base, amount) {
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, w, h);
  const img = ctx.getImageData(0, 0, w, h);
  for (let i = 0; i < img.data.length; i += 4) {
    const k = (Math.random() - 0.5) * amount;
    img.data[i] += k; img.data[i + 1] += k; img.data[i + 2] += k;
  }
  ctx.putImageData(img, 0, 0);
}

const sceneries = new Map(); // course id → CircuitScenery (built once per session)
export function circuitScenery(circuit) {
  if (!sceneries.has(circuit.id)) sceneries.set(circuit.id, new CircuitScenery(circuit));
  const sc = sceneries.get(circuit.id);
  sc.group.position.set(0, 0, 0);
  return sc;
}

class CircuitScenery {
  constructor(c) {
    const C = { ...PALETTE, ...c.data.palette };
    this.group = new THREE.Group();
    const n = c.n;
    const P = [];
    for (let i = 0; i < n; i++) {
      P.push({ x: c.x[i], y: c.y[i], z: c.z[i], h: c.h[i], rx: Math.sin(c.h[i]), rz: Math.cos(c.h[i]), wl: c.wl[i], wr: c.wr[i], grade: c.sl[i], s: c.cum[i], gap: c.surfaceAt(c.cum[i], 0).gap });
    }
    for (let i = 0; i < n; i++) P[i].k = wrapA(P[(i + 3) % n].h - P[(i - 3 + n) % n].h) / Math.max(1, c.cum[Math.min(n, i + 3)] - c.cum[Math.max(0, i - 3)]);
    this.P = P;
    this.c = c;
    const add = (geo, mat, { cast = false, receive = true } = {}) => {
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = cast; m.receiveShadow = receive;
      this.group.add(m);
      return m;
    };
    const edge = (p, d, up = 0) => new THREE.Vector3(p.x + p.rx * d, p.y + up, p.z + p.rz * d);
    // A strip along the course; cols(p) → [[offset across, height], …]; v runs along in metres.
    const ribbon = (cols, mat, { from = 0, to = n, vScale = 1 / 24, cast = false, openings = [] } = {}) => {
      const pos = [], uv = [], idx = [];
      let s = 0, rows = 0;
      const m = cols(P[0]).length;
      for (let j = from; j <= to; j++) {
        const p = P[j % n];
        if (j > from) { const o = P[(j - 1) % n]; s += Math.hypot(p.x - o.x, p.z - o.z); }
        cols(p).forEach(([d, up], k) => { const v = edge(p, d, up); pos.push(v.x, v.y, v.z); uv.push(k / (m - 1), s * vScale); });
        rows++;
      }
      for (let r = 0; r < rows - 1; r++) for (let k = 0; k < m - 1; k++) {
        const aS = c.cum[(from + r) % n], bS = from + r + 1 >= n ? c.length : c.cum[(from + r + 1) % n];
        if ((c.data.gaps || []).some(g => (aS + bS) / 2 >= g.from && (aS + bS) / 2 < g.to)) continue;
        if (openings.some(g => (aS + bS) / 2 >= g.from && (aS + bS) / 2 < g.to)) continue;
        const a = r * m + k, b = a + 1, cc = a + m, d = cc + 1;
        idx.push(a, b, cc, b, d, cc); // counter-clockwise from above
      }
      const g = new THREE.BufferGeometry();
      g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
      g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
      g.setIndex(idx);
      g.computeVertexNormals();
      return add(g, mat, { cast });
    };

    // Road, run-off, kerbs, walls
    const roadMap = canvasTex(512, 1024, (ctx, w, h) => {
      speckle(ctx, w, h, C.asphalt, 9);
      ctx.fillStyle = C.line;
      ctx.fillRect(w * 0.025, 0, w * 0.018, h);
      ctx.fillRect(w * 0.957, 0, w * 0.018, h);
    });
    roadMap.wrapS = THREE.ClampToEdgeWrapping;
    ribbon((p) => [[-p.wl, 0.02], [p.wr, 0.02]], new THREE.MeshStandardMaterial({ map: roadMap, roughness: 0.82, color: c.data.version >= 2 ? '#8a9695' : '#ffffff' }));
    const gravel = new THREE.MeshStandardMaterial({ color: C.gravel, roughness: 0.95 });
    ribbon((p) => [[-p.wl - RUNOFF, -0.1], [-p.wl, 0.0]], gravel, { vScale: 1 / 8 });
    ribbon((p) => [[p.wr, 0.0], [p.wr + RUNOFF, -0.1]], gravel, { vScale: 1 / 8 });
    const kerbMap = canvasTex(64, 256, (ctx, w, h) => {
      ctx.fillStyle = C.red; ctx.fillRect(0, 0, w, h / 2);
      ctx.fillStyle = '#fbfaf8'; ctx.fillRect(0, h / 2, w, h / 2);
    });
    const kerb = new THREE.MeshStandardMaterial({ map: kerbMap, roughness: 0.6 });
    for (let i = 0, start = -1; i <= n; i++) {
      const on = i < n && Math.abs(P[i].k) > 1 / 170;
      if (on && start < 0) start = i;
      if (!on && start >= 0) {
        if (i - start > 3) {
          const a = Math.max(0, start - 3), b = Math.min(n - 1, i + 3);
          ribbon((p) => [[-p.wl - 1.3, 0.03], [-p.wl, 0.06]], kerb, { from: a, to: b, vScale: 1 / 3 });
          ribbon((p) => [[p.wr, 0.06], [p.wr + 1.3, 0.03]], kerb, { from: a, to: b, vScale: 1 / 3 });
        }
        start = -1;
      }
    }
    const wall = new THREE.MeshStandardMaterial({ color: C.concrete, roughness: 0.7 });
    const railOpenings = side => c.routes.flatMap(route => {
      const entry=c.frame(route.from+70),fork=c.drivingFrame(route.from+70,route.id);
      const exit=c.frame(route.to-70),merge=c.drivingFrame(route.to-70,route.id);
      const a=Math.sign((fork.x-entry.x)*entry.rx+(fork.z-entry.z)*entry.rz);
      const b=Math.sign((merge.x-exit.x)*exit.rx+(merge.z-exit.z)*exit.rz);
      return [...(a===side?[{from:route.from-10,to:route.from+115}]:[]),...(b===side?[{from:route.to-115,to:route.to+10}]:[])];
    });
    ribbon((p) => [[-p.wl - RUNOFF, -0.6], [-p.wl - RUNOFF, 0.95]], wall, { vScale: 1 / 6, cast: true, openings: railOpenings(-1) });
    ribbon((p) => [[p.wr + RUNOFF, 0.95], [p.wr + RUNOFF, -0.6]], wall, { vScale: 1 / 6, cast: true, openings: railOpenings(1) });

    // Start / finish: chequered line, a red gantry with the course name, grid boxes behind it.
    {
      const p = P[0];
      const chk = canvasTex(512, 64, (ctx) => {
        for (let x = 0; x < 32; x++) for (let y = 0; y < 4; y++) { ctx.fillStyle = (x + y) % 2 ? C.ink : '#fbfaf8'; ctx.fillRect(x * 16, y * 16, 16, 16); }
      }, false);
      const width = p.wl + p.wr;
      const line = add(new THREE.PlaneGeometry(width, 2.4), new THREE.MeshStandardMaterial({ map: chk, roughness: 0.8, polygonOffset: true, polygonOffsetFactor: -2 }));
      line.position.copy(edge(p, (p.wr - p.wl) / 2, 0.035));
      line.rotation.order = 'YXZ';
      line.rotation.set(-Math.PI / 2, p.h - Math.PI / 2, 0);
      const steel = new THREE.MeshStandardMaterial({ color: '#9fa3a8', roughness: 0.35, metalness: 0.7 });
      for (const d of [-p.wl - 1, p.wr + 1]) add(new THREE.BoxGeometry(0.4, 8, 0.4), steel, { cast: true }).position.copy(edge(p, d, 4));
      const board = canvasTex(1024, 160, (ctx, w, h) => {
        ctx.fillStyle = C.red; ctx.fillRect(0, 0, w, h);
        ctx.fillStyle = '#fbfaf8'; ctx.font = '400 104px Crosner, Pretendard, sans-serif';
        ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(c.name.toUpperCase(), w / 2, h / 2 + 6);
      }, false);
      const face = new THREE.MeshStandardMaterial({ map: board });
      const beam = add(new THREE.BoxGeometry(width + 2.4, 1.6, 0.5), [steel, steel, steel, steel, face, face], { cast: true });
      beam.position.copy(edge(p, (p.wr - p.wl) / 2, 7.6));
      beam.rotation.y = p.h + Math.PI / 2;
      const boxMat = new THREE.MeshBasicMaterial({ color: '#fbfbf9' });
      for (let k = 0; k < 6; k++) {
        const f = c.frame(-10 - Math.floor(k / 2) * 12 + 1.6);
        const g = { x: f.x, y: f.y, z: f.z, rx: f.rx, rz: f.rz };
        const bar = add(new THREE.PlaneGeometry(2.2, 0.25), boxMat);
        bar.position.copy(edge(g, (k % 2 ? 1.85 : -1.85), 0.04));
        bar.rotation.order = 'YXZ';
        bar.rotation.set(-Math.PI / 2, f.h - Math.PI / 2, 0);
      }
    }

    // Terrain: always under the nearest road, blending into a smooth fit of the course's heights.
    let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
    for (const p of P) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minZ = Math.min(minZ, p.z); maxZ = Math.max(maxZ, p.z); }
    const pad = 450, cx = (minX + maxX) / 2, cz = (minZ + maxZ) / 2, sx = maxX - minX + pad * 2, sz = maxZ - minZ + pad * 2;
    const terrainP = [...P];
    for (const route of c.routes) for (let i = 0; i < route.path.n; i++) {
      const p = route.path;
      terrainP.push({ x: p.x[i], y: p.y[i], z: p.z[i], wl: 6, wr: 6, branch: true, gap: route.gaps.some(g => p.cum[i] >= g.from && p.cum[i] < g.to) });
    }
    const coarse = P.filter((_, i) => i % 8 === 0);
    const CELL = 40, cells = new Map();
    for (const p of terrainP) {
      const key = `${Math.floor(p.x / CELL)},${Math.floor(p.z / CELL)}`;
      if (!cells.has(key)) cells.set(key, []);
      cells.get(key).push(p);
    }
    const nearest = (x, z, reach = 2) => {
      const gx = Math.floor(x / CELL), gz = Math.floor(z / CELL);
      let best = null, bd = Infinity, lowest = Infinity;
      for (let a = -reach; a <= reach; a++) for (let b = -reach; b <= reach; b++) {
        for (const p of cells.get(`${gx + a},${gz + b}`) || []) {
          const d = (p.x - x) ** 2 + (p.z - z) ** 2;
          if (d < 625 && !p.branch) lowest = Math.min(lowest, p.y - .45);
          if (d < bd) { bd = d; best = p; }
        }
      }
      return best && { p: best, d: Math.sqrt(bd), lowest };
    };
    const smooth01 = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
    const landAt = (x, z) => {
      let ws = 0, hs = 0;
      for (const p of coarse) {
        const w = 1 / (((p.x - x) ** 2 + (p.z - z) ** 2) + 400) ** 1.6;
        ws += w; hs += w * p.y;
      }
      const fit = hs / ws - 0.4, nb = nearest(x, z);
      if (!nb) return { h: fit, d: 999 };
      const under = Math.min(nb.lowest, nb.p.branch ? fit - (nb.p.gap ? 18 : .5) : nb.p.y - (nb.p.gap ? 22 : .45)) - Math.max(0, nb.d - Math.max(nb.p.wl, nb.p.wr) - RUNOFF) * .04;
      const k = smooth01((nb.d - 30) / 110);
      return { h: Math.min(under + k * 40, under * (1 - k) + fit * k), d: nb.d };
    };
    {
      const seg = 150;
      const g = new THREE.PlaneGeometry(sx, sz, seg, Math.round((seg * sz) / sx));
      g.rotateX(-Math.PI / 2);
      const pa = g.attributes.position;
      for (let i = 0; i < pa.count; i++) {
        const x = pa.getX(i) + cx, z = pa.getZ(i) + cz;
        pa.setXYZ(i, x, landAt(x, z).h, z);
      }
      g.computeVertexNormals();
      const map = canvasTex(1024, 1024, (ctx, w, h) => speckle(ctx, w, h, C.ground, 8));
      map.repeat.set(sx / 18, sz / 18);
      add(g, new THREE.MeshStandardMaterial({ map, roughness: 0.95 }));
    }

    // Trees, in clumps, kept clear of the run-off.
    {
      const N = 1800;
      const canopy = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshStandardMaterial({ color: C.canopy, roughness: 0.9, flatShading: true }), N);
      const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.18, 1, 6), new THREE.MeshStandardMaterial({ color: C.trunk, roughness: 0.9 }), N);
      canopy.castShadow = trunk.castShadow = true;
      let seed = 11;
      const rand = () => (seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0) / 4294967296;
      const m = new THREE.Object3D();
      let count = 0;
      for (let tries = 0; count < N && tries < 30000; tries++) {
        const x = cx + (rand() - 0.5) * sx * 0.96, z = cz + (rand() - 0.5) * sz * 0.96;
        const nb = nearest(x, z, 1);
        if (nb && nb.d < Math.max(nb.p.wl, nb.p.wr) + RUNOFF + 8) continue;
        if (Math.sin(x * 0.011 + 1.3) * Math.cos(z * 0.009) < -0.25 && rand() < 0.8) continue;
        const h = landAt(x, z).h;
        const s = 2.2 + rand() * 2.6, ht = 2 + rand() * 2.5;
        m.position.set(x, h - 0.5 + ht + s * 0.7, z); m.scale.set(s, s * (1.1 + rand() * 0.5), s); m.rotation.set(rand(), rand() * 6, 0); m.updateMatrix();
        canopy.setMatrixAt(count, m.matrix);
        m.position.set(x, h - 0.5 + ht / 2, z); m.scale.set(1, ht, 1); m.rotation.set(0, 0, 0); m.updateMatrix();
        trunk.setMatrixAt(count, m.matrix);
        count++;
      }
      canopy.count = trunk.count = count;
      this.group.add(canopy, trunk);
    }
    if (c.data.version >= 2) this.group.add(buildStuntScenery(c, C));
  }

  update() {}
  // Cached for the next race on this course, so nothing is disposed here.
  clear() {}
  rebase(dx, dz) {
    this.group.position.x -= dx;
    this.group.position.z -= dz;
  }
}
