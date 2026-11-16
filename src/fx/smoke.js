import * as THREE from 'three';

// Billowing white jet smoke for the jump (lift) jets. Puffs live in world space, so the cloud stays
// where the car took off and rolls out over the road instead of following it. Each puff is a soft
// sprite with a noisy edge, lit like a small cumulus (bright top, grey underside) so a pile of them
// reads as volume against the pale sky; it grows, slows and thins out as it ages. Puffs that reach
// the road spread sideways along it, the way a jet's blast fans out over the ground.
const NOISE = /* glsl */ `
  float hash(vec2 p) { return fract(sin(dot(p, vec2(127.1, 311.7))) * 43758.5453); }
  float noise(vec2 p) {
    vec2 i = floor(p), f = fract(p);
    vec2 u = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash(i), hash(i + vec2(1, 0)), u.x), mix(hash(i + vec2(0, 1)), hash(i + vec2(1, 1)), u.x), u.y);
  }
  float fbm(vec2 p) {
    float v = 0.0, a = 0.5;
    for (int i = 0; i < 4; i++) { v += a * noise(p); p = p * 2.03 + 17.0; a *= 0.5; }
    return v;
  }`;
export { NOISE };

const vertex = /* glsl */ `
  attribute float size;
  attribute float alpha;
  attribute float seed;
  attribute float spin;
  uniform float scale;
  varying float vAlpha;
  varying float vSeed;
  varying float vSpin;
  void main() {
    vAlpha = alpha;
    vSeed = seed;
    vSpin = spin;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    gl_PointSize = size * scale / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;

const fragment = /* glsl */ `
  uniform float uBright;
  varying float vAlpha;
  varying float vSeed;
  varying float vSpin;
  ${NOISE}
  void main() {
    vec2 p = gl_PointCoord * 2.0 - 1.0;
    p.y = -p.y;
    float c = cos(vSpin), s = sin(vSpin);
    vec2 q = mat2(c, -s, s, c) * p;
    float n = fbm(q * 1.7 + vSeed * 31.0);
    float r = length(p) + (n - 0.5) * 0.6;
    float a = smoothstep(1.0, 0.35, r) * vAlpha;
    if (a < 0.01) discard;
    // a lumpy sphere: lit from above and a little toward the camera, grey underneath
    vec3 N = normalize(vec3(p * 0.85 + (vec2(n) - 0.5) * 0.7, sqrt(max(0.05, 1.0 - dot(p, p)))));
    float lit = clamp(dot(N, normalize(vec3(0.25, 0.85, 0.45))), 0.0, 1.0);
    float shade = 0.42 + 0.58 * lit;
    gl_FragColor = vec4(vec3(1.0, 0.995, 0.985) * shade * uBright, a);
  }`;

export class JetSmoke {
  constructor(count = 720) {
    this.count = count;
    this.next = 0;
    this.pos = new Float32Array(count * 3);
    this.vel = new Float32Array(count * 3);
    this.size = new Float32Array(count);
    this.alpha = new Float32Array(count);
    this.seed = new Float32Array(count);
    this.spin = new Float32Array(count);
    this.spinV = new Float32Array(count);
    this.life = new Float32Array(count);
    this.max = new Float32Array(count);
    this.s0 = new Float32Array(count);
    this.s1 = new Float32Array(count);
    this.a0 = new Float32Array(count);
    this.drag = new Float32Array(count);
    this.floor = new Float32Array(count);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(this.size, 1));
    geo.setAttribute('alpha', new THREE.BufferAttribute(this.alpha, 1));
    geo.setAttribute('seed', new THREE.BufferAttribute(this.seed, 1));
    geo.setAttribute('spin', new THREE.BufferAttribute(this.spin, 1));
    this.points = new THREE.Points(geo, new THREE.ShaderMaterial({
      vertexShader: vertex,
      fragmentShader: fragment,
      // the game's white world sits around 2.5 in HDR before tone mapping (main.js preToned): the
      // lit tops of the puffs match it, their undersides fall to a soft grey
      uniforms: { scale: { value: 400 }, uBright: { value: 2.5 } },
      transparent: true,
      depthWrite: false,
    }));
    this.points.frustumCulled = false;
    this.points.renderOrder = 4;
  }

  // Point sprites are sized in pixels: match a puff's size in metres to the camera's projection.
  setView(camera, heightPx) {
    this.points.material.uniforms.scale.value = heightPx / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov) / 2));
  }

  // One puff. size: [start, end] diameter in metres; life in seconds; floor: the road height.
  emit(x, y, z, vx, vy, vz, { life = 1.6, size = [0.5, 2.6], alpha = 0.75, drag = 2.6, floor = -1e9 } = {}) {
    const i = this.next;
    this.next = (this.next + 1) % this.count;
    this.pos.set([x, y, z], i * 3);
    this.vel.set([vx, vy, vz], i * 3);
    this.life[i] = this.max[i] = life * (0.8 + Math.random() * 0.4);
    this.s0[i] = size[0];
    this.s1[i] = size[1] * (0.85 + Math.random() * 0.3);
    this.a0[i] = alpha;
    this.drag[i] = drag;
    this.floor[i] = floor;
    this.seed[i] = Math.random();
    this.spin[i] = Math.random() * 6.283;
    this.spinV[i] = (Math.random() - 0.5) * 0.8;
  }

  // A ground blast: a ring of puffs rolling outward from (x, y, z) over the road, carried a little by v.
  blast(x, y, z, n, v = { x: 0, z: 0 }, opts = {}) {
    for (let k = 0; k < n; k++) {
      const a = Math.random() * 6.283, sp = 3 + Math.random() * 5;
      this.emit(x + Math.cos(a) * 0.6, y + Math.random() * 0.4, z + Math.sin(a) * 0.6,
        v.x * 0.25 + Math.cos(a) * sp, 0.4 + Math.random() * 1.2, v.z * 0.25 + Math.sin(a) * sp,
        { life: 2.4, size: [1.0, 4.0], alpha: 0.9, drag: 2.2, floor: y, ...opts });
    }
  }

  update(dt) {
    if (dt <= 0) return;
    for (let i = 0; i < this.count; i++) {
      if (this.life[i] <= 0) { this.alpha[i] = 0; continue; }
      this.life[i] -= dt;
      const t = 1 - Math.max(0, this.life[i] / this.max[i]);   // 0 new .. 1 gone
      const k = Math.max(0, 1 - this.drag[i] * dt);
      const j = i * 3;
      this.vel[j] *= k;
      this.vel[j + 2] *= k;
      this.vel[j + 1] = this.vel[j + 1] * k + 0.9 * dt;           // warm exhaust rises slowly
      this.pos[j] += this.vel[j] * dt;
      this.pos[j + 1] += this.vel[j + 1] * dt;
      this.pos[j + 2] += this.vel[j + 2] * dt;
      const fl = this.floor[i] + this.size[i] * 0.3;
      if (this.pos[j + 1] < fl) {
        // hit the road: the downward rush turns into a sideways roll
        const down = Math.max(0, -this.vel[j + 1]);
        this.pos[j + 1] = fl;
        this.vel[j + 1] = 0.2;
        const a = this.seed[i] * 6.283;
        this.vel[j] += Math.cos(a) * down * 0.55;
        this.vel[j + 2] += Math.sin(a) * down * 0.55;
      }
      this.spin[i] += this.spinV[i] * dt;
      // grows fast at first (the jet expanding), then slowly; fades in quickly, out softly
      this.size[i] = this.s0[i] + (this.s1[i] - this.s0[i]) * (1 - Math.pow(1 - t, 2.2));
      this.alpha[i] = this.a0[i] * Math.min(1, t * 12) * Math.pow(1 - t, 1.4);
    }
    const a = this.points.geometry.attributes;
    a.position.needsUpdate = a.size.needsUpdate = a.alpha.needsUpdate = a.spin.needsUpdate = a.seed.needsUpdate = true;
  }

  // The highway re-centres its world now and then.
  shift(dx, dy, dz) {
    for (let i = 0; i < this.count; i++) {
      this.pos[i * 3] += dx;
      this.pos[i * 3 + 1] += dy;
      this.pos[i * 3 + 2] += dz;
      this.floor[i] += dy;
    }
  }

  clear() {
    this.life.fill(0);
    this.alpha.fill(0);
    this.points.geometry.attributes.alpha.needsUpdate = true;
  }
}
