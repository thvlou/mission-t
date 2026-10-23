import * as THREE from 'three';

// Pooled additive particles with per-particle colour, size and fade.
export class Particles {
  constructor(count = 900) {
    this.count = count;
    this.next = 0;
    this.pos = new Float32Array(count * 3);
    this.vel = new Float32Array(count * 3);
    this.col = new Float32Array(count * 3);
    this.size = new Float32Array(count);
    this.alpha = new Float32Array(count);
    this.life = new Float32Array(count);
    this.max = new Float32Array(count);
    this.drag = new Float32Array(count);
    this.grav = new Float32Array(count);
    this.floor = new Float32Array(count);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(this.col, 3));
    geo.setAttribute('size', new THREE.BufferAttribute(this.size, 1));
    geo.setAttribute('alpha', new THREE.BufferAttribute(this.alpha, 1));
    const mat = new THREE.ShaderMaterial({
      transparent: true,
      depthWrite: false,
      blending: THREE.NormalBlending,
      uniforms: { scale: { value: 400 } },
      vertexShader: `
        attribute float size;
        attribute float alpha;
        attribute vec3 color;
        uniform float scale;
        varying float vAlpha;
        varying vec3 vColor;
        void main() {
          vAlpha = alpha;
          vColor = color;
          vec4 mv = modelViewMatrix * vec4(position, 1.0);
          gl_PointSize = size * scale / -mv.z;
          gl_Position = projectionMatrix * mv;
        }`,
      fragmentShader: `
        varying float vAlpha;
        varying vec3 vColor;
        void main() {
          float d = length(gl_PointCoord - 0.5);
          float a = smoothstep(0.5, 0.0, d) * vAlpha;
          if (a < 0.01) discard;
          gl_FragColor = vec4(vColor, a * 0.85);
        }`,
    });
    this.points = new THREE.Points(geo, mat);
    this.points.frustumCulled = false;
  }

  emit(x, y, z, vx, vy, vz, { life = 0.6, size = 0.4, color = [0.5, 0.9, 1], drag = 1.5, gravity = 0, floor = 0.02 } = {}) {
    const i = this.next;
    this.next = (this.next + 1) % this.count;
    this.pos.set([x, y, z], i * 3);
    this.vel.set([vx, vy, vz], i * 3);
    this.col.set(color, i * 3);
    this.size[i] = size;
    this.life[i] = this.max[i] = life;
    this.drag[i] = drag;
    this.grav[i] = gravity;
    this.floor[i] = floor;
  }

  burst(x, y, n, opts, spread = 4, up = 2) {
    for (let k = 0; k < n; k++) {
      this.emit(x, y, (Math.random() - 0.5) * 3, (Math.random() - 0.5) * spread, Math.random() * up, (Math.random() - 0.5) * spread, opts);
    }
  }

  update(dt) {
    for (let i = 0; i < this.count; i++) {
      if (this.life[i] <= 0) {
        this.alpha[i] = 0;
        continue;
      }
      this.life[i] -= dt;
      const k = Math.max(0, 1 - this.drag[i] * dt);
      this.vel[i * 3] *= k;
      this.vel[i * 3 + 1] = this.vel[i * 3 + 1] * k - this.grav[i] * dt;
      this.vel[i * 3 + 2] *= k;
      this.pos[i * 3] += this.vel[i * 3] * dt;
      this.pos[i * 3 + 1] = Math.max(this.floor[i], this.pos[i * 3 + 1] + this.vel[i * 3 + 1] * dt);
      this.pos[i * 3 + 2] += this.vel[i * 3 + 2] * dt;
      const r = Math.max(0, this.life[i] / this.max[i]);
      this.alpha[i] = r * r;
    }
    const a = this.points.geometry.attributes;
    a.position.needsUpdate = a.alpha.needsUpdate = a.color.needsUpdate = a.size.needsUpdate = true;
  }

  // Move every live particle (the highway re-centres its world now and then).
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
  }
}

// Dashed ballistic forecast and a ring where the car would touch down without more thrust.
export class Forecast {
  constructor() {
    this.n = 120;
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(this.n * 3), 3));
    this.line = new THREE.Line(geo, new THREE.LineDashedMaterial({ color: '#121316', dashSize: 0.5, gapSize: 0.35, transparent: true, opacity: 0.45 }));
    this.line.frustumCulled = false;
    this.ring = new THREE.Mesh(
      new THREE.RingGeometry(0.9, 1.15, 40),
      new THREE.MeshBasicMaterial({ color: '#121316', transparent: true, opacity: 0.75, depthWrite: false, toneMapped: false }),
    );
    this.ring.rotation.x = -Math.PI / 2;
    this.group = new THREE.Group();
    this.group.add(this.line, this.ring);
    this.group.visible = false;
  }

  update(sim, ride, zone) {
    if (sim.state !== 'air') {
      this.group.visible = false;
      return;
    }
    this.group.visible = true;
    const g = sim.p.gravity;
    let x = sim.x, y = sim.y, vx = sim.vx, vy = sim.vy;
    const pos = this.line.geometry.attributes.position;
    const dt = 1 / 30;
    let i = 0;
    for (; i < this.n; i++) {
      pos.setXYZ(i, x, y, 0);
      if (y <= ride && i > 0) break;
      const sp = Math.hypot(vx, vy);
      vx -= vx * sp * 0.0035 * dt;
      vy -= (g + vy * sp * 0.0035) * dt;
      x += vx * dt;
      y += vy * dt;
    }
    const used = Math.min(i + 1, this.n);
    for (let j = used; j < this.n; j++) pos.setXYZ(j, x, y, 0);
    pos.needsUpdate = true;
    this.line.geometry.setDrawRange(0, used);
    this.line.computeLineDistances();
    this.ring.position.set(x, 0.05, 0);
    const inside = Math.abs(x - zone.x) <= zone.half;
    this.ring.material.color.set(inside ? '#d23437' : '#121316');
  }
}
