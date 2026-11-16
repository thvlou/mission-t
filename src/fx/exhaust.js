import * as THREE from 'three';
import { NOISE } from './smoke.js';

// Boost fire out of a car's own tail pipes (the mouths found by car-model.js fitExhausts).
// Each pipe streams small fire puffs in the car's own space, so the flame stays on the pipe at any
// speed. A puff leaves the mouth white-hot and cools as it travels back: yellow, orange, deep red,
// then a wisp of soot, its edge torn by animated noise so the plume licks and flutters like real
// fire. Every car burns the same natural colours. set() picks the target (0 off, 'boost' a long
// steady flame, 'pop' a short, fat drift-boost burst); update() eases toward it and moves the puffs.
const vertex = /* glsl */ `
  attribute float size;
  attribute float age;
  attribute float seed;
  uniform float scale;
  varying float vAge;
  varying float vSeed;
  void main() {
    vAge = age;
    vSeed = seed;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = size * scale / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const fragment = /* glsl */ `
  uniform float uTime;
  varying float vAge;
  varying float vSeed;
  ${NOISE}
  vec3 ramp(float t) {                       // flame temperature 0 (soot) .. 1 (white-hot)
    vec3 soot = vec3(0.09, 0.08, 0.08), red = vec3(0.62, 0.07, 0.02), orange = vec3(1.0, 0.34, 0.05);
    vec3 yellow = vec3(1.0, 0.72, 0.24), white = vec3(1.0, 0.95, 0.82);
    if (t < 0.25) return mix(soot, red, t / 0.25);
    if (t < 0.5) return mix(red, orange, (t - 0.25) / 0.25);
    if (t < 0.75) return mix(orange, yellow, (t - 0.5) / 0.25);
    return mix(yellow, white, (t - 0.75) / 0.25);
  }
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    float n = fbm(p * 2.3 + vec2(vSeed * 19.0, uTime * 9.0 + vSeed * 5.0));
    float r = length(p) + (n - 0.5) * 0.8;
    float shape = smoothstep(1.0, 0.2, r);
    float temp = clamp(1.0 - vAge * 1.2 + (n - 0.5) * 0.4, 0.0, 1.0);
    float a = shape * smoothstep(1.0, 0.5, vAge) * mix(0.35, 1.0, smoothstep(0.1, 0.45, temp));
    if (a < 0.01) discard;
    gl_FragColor = vec4(ramp(temp) * (1.0 + 7.0 * temp * temp * temp), a);
  }`;

// Shared by every car's fire: the projection scale that turns a puff's size in metres into pixels.
const view = { value: 1000 };
export function setFireView(camera, heightPx) {
  view.value = heightPx / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
}

let glowTex = null;
function glowTexture() {
  if (glowTex) return glowTex;
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.3, 'rgba(255,255,255,0.4)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  glowTex = new THREE.CanvasTexture(c);
  glowTex.colorSpace = THREE.SRGBColorSpace;
  return glowTex;
}

const POOL = 480;
const KIND = {
  boost: { rate: 320, life: 0.24, speed: 11, grow: 7.5 },
  pop: { rate: 520, life: 0.13, speed: 8, grow: 9 },
};

export class ExhaustFlames {
  // parent: the car's holder (pipe mouths are in its space). theme: unused (fire is fire).
  constructor(parent, exhausts) {
    this.group = new THREE.Group();
    this.k = 1 / parent.scale.x; // metres → holder units
    parent.add(this.group);
    this.level = 0;
    this.target = 0;
    this.kind = 'boost';
    this.t = 0;
    this.pipes = exhausts.map((e) => ({ pos: e.pos.clone(), r: e.r, carry: 0 }));
    this.next = 0;
    this.off = new Float32Array(POOL * 3);   // metres from the mouth
    this.vel = new Float32Array(POOL * 3);
    this.from = new Int16Array(POOL);
    this.life = new Float32Array(POOL);
    this.max = new Float32Array(POOL);
    this.s0 = new Float32Array(POOL);
    this.s1 = new Float32Array(POOL);
    this.posA = new Float32Array(POOL * 3);
    this.sizeA = new Float32Array(POOL);
    this.ageA = new Float32Array(POOL).fill(1);
    this.seedA = new Float32Array(POOL);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.posA, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(this.sizeA, 1));
    geo.setAttribute('age', new THREE.BufferAttribute(this.ageA, 1));
    geo.setAttribute('seed', new THREE.BufferAttribute(this.seedA, 1));
    this.points = new THREE.Points(geo, new THREE.ShaderMaterial({
      vertexShader: vertex,
      fragmentShader: fragment,
      uniforms: { scale: view, uTime: { value: 0 } },
      transparent: true,
      depthWrite: false,
    }));
    this.points.frustumCulled = false;
    this.points.renderOrder = 3;
    this.group.add(this.points);
    // a warm glow on the pipe mouths while the fire burns
    this.glows = this.pipes.map((p) => {
      const s = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), color: new THREE.Color(3.2, 1.3, 0.35), transparent: true, depthWrite: false, toneMapped: false, blending: THREE.AdditiveBlending }));
      s.position.copy(p.pos);
      s.renderOrder = 3;
      this.group.add(s);
      return s;
    });
    this.alive = 0;
  }

  setTheme() {}

  // target 0..1; kind 'boost' (long steady flame) or 'pop' (short drift-boost burst)
  set(target, kind = 'boost') {
    this.target = target;
    if (target > 0) this.kind = kind;
  }

  spawn(pi) {
    const p = this.pipes[pi], K = KIND[this.kind], i = this.next;
    this.next = (this.next + 1) % POOL;
    const a = Math.random() * 6.283, rr = p.r * 0.5 * Math.sqrt(Math.random());
    this.off.set([0, Math.cos(a) * rr, Math.sin(a) * rr], i * 3);
    const sp = K.speed * (0.8 + Math.random() * 0.4) * (0.75 + 0.25 * this.level);
    this.vel.set([-sp, (Math.random() - 0.5) * 1.6, (Math.random() - 0.5) * 1.6], i * 3);
    this.from[i] = pi;
    this.life[i] = this.max[i] = K.life * (0.75 + Math.random() * 0.5) * (0.6 + 0.4 * this.level);
    this.s0[i] = p.r * 2.2;
    this.s1[i] = p.r * K.grow * (0.8 + Math.random() * 0.4);
    this.seedA[i] = Math.random();
  }

  update(dt, t) {
    dt = Math.min(0.05, Math.max(0, dt));
    this.t = t;
    const rate = this.target > this.level ? 22 : 9;
    this.level += (this.target - this.level) * (1 - Math.exp(-dt * rate));
    if (this.level > 0.03) {
      const per = KIND[this.kind].rate * this.level * dt;
      this.pipes.forEach((p, pi) => {
        p.carry += per;
        while (p.carry >= 1) { p.carry -= 1; this.spawn(pi); }
      });
    }
    const k = this.k;
    let alive = 0;
    for (let i = 0; i < POOL; i++) {
      if (this.life[i] <= 0) { this.ageA[i] = 1; this.sizeA[i] = 0; continue; }
      alive++;
      this.life[i] -= dt;
      const age = 1 - Math.max(0, this.life[i] / this.max[i]);
      const j = i * 3;
      this.vel[j] *= 1 - 1.0 * dt;            // the jet slows as it mixes with the air
      this.vel[j + 1] += 2.5 * dt;            // hot gas rises
      this.off[j] += this.vel[j] * dt;
      this.off[j + 1] += this.vel[j + 1] * dt;
      this.off[j + 2] += this.vel[j + 2] * dt;
      const m = this.pipes[this.from[i]].pos;
      this.posA[j] = m.x + this.off[j] * k;
      this.posA[j + 1] = m.y + this.off[j + 1] * k;
      this.posA[j + 2] = m.z + this.off[j + 2] * k;
      this.sizeA[i] = this.s0[i] + (this.s1[i] - this.s0[i]) * Math.sqrt(age);
      this.ageA[i] = age;
    }
    this.alive = alive;
    const g = this.points.geometry.attributes;
    g.position.needsUpdate = g.size.needsUpdate = g.age.needsUpdate = g.seed.needsUpdate = true;
    this.points.material.uniforms.uTime.value = t;
    const flick = 0.85 + 0.15 * Math.sin(t * 47) * Math.sin(t * 31 + 1.1);
    this.pipes.forEach((p, pi) => {
      const s = this.glows[pi];
      s.visible = this.level > 0.03;
      s.scale.setScalar(p.r * (5 + 3 * this.level) * flick);
      s.material.opacity = 0.9 * this.level;
    });
    this.group.visible = alive > 0 || this.level > 0.03;
  }

  // Pipe mouths in world space (for embers and the glow light).
  mouths(out = []) {
    out.length = 0;
    for (const s of this.glows) out.push(s.getWorldPosition(new THREE.Vector3()));
    return out;
  }

  dispose() {
    this.group.removeFromParent();
  }
}
