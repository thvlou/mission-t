import * as THREE from 'three';
import { RoundedBoxGeometry } from 'three/addons/geometries/RoundedBoxGeometry.js';
import { DECK, DECK_WIDTH, CHALLENGES, OBSTACLES } from './config.js';

function canvasTexture(size, draw, repeat = [1, 1]) {
  const c = document.createElement('canvas');
  c.width = c.height = size;
  draw(c.getContext('2d'), size);
  const tex = new THREE.CanvasTexture(c);
  tex.wrapS = tex.wrapT = THREE.RepeatWrapping;
  tex.repeat.set(repeat[0], repeat[1]);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 16;
  return tex;
}

function speckle(ctx, size, base, amount) {
  ctx.fillStyle = base;
  ctx.fillRect(0, 0, size, size);
  const img = ctx.getImageData(0, 0, size, size);
  for (let i = 0; i < img.data.length; i += 4) {
    const n = (Math.random() - 0.5) * amount;
    img.data[i] += n;
    img.data[i + 1] += n;
    img.data[i + 2] += n;
  }
  ctx.putImageData(img, 0, 0);
}

const groundTex = () => canvasTexture(1024, (ctx, n) => {
  speckle(ctx, n, '#e9e7e2', 8);
  ctx.strokeStyle = 'rgba(18,19,22,0.05)';
  ctx.lineWidth = 3;
  ctx.strokeRect(0, 0, n, n);
}, [60, 20]);

const deckTex = () => canvasTexture(1024, (ctx, n) => {
  speckle(ctx, n, '#dcdad5', 10);
  ctx.fillStyle = 'rgba(18,19,22,0.12)';
  ctx.fillRect(0, 0, n, 6);
  for (let i = 0; i < 160; i++) {
    ctx.fillStyle = `rgba(255,255,255,${Math.random() * 0.05})`;
    ctx.fillRect(Math.random() * n, Math.random() * n, 2 + Math.random() * 20, 1);
  }
});

const roadTex = () => canvasTexture(1024, (ctx, n) => {
  speckle(ctx, n, '#d4d2cd', 8);
  ctx.fillStyle = 'rgba(18,19,22,0.35)';
  ctx.fillRect(n / 2 - 10, 0, 20, n / 2);
});

const zoneTex = (bull) => canvasTexture(2048, (ctx, n) => {
  ctx.clearRect(0, 0, n, n);
  ctx.fillStyle = 'rgba(210,52,55,0.08)';
  ctx.fillRect(0, 0, n, n);
  ctx.strokeStyle = '#d23437';
  ctx.lineWidth = 36;
  ctx.strokeRect(18, 18, n - 36, n - 36);
  ctx.save();
  ctx.beginPath();
  ctx.rect(18, 18, n - 36, n - 36);
  ctx.clip();
  ctx.strokeStyle = 'rgba(210,52,55,0.18)';
  ctx.lineWidth = 52;
  for (let i = -n; i < n * 2; i += 190) {
    ctx.beginPath();
    ctx.moveTo(i, 0);
    ctx.lineTo(i + n, n);
    ctx.stroke();
  }
  ctx.restore();
  const w = n * bull;
  ctx.fillStyle = 'rgba(210,52,55,0.28)';
  ctx.fillRect(n / 2 - w / 2, 0, w, n);
});

const corrugated = (color) => canvasTexture(256, (ctx, n) => {
  ctx.fillStyle = color;
  ctx.fillRect(0, 0, n, n);
  for (let x = 0; x < n; x += 16) {
    ctx.fillStyle = 'rgba(0,0,0,0.22)';
    ctx.fillRect(x, 0, 5, n);
    ctx.fillStyle = 'rgba(255,255,255,0.08)';
    ctx.fillRect(x + 7, 0, 3, n);
  }
  ctx.fillStyle = 'rgba(0,0,0,0.35)';
  ctx.fillRect(0, 0, n, 10);
  ctx.fillRect(0, n - 10, n, 10);
});

function label(text) {
  const c = document.createElement('canvas');
  c.width = 512;
  c.height = 256;
  const ctx = c.getContext('2d');
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  tex.anisotropy = 16;
  const draw = () => {
    ctx.clearRect(0, 0, c.width, c.height);
    ctx.font = '300 132px Pretendard, system-ui, sans-serif';
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = 'rgba(18,19,22,0.7)';
    ctx.fillText(text, 256, 128);
    tex.needsUpdate = true;
  };
  draw();
  document.fonts?.load('300 132px Pretendard').then(draw).catch(() => {});
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, transparent: true, depthWrite: false }));
  sprite.scale.set(2.4, 1.2, 1);
  return sprite;
}

// Triangle strip along the track samples. side(sample, edge) returns { p: [x,y,z], n: [x,y,z], uv: [u,v] }.
function strip(samples, side) {
  const pos = [], nor = [], uv = [], idx = [];
  samples.forEach((smp, i) => {
    for (const edge of [0, 1]) {
      const v = side(smp, edge);
      pos.push(...v.p);
      nor.push(...v.n);
      uv.push(...v.uv);
    }
    if (i < samples.length - 1) {
      const b = i * 2;
      idx.push(b, b + 1, b + 2, b + 1, b + 3, b + 2);
    }
  });
  const geo = new THREE.BufferGeometry();
  geo.setAttribute('position', new THREE.Float32BufferAttribute(pos, 3));
  geo.setAttribute('normal', new THREE.Float32BufferAttribute(nor, 3));
  geo.setAttribute('uv', new THREE.Float32BufferAttribute(uv, 2));
  geo.setIndex(idx);
  return geo;
}

export function buildWorld(track) {
  const group = new THREE.Group();
  const disposables = [];
  const keep = (...things) => { disposables.push(...things); return things[0]; };
  const half = DECK_WIDTH / 2;

  const ground = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(900, 300)),
    keep(new THREE.MeshStandardMaterial({ map: keep(groundTex()), roughness: 0.95 })),
  );
  ground.rotation.x = -Math.PI / 2;
  ground.receiveShadow = true;
  group.add(ground);

  // Run-in road
  const roadLen = track.curveStart;
  const road = new THREE.Mesh(
    keep(new THREE.PlaneGeometry(roadLen, DECK_WIDTH)),
    keep(new THREE.MeshStandardMaterial({ map: keep(roadTex()), roughness: 0.9 })),
  );
  road.material.map.repeat.set(roadLen / 6, 1);
  road.rotation.x = -Math.PI / 2;
  road.position.set(track.x0 + roadLen / 2, 0.01, 0);
  road.receiveShadow = true;
  group.add(road);

  // Raised deck, sampled every 0.25 m from just before the curve.
  const samples = [];
  const from = Math.max(0, track.curveStart - 0.5);
  for (let s = from; s <= track.length + 1e-6; s += 0.25) {
    const q = track.at(s);
    samples.push({ s, x: q.x, y: q.y, nx: -Math.sin(q.a), ny: Math.cos(q.a) });
  }
  const last = track.at(track.length);
  samples.push({ s: track.length, x: last.x, y: last.y, nx: -Math.sin(last.a), ny: Math.cos(last.a) });

  const deckMat = keep(new THREE.MeshStandardMaterial({ map: keep(deckTex()), roughness: 0.85, side: THREE.DoubleSide }));
  const faces = [
    (m, e) => ({ p: [m.x, m.y, e ? -half : half], n: [m.nx, m.ny, 0], uv: [m.s / 4, e] }),
    (m, e) => ({ p: [m.x - m.nx * DECK, m.y - m.ny * DECK, e ? half : -half], n: [-m.nx, -m.ny, 0], uv: [m.s / 4, e] }),
    (m, e) => ({ p: [m.x - m.nx * DECK * e, m.y - m.ny * DECK * e, half], n: [0, 0, 1], uv: [m.s / 4, e * 0.1] }),
    (m, e) => ({ p: [m.x - m.nx * DECK * (1 - e), m.y - m.ny * DECK * (1 - e), -half], n: [0, 0, -1], uv: [m.s / 4, e * 0.1] }),
  ];
  for (const f of faces) {
    const mesh = new THREE.Mesh(keep(strip(samples, f)), deckMat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    group.add(mesh);
  }

  // LED rails along both edges; their colours follow the furthest point reached.
  const railGeo = [];
  for (const z of [half - 0.12, -half + 0.12]) {
    const geo = keep(strip(samples, (m, e) => ({ p: [m.x + m.nx * 0.02, m.y + m.ny * 0.02, z + (e ? -0.07 : 0.07)], n: [m.nx, m.ny, 0], uv: [0, e] })));
    geo.setAttribute('color', new THREE.Float32BufferAttribute(new Float32Array(samples.length * 6), 3));
    railGeo.push(geo);
    group.add(new THREE.Mesh(geo, keep(new THREE.MeshBasicMaterial({ vertexColors: true, toneMapped: false, side: THREE.DoubleSide }))));
  }
  const lit = new THREE.Color('#d23437').multiplyScalar(1.6);
  const dim = new THREE.Color('#bdb9b2');
  let shown = null;
  const setProgress = (progress, t) => {
    const key = Math.round(progress * 4);
    if (key === shown && progress >= 0) return;
    shown = key;
    for (const geo of railGeo) {
      const col = geo.attributes.color;
      samples.forEach((m, i) => {
        let c;
        if (progress < 0) {
          // Idle: a slow chase pulse up the ramp.
          const wave = 0.5 + 0.5 * Math.sin(m.s * 0.9 - t * 4);
          c = dim.clone().lerp(lit, wave * 0.35);
        } else {
          c = m.s <= progress ? lit : dim;
        }
        col.setXYZ(i * 2, c.r, c.g, c.b);
        col.setXYZ(i * 2 + 1, c.r, c.g, c.b);
      });
      col.needsUpdate = true;
    }
  };

  // Steel supports
  const steel = keep(new THREE.MeshStandardMaterial({ color: '#9b9d9f', roughness: 0.5, metalness: 0.6 }));
  const bar = (x1, y1, x2, y2, z, thick = 0.18) => {
    const len = Math.hypot(x2 - x1, y2 - y1);
    if (len < 0.05) return;
    const m = new THREE.Mesh(keep(new THREE.BoxGeometry(len, thick, thick)), steel);
    m.position.set((x1 + x2) / 2, (y1 + y2) / 2, z);
    m.rotation.z = Math.atan2(y2 - y1, x2 - x1);
    m.castShadow = true;
    group.add(m);
  };
  // A braced tower stands behind the wall; the overhang hangs from it.
  const towerX = Math.max(...samples.map((m) => m.x)) + DECK + 1.6;
  const towerTop = track.top - 1;
  for (const m of samples) {
    if (Math.round(m.s / 0.25) % 8 !== 0 || m.y < 0.6) continue;
    const ux = m.x - m.nx * DECK, uy = m.y - m.ny * DECK;
    for (const z of [half - 0.3, -half + 0.3]) {
      if (m.ny > 0.35) bar(ux, uy, ux, 0, z);
      else if (m.ny > -0.35 && uy < towerTop + 0.5) bar(ux, uy, towerX, uy, z, 0.12);
      else if (m.ny > -0.35 || m.x > towerX - 6) bar(ux, uy, towerX, towerTop, z, 0.12);
    }
  }
  {
    for (const z of [half - 0.3, -half + 0.3]) {
      for (const x of [towerX, towerX + 2.6]) bar(x, 0, x, towerTop, z, 0.26);
      for (let y = 2.5; y < towerTop; y += 2.5) {
        bar(towerX, y, towerX + 2.6, y, z, 0.14);
        bar(towerX, y - 2.5, towerX + 2.6, y, z, 0.08);
      }
    }
    for (let y = 2.5; y < towerTop; y += 5) {
      for (const x of [towerX, towerX + 2.6]) {
        const m = new THREE.Mesh(keep(new THREE.BoxGeometry(0.14, 0.14, DECK_WIDTH - 0.8)), steel);
        m.position.set(x, y, 0);
        group.add(m);
      }
    }
  }

  // Landing zones, one per challenge; the active one is bright.
  const zones = {};
  const zoneTexture = keep(zoneTex(0.3));
  for (const ch of Object.values(CHALLENGES)) {
    const mesh = new THREE.Mesh(
      keep(new THREE.PlaneGeometry(ch.zone.half * 2, DECK_WIDTH + 3)),
      keep(new THREE.MeshBasicMaterial({ map: zoneTexture, transparent: true, depthWrite: false, opacity: 0.25 })),
    );
    mesh.rotation.x = -Math.PI / 2;
    mesh.position.set(ch.zone.x, 0.03, 0);
    group.add(mesh);
    zones[ch.key] = mesh;
  }
  const setChallenge = (key) => {
    for (const [k, mesh] of Object.entries(zones)) mesh.material.opacity = k === key ? 1 : 0.2;
  };

  // Parked vehicles on the run-in
  const wheelGeo = keep(new THREE.CylinderGeometry(0.36, 0.36, 0.26, 40));
  const rimGeo = keep(new THREE.CylinderGeometry(0.22, 0.22, 0.27, 32));
  const rimMat = keep(new THREE.MeshStandardMaterial({ color: '#c9ccd0', roughness: 0.25, metalness: 0.9 }));
  const tireMat = keep(new THREE.MeshStandardMaterial({ color: '#121316', roughness: 0.9 }));
  const glassMat = keep(new THREE.MeshPhysicalMaterial({ color: '#0d1116', roughness: 0.05, metalness: 0.2, clearcoat: 1, clearcoatRoughness: 0.03 }));
  const part = (mat, sx, sy, sz, x, y) => {
    const r = Math.min(0.14, sx * 0.2, sy * 0.3, sz * 0.2);
    const m = new THREE.Mesh(keep(new RoundedBoxGeometry(sx, sy, sz, 4, r)), mat);
    m.position.set(x, y, 0);
    m.castShadow = true;
    m.receiveShadow = true;
    return m;
  };
  for (const o of OBSTACLES) {
    const v = new THREE.Group();
    const L = o.length, H = o.height, W = o.width;
    const paint = keep(new THREE.MeshPhysicalMaterial({ color: o.color, roughness: 0.35, metalness: 0.25, clearcoat: 1, clearcoatRoughness: 0.08 }));
    const clear = 0.32; // ground clearance
    if (o.kind === 'truck') {
      v.add(part(paint, 1.9, H * 0.68 - clear, W, L / 2 - 0.95, clear + (H * 0.68 - clear) / 2));
      v.add(part(glassMat, 0.05, 0.7, W * 0.85, L / 2 - 0.02, H * 0.55));
      const cargo = keep(new THREE.MeshStandardMaterial({ map: keep(corrugated(o.color)), roughness: 0.6 }));
      v.add(part(cargo, L - 2.1, H - clear - 0.1, W, -1.05, clear + 0.1 + (H - clear - 0.1) / 2));
    } else {
      const deck = o.kind === 'pickup' ? 0.55 : 0.6;
      v.add(part(paint, L, H * deck - clear, W, 0, clear + (H * deck - clear) / 2));
      const cabLen = o.kind === 'pickup' ? L * 0.38 : L * 0.5;
      const cabX = o.kind === 'pickup' ? L * 0.08 : -L * 0.04;
      v.add(part(glassMat, cabLen, H * (1 - deck), W * 0.86, cabX, H * deck + (H * (1 - deck)) / 2));
    }
    for (const wx of [L / 2 - 0.85, -L / 2 + 0.85]) {
      for (const wz of [W / 2 - 0.12, -W / 2 + 0.12]) {
        const w = new THREE.Mesh(wheelGeo, tireMat);
        w.rotation.x = Math.PI / 2;
        w.position.set(wx, 0.36, wz);
        w.castShadow = true;
        const rim = new THREE.Mesh(rimGeo, rimMat);
        rim.rotation.x = Math.PI / 2;
        rim.position.copy(w.position);
        v.add(w, rim);
      }
    }
    // Parked side-on to the run-in would block it; these face along it, nose toward the ramp.
    v.position.set((o.x0 + o.x1) / 2, 0, 0);
    group.add(v);
  }

  // Distance markers every 10 m, measured back from the foot of the ramp.
  for (let d = 10; d <= 180; d += 10) {
    const x = -d;
    const post = new THREE.Mesh(keep(new THREE.BoxGeometry(0.08, 0.5, 0.08)), steel);
    post.position.set(x, 0.25, half + 1.8);
    group.add(post);
    const tag = label(`${d}m`);
    keep(tag.material.map, tag.material);
    tag.position.set(x, 1, half + 1.8);
    group.add(tag);
  }

  return {
    group,
    setProgress,
    setChallenge,
    dispose() {
      for (const d of disposables) d.dispose?.();
    },
  };
}
