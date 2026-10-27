import * as THREE from 'three';
import { buildVehicleModel } from '../src/car-model.js';

// Renders a course from assets/tracks/<id>.json in the game's look: pale terrain that follows the
// road, speckled asphalt with white edge lines, red-and-white kerbs on the corners, gravel run-off,
// low concrete walls, low-poly trees and the Vertigo cars on the grid.
//   tools/track-preview.html?track=ridgeline&view=map|hero|climb|overview[&save=http://localhost:5181]
const q = new URLSearchParams(location.search);
const TRACK = q.get('track') || 'ridgeline';
const VIEW = q.get('view') || 'hero';
const W = +(q.get('w') || 1920), H = +(q.get('h') || 1080);
const C = {
  bg: '#f4f3f0', asphalt: '#a8a6a1', line: '#fbfbf9', ground: '#e6e3dc', gravel: '#d6d2ca',
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
    const n = (Math.random() - 0.5) * amount;
    img.data[i] += n; img.data[i + 1] += n; img.data[i + 2] += n;
  }
  ctx.putImageData(img, 0, 0);
}
const rand = (() => { let s = 7; return () => (s = (Math.imul(s, 1664525) + 1013904223) >>> 0) / 4294967296; })();

const data = await (await fetch(`assets/tracks/${TRACK}.json`)).json();
const P = data.points.map(([x, y, z, wr, wl]) => ({ x, y, z, wr, wl }));
const n = P.length;
// Heading, right-hand normal and curvature at each point (closed loop).
for (let i = 0; i < n; i++) {
  const a = P[(i - 1 + n) % n], b = P[(i + 1) % n];
  const tx = b.x - a.x, tz = b.z - a.z, l = Math.hypot(tx, tz);
  P[i].tx = tx / l; P[i].tz = tz / l;
  P[i].rx = -P[i].tz; P[i].rz = P[i].tx; // right of travel (x east, z south)
  P[i].h = Math.atan2(-P[i].tz, P[i].tx);
}
for (let i = 0; i < n; i++) {
  const a = P[(i - 3 + n) % n], b = P[(i + 3) % n];
  let dh = b.h - a.h;
  dh = Math.atan2(Math.sin(dh), Math.cos(dh));
  P[i].k = dh / 30; // 1/m, positive = turning left
  const g = P[(i + 2) % n], f = P[(i - 2 + n) % n];
  P[i].grade = (g.y - f.y) / 20;
}
const edge = (p, d, up = 0) => new THREE.Vector3(p.x + p.rx * d, p.y + up, p.z + p.rz * d);

// ---------- renderer & scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true, preserveDrawingBuffer: true });
renderer.setPixelRatio(1);
renderer.setSize(W, H);
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = VIEW === 'map' || VIEW === 'overview' ? 0.82 : 0.92;
document.body.appendChild(renderer.domElement);
const scene = new THREE.Scene();
scene.background = new THREE.Color(C.bg);
const { RoomEnvironment } = await import('three/addons/environments/RoomEnvironment.js');
scene.environment = new THREE.PMREMGenerator(renderer).fromScene(new RoomEnvironment(), 0.04).texture;
scene.add(new THREE.HemisphereLight('#ffffff', '#d9d6d0', 0.9));
const sun = new THREE.DirectionalLight('#ffffff', 2.2);
sun.castShadow = true;
sun.shadow.bias = -0.0004;
scene.add(sun, sun.target);

const mesh = (geo, mat, { cast = false, receive = true } = {}) => {
  const m = new THREE.Mesh(geo, mat);
  m.castShadow = cast; m.receiveShadow = receive;
  scene.add(m);
  return m;
};
// A strip along the course: cols(p) → list of [offset across, height] pairs; v runs along in metres.
function ribbon(cols, mat, { from = 0, to = n, vScale = 1 / 24, cast = false } = {}) {
  const pos = [], uv = [], idx = [];
  let s = 0, rows = 0;
  for (let j = from; j <= to; j++) {
    const p = P[j % n];
    if (j > from) { const o = P[(j - 1) % n]; s += Math.hypot(p.x - o.x, p.z - o.z); }
    const cs = cols(p);
    cs.forEach(([d, up], k) => { const v = edge(p, d, up); pos.push(v.x, v.y, v.z); uv.push(k / (cs.length - 1), s * vScale); });
    rows++;
  }
  const m = cols(P[0]).length;
  for (let r = 0; r < rows - 1; r++) for (let k = 0; k < m - 1; k++) {
    const a = r * m + k, b = a + 1, c = a + m, d = c + 1;
    idx.push(a, b, c, b, d, c); // counter-clockwise from above, like the game's road strips
  }
  const g = new THREE.BufferGeometry();
  g.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  g.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  g.setIndex(idx);
  g.computeVertexNormals();
  return mesh(g, mat, { cast });
}

// ---------- terrain that follows the road ----------
let minX = Infinity, maxX = -Infinity, minZ = Infinity, maxZ = -Infinity;
for (const p of P) { minX = Math.min(minX, p.x); maxX = Math.max(maxX, p.x); minZ = Math.min(minZ, p.z); maxZ = Math.max(maxZ, p.z); }
const pad = VIEW === 'map' ? 900 : 520;
const cx = (minX + maxX) / 2, cz = (minZ + maxZ) / 2, sx = maxX - minX + pad * 2, sz = maxZ - minZ + pad * 2;
const coarse = P.filter((_, i) => i % 6 === 0);
const CELL = 40, cells = new Map();
for (const p of P) {
  const key = `${Math.floor(p.x / CELL)},${Math.floor(p.z / CELL)}`;
  if (!cells.has(key)) cells.set(key, []);
  cells.get(key).push(p);
}
// The nearest course point (exact within ~80 m, else null).
function nearest(x, z) {
  const gx = Math.floor(x / CELL), gz = Math.floor(z / CELL);
  let best = null, bd = Infinity;
  for (let a = -2; a <= 2; a++) for (let b = -2; b <= 2; b++) {
    for (const p of cells.get(`${gx + a},${gz + b}`) || []) {
      const d = (p.x - x) ** 2 + (p.z - z) ** 2;
      if (d < bd) { bd = d; best = p; }
    }
  }
  return best && { p: best, d: Math.sqrt(bd) };
}
const smooth01 = (t) => (t <= 0 ? 0 : t >= 1 ? 1 : t * t * (3 - 2 * t));
// Height of the land: always under the nearest road, blending into a smooth fit of the course's
// heights further out, so the road never sinks into a hillside.
function landAt(x, z) {
  let ws = 0, hs = 0, far = Infinity;
  for (const p of coarse) {
    const d2 = (p.x - x) ** 2 + (p.z - z) ** 2;
    far = Math.min(far, d2);
    const w = 1 / (d2 + 400) ** 1.6;
    ws += w; hs += w * p.y;
  }
  const fit = hs / ws, nb = nearest(x, z);
  if (!nb) return { h: fit - 0.4, d: Math.sqrt(far) };
  const edgeD = Math.max(0, nb.d - Math.max(nb.p.wl, nb.p.wr) - 8);
  const under = nb.p.y - 0.45 - edgeD * 0.04;
  const k = smooth01((nb.d - 30) / 110);
  return { h: Math.min(under + k * 40, under * (1 - k) + (fit - 0.4) * k), d: nb.d };
}
{
  const seg = 280;
  const g = new THREE.PlaneGeometry(sx, sz, seg, Math.round((seg * sz) / sx));
  g.rotateX(-Math.PI / 2);
  const pa = g.attributes.position;
  for (let i = 0; i < pa.count; i++) {
    const x = pa.getX(i) + cx, z = pa.getZ(i) + cz;
    const { h, d } = landAt(x, z);
    // Sit just under the road beside it; gentle rolling further out.
    const roll = Math.sin(x * 0.006) * Math.cos(z * 0.005) * 4 * Math.min(1, Math.max(0, (d - 40) / 160));
    pa.setXYZ(i, x, h + roll, z);
  }
  g.computeVertexNormals();
  const map = canvasTex(1024, 1024, (ctx, w, h) => speckle(ctx, w, h, C.ground, 8));
  map.repeat.set(sx / 18, sz / 18);
  mesh(g, new THREE.MeshStandardMaterial({ map, roughness: 0.95 }));
}

// ---------- road, run-off, kerbs, walls, start line ----------
const roadMap = canvasTex(512, 1024, (ctx, w, h) => {
  speckle(ctx, w, h, C.asphalt, 9);
  ctx.fillStyle = C.line;
  ctx.fillRect(w * 0.025, 0, w * 0.018, h);
  ctx.fillRect(w * 0.957, 0, w * 0.018, h);
});
roadMap.wrapS = THREE.ClampToEdgeWrapping;
// From high up the asphalt is drawn a shade darker so the course reads against the pale land.
ribbon((p) => [[-p.wl, 0.02], [p.wr, 0.02]], new THREE.MeshStandardMaterial({ map: roadMap, roughness: 0.82, color: VIEW === 'map' || VIEW === 'overview' ? '#6f6d69' : '#ffffff' }));
// Gravel / run-off band and grass shoulder
const gravel = new THREE.MeshStandardMaterial({ color: C.gravel, roughness: 0.95 });
ribbon((p) => [[-p.wl - 7, -0.12], [-p.wl, 0.0]], gravel, { vScale: 1 / 8 });
ribbon((p) => [[p.wr, 0.0], [p.wr + 7, -0.12]], gravel, { vScale: 1 / 8 });
// Kerbs on both sides through corners (radius under ~170 m), red and white every 1.5 m.
const kerbMap = canvasTex(64, 256, (ctx, w, h) => {
  ctx.fillStyle = C.red; ctx.fillRect(0, 0, w, h / 2);
  ctx.fillStyle = '#fbfaf8'; ctx.fillRect(0, h / 2, w, h / 2);
});
const kerbMat = new THREE.MeshStandardMaterial({ map: kerbMap, roughness: 0.6 });
const runs = [];
for (let i = 0, start = -1; i <= n; i++) {
  const on = i < n && Math.abs(P[i].k) > 1 / 170;
  if (on && start < 0) start = i;
  if (!on && start >= 0) { if (i - start > 3) runs.push([Math.max(0, start - 3), Math.min(n - 1, i + 3)]); start = -1; }
}
for (const [a, b] of runs) {
  ribbon((p) => [[-p.wl - 1.3, 0.03], [-p.wl, 0.06]], kerbMat, { from: a, to: b, vScale: 1 / 3 });
  ribbon((p) => [[p.wr, 0.06], [p.wr + 1.3, 0.03]], kerbMat, { from: a, to: b, vScale: 1 / 3 });
}
// Low concrete walls past the run-off
const wall = new THREE.MeshStandardMaterial({ color: C.concrete, roughness: 0.7 });
for (const side of [-1, 1]) {
  ribbon((p) => { const d = side > 0 ? p.wr + 9 : -p.wl - 9; return [[d, -0.6], [d, 0.95]]; }, wall, { vScale: 1 / 6, cast: true });
}
// Start line: chequered across the road at point 0, a red gantry overhead, grid boxes behind.
{
  const p = P[0];
  const chk = canvasTex(512, 64, (ctx, w, h) => {
    for (let x = 0; x < 32; x++) for (let y = 0; y < 4; y++) { ctx.fillStyle = (x + y) % 2 ? C.ink : '#fbfaf8'; ctx.fillRect(x * 16, y * 16, 16, 16); }
  }, false);
  const width = p.wl + p.wr;
  const line = mesh(new THREE.PlaneGeometry(width, 2.4), new THREE.MeshStandardMaterial({ map: chk, roughness: 0.8, polygonOffset: true, polygonOffsetFactor: -2 }));
  line.position.copy(edge(p, (p.wr - p.wl) / 2, 0.035));
  line.rotation.order = 'YXZ'; // lie flat, then turn its width across the road
  line.rotation.set(-Math.PI / 2, p.h - Math.PI / 2, 0);
  const steel = new THREE.MeshStandardMaterial({ color: '#9fa3a8', roughness: 0.35, metalness: 0.7 });
  for (const d of [-p.wl - 1, p.wr + 1]) {
    const post = mesh(new THREE.BoxGeometry(0.4, 8, 0.4), steel, { cast: true });
    post.position.copy(edge(p, d, 4));
  }
  const board = canvasTex(1024, 160, (ctx, w, h) => {
    ctx.fillStyle = C.red; ctx.fillRect(0, 0, w, h);
    ctx.fillStyle = '#fbfaf8'; ctx.font = '400 104px Crosner, Pretendard, sans-serif';
    ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(data.name.toUpperCase(), w / 2, h / 2 + 6);
  }, false);
  const beam = mesh(new THREE.BoxGeometry(width + 2.4, 1.6, 0.5), [steel, steel, steel, steel, new THREE.MeshStandardMaterial({ map: board }), new THREE.MeshStandardMaterial({ map: board })], { cast: true });
  beam.position.copy(edge(p, (p.wr - p.wl) / 2, 7.6));
  beam.rotation.y = p.h + Math.PI / 2;
  // grid boxes: two columns, 8 m apart
  const boxMat = new THREE.MeshBasicMaterial({ color: '#fbfbf9' });
  for (let k = 0; k < 6; k++) {
    const g = P[(n - 2 - k * 2 + n) % n];
    const d = (k % 2 ? 1 : -1) * 2.6 + (g.wr - g.wl) / 2;
    const bar = mesh(new THREE.PlaneGeometry(2.2, 0.25), boxMat);
    bar.position.copy(edge(g, d, 0.04));
    bar.rotation.order = 'YXZ';
    bar.rotation.set(-Math.PI / 2, g.h - Math.PI / 2, 0);
  }
}

// ---------- trees ----------
{
  const cell = 40, grid = new Map();
  for (const p of P) {
    const key = `${Math.floor(p.x / cell)},${Math.floor(p.z / cell)}`;
    if (!grid.has(key)) grid.set(key, []);
    grid.get(key).push(p);
  }
  const clear = (x, z) => {
    const gx = Math.floor(x / cell), gz = Math.floor(z / cell);
    for (let a = -1; a <= 1; a++) for (let b = -1; b <= 1; b++) {
      for (const p of grid.get(`${gx + a},${gz + b}`) || []) if ((p.x - x) ** 2 + (p.z - z) ** 2 < 26 * 26) return false;
    }
    return true;
  };
  const canopy = new THREE.InstancedMesh(new THREE.IcosahedronGeometry(1, 0), new THREE.MeshStandardMaterial({ color: C.canopy, roughness: 0.9, flatShading: true }), 2600);
  const trunk = new THREE.InstancedMesh(new THREE.CylinderGeometry(0.12, 0.18, 1, 6), new THREE.MeshStandardMaterial({ color: C.trunk, roughness: 0.9 }), 2600);
  canopy.castShadow = trunk.castShadow = true;
  const m = new THREE.Object3D();
  let count = 0;
  for (let tries = 0; count < 2600 && tries < 40000; tries++) {
    const x = cx + (rand() - 0.5) * sx * 0.96, z = cz + (rand() - 0.5) * sz * 0.96;
    if (!clear(x, z)) continue;
    // Forest in clumps
    if (Math.sin(x * 0.011 + 1.3) * Math.cos(z * 0.009) < -0.25 && rand() < 0.8) continue;
    const { h } = landAt(x, z);
    const s = 2.2 + rand() * 2.6, ht = 2 + rand() * 2.5;
    m.position.set(x, h - 0.5 + ht + s * 0.7, z); m.scale.set(s, s * (1.1 + rand() * 0.5), s); m.rotation.set(rand(), rand() * 6, 0); m.updateMatrix();
    canopy.setMatrixAt(count, m.matrix);
    m.position.set(x, h - 0.5 + ht / 2, z); m.scale.set(1, ht, 1); m.rotation.set(0, 0, 0); m.updateMatrix();
    trunk.setMatrixAt(count, m.matrix);
    count++;
  }
  canopy.count = trunk.count = count;
  scene.add(canopy, trunk);
}

// ---------- cars on the grid ----------
const ids = ['vertigo-gt', 'vertigo-arc', 'vertigo-apex', 'vertigo-grand', 'vertigo-terra'];
await Promise.all(ids.map(async (id, k) => {
  const built = await buildVehicleModel(id);
  const g = P[(n - 3 - k * 2 + n) % n];
  const d = (k % 2 ? 1 : -1) * 2.6 + (g.wr - g.wl) / 2;
  const car = new THREE.Group();
  car.rotation.order = 'YZX';
  car.add(built.holder);
  car.position.copy(edge(g, d, 0.62));
  car.rotation.set(0, g.h, Math.atan(g.grade));
  scene.add(car);
}));

// ---------- views ----------
let camera;
const steepest = P.reduce((best, p, i) => (p.grade > P[best].grade ? i : best), 0);
const look = (pos, at, fov = 38) => {
  camera = new THREE.PerspectiveCamera(fov, W / H, 1, 9000);
  camera.position.copy(pos);
  camera.lookAt(at);
};
const fog = (near, far) => { scene.fog = new THREE.Fog(C.bg, near, far); };
const sunAt = (target, span) => {
  sun.position.set(target.x + span * 0.6, target.y + span * 1.2, target.z + span * 0.45);
  sun.target.position.copy(target);
  const cam = sun.shadow.camera;
  cam.left = cam.bottom = -span; cam.right = cam.top = span; cam.near = 1; cam.far = span * 4;
  sun.shadow.mapSize.set(4096, 4096);
  cam.updateProjectionMatrix();
};
if (VIEW === 'map') {
  // Fit the course (plus a margin) to the frame, north up; a low sun shades the hills.
  const fx = maxX - minX + 360, fz = maxZ - minZ + 360;
  const span = Math.max(fx / W, fz / H) * 0.5;
  camera = new THREE.OrthographicCamera(-W * span, W * span, H * span, -H * span, 1, 5000);
  camera.position.set(cx, 2000, cz);
  camera.up.set(0, 0, -1);
  camera.lookAt(cx, 0, cz);
  const span2 = Math.max(sx, sz) * 0.6;
  sun.position.set(cx - span2 * 0.9, span2 * 0.75, cz - span2 * 0.5);
  sun.target.position.set(cx, 0, cz);
  Object.assign(sun.shadow.camera, { left: -span2, right: span2, top: span2, bottom: -span2, near: 1, far: span2 * 4 });
  sun.shadow.mapSize.set(8192, 8192);
  sun.shadow.camera.updateProjectionMatrix();
} else if (VIEW === 'overview') {
  const c = new THREE.Vector3(cx, 40, cz + 80);
  look(new THREE.Vector3(cx - 500, 820, cz + (maxZ - minZ) * 0.95), c, 44);
  sunAt(c, Math.max(sx, sz) * 0.6);
  fog(2600, 6500);
} else if (VIEW === 'climb') {
  // Low, from the bottom of the steepest climb, looking up it.
  const p = P[(steepest - 45 + n) % n], t = P[(steepest + 25) % n];
  const at = new THREE.Vector3(t.x, t.y + 1, t.z);
  look(new THREE.Vector3(p.x - p.rx * 9 - p.tx * 10, p.y + 3.2, p.z - p.rz * 9 - p.tz * 10), at, 44);
  sunAt(at, 260);
  fog(300, 1400);
} else {
  // hero: behind and above the grid, looking down to the first corner
  const g = P[(n - 14) % n], t = P[40 % n];
  const at = new THREE.Vector3(t.x, t.y, t.z);
  look(new THREE.Vector3(g.x - g.tx * 26 + g.rx * 12, g.y + 13, g.z - g.tz * 26 + g.rz * 12), at, 40);
  sunAt(new THREE.Vector3(P[0].x, P[0].y, P[0].z), 240);
  fog(260, 1500);
}
renderer.render(scene, camera);
window.__track = { length: data.length, climb: data.climb, steepest: { i: steepest, grade: P[steepest].grade } };

const save = q.get('save');
if (save) {
  const url = renderer.domElement.toDataURL('image/png');
  await fetch(`${save}/save?name=${encodeURIComponent(`${TRACK}-${VIEW}`)}`, { method: 'POST', body: url });
}
window.__done = true;
