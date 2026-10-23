import * as THREE from 'three';

const MAX = 2400;     // segments kept on the road; the oldest are overwritten
const WIDTH = 0.26;   // tyre print width, m
const STEP = 0.35;    // new segment every this many metres

// Dark rubber strips laid on the road under the rear tyres while they slide.
export class SkidMarks {
  constructor(parent) {
    this.pos = new Float32Array(MAX * 4 * 3);
    this.col = new Float32Array(MAX * 4 * 4);
    const idx = new Uint32Array(MAX * 6);
    for (let i = 0; i < MAX; i++) idx.set([i * 4, i * 4 + 2, i * 4 + 1, i * 4 + 1, i * 4 + 2, i * 4 + 3], i * 6);
    const geo = new THREE.BufferGeometry();
    geo.setAttribute('position', new THREE.BufferAttribute(this.pos, 3));
    geo.setAttribute('color', new THREE.BufferAttribute(this.col, 4));
    geo.setIndex(new THREE.BufferAttribute(idx, 1));
    this.mesh = new THREE.Mesh(geo, new THREE.MeshBasicMaterial({
      vertexColors: true,
      transparent: true,
      depthWrite: false,
      polygonOffset: true,
      polygonOffsetFactor: -2,
      polygonOffsetUnits: -2,
    }));
    this.mesh.frustumCulled = false;
    this.mesh.renderOrder = 1;
    parent.add(this.mesh);
    this.next = 0;
    this.trails = [null, null];
  }

  clear() {
    this.col.fill(0);
    this.next = 0;
    this.trails = [null, null];
    this.mesh.geometry.attributes.color.needsUpdate = true;
  }

  // points: one {x, y, z} per tyre; strength 0..1 (0 lifts the tyre and breaks the trail).
  update(points, strength) {
    let changed = false;
    points.forEach((p, k) => {
      const last = this.trails[k];
      if (strength <= 0.02) {
        this.trails[k] = null;
        return;
      }
      if (!last) {
        this.trails[k] = { x: p.x, y: p.y, z: p.z, a: strength };
        return;
      }
      const dx = p.x - last.x, dz = p.z - last.z;
      const len = Math.hypot(dx, dz);
      if (len < STEP) return;
      if (len > 6) {
        this.trails[k] = { x: p.x, y: p.y, z: p.z, a: strength };
        return;
      }
      this.segment(last, p, dx / len, dz / len, last.a, strength);
      this.trails[k] = { x: p.x, y: p.y, z: p.z, a: strength };
      changed = true;
    });
    if (changed) {
      const g = this.mesh.geometry.attributes;
      g.position.needsUpdate = g.color.needsUpdate = true;
    }
  }

  segment(a, b, ux, uz, aa, ab) {
    const i = this.next;
    this.next = (this.next + 1) % MAX;
    const nx = -uz * WIDTH / 2, nz = ux * WIDTH / 2;
    this.pos.set([
      a.x + nx, a.y, a.z + nz,
      a.x - nx, a.y, a.z - nz,
      b.x + nx, b.y, b.z + nz,
      b.x - nx, b.y, b.z - nz,
    ], i * 12);
    const c = [0.1, 0.1, 0.11];
    const o0 = 0.55 * Math.min(1, aa), o1 = 0.55 * Math.min(1, ab);
    this.col.set([...c, o0, ...c, o0, ...c, o1, ...c, o1], i * 16);
  }

  rebase(dx, dz) {
    for (let i = 0; i < this.pos.length; i += 3) {
      this.pos[i] -= dx;
      this.pos[i + 2] -= dz;
    }
    for (const t of this.trails) if (t) { t.x -= dx; t.z -= dz; }
    this.mesh.geometry.attributes.position.needsUpdate = true;
  }
}
