import * as THREE from 'three';

// Metal sparks as streaks: each spark is a thin camera-facing quad stretched along its velocity,
// white-hot when it leaves the contact and cooling through orange to red as it falls, bouncing once
// off the road. Colours run above 1 so the bloom pass gives them a glow; they are saturated enough
// to read against the pale road and walls.
const HOT = [5.2, 3.4, 1.5], WARM = [3.6, 1.05, 0.16], COOL = [1.1, 0.24, 0.05];

export class Sparks {
  constructor(max = 600) {
    this.max = max;
    this.next = 0;
    this.p = new Float32Array(max * 3);
    this.v = new Float32Array(max * 3);
    this.life = new Float32Array(max);
    this.age = new Float32Array(max);
    this.floor = new Float32Array(max);
    this.width = new Float32Array(max);
    const geo = new THREE.BufferGeometry();
    this.pos = new Float32Array(max * 4 * 3);
    this.col = new Float32Array(max * 4 * 4);
    geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3).setUsage(THREE.DynamicDrawUsage));
    geo.setAttribute('color', new THREE.BufferAttribute(this.col, 4).setUsage(THREE.DynamicDrawUsage));
    const idx = new Uint32Array(max * 6);
    for (let i = 0; i < max; i++) idx.set([i * 4, i * 4 + 1, i * 4 + 2, i * 4 + 2, i * 4 + 1, i * 4 + 3], i * 6);
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    this.mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      vertexColors: true, transparent: true, depthWrite: false, side: THREE.DoubleSide, toneMapped: false,
    }));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 4;
    this.camDir = new THREE.Vector3();
  }

  emit(x, y, z, vx, vy, vz, { life = 0.45, width = 0.035, floor = -1e9 } = {}) {
    const i = this.next;
    this.next = (i + 1) % this.max;
    this.p.set([x, y, z], i * 3);
    this.v.set([vx, vy, vz], i * 3);
    this.life[i] = life;
    this.age[i] = 0;
    this.floor[i] = floor;
    this.width[i] = width;
  }

  // A spray from a contact point: carried along with the car, thrown out along the normal
  // (nx, nz) and up, the faster the harder the hit.
  burst(at, n, carry, power, floor) {
    const k = Math.min(1, power / 15);
    for (let j = 0; j < n; j++) {
      const out = 2 + Math.random() * 6 * (0.4 + k);
      const back = 0.55 + Math.random() * 0.4;
      this.emit(at.x, at.y + Math.random() * 0.25, at.z,
        carry.x * back + (at.nx || 0) * out + (Math.random() - 0.5) * 5,
        1 + Math.random() * 4.5 * (0.5 + k),
        carry.z * back + (at.nz || 0) * out + (Math.random() - 0.5) * 5,
        { life: 0.25 + Math.random() * 0.35, width: 0.025 + Math.random() * 0.03, floor });
    }
  }

  shift(dx, dz) {
    for (let i = 0; i < this.max; i++) {
      this.p[i * 3] -= dx;
      this.p[i * 3 + 2] -= dz;
    }
  }

  clear() {
    this.life.fill(0);
  }

  update(dt, camera) {
    camera.getWorldDirection(this.camDir);
    const cd = this.camDir;
    const P = this.p, V = this.v, pos = this.pos, col = this.col;
    for (let i = 0; i < this.max; i++) {
      const o = i * 3, q = i * 12, c = i * 16;
      if (this.life[i] <= 0) {
        col.fill(0, c, c + 16);
        continue;
      }
      this.age[i] += dt;
      if (this.age[i] >= this.life[i]) {
        this.life[i] = 0;
        col.fill(0, c, c + 16);
        continue;
      }
      // Fall with a little air drag; bounce once off the road, losing most of the speed.
      const drag = Math.exp(-1.6 * dt);
      V[o] *= drag; V[o + 2] *= drag;
      V[o + 1] = V[o + 1] * drag - 14 * dt;
      P[o] += V[o] * dt; P[o + 1] += V[o + 1] * dt; P[o + 2] += V[o + 2] * dt;
      if (P[o + 1] < this.floor[i]) {
        P[o + 1] = this.floor[i];
        V[o + 1] = Math.abs(V[o + 1]) * 0.3;
        V[o] *= 0.6; V[o + 2] *= 0.6;
      }
      // Streak: from the spark back along its velocity, facing the camera.
      const vx = V[o], vy = V[o + 1], vz = V[o + 2];
      const sp = Math.hypot(vx, vy, vz) || 1;
      const len = Math.min(0.7, Math.max(0.06, sp * 0.022));
      const dx = vx / sp, dy = vy / sp, dz = vz / sp;
      let sx = dy * cd.z - dz * cd.y, sy = dz * cd.x - dx * cd.z, sz = dx * cd.y - dy * cd.x;
      const sl = Math.hypot(sx, sy, sz) || 1;
      const w = this.width[i] * (1 - 0.5 * (this.age[i] / this.life[i]));
      sx *= w / sl; sy *= w / sl; sz *= w / sl;
      const ax = P[o], ay = P[o + 1], az = P[o + 2];
      const bx = ax - dx * len, by = ay - dy * len, bz = az - dz * len;
      pos[q] = ax + sx; pos[q + 1] = ay + sy; pos[q + 2] = az + sz;
      pos[q + 3] = ax - sx; pos[q + 4] = ay - sy; pos[q + 5] = az - sz;
      pos[q + 6] = bx + sx; pos[q + 7] = by + sy; pos[q + 8] = bz + sz;
      pos[q + 9] = bx - sx; pos[q + 10] = by - sy; pos[q + 11] = bz - sz;
      // Colour cools with age; the tail of the streak is dimmer than the head.
      const t = this.age[i] / this.life[i];
      const from = t < 0.35 ? HOT : WARM, to = t < 0.35 ? WARM : COOL;
      const u = t < 0.35 ? t / 0.35 : (t - 0.35) / 0.65;
      const r = from[0] + (to[0] - from[0]) * u, g = from[1] + (to[1] - from[1]) * u, b = from[2] + (to[2] - from[2]) * u;
      const a = 1 - t * t;
      for (let k = 0; k < 4; k++) {
        const tail = k >= 2 ? 0.35 : 1;
        col[c + k * 4] = r; col[c + k * 4 + 1] = g; col[c + k * 4 + 2] = b; col[c + k * 4 + 3] = a * tail;
      }
    }
    this.mesh.geometry.attributes.position.needsUpdate = true;
    this.mesh.geometry.attributes.color.needsUpdate = true;
  }
}
