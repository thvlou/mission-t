import { LAYOUT } from './road.js';

// Arcade highway handling. The car carries a world-space velocity; its heading turns with the
// steering and lateral grip pulls the velocity back in line. Pull the e-brake (Shift) and the rear
// lets go: grip drops, the tail swings and the car drifts. Space hops and hovers, B boosts.
// A hard traffic collision wrecks the car and ends the run. All speeds in m/s.
const G = 9.81;
export const RIDE = 0.6;
const WB = 2.76;
export const HALF_L = 2.3;
export const HALF_W = 0.98;
const V_TOP = 72;          // ≈ 260 km/h
const V_BOOST = 92;        // ≈ 330 km/h
const ACC = 8.5;
const BOOST_ACC = 7;
const BRAKE = 16;
const V_REV = -10;
const STEER_MAX = 0.72;    // rad at the wheels, low speed
const STEER_RATE = 16;      // how fast the wheel follows the input, 1/s
const LAT_MAX = 13;        // m/s² cornering limit with full grip
const GRIP = 9;            // lateral velocity decay with full grip, 1/s
const DRIFT_GRIP = 0.8;    // ... with the rear wheels locked
const SLIDE_GRIP = 1.5;    // ... while powering through a slide after the e-brake is released
const EBRAKE = 3.5;        // m/s² of drag from the locked rear wheels
const WRECK = 14;          // closing speed (m/s, ≈ 50 km/h) that wrecks the car
const BARRIER_HALF = 0.34; // median barrier half-width, m
const BARRIER_TOP = 0.85;  // clear this height to jump the median
const EDGE_R = LAYOUT.roadR - 1.05;
const EDGE_L = LAYOUT.oncL + 1.05;
export const FUEL = 100;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));

function obb(a, b) {
  // Separating-axis test for two boxes on the ground plane; returns penetration pushing a out of b.
  const axes = [[a.c, -a.s], [a.s, a.c], [b.c, -b.s], [b.s, b.c]];
  const dx = a.x - b.x, dz = a.z - b.z;
  let depth = Infinity, nx = 0, nz = 0;
  for (const [ax, az] of axes) {
    const ra = a.hl * Math.abs(a.c * ax - a.s * az) + a.hw * Math.abs(a.s * ax + a.c * az);
    const rb = b.hl * Math.abs(b.c * ax - b.s * az) + b.hw * Math.abs(b.s * ax + b.c * az);
    const dist = dx * ax + dz * az;
    const over = ra + rb - Math.abs(dist);
    if (over <= 0) return null;
    if (over < depth) { depth = over; nx = ax * Math.sign(dist || 1); nz = az * Math.sign(dist || 1); }
  }
  return { depth, nx, nz };
}

export class HighwayCar {
  constructor(road) {
    this.road = road;
    this.events = [];
    this.reset();
  }

  reset(s = 30, d = 0) {
    const f = this.road.frame(s);
    this.s = s;
    this.d = d;
    this.pos = { x: f.x + f.rx * d, y: f.y + RIDE, z: f.z + f.rz * d };
    this.groundY = f.y;
    this.yaw = f.h;
    this.vx = 0;
    this.vz = 0;
    this.v = 0;        // speed along the heading
    this.vlat = 0;     // sideways slip (positive = sliding to the right)
    this.vs = 0;       // speed along the road
    this.vy = 0;
    this.yawRate = 0;
    this.steer = 0;
    this.ebrake = false;
    this.grip = GRIP;
    this.airborne = false;
    this.liftHeld = false;
    this.fuel = FUEL;
    this.distance = 0;
    this.time = 0;
    this.top = 0;
    this.passed = 0;
    this.hits = 0;
    this.roll = 0;
    this.lean = 0;
    this.pitch = Math.atan(f.slope);
    this.gForce = 1;
    this.started = false;
    this.wrecked = false;
    this.wreckT = 0;
    this.wreckInfo = null;
    this.jets = { lift: false, boost: false, spin: 0, grip: false };
    this.vel = { x: 0, y: 0, z: 0 };
    this.contacts = new Set();
    this.travel = 1;
    this.travelT = 0;
  }

  // Half of the car's footprint measured across the road (grows when the car is angled).
  get halfAcross() {
    const off = wrap(this.yaw - this.road.frame(this.s).h);
    return Math.abs(Math.sin(off)) * HALF_L + Math.abs(Math.cos(off)) * HALF_W;
  }

  get height() {
    return Math.max(0, this.pos.y - RIDE - this.groundY);
  }

  // Which way along the road (±1) the car has been pointing for the last second or so; scenery and
  // traffic stream toward it, so a quick spin doesn't reshuffle the world.
  get facing() {
    return this.travel;
  }

  get speed() {
    return Math.hypot(this.vx, this.vz);
  }

  // Front wheel angle for the model: the steering input, eased off at speed, frozen after a wreck.
  get wheelAngle() {
    if (this.wrecked) return 0;
    return this.steer * 0.5 * Math.max(0.4, 1 - this.speed / 100);
  }

  step(dt, inp, traffic) {
    this.jets = { lift: false, boost: false, spin: 0, grip: false };
    if (this.wrecked) return this.stepWreck(dt);
    if (!this.started) {
      if (!inp.throttle && !inp.lift && !inp.boost && !inp.ebrake) return;
      this.started = true;
      this.events.push({ type: 'go' });
    }
    this.time += dt;

    // Velocity in the car's frame
    const f0 = this.axes();
    let vf = this.vx * f0.fx + this.vz * f0.fz;
    let vr = this.vx * f0.rx + this.vz * f0.rz;
    const eb = !!inp.ebrake && !this.airborne;
    this.ebrake = eb;

    // Longitudinal
    const boosting = inp.boost && this.fuel > 0 && inp.throttle >= 0;
    let a = 0;
    if (inp.throttle > 0 || boosting) {
      const top = boosting ? V_BOOST : V_TOP;
      a = vf < top ? ACC * (1 - (Math.max(0, vf) / top) ** 2) + (boosting ? BOOST_ACC : 0) : -2;
      if (eb) a *= 0.4;
    } else if (inp.throttle < 0) {
      a = vf > 0.5 ? -BRAKE : vf > V_REV ? -4 : 0;
    }
    if (boosting) {
      this.fuel = Math.max(0, this.fuel - 22 * dt);
      this.jets.boost = true;
    }
    vf += a * dt;
    vf -= Math.sign(vf) * Math.min(Math.abs(vf), (0.00035 * vf * vf + 0.15 + (eb ? EBRAKE : 0)) * dt);

    // Lateral grip pulls the velocity back in line with the heading. A locked rear lets it slide, and
    // grip only comes back gradually, so a slide can be held on the throttle and steered.
    const slipAngle = Math.atan2(Math.abs(vr), Math.max(Math.abs(vf), 1));
    let gripTarget = eb ? DRIFT_GRIP : GRIP;
    if (!eb && slipAngle > 0.12 && inp.throttle > 0) gripTarget = SLIDE_GRIP;
    this.grip += (gripTarget - this.grip) * Math.min(1, dt * (eb ? 10 : gripTarget === GRIP ? 2.4 : 1.2));
    const sliding = !eb && !this.airborne && this.grip < GRIP - 1 && inp.throttle > 0;
    const sp0 = Math.hypot(vf, vr);
    vr *= Math.exp(-(this.airborne ? 0.3 : this.grip) * dt);
    // Powering through a slide swings the velocity round instead of scrubbing it off, so a drift
    // can be carried through a whole corner.
    if (sliding && Math.abs(vf) > 1) vf = Math.sign(vf) * Math.sqrt(Math.max(0, sp0 * sp0 - vr * vr));

    // Steering
    this.steer += (inp.spin - this.steer) * Math.min(1, dt * STEER_RATE);
    const geo = (vf * Math.tan(this.steer * STEER_MAX)) / WB;
    const lim = LAT_MAX / Math.max(Math.abs(vf), 1);
    let target = clamp(geo, -lim, lim);
    // Slide authority scales with total speed (not just forward speed) and always turns the way the
    // wheel points, so a car that is sideways or sliding backwards keeps rotating all the way round.
    // With the throttle on, the e-brake can pivot the car on the spot (donuts).
    let reach = Math.min(1, Math.hypot(vf, vr) / 12);
    if (eb && inp.throttle > 0) reach = Math.max(reach, 0.85);
    if (eb) {
      // Oversteer: the tail snaps out in the steering direction and counter-steer catches it.
      target = target * 1.3 + this.steer * 2.1 * reach;
    } else if (this.grip < GRIP - 1) {
      // Mid-slide the steering keeps a lot of authority over the angle.
      target = target * 1.3 + this.steer * 0.7 * reach;
    }
    if (this.airborne) target *= 0.4;
    this.yawRate += (target - this.yawRate) * Math.min(1, dt * (eb ? 7 : this.grip < GRIP - 1 ? 8 : 15));

    // Velocity keeps its direction while the body turns — that difference is the slip.
    this.vx = f0.fx * vf + f0.rx * vr;
    this.vz = f0.fz * vf + f0.rz * vr;
    this.yaw += this.yawRate * dt;

    const prevD = this.d;
    this.pos.x += this.vx * dt;
    this.pos.z += this.vz * dt;
    const fr = this.locate();

    this.barriers(fr, prevD, true);
    if (traffic) this.collide(traffic);
    if (this.wrecked) return;
    this.vertical(dt, inp, fr);
    if (!this.jets.boost && !this.jets.lift) this.fuel = Math.min(FUEL, this.fuel + 7 * dt);
    this.finish(dt, fr);
  }

  locate() {
    const pr = this.road.project(this.pos.x, this.pos.z, this.s);
    this.distance += Math.abs(pr.s - this.s);
    this.s = pr.s;
    this.d = pr.d;
    const fr = this.road.frame(this.s);
    this.groundY = fr.y;
    return fr;
  }

  // Outer guardrails always hold; the median barrier only stops a car that is low enough to hit it.
  barriers(fr, prevD, bounce) {
    const push = (target, side) => {
      const over = this.d - target;
      this.pos.x -= fr.rx * over;
      this.pos.z -= fr.rz * over;
      this.d = target;
      const vn = this.vx * fr.rx + this.vz * fr.rz;
      if (bounce && vn * side > 0) {
        this.vx = (this.vx - fr.rx * vn * 1.3) * 0.94;
        this.vz = (this.vz - fr.rz * vn * 1.3) * 0.94;
        // Glance off the rail: turn toward whichever way along the road the car already points.
        const along = Math.cos(this.yaw - fr.h) >= 0 ? fr.h : fr.h + Math.PI;
        this.yaw += wrap(along - this.yaw) * 0.25;
        this.yawRate *= 0.3;
        this.events.push({ type: 'scrape', power: Math.abs(vn) });
      } else if (!bounce && vn * side > 0) {
        this.vx -= fr.rx * vn;
        this.vz -= fr.rz * vn;
      }
    };
    const half = this.halfAcross;
    if (this.d > EDGE_R + HALF_W - half) push(EDGE_R + HALF_W - half, 1);
    if (this.d < EDGE_L - HALF_W + half) push(EDGE_L - HALF_W + half, -1);
    const m = LAYOUT.median;
    if (this.height < BARRIER_TOP && this.d + half > m - BARRIER_HALF && this.d - half < m + BARRIER_HALF) {
      const fromRight = prevD > m;
      push(fromRight ? m + BARRIER_HALF + half : m - BARRIER_HALF - half, fromRight ? -1 : 1);
    }
  }

  collide(traffic) {
    const me = { x: this.pos.x, z: this.pos.z, c: Math.cos(this.yaw), s: Math.sin(this.yaw), hl: HALF_L, hw: HALF_W };
    const touching = new Set();
    for (const t of traffic.cars) {
      if (Math.abs(t.s - this.s) > 12 || this.height > t.hgt - 0.15) continue;
      const hit = obb(me, { x: t.x, z: t.z, c: Math.cos(t.yaw), s: Math.sin(t.yaw), hl: t.hl, hw: t.hw });
      if (!hit) continue;
      touching.add(t);
      const fresh = !this.contacts.has(t);
      this.pos.x += hit.nx * hit.depth;
      this.pos.z += hit.nz * hit.depth;
      me.x = this.pos.x;
      me.z = this.pos.z;
      const tvx = Math.cos(t.yaw) * t.v, tvz = -Math.sin(t.yaw) * t.v;
      const rel = (this.vx - tvx) * hit.nx + (this.vz - tvz) * hit.nz;
      if (rel >= 0) continue;
      if (fresh && -rel > WRECK) {
        this.wreck(t, -rel);
        break;
      }
      this.vx = (this.vx - hit.nx * rel * 1.25) * 0.9;
      this.vz = (this.vz - hit.nz * rel * 1.25) * 0.9;
      if (fresh) {
        this.yawRate += (Math.random() - 0.5) * Math.min(1.2, -rel * 0.06);
        t.v *= 0.94;
        this.hits++;
        this.events.push({ type: 'hit', power: -rel });
      }
    }
    this.contacts = touching;
  }

  wreck(t, closing) {
    const facing = Math.cos(this.yaw) * Math.cos(t.yaw) + Math.sin(this.yaw) * Math.sin(t.yaw);
    const ahead = (t.s - this.s) * Math.sign(facing || 1);
    let kind;
    if (facing < -0.5) kind = 'Head-on with';
    else if (Math.abs(facing) < 0.5) kind = 'T-boned';
    else kind = ahead > 0 ? 'Rear-ended' : 'Hit from behind by';
    this.wrecked = true;
    this.wreckT = 0;
    this.wreckInfo = { kind, other: t.kind || 'car', closing };
    this.yawRate = (Math.random() < 0.5 ? -1 : 1) * (2.5 + Math.random() * 2.5);
    this.vy = Math.min(6, 2 + closing * 0.12);
    this.airborne = true;
    this.vx *= 0.45;
    this.vz *= 0.45;
    this.leanTarget = (Math.random() < 0.5 ? -1 : 1) * (0.25 + Math.random() * 0.2);
    t.v = 0;
    t.wrecked = true;
    this.hits++;
    this.events.push({ type: 'wreck', power: closing });
  }

  // After a wreck: the car spins and slides to a stop on its own.
  stepWreck(dt) {
    this.wreckT += dt;
    const sp = this.speed;
    if (sp > 0) {
      const k = Math.min(sp, 9 * dt) / sp;
      this.vx -= this.vx * k;
      this.vz -= this.vz * k;
    }
    this.yawRate *= Math.exp(-1.4 * dt);
    this.yaw += this.yawRate * dt;
    const prevD = this.d;
    this.pos.x += this.vx * dt;
    this.pos.z += this.vz * dt;
    const fr = this.locate();
    this.barriers(fr, prevD, false);
    const ground = fr.y + RIDE;
    if (this.airborne) {
      this.vy -= G * dt;
      this.pos.y += this.vy * dt;
      if (this.pos.y <= ground) {
        this.pos.y = ground;
        this.vy = 0;
        this.airborne = false;
      }
    } else {
      this.pos.y = ground;
    }
    this.lean += ((this.leanTarget || 0) - this.lean) * Math.min(1, dt * 5);
    this.pitch += (Math.atan(fr.slope) - 0.06 - this.pitch) * Math.min(1, dt * 5);
    const ax = this.axes();
    this.v = this.vx * ax.fx + this.vz * ax.fz;
  }

  vertical(dt, inp, fr) {
    const ground = fr.y + RIDE;
    if (inp.lift && !this.liftHeld && !this.airborne && this.fuel > 12) {
      this.vy = 6.5;
      this.airborne = true;
      this.fuel -= 12;
      this.events.push({ type: 'hop' });
    }
    this.liftHeld = inp.lift;
    if (this.airborne) {
      let ay = -G;
      if (inp.lift && this.fuel > 0) {
        ay += G * 0.85;
        this.fuel = Math.max(0, this.fuel - 28 * dt);
        this.jets.lift = true;
      }
      this.vy += ay * dt;
      this.pos.y += this.vy * dt;
      if (this.pos.y <= ground && this.vy <= 0) {
        this.events.push({ type: 'land', power: -this.vy });
        this.pos.y = ground;
        this.vy = 0;
        this.airborne = false;
      }
    } else {
      this.pos.y = ground;
    }
  }

  // Pose, odometer and g-load.
  finish(dt, fr) {
    const raw = Math.cos(this.yaw - fr.h) >= 0 ? 1 : -1;
    this.travelT = raw === this.travel ? 0 : this.travelT + dt;
    if (this.travelT > 1.2) {
      this.travel = raw;
      this.travelT = 0;
    }
    const ax = this.axes();
    this.v = this.vx * ax.fx + this.vz * ax.fz;
    this.vlat = this.vx * ax.rx + this.vz * ax.rz;
    this.vs = this.vx * fr.fx + this.vz * fr.fz;
    this.pitch += (Math.atan(fr.slope) + (this.airborne ? this.vy * 0.01 : 0) - this.pitch) * Math.min(1, dt * 8);
    const leanTarget = clamp(this.yawRate * this.v * 0.012 + this.vlat * 0.01, -0.1, 0.1);
    this.lean += (leanTarget - this.lean) * Math.min(1, dt * 10);
    this.roll += this.v * dt;
    this.top = Math.max(this.top, this.speed);
    const nvy = this.airborne ? this.vy : 0;
    const gx = (this.vx - this.vel.x) / dt, gy = (nvy - this.vel.y) / dt + G, gz = (this.vz - this.vel.z) / dt;
    this.gForce += (Math.min(6, Math.hypot(gx, gy, gz) / G) - this.gForce) * 0.05;
    this.vel = { x: this.vx, y: nvy, z: this.vz };
  }

  axes() {
    return { fx: Math.cos(this.yaw), fz: -Math.sin(this.yaw), rx: Math.sin(this.yaw), rz: Math.cos(this.yaw) };
  }
}
