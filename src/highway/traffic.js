import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { LAYOUT } from './road.js';

const DRACO_PATH = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/';
const KINDS = ['sedan', 'crossover', 'hatch', 'van'];
// Mostly whites and greys like the rest of the site, with the occasional primary red.
const PALETTE = ['#ecebe8', '#ecebe8', '#dcdbd7', '#c2c1bd', '#8e9196', '#2b2d31', '#2b2d31', '#a59a8c', '#d23437'];
const AHEAD = 1150;
const BEHIND = 230;
const COUNT = { 1: 22, [-1]: 14 };

// Intelligent Driver Model
const IDM = { a: 1.4, b: 3.0, T: 1.2, s0: 6 };

const smooth = (t) => t * t * (3 - 2 * t);

export class Traffic {
  constructor(parent) {
    this.group = new THREE.Group();
    parent.add(this.group);
    this.templates = [];
    this.cars = [];
    this.paints = new Map();
    this.road = null;
    this.player = null;
    this.enabled = true;
    this.ready = this.load().catch((err) => console.warn('Traffic models failed to load', err));
  }

  async load() {
    const loader = new GLTFLoader();
    const draco = new DRACOLoader();
    draco.setDecoderPath(DRACO_PATH);
    loader.setDRACOLoader(draco);
    const loaded = await Promise.all(KINDS.map((k) => loader.loadAsync(`assets/traffic/${k}.glb`)));
    draco.dispose();
    this.templates = loaded.map((gltf, i) => {
      const scene = gltf.scene;
      scene.traverse((o) => {
        if (o.isMesh) { o.castShadow = true; o.receiveShadow = true; }
      });
      // Collision size comes from the body shell only; lamp strips and wheels can poke out.
      const box = new THREE.Box3();
      scene.traverse((o) => { if (o.isMesh && /Body/i.test(o.name + (o.parent?.name || ''))) box.expandByObject(o); });
      if (box.isEmpty()) box.setFromObject(scene);
      const size = box.getSize(new THREE.Vector3());
      return { kind: KINDS[i], scene, len: size.x, wid: size.z, hgt: size.y };
    });
    if (this.enabled && this.road && this.player && !this.cars.length) this.populate();
  }

  attach(road) {
    this.road = road;
  }

  reset(player) {
    this.player = player;
    this.clear();
    if (this.enabled && this.templates.length) this.populate();
  }

  clear() {
    for (const c of this.cars) this.group.remove(c.mesh);
    this.cars = [];
  }

  paint(base, hex) {
    const key = `${base.uuid}:${hex}`;
    if (!this.paints.has(key)) {
      const m = base.clone();
      m.color.set(hex);
      this.paints.set(key, m);
    }
    return this.paints.get(key);
  }

  lanes(dir) {
    return dir > 0 ? LAYOUT.fwdLanes : LAYOUT.oncLanes;
  }

  makeCar(dir, lane, s) {
    const t = this.templates[Math.floor(Math.random() * this.templates.length)];
    const mesh = t.scene.clone(true);
    const hex = PALETTE[Math.floor(Math.random() * PALETTE.length)];
    mesh.traverse((o) => {
      if (o.isMesh && o.material?.name?.startsWith('TrafficPaint')) o.material = this.paint(o.material, hex);
    });
    mesh.rotation.order = 'YZX';
    this.group.add(mesh);
    // Left lanes run faster, right lanes slower.
    const v0 = dir > 0 ? [34, 30, 26][lane] + Math.random() * 3 : 27 + Math.random() * 8;
    const car = { mesh, kind: t.kind, dir, lane, d: this.lanes(dir)[lane], s, v: v0 * 0.9, v0, hl: t.len / 2, hw: t.wid / 2, len: t.len, hgt: t.hgt, change: null, cool: 2 + Math.random() * 4, x: 0, z: 0, yaw: 0, rel: 0, wrecked: false };
    this.cars.push(car);
    this.pose(car);
    return car;
  }

  // Is the stretch [s - back, s + front] of a lane free of cars (and the player)?
  free(dir, d, s, back = 25, front = 45, except = null) {
    for (const c of this.cars) {
      if (c === except || c.dir !== dir || Math.abs(c.d - d) > 2.2) continue;
      const ahead = (c.s - s) * dir;
      if (ahead > -back - c.hl && ahead < front + c.hl) return false;
    }
    // The player can be on either carriageway now.
    if (this.player && Math.abs(this.player.d - d) < 2.4) {
      const ahead = (this.player.s - s) * dir;
      if (ahead > -back - 3 && ahead < front + 3) return false;
    }
    return true;
  }

  populate() {
    const sP = this.player.s;
    for (const dir of [1, -1]) {
      const n = COUNT[dir];
      for (let i = 0; i < n; i++) {
        const lane = i % 3;
        let s = sP - 140 + (i / n) * (AHEAD + 120) + Math.random() * 40;
        for (let k = 0; k < 6 && !this.free(dir, this.lanes(dir)[lane], s, 30, 30); k++) s += 37;
        if (dir > 0 && Math.abs(s - sP) < 30 && lane === 1) s += 60;
        this.makeCar(dir, lane, s);
      }
    }
  }

  respawn(car, sStart, spread) {
    for (let k = 0; k < 12; k++) {
      const lane = Math.floor(Math.random() * 3);
      const d = this.lanes(car.dir)[lane];
      const s = sStart + Math.random() * spread;
      if (this.free(car.dir, d, s, 40, 40, car)) {
        car.lane = lane;
        car.d = d;
        car.s = s;
        car.change = null;
        car.v = car.v0 * 0.95;
        return;
      }
    }
  }

  update(dt, player) {
    if (!this.cars.length || !this.road) return;
    const sP = player.s;
    // Traffic is kept mostly ahead of the way the player faces, so driving the wrong way works too.
    const fwd = player.facing;
    for (const car of this.cars) {
      if (car.wrecked) {
        // Wrecked cars stay where they stopped until they drop out of view.
        car.v = 0;
        if ((car.s - sP) * fwd < -BEHIND || (car.s - sP) * fwd > AHEAD + 300) {
          car.wrecked = false;
          this.respawn(car, fwd > 0 ? sP + 720 : sP - 1140, 420);
        }
        this.pose(car);
        continue;
      }
      // Leader in the same lane (or the lane being moved into)
      const laneD = car.change ? car.change.to : car.d;
      let gap = Infinity, vLead = car.v0;
      for (const o of this.cars) {
        if (o === car || o.dir !== car.dir) continue;
        const od = o.change ? o.change.to : o.d;
        if (Math.abs(od - laneD) > 1.9 && Math.abs(o.d - car.d) > 1.9) continue;
        const ahead = (o.s - car.s) * car.dir - (o.hl + car.hl);
        if (ahead > -car.hl && ahead < gap) { gap = ahead; vLead = o.v; }
      }
      // The player is a leader in either direction (a wrong-way player reads as a stopped car).
      if (player.height < car.hgt && Math.abs(player.d - car.d) < player.halfAcross + car.hw + 0.4) {
        const ahead = (player.s - car.s) * car.dir - (2.3 + car.hl);
        if (ahead > -car.hl && ahead < gap) { gap = ahead; vLead = Math.max(0, player.vs * car.dir); }
      }
      const dv = car.v - vLead;
      const sStar = IDM.s0 + car.v * IDM.T + (car.v * dv) / (2 * Math.sqrt(IDM.a * IDM.b));
      let acc = IDM.a * (1 - (car.v / car.v0) ** 4 - (gap === Infinity ? 0 : (Math.max(0, sStar) / Math.max(0.5, gap)) ** 2));
      acc = Math.max(-9, acc);
      car.v = Math.max(0, car.v + acc * dt);
      car.s += car.dir * car.v * dt;

      // Lane changes when held up
      car.cool -= dt;
      if (!car.change && car.cool <= 0) {
        car.cool = 2 + Math.random() * 3;
        if (gap < 70 && vLead < car.v0 - 3) {
          for (const next of [car.lane - 1, car.lane + 1]) {
            if (next < 0 || next > 2) continue;
            const d = this.lanes(car.dir)[next];
            if (this.free(car.dir, d, car.s, 22, 50, car)) {
              car.change = { from: car.d, to: d, t: 0, lane: next };
              break;
            }
          }
        }
      }
      if (car.change) {
        car.change.t += dt / 3;
        const k = smooth(Math.min(1, car.change.t));
        car.d = car.change.from + (car.change.to - car.change.from) * k;
        if (car.change.t >= 1) {
          car.lane = car.change.lane;
          car.d = car.change.to;
          car.change = null;
        }
      }

      // Recycle out of view
      const rel = (car.s - sP) * fwd;
      if (rel < -BEHIND) this.respawn(car, fwd > 0 ? sP + 720 : sP - 1140, 420);
      else if (rel > AHEAD + 300) this.respawn(car, fwd > 0 ? sP - 250 : sP + 210, 40);

      // Overtakes by the player
      const relNow = car.s - sP;
      if (car.dir > 0 && car.rel > 0 && relNow <= 0 && !player.wrecked && Math.abs(car.d - player.d) < 9) player.passed++;
      car.rel = relNow;

      this.pose(car);
    }
  }

  pose(car) {
    const f = this.road.frame(car.s);
    car.x = f.x + f.rx * car.d;
    car.z = f.z + f.rz * car.d;
    let yaw = f.h + (car.dir < 0 ? Math.PI : 0);
    if (car.change) {
      const t = Math.min(1, car.change.t);
      const rate = ((car.change.to - car.change.from) * 6 * t * (1 - t)) / 3; // d(d)/dt of the smoothstep over 3 s
      yaw -= car.dir * Math.atan2(rate, Math.max(5, car.v));
    }
    car.yaw = yaw;
    car.mesh.position.set(car.x, f.y, car.z);
    car.mesh.rotation.set(0, yaw, Math.atan(f.slope) * car.dir);
  }
}
