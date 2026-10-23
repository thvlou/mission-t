import * as THREE from 'three';
import { Road } from './road.js';
import { Scenery } from './scenery.js';
import { Traffic } from './traffic.js';
import { HighwayCar, FUEL } from './car.js';
import { SkidMarks } from './skids.js';

const STEP = 1 / 120;
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const REBASE = 1500; // shift the world back to the origin past this distance (float precision)

export const HIGHWAY_VIEWS = [
  { key: 'chase', name: 'Chase' },
  { key: 'hood', name: 'Hood' },
  { key: 'drone', name: 'Drone' },
  { key: 'side', name: 'Side' },
];

// Endless highway free-roam: owns its own road, scenery, traffic and car, and drives the camera.
export class HighwayMode {
  constructor(scene) {
    this.group = new THREE.Group();
    this.group.visible = false;
    scene.add(this.group);
    this.traffic = new Traffic(this.group);
    this.skids = new SkidMarks(this.group);
    this.road = null;
    this.scenery = null;
    this.car = null;
    this.acc = 0;
    this.camPos = new THREE.Vector3();
    this.camLook = new THREE.Vector3();
    this.camReady = false;
    this.camYaw = 0;
    this.shake = 0;
    this.shift = null;
    // Other cars the player can hit besides traffic (race opponents), refreshed by their owner each frame.
    this.extraCars = [];
    this.reset();
  }

  // +1 when the car points along +s, −1 when it points back down the road.
  get facing() {
    return this.car.facing;
  }

  get fuelMax() {
    return FUEL;
  }

  // opts: { seed, traffic = true, s, d } — a race passes a shared seed, no traffic and a grid slot.
  reset(opts = {}) {
    const seed = opts.seed ?? Math.floor(Math.random() * 1e9);
    this.seed = seed;
    if (this.scenery) {
      this.scenery.clear();
      this.group.remove(this.scenery.group);
    }
    this.road = new Road(seed);
    this.scenery = new Scenery(this.road, seed);
    this.group.add(this.scenery.group);
    this.car = new HighwayCar(this.road);
    if (opts.s !== undefined) this.car.reset(opts.s, opts.d ?? 0);
    this.traffic.enabled = opts.traffic ?? true;
    this.traffic.attach(this.road);
    this.traffic.reset(this.car);
    this.scenery.update(this.car.s);
    this.acc = 0;
    this.camReady = false;
    this.shake = 0;
    this.skids.clear();
  }

  setActive(on) {
    this.group.visible = on;
  }

  update(dt, input) {
    this.acc += dt;
    let n = 0;
    const others = this.extraCars.length ? { cars: this.traffic.cars.concat(this.extraCars) } : this.traffic;
    while (this.acc >= STEP && n++ < 30) {
      this.acc -= STEP;
      this.car.step(STEP, input, others);
      this.traffic.update(STEP, this.car);
    }
    if (dt > 0) {
      const y = this.car.groundY + 0.03;
      this.skids.update(this.rearPatches().map((p) => ({ x: p.x, y, z: p.z })), this.skidLevel);
    }
    this.scenery.update(this.car.s, this.facing, 2);
    this.road.trim(this.car.s - 2000, this.car.s + 2000);
    const p = this.car.pos;
    if (Math.abs(p.x) > REBASE || Math.abs(p.z) > REBASE) {
      const dx = p.x, dz = p.z;
      this.road.rebase(dx, dz);
      this.scenery.rebase(dx, dz);
      this.skids.rebase(dx, dz);
      p.x -= dx;
      p.z -= dz;
      this.shift = { dx, dz };
    }
  }

  // How hard the rear tyres are sliding, 0..1: drives skid marks, smoke and squeal.
  get skidLevel() {
    const c = this.car;
    if (c.airborne) return 0;
    if (c.wrecked) return c.speed > 1.5 ? Math.min(1, c.speed / 10) : 0;
    const slide = Math.min(1, Math.max(0, (Math.abs(c.vlat) - 2) / 5));
    return Math.max(slide, c.ebrake && c.speed > 3 ? 0.7 : 0);
  }

  // Where the rear tyres touch the road, for drift smoke.
  rearPatches() {
    const c = this.car, a = c.axes(), y = c.pos.y - 0.5;
    const bx = c.pos.x - a.fx * 1.38, bz = c.pos.z - a.fz * 1.38;
    return [
      { x: bx + a.rx * 0.84, y, z: bz + a.rz * 0.84 },
      { x: bx - a.rx * 0.84, y, z: bz - a.rz * 0.84 },
    ];
  }

  // Drive the shared rover model from the highway car.
  poseRover(rover, t) {
    const c = this.car;
    rover.pose3d(c.pos, c.yaw, c.pitch, c.lean, c.roll, c.jets, t, c.ebrake || c.wrecked, c.wheelAngle);
  }

  updateCamera(camera, dt, viewKey, baseFov) {
    const c = this.car;
    const speed = c.speed;
    // The camera sits behind the car's own heading, whichever way it points on the road. After a
    // wreck it holds still so it does not whip around with the spinning car.
    if (!this.camReady) this.camYaw = c.yaw;
    if (!c.wrecked) this.camYaw += wrap(c.yaw - this.camYaw) * Math.min(1, dt * 12);
    const yaw = viewKey === 'hood' ? c.yaw : this.camYaw;
    const f = new THREE.Vector3(Math.cos(yaw), 0, -Math.sin(yaw));
    const r = new THREE.Vector3(Math.sin(yaw), 0, Math.cos(yaw));
    const car = new THREE.Vector3(c.pos.x, c.pos.y, c.pos.z);
    let pos, look, rigid = false;
    if (viewKey === 'hood') {
      pos = car.clone().addScaledVector(f, 0.5).add(new THREE.Vector3(0, 0.62, 0));
      look = car.clone().addScaledVector(f, 40).add(new THREE.Vector3(0, 0.4, 0));
      rigid = true;
    } else if (viewKey === 'drone') {
      pos = car.clone().addScaledVector(f, -24).add(new THREE.Vector3(0, 15, 0));
      look = car.clone().addScaledVector(f, 22);
    } else if (viewKey === 'side') {
      pos = car.clone().addScaledVector(r, 9).addScaledVector(f, -3).add(new THREE.Vector3(0, 1.6, 0));
      look = car.clone().addScaledVector(f, 4).add(new THREE.Vector3(0, 0.5, 0));
    } else {
      pos = car.clone().addScaledVector(f, -(6.6 + speed * 0.02)).add(new THREE.Vector3(0, 2.3 + speed * 0.006, 0));
      look = car.clone().addScaledVector(f, 6).add(new THREE.Vector3(0, -0.2, 0));
    }
    // Smooth the camera's offset from the car rather than its world position, so it never trails at speed.
    const offPos = pos.sub(car), offLook = look.sub(car);
    if (!this.camReady || rigid) {
      this.camPos.copy(offPos);
      this.camLook.copy(offLook);
      this.camReady = true;
    } else {
      this.camPos.lerp(offPos, 1 - Math.exp(-dt * 7));
      this.camLook.lerp(offLook, 1 - Math.exp(-dt * 9));
    }
    camera.position.copy(car).add(this.camPos);
    camera.lookAt(this.camLook.clone().add(car));
    if (this.shake > 0.001) {
      const k = this.shake * this.shake * 0.6;
      camera.position.x += (Math.random() - 0.5) * k;
      camera.position.y += (Math.random() - 0.5) * k;
      camera.position.z += (Math.random() - 0.5) * k;
      this.shake *= Math.exp(-dt * 3.5);
    }
    // Widen the lens with speed for a sense of pace.
    const fov = baseFov + 16 * Math.min(1, speed / 80) ** 1.5;
    if (Math.abs(camera.fov - fov) > 0.05) {
      camera.fov = fov;
      camera.updateProjectionMatrix();
    }
  }

  telemetry() {
    const c = this.car;
    return {
      kmh: c.speed * 3.6,
      km: c.distance / 1000,
      g: c.gForce,
      passed: c.passed,
      fuel: c.fuel,
      airborne: c.airborne,
    };
  }

  // Shape the sound engine expects from the stunt sim.
  get soundState() {
    const c = this.car;
    return { vx: c.speed, vy: c.airborne ? c.vy : 0, state: c.airborne ? 'air' : 'track', jets: c.jets };
  }

  // Numbers for the wreck card.
  summary() {
    const c = this.car;
    return { distance: c.distance, top: c.top * 3.6, passed: c.passed, time: c.time, info: c.wreckInfo };
  }
}
