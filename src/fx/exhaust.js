import * as THREE from 'three';

// Boost flames out of a car's own tail pipes (the mouths found by car-model.js fitExhausts).
// Each pipe gets a long outer flame in the car's boost colour, a short white-hot core, a glow at
// the mouth and, at full boost, a row of bright shock diamonds. The flames flicker and breathe in
// a shader; set() picks the target (0 off, 'boost' full, 'pop' a short drift-boost burst) and
// update() eases toward it.
const vertex = /* glsl */ `
  uniform float uTime;
  uniform float uSeed;
  varying float vT;
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    vT = uv.y; // 0 at the pipe, 1 at the tip
    vec3 p = position;
    float w = 1.0 + (0.14 * sin(uTime * 41.0 + uv.y * 11.0 + uSeed) + 0.08 * sin(uTime * 23.0 - uv.y * 7.0)) * uv.y;
    p.yz *= w;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    vN = normalize(normalMatrix * normal);
    vV = normalize(-mv.xyz);
    gl_Position = projectionMatrix * mv;
  }`;
const fragment = /* glsl */ `
  uniform vec3 uEdge;
  uniform vec3 uCore;
  uniform float uAlpha;
  uniform float uTime;
  uniform float uSeed;
  varying float vT;
  varying vec3 vN;
  varying vec3 vV;
  void main() {
    float facing = abs(dot(normalize(vN), normalize(vV)));
    float along = 1.0 - vT;
    vec3 col = mix(uEdge, uCore, pow(facing, 1.6) * along);
    float flick = 0.82 + 0.18 * sin(uTime * 57.0 + vT * 19.0 + uSeed);
    float a = uAlpha * smoothstep(0.0, 0.45, along) * (0.25 + 0.75 * pow(facing, 0.8)) * flick;
    gl_FragColor = vec4(col * 6.0, a);
  }`;

let glowTex = null;
function glowTexture() {
  if (glowTex) return glowTex;
  const c = document.createElement('canvas');
  c.width = c.height = 128;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
  grad.addColorStop(0, 'rgba(255,255,255,1)');
  grad.addColorStop(0.25, 'rgba(255,255,255,0.55)');
  grad.addColorStop(1, 'rgba(255,255,255,0)');
  g.fillStyle = grad;
  g.fillRect(0, 0, 128, 128);
  glowTex = new THREE.CanvasTexture(c);
  glowTex.colorSpace = THREE.SRGBColorSpace;
  return glowTex;
}

// A unit cone along −x: its open base (radius 1) at the origin, the tip at x = −1.
let coneGeo = null;
function cone() {
  if (!coneGeo) {
    coneGeo = new THREE.ConeGeometry(1, 1, 24, 6, true);
    coneGeo.translate(0, 0.5, 0);
    coneGeo.rotateZ(Math.PI / 2);
  }
  return coneGeo;
}

const flameMaterial = (seed) => new THREE.ShaderMaterial({
  vertexShader: vertex,
  fragmentShader: fragment,
  uniforms: { uTime: { value: 0 }, uSeed: { value: seed }, uEdge: { value: new THREE.Color() }, uCore: { value: new THREE.Color() }, uAlpha: { value: 0 } },
  transparent: true,
  depthWrite: false,
  side: THREE.DoubleSide,
  toneMapped: false,
});

export class ExhaustFlames {
  // parent: the car's holder (pipe mouths are in its space). theme: the car's colours.
  constructor(parent, exhausts, theme) {
    this.group = new THREE.Group();
    this.k = 1 / parent.scale.x; // metres → holder units
    parent.add(this.group);
    this.level = 0;
    this.target = 0;
    this.kind = 'boost';
    this.t = 0;
    this.items = exhausts.map((e, i) => {
      const g = new THREE.Group();
      g.position.copy(e.pos);
      const outer = new THREE.Mesh(cone(), flameMaterial(i * 1.7));
      const inner = new THREE.Mesh(cone(), flameMaterial(i * 1.7 + 0.9));
      const glow = new THREE.Sprite(new THREE.SpriteMaterial({ map: glowTexture(), transparent: true, depthWrite: false, toneMapped: false }));
      const diamonds = [0.22, 0.4, 0.58].map(() => {
        const d = new THREE.Mesh(new THREE.SphereGeometry(1, 12, 8), new THREE.MeshBasicMaterial({ color: '#fffaf0', transparent: true, depthWrite: false, toneMapped: false }));
        g.add(d);
        return d;
      });
      for (const m of [outer, inner, glow]) { m.renderOrder = 2; g.add(m); }
      for (const d of diamonds) d.renderOrder = 3;
      this.group.add(g);
      return { g, outer, inner, glow, diamonds, r: e.r };
    });
    this.setTheme(theme);
    this.apply();
  }

  setTheme(theme) {
    const boost = theme?.boost || ['#ffb36b', '#ff5a2e', '#ff1f3d', '#b5001c'];
    const flame = theme?.flame || '#ff2d3d';
    for (const it of this.items) {
      it.outer.material.uniforms.uEdge.value.set(flame);
      it.outer.material.uniforms.uCore.value.set(boost[0]);
      it.inner.material.uniforms.uEdge.value.set(boost[0]);
      it.inner.material.uniforms.uCore.value.set('#fff8ec');
      it.glow.material.color.set(flame);
    }
  }

  // target 0..1; kind 'boost' (long, with diamonds) or 'pop' (short drift-boost burst)
  set(target, kind = 'boost') {
    this.target = target;
    if (target > 0) this.kind = kind;
  }

  update(dt, t) {
    this.t = t;
    const rate = this.target > this.level ? 22 : 9;
    this.level += (this.target - this.level) * (1 - Math.exp(-dt * rate));
    this.apply();
  }

  apply() {
    const L = this.level, k = this.k, pop = this.kind === 'pop';
    this.group.visible = L > 0.02;
    if (!this.group.visible) return;
    const breathe = 1 + 0.12 * Math.sin(this.t * 17) * Math.sin(this.t * 29 + 1.3);
    const len = (pop ? 0.8 : 1.9) * L * breathe;
    for (const it of this.items) {
      const r = it.r;
      it.outer.scale.set(len * k, r * 1.45, r * 1.45);
      it.inner.scale.set(len * 0.55 * k, r * 0.75, r * 0.75);
      for (const m of [it.outer, it.inner]) {
        m.material.uniforms.uTime.value = this.t;
        m.material.uniforms.uAlpha.value = Math.min(1, L * 1.15);
      }
      it.glow.scale.setScalar(r * (5 + 2 * L));
      it.glow.material.opacity = 0.85 * L;
      it.diamonds.forEach((d, j) => {
        const show = pop ? 0 : Math.max(0, L - 0.4) / 0.6;
        d.position.x = -[0.22, 0.4, 0.58][j] * len * k;
        d.scale.set(r * 0.5 * (1 - j * 0.18), r * 0.32, r * 0.32);
        d.material.opacity = show * (0.7 - j * 0.15) * (0.75 + 0.25 * Math.sin(this.t * 63 + j));
      });
    }
  }

  // Pipe mouths in world space (for embers and the glow light).
  mouths(out = []) {
    out.length = 0;
    for (const it of this.items) out.push(it.g.getWorldPosition(new THREE.Vector3()));
    return out;
  }

  dispose() {
    this.group.removeFromParent();
  }
}
