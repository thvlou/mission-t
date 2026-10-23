import * as THREE from 'three';
import { LAYOUT, rng } from './road.js';

// Scenery is built in 240 m chunks along the road: road surfaces, median barrier, guardrails,
// verges, lamp posts, trees, corner chevrons, a distance gantry every kilometre and interchanges
// (an overpass with slip roads on both sides).
export const CHUNK = 240;
const SEG = 4; // m between cross-sections inside a chunk

// Interchange geometry. Each slip road leaves the outer edge of a carriageway at sJoin and climbs to
// the overpass deck at sTop; u runs 0 → 1 between them.
const DECK = 7.6;       // deck surface above the highway, m
const DECK_HALF = 6;    // half the overpass width, m
const RAMP_HALF = 3.5;  // half the slip-road width, m
const smooth = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
function slipRoads(c) {
  return [
    { side: 1, sJoin: c - 360, sTop: c - 5 },   // our exit
    { side: 1, sJoin: c + 360, sTop: c + 5 },   // our entry
    { side: -1, sJoin: c + 360, sTop: c + 5 },  // oncoming exit
    { side: -1, sJoin: c - 360, sTop: c - 5 },  // oncoming entry
  ].map((r) => {
    const edge = r.side > 0 ? LAYOUT.roadR : -LAYOUT.oncL;
    const u = (s) => Math.min(1, Math.max(0, (s - r.sJoin) / (r.sTop - r.sJoin)));
    return {
      ...r,
      a: Math.min(r.sJoin, r.sTop),
      b: Math.max(r.sJoin, r.sTop),
      u,
      center: (s) => r.side * (edge + 3.4 + 62 * u(s) ** 2),
      height: (s) => DECK * smooth((u(s) - 0.12) / 0.88),
    };
  });
}
// The cross road's height along its own length (it comes down to the ground past the verges).
const INTERCHANGE_CLEAR = 420; // no trees this close to an overpass
const deckProfile = (d) => 0.4 + (DECK - 0.4) * (1 - smooth((Math.abs(d) - 120) / 55));

function canvasTex(w, h, draw, wrap = true) {
  const c = document.createElement('canvas');
  c.width = w;
  c.height = h;
  draw(c.getContext('2d'), w, h);
  const t = new THREE.CanvasTexture(c);
  t.colorSpace = THREE.SRGBColorSpace;
  t.anisotropy = 16;
  if (wrap) t.wrapS = t.wrapT = THREE.RepeatWrapping;
  return t;
}

function speckle(ctx, w, h, base, amount) {
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, w, h);
  const img = ctx.getImageData(0, 0, w, h);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * amount;
    img.data[i] += n; img.data[i + 1] += n; img.data[i + 2] += n;
  }
  ctx.putImageData(img, 0, 0);
}

// Asphalt with lane markings. u spans one carriageway (narrow shoulder → wide shoulder), v spans 24 m.
function roadTexture() {
  const width = LAYOUT.roadR - LAYOUT.roadL;
  const t = canvasTex(1024, 2048, (ctx, w, h) => {
    speckle(ctx, w, h, '#a8a6a1', 9);
    const px = (d) => ((d - LAYOUT.roadL) / width) * w;
    const line = (d, wide = 0.15) => ctx.fillRect(px(d) - (wide / width) * w / 2, 0, (wide / width) * w, h);
    ctx.fillStyle = 'rgba(255,255,255,0.12)';
    ctx.fillRect(0, 0, px(-5.55), h);
    ctx.fillRect(px(5.55), 0, w - px(5.55), h);
    ctx.fillStyle = '#fbfbf9';
    line(-5.55);
    line(5.55);
    // 3 m dashes every 12 m → two per 24 m tile
    for (const d of [-1.85, 1.85]) {
      for (const v0 of [0, 0.5]) ctx.fillRect(px(d) - (0.15 / width) * w / 2, v0 * h, (0.15 / width) * w, h * (3 / 24));
    }
  });
  t.wrapS = THREE.ClampToEdgeWrapping;
  return t;
}

// Plain asphalt with an edge line on both sides, for slip roads and the overpass.
function laneTexture() {
  return canvasTex(256, 1024, (ctx, w, h) => {
    speckle(ctx, w, h, '#a8a6a1', 9);
    ctx.fillStyle = '#fbfbf9';
    ctx.fillRect(w * 0.05, 0, w * 0.025, h);
    ctx.fillRect(w * 0.925, 0, w * 0.025, h);
  });
}

// Corner warning board: primary-red chevrons on white, pointing left or right.
function chevronTexture(dir) {
  return canvasTex(256, 256, (ctx, w, h) => {
    ctx.fillStyle = '#fbfaf8';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#d23437';
    for (const x0 of [0.3, 0.62]) {
      ctx.beginPath();
      const tip = dir < 0 ? x0 - 0.16 : x0 + 0.16;
      ctx.moveTo(tip * w, 0.5 * h);
      ctx.lineTo(x0 * w, 0.14 * h);
      ctx.lineTo((x0 + 0.12 * Math.sign(dir)) * w, 0.14 * h);
      ctx.lineTo((tip + 0.12 * Math.sign(dir)) * w, 0.5 * h);
      ctx.lineTo((x0 + 0.12 * Math.sign(dir)) * w, 0.86 * h);
      ctx.lineTo(x0 * w, 0.86 * h);
      ctx.closePath();
      ctx.fill();
    }
  }, false);
}

function materials() {
  const groundMap = canvasTex(1024, 1024, (ctx, w, h) => speckle(ctx, w, h, '#e6e3dc', 8));
  return {
    road: new THREE.MeshStandardMaterial({ map: roadTexture(), roughness: 0.82 }),
    lane: new THREE.MeshStandardMaterial({ map: laneTexture(), roughness: 0.82 }),
    wall: new THREE.MeshStandardMaterial({ color: '#e4e1db', roughness: 0.7, side: THREE.DoubleSide }),
    chevL: new THREE.MeshStandardMaterial({ map: chevronTexture(-1), roughness: 0.5 }),
    chevR: new THREE.MeshStandardMaterial({ map: chevronTexture(1), roughness: 0.5 }),
    ground: new THREE.MeshStandardMaterial({ map: groundMap, roughness: 0.95 }),
    gravel: new THREE.MeshStandardMaterial({ color: '#d6d2ca', roughness: 0.95 }),
    concrete: new THREE.MeshStandardMaterial({ color: '#e4e1db', roughness: 0.7 }),
    steel: new THREE.MeshStandardMaterial({ color: '#b6b9bd', roughness: 0.32, metalness: 0.75, side: THREE.DoubleSide }),
    canopy: new THREE.MeshStandardMaterial({ color: '#d4d7c9', roughness: 0.9, flatShading: true }),
    trunk: new THREE.MeshStandardMaterial({ color: '#b5ad9f', roughness: 0.9 }),
    lampHead: new THREE.MeshStandardMaterial({ color: '#f6f5f2', emissive: '#ffffff', emissiveIntensity: 0.25 }),
    signFrame: new THREE.MeshStandardMaterial({ color: '#9fa3a8', roughness: 0.35, metalness: 0.7 }),
  };
}

const GEO = {
  post: new THREE.BoxGeometry(0.12, 0.9, 0.12),
  pole: new THREE.CylinderGeometry(0.09, 0.14, 10, 10),
  arm: new THREE.BoxGeometry(0.1, 0.1, 4.6),
  head: new THREE.BoxGeometry(0.75, 0.12, 0.3),
  canopy: new THREE.IcosahedronGeometry(1, 0),
  board: new THREE.PlaneGeometry(0.9, 0.9),
  trunk: new THREE.CylinderGeometry(0.12, 0.18, 1, 6),
};

// Triangle strip across the road. cols: [{ d, dy }], uv(colIndex, d, s) → [u, v].
function strip(samples, cols, uv) {
  const pos = [], uvs = [], idx = [];
  const n = cols.length;
  samples.forEach((m) => {
    cols.forEach((c, k) => {
      const dy = typeof c.dy === 'function' ? c.dy(m.s) : c.dy;
      const d = typeof c.d === 'function' ? c.d(m.s) : c.d;
      pos.push(m.x + m.rx * d, m.y + dy, m.z + m.rz * d);
      uvs.push(...uv(k, d, m.s));
    });
  });
  for (let i = 0; i < samples.length - 1; i++) {
    for (let k = 0; k < n - 1; k++) {
      // a/b step across the road (left → right), c/d are the next cross-section ahead: counter-clockwise from above.
      const a = i * n + k, b = a + 1, c = a + n, d = c + 1;
      idx.push(a, b, c, b, d, c);
    }
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uvs, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return g;
}

function gantryTexture(km) {
  return canvasTex(1024, 384, (ctx, w, h) => {
    ctx.fillStyle = '#fbfaf8';
    ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#d23437';
    ctx.fillRect(0, 0, 18, h);
    ctx.fillStyle = '#121316';
    ctx.font = '400 64px Crosner, Pretendard, sans-serif';
    ctx.textBaseline = 'alphabetic';
    ctx.fillText('MISSION T', 64, 120);
    ctx.font = '300 150px Pretendard, sans-serif';
    ctx.fillText(`${km}`, 64, 300);
    const wNum = ctx.measureText(`${km}`).width;
    ctx.font = '300 54px Pretendard, sans-serif';
    ctx.fillStyle = '#6b6e74';
    ctx.fillText('KM', 64 + wNum + 18, 300);
  }, false);
}

export class Scenery {
  constructor(road, seed) {
    this.road = road;
    this.seed = seed;
    this.group = new THREE.Group();
    this.chunks = new Map();
    this.mats = materials();
  }

  // Keep chunks built around the car, reaching further the way it faces (dir = ±1 along s).
  // budget caps how many new chunks are built per call, nearest first, so turning round doesn't hitch.
  update(sCar, dir = 1, budget = Infinity) {
    const fwd = 1500, back = 600;
    const first = Math.floor((sCar - (dir > 0 ? back : fwd)) / CHUNK);
    const last = Math.floor((sCar + (dir > 0 ? fwd : back)) / CHUNK);
    const missing = [];
    for (let i = first; i <= last; i++) if (!this.chunks.has(i)) missing.push(i);
    missing.sort((a, b) => Math.abs((a + 0.5) * CHUNK - sCar) - Math.abs((b + 0.5) * CHUNK - sCar));
    for (const i of missing.slice(0, budget)) this.build(i);
    const keepLo = Math.floor((sCar - 1700) / CHUNK), keepHi = Math.floor((sCar + 1700) / CHUNK);
    for (const [i, c] of this.chunks) {
      if (i < keepLo || i > keepHi) {
        this.group.remove(c.group);
        c.dispose();
        this.chunks.delete(i);
      }
    }
  }

  rebase(dx, dz) {
    for (const c of this.chunks.values()) {
      c.group.position.x -= dx;
      c.group.position.z -= dz;
    }
  }

  clear() {
    for (const c of this.chunks.values()) {
      this.group.remove(c.group);
      c.dispose();
    }
    this.chunks.clear();
  }

  build(index) {
    const road = this.road;
    const L = LAYOUT;
    const s0 = index * CHUNK, s1 = s0 + CHUNK;
    road.ensure(s1 + 4);
    const samples = [];
    for (let s = s0; s <= s1 + 1e-6; s += SEG) samples.push({ s, ...road.frame(s) });
    const g = new THREE.Group();
    const own = [];
    const mesh = (geo, mat, { cast = false, receive = true } = {}) => {
      own.push(geo);
      const m = new THREE.Mesh(geo, mat);
      m.castShadow = cast;
      m.receiveShadow = receive;
      g.add(m);
      return m;
    };
    const M = this.mats;
    const width = L.roadR - L.roadL;
    const dummy = new THREE.Object3D();
    // Samples between a and b, clipped to this chunk.
    const span = (a, b) => {
      const lo = Math.max(a, s0), hi = Math.min(b, s1);
      if (hi - lo < 0.5) return [];
      const out = [];
      for (let s = lo; s < hi; s += SEG) out.push({ s, ...road.frame(s) });
      out.push({ s: hi, ...road.frame(hi) });
      return out;
    };
    const centres = road.interchangesIn(s0, s1);
    const ramps = centres.flatMap(slipRoads);
    const nearBridge = (s, margin) => centres.some((c) => Math.abs(s - c) < margin);
    // Where a slip road peels away, the carriageway's outer guardrail opens up.
    const gap = (side, s) => ramps.some((r) => r.side === side && s >= r.a && s <= r.b && r.u(s) < 0.16);

    // Carriageways
    mesh(strip(samples, [{ d: L.roadL, dy: 0 }, { d: L.roadR, dy: 0 }], (k, d, s) => [(d - L.roadL) / width, s / 24]), M.road);
    mesh(strip(samples, [{ d: L.oncL, dy: 0 }, { d: L.oncR, dy: 0 }], (k, d, s) => [(L.oncR - d) / width, s / 24]), M.road);
    mesh(strip(samples, [{ d: L.oncR, dy: -0.02 }, { d: L.roadL, dy: -0.02 }], (k, d, s) => [d, s]), M.gravel);

    // Median barrier (concrete safety profile)
    const prof = [[-0.32, 0], [-0.22, 0.26], [-0.08, 0.82], [0.08, 0.82], [0.22, 0.26], [0.32, 0]];
    mesh(strip(samples, prof.map(([o, h]) => ({ d: L.median + o, dy: h })), (k, d, s) => [k / 5, s / 4]), M.concrete, { cast: true });

    // Guardrails: a steel beam on posts, broken where a slip road leaves or joins
    const rail = (list, d, dy = 0) => {
      if (list.length > 1) mesh(strip(list, [{ d, dy: typeof dy === 'function' ? (s) => dy(s) + 0.5 : dy + 0.5 }, { d, dy: typeof dy === 'function' ? (s) => dy(s) + 0.86 : dy + 0.86 }], (k, dd, s) => [k, s]), M.steel, { cast: true });
    };
    for (const [d, side] of [[L.guardR, 1], [L.guardL, -1]]) {
      let run = [];
      for (const m of samples) {
        if (gap(side, m.s)) { rail(run, d); run = []; } else run.push(m);
      }
      rail(run, d);
    }
    const posts = new THREE.InstancedMesh(GEO.post, M.steel, samples.length * 2);
    let pi = 0;
    for (const m of samples) {
      for (const [d, side] of [[L.guardR + 0.12, 1], [L.guardL - 0.12, -1]]) {
        if (gap(side, m.s)) continue;
        dummy.position.set(m.x + m.rx * d, m.y + 0.45, m.z + m.rz * d);
        dummy.rotation.set(0, m.h, 0);
        dummy.updateMatrix();
        posts.setMatrixAt(pi++, dummy.matrix);
      }
    }
    posts.count = pi;
    posts.castShadow = true;
    g.add(posts);

    // Verges with gentle rolling ground
    const roll = (d) => (s) => 1.8 * Math.sin(s * 0.013 + d * 0.07) * Math.sin(s * 0.0041 - d * 0.031) * Math.min(1, Math.abs(d) / 40);
    const right = [8.6, 9.8, 14, 26, 50, 90, 170].map((d, k) => ({ d, dy: k < 2 ? -0.05 * k : roll(d) }));
    const left = [-175, -105, -64, -40, -28, -24.4, -23.2].map((d, k) => ({ d, dy: k > 4 ? -0.05 * (6 - k) : roll(d) }));
    mesh(strip(samples, right, (k, d, s) => [d / 18, s / 18]), M.ground);
    mesh(strip(samples, left, (k, d, s) => [d / 18, s / 18]), M.ground);

    // Median lamp posts every 60 m
    const lamps = [];
    for (let s = Math.ceil(s0 / 60) * 60; s < s1; s += 60) if (!nearBridge(s, 12)) lamps.push(road.frame(s));
    if (lamps.length) {
      const poles = new THREE.InstancedMesh(GEO.pole, M.steel, lamps.length);
      const arms = new THREE.InstancedMesh(GEO.arm, M.steel, lamps.length);
      const heads = new THREE.InstancedMesh(GEO.head, M.lampHead, lamps.length * 2);
      lamps.forEach((m, i) => {
        const bx = m.x + m.rx * L.median, bz = m.z + m.rz * L.median;
        dummy.position.set(bx, m.y + 5, bz); dummy.rotation.set(0, m.h, 0); dummy.updateMatrix();
        poles.setMatrixAt(i, dummy.matrix);
        dummy.position.set(bx, m.y + 9.9, bz); dummy.updateMatrix();
        arms.setMatrixAt(i, dummy.matrix);
        for (const [k, o] of [[0, 2.2], [1, -2.2]]) {
          dummy.position.set(bx + m.rx * o, m.y + 9.82, bz + m.rz * o); dummy.updateMatrix();
          heads.setMatrixAt(i * 2 + k, dummy.matrix);
        }
      });
      poles.castShadow = arms.castShadow = true;
      g.add(poles, arms, heads);
    }

    // Trees scattered on both verges
    const rand = rng(this.seed * 7919 + index * 104729);
    const trees = [];
    for (let k = 0; k < 44; k++) {
      const s = s0 + rand() * CHUNK;
      const sideR = k % 2 === 0;
      const d = sideR ? 15 + rand() * 95 : -(30 + rand() * 95);
      if (nearBridge(s, INTERCHANGE_CLEAR) && Math.abs(d) < 115) continue;
      trees.push({ m: road.frame(s), s, d, r: 1.1 + rand() * 1.1, h: 1.6 + rand() * 1.2, yaw: rand() * 6.28 });
    }
    const canopies = new THREE.InstancedMesh(GEO.canopy, M.canopy, trees.length);
    const trunks = new THREE.InstancedMesh(GEO.trunk, M.trunk, trees.length);
    trees.forEach((t, i) => {
      const x = t.m.x + t.m.rx * t.d, z = t.m.z + t.m.rz * t.d;
      const ground = t.m.y + roll(t.d)(t.s);
      dummy.position.set(x, ground + t.h + t.r * 0.7, z);
      dummy.rotation.set(0, t.yaw, 0);
      dummy.scale.set(t.r, t.r * 1.25, t.r);
      dummy.updateMatrix();
      canopies.setMatrixAt(i, dummy.matrix);
      dummy.position.set(x, ground + t.h / 2, z);
      dummy.scale.set(1, t.h, 1);
      dummy.updateMatrix();
      trunks.setMatrixAt(i, dummy.matrix);
    });
    dummy.scale.set(1, 1, 1);
    canopies.castShadow = trunks.castShadow = true;
    g.add(canopies, trunks);

    // Kilometre gantry
    let signTex = null, signMat = null;
    const km = Math.ceil(s0 / 1000) * 1000;
    if (km !== 0 && km >= s0 && km < s1 && !nearBridge(km, 40)) {
      const m = road.frame(km);
      const post = (d) => {
        const geo = new THREE.BoxGeometry(0.28, 7.4, 0.28);
        const p = mesh(geo, M.signFrame, { cast: true });
        p.position.set(m.x + m.rx * d, m.y + 3.7, m.z + m.rz * d);
        p.rotation.y = m.h;
      };
      post(-6.9);
      post(9.4);
      const beamGeo = new THREE.BoxGeometry(0.3, 0.3, 16.3);
      const beam = mesh(beamGeo, M.signFrame, { cast: true });
      beam.position.set(m.x + m.rx * 1.25, m.y + 7.2, m.z + m.rz * 1.25);
      beam.rotation.y = m.h;
      signTex = gantryTexture(Math.abs(km) / 1000);
      signMat = new THREE.MeshStandardMaterial({ map: signTex, roughness: 0.6 });
      const panelGeo = new THREE.PlaneGeometry(5.6, 2.1);
      const panel = mesh(panelGeo, signMat, { cast: true });
      panel.position.set(m.x + m.rx * 1.85 - m.fx * 0.2, m.y + 7.4, m.z + m.rz * 1.85 - m.fz * 0.2);
      panel.rotation.y = m.h - Math.PI / 2; // face oncoming drivers (toward -forward)
    }

    // Interchanges: slip roads climbing to an overpass that crosses the highway.
    for (const r of ramps) {
      const list = span(r.a, r.b);
      if (list.length < 2) continue;
      const c = r.center, h = (s) => r.height(s) + 0.012;
      const left = (s) => c(s) - RAMP_HALF, right = (s) => c(s) + RAMP_HALF;
      mesh(strip(list, [{ d: left, dy: h }, { d: right, dy: h }], (k, d, s) => [k, s / 24]), M.lane, { cast: true });
      mesh(strip(list, [{ d: (s) => left(s) - 0.3, dy: -0.4 }, { d: left, dy: h }], (k, d, s) => [k, s / 8]), M.concrete);
      mesh(strip(list, [{ d: right, dy: h }, { d: (s) => right(s) + 0.3, dy: -0.4 }], (k, d, s) => [k, s / 8]), M.concrete);
      rail(list, (s) => c(s) + r.side * (RAMP_HALF - 0.1), h);
      rail(list.filter((m) => r.u(m.s) >= 0.16), (s) => c(s) - r.side * (RAMP_HALF - 0.1), h);
    }
    for (const cs of centres) {
      if (cs < s0 || cs >= s1) continue;
      const m = road.frame(cs);
      // Samples running along the cross road; its "right" is the highway's backward direction.
      const cross = [];
      for (let d = -175; d <= 175; d += 5) {
        cross.push({ s: d, x: m.x + m.rx * d, y: m.y + deckProfile(d), z: m.z + m.rz * d, rx: -m.fx, rz: -m.fz });
      }
      mesh(strip(cross, [{ d: -DECK_HALF, dy: 0 }, { d: DECK_HALF, dy: 0 }], (k, d, s) => [k, s / 24]), M.lane, { cast: true });
      const raised = cross.filter((p) => Math.abs(p.s) <= 150);
      mesh(strip(raised, [{ d: DECK_HALF, dy: -1.2 }, { d: -DECK_HALF, dy: -1.2 }], (k, d, s) => [k, s]), M.concrete);
      for (const side of [-1, 1]) {
        const o = side * DECK_HALF;
        mesh(strip(raised, [{ d: o, dy: -1.2 }, { d: o, dy: 0 }], (k, d, s) => [k, s / 8]), M.wall, { cast: true });
        mesh(strip(cross, [{ d: o, dy: 0 }, { d: o, dy: 1.0 }], (k, d, s) => [k, s / 8]), M.wall, { cast: true });
      }
      for (const d of [L.median, 13, -27, 45, -48, 78, -95, 108, -118]) {
        const hgt = m.y + deckProfile(d) - 1.2;
        const pier = mesh(new THREE.BoxGeometry(DECK_HALF * 1.5, hgt - m.y + 2, 1.4), M.concrete, { cast: true });
        pier.position.set(m.x + m.rx * d, (hgt + m.y - 2) / 2, m.z + m.rz * d);
        pier.rotation.y = m.h;
      }
    }

    // Chevron boards on the outside of tight corners, facing our traffic
    const chevL = [], chevR = [];
    for (let s = Math.ceil(s0 / 28) * 28; s < s1; s += 28) {
      const k = road.curvature(s);
      if (Math.abs(k) < 1 / 450) continue;
      const m = road.frame(s);
      // Left bends: on the right guardrail. Right bends: on top of the median barrier.
      const d = k > 0 ? L.guardR + 0.3 : L.median + 0.4;
      const list = k > 0 ? chevL : chevR;
      list.push({ x: m.x + m.rx * d, y: m.y + (k > 0 ? 1.45 : 1.3), z: m.z + m.rz * d, h: m.h });
    }
    for (const [list, mat] of [[chevL, M.chevL], [chevR, M.chevR]]) {
      if (!list.length) continue;
      const boards = new THREE.InstancedMesh(GEO.board, mat, list.length);
      list.forEach((b, i) => {
        dummy.position.set(b.x, b.y, b.z);
        dummy.rotation.set(0, b.h - Math.PI / 2, 0);
        dummy.updateMatrix();
        boards.setMatrixAt(i, dummy.matrix);
      });
      boards.castShadow = true;
      g.add(boards);
    }

    this.group.add(g);
    const instanced = g.children.filter((c) => c.isInstancedMesh);
    this.chunks.set(index, {
      group: g,
      dispose() {
        for (const geo of own) geo.dispose();
        for (const im of instanced) im.dispose();
        signTex?.dispose();
        signMat?.dispose();
      },
    });
  }
}
