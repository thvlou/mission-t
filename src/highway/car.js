import { LAYOUT } from './road.js';
import { vehicleLightState } from '../vehicle-controls.js';

// Arcade highway handling. The car carries a world-space velocity; its heading turns with the
// steering and lateral grip pulls the velocity back in line. Pull the e-brake (Shift) and the rear
// lets go: grip drops, the tail swings and the car drifts. Space hops and hovers, E boosts.
// Gravity acts along the road, so climbs cost speed and descents add it. A hard traffic collision
// wrecks the car and ends the run; race cars only bump each other. All speeds in m/s.
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
const BOOST_MIN = 12;      // fuel needed to light the boost; running dry locks it until E is released
const REGEN_DELAY = 0.8;   // s after the last jet before the tank starts to refill
const SLOPE_GAIN = 1.25;   // gravity along the road, a touch stronger than life so hills read
const BUMP_E = 0.35;       // restitution between two race cars
const INERTIA = (4.6 * 4.6 + 1.96 * 1.96) / 12; // yaw inertia per unit mass of a 4.6 × 1.96 m car, m²

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
    this.lights = { brake: false, reverse: false };
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
    this.grade = f.slope;   // road slope along the car's heading (rise per metre)
    this.boostOn = false;
    this.boostLock = false;
    this.liftLock = false;
    this.jetIdle = 0;
    this.spin = 0;          // extra yaw rate from knocks; fades on its own
    this.squat = 0;         // body pitch on the springs: nose up under power, down under braking
    this.vPrev = 0;
    this.prev = null;       // pose before the last physics step, for smooth drawing
    this.contactAt = new Map(); // race car id → time we last resolved a hit with it ourselves
    this.bumpedAt = new Map();  // race car id → time that player's own report of a hit reached us
    this.bumps = [];        // impulses we gave other race cars, sent to them by the race
  }

  // Remember the pose before a physics step; view() blends toward the new one.
  savePrev() {
    const p = this.prev || (this.prev = {});
    p.x = this.pos.x; p.y = this.pos.y; p.z = this.pos.z;
    p.yaw = this.yaw; p.pitch = this.pitch; p.lean = this.lean; p.roll = this.roll; p.squat = this.squat;
  }

  // The pose to draw: a blend of the last two physics steps (alpha = how far into the next step
  // the clock is), so motion stays smooth whatever the display's frame rate.
  view(alpha, out = { pos: {} }) {
    const p = this.prev;
    const mix = (a, b) => (p ? a + (b - a) * alpha : b);
    out.pos.x = mix(p?.x, this.pos.x);
    out.pos.y = mix(p?.y, this.pos.y);
    out.pos.z = mix(p?.z, this.pos.z);
    out.yaw = p ? p.yaw + wrap(this.yaw - p.yaw) * alpha : this.yaw;
    out.pitch = mix(p?.pitch, this.pitch);
    out.lean = mix(p?.lean, this.lean);
    out.roll = mix(p?.roll, this.roll);
    out.squat = mix(p?.squat, this.squat);
    return out;
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
    this.lights = vehicleLightState(inp.throttle, vf, eb);

    // Longitudinal. The boost needs a little in the tank to light, and running dry locks it until
    // E is released, so holding E can't live off the trickle of refuel.
    if (!inp.boost) this.boostLock = false;
    const wantBoost = inp.boost && inp.throttle >= 0;
    const boosting = wantBoost && !this.boostLock && this.fuel > 0 && (this.boostOn || this.fuel >= BOOST_MIN);
    if (wantBoost && !boosting) this.boostLock = true;
    this.boostOn = boosting;
    let a = 0;
    if (inp.throttle > 0 || boosting) {
      const top = boosting ? V_BOOST : V_TOP;
      const u = Math.max(0, vf) / top;
      // Engine pull fades toward top speed; past it (off a boost, or down a hill) a soft cap eases back.
      a = u < 1 ? ACC * (1 - u * u) + (boosting ? BOOST_ACC : 0) : -(vf - top) * 0.25;
      if (eb) a *= 0.4;
    } else if (inp.throttle < 0) {
      a = vf > 0.5 ? -BRAKE : vf > V_REV ? -4 : 0;
    }
    // Gravity along the road: a climb bleeds speed, a descent adds it, even off the throttle.
    if (!this.airborne) a -= G * SLOPE_GAIN * this.grade / Math.sqrt(1 + this.grade * this.grade);
    if (boosting) {
      this.fuel -= 22 * dt;
      if (this.fuel <= 0) {
        this.fuel = 0;
        this.boostLock = true;
      }
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
    this.yaw += (this.yawRate + this.spin) * dt;
    this.spin *= Math.exp(-2.4 * dt);

    const prevD = this.d;
    this.pos.x += this.vx * dt;
    this.pos.z += this.vz * dt;
    const fr = this.locate();

    this.barriers(fr, prevD, true);
    if (traffic) this.collide(traffic);
    if (this.wrecked) return;
    this.vertical(dt, inp, fr);
    // The tank refills a moment after the jets go quiet.
    this.jetIdle = this.jets.boost || this.jets.lift ? 0 : this.jetIdle + dt;
    if (this.jetIdle > REGEN_DELAY) this.fuel = Math.min(FUEL, this.fuel + 7 * dt);
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
        // The speed into the rail is lost (with a small bounce back), and friction takes a share of
        // the speed along it in proportion to how hard the car hit: a graze costs very little, a
        // square hit a lot.
        // Leaning on the rail after that (the steering still points into it) is only a light scrape.
        const impact = Math.abs(vn) > 1.5;
        const tx = this.vx - fr.rx * vn, tz = this.vz - fr.rz * vn;
        const tan = Math.hypot(tx, tz);
        const keep = tan > 0 ? Math.max(0, tan - Math.abs(vn) * (impact ? 0.25 : 0.04)) / tan : 0;
        this.vx = tx * keep - fr.rx * vn * (impact ? 0.25 : 0);
        this.vz = tz * keep - fr.rz * vn * (impact ? 0.25 : 0);
        // Glance off the rail: turn toward whichever way along the road the car already points.
        const along = Math.cos(this.yaw - fr.h) >= 0 ? fr.h : fr.h + Math.PI;
        const k = clamp(Math.abs(vn) / 12, 0.04, 0.45);
        this.yaw += wrap(along - this.yaw) * k;
        this.yawRate *= 1 - k * 2;
        if (Math.abs(vn) > 0.6) {
          this.events.push({ type: 'scrape', power: Math.abs(vn), x: this.pos.x + fr.rx * side * HALF_W, y: this.pos.y - 0.2, z: this.pos.z + fr.rz * side * HALF_W });
        }
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
      if (t.player) {
        this.bump(t, hit, fresh);
        continue;
      }
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
        this.events.push({ type: 'hit', power: -rel, x: this.pos.x - hit.nx * HALF_W, y: this.pos.y - 0.1, z: this.pos.z - hit.nz * HALF_W });
      }
    }
    this.contacts = touching;
  }

  // Car against race car: an impulse between two equal masses, with some bounce and a little
  // friction, applied where the cars touch, so an off-centre knock spins the car. The other car is
  // drawn from the network, so its half of the impulse goes two ways: onto its proxy (t.kvx/kvz,
  // so it visibly reacts here and doesn't keep shoving) and out to that player (this.bumps).
  bump(t, hit, fresh) {
    const nx = hit.nx, nz = hit.nz; // from the other car toward us
    const a = this.axes();
    // Contact: the point of our box nearest the other car's centre.
    const ox = t.x - this.pos.x, oz = t.z - this.pos.z;
    const lf = clamp(ox * a.fx + oz * a.fz, -HALF_L, HALF_L), lr = clamp(ox * a.rx + oz * a.rz, -HALF_W, HALF_W);
    const rx = a.fx * lf + a.rx * lr, rz = a.fz * lf + a.rz * lr;
    const w = this.yawRate + this.spin;
    const tvx = t.vx + t.kvx, tvz = t.vz + t.kvz;
    const rel = (this.vx + w * rz - tvx) * nx + (this.vz - w * rx - tvz) * nz;
    if (rel >= 0) return;
    // That player already reported this knock and we've taken it; just keep the cars apart.
    if (this.time - (this.bumpedAt.get(t.id) ?? -1e9) < 0.3) {
      this.vx -= nx * rel;
      this.vz -= nz * rel;
      return;
    }
    const rn = rz * nx - rx * nz; // (r × n)·up
    const j = (-(1 + BUMP_E) * rel) / (2 + (rn * rn) / INERTIA);
    this.vx += j * nx;
    this.vz += j * nz;
    // Rubbing doors: friction along the contact takes a little of the sliding speed.
    const vn = (this.vx - tvx) * nx + (this.vz - tvz) * nz;
    const sx = this.vx - tvx - nx * vn, sz = this.vz - tvz - nz * vn;
    const sl = Math.hypot(sx, sz);
    if (sl > 0.05) {
      const fj = Math.min(sl * 0.5, j * 0.2);
      this.vx -= (sx / sl) * fj;
      this.vz -= (sz / sl) * fj;
    }
    this.spin = clamp(this.spin + (rn * j) / INERTIA, -3, 3);
    // A real knock breaks the tyres loose for a moment, so the push carries instead of being gripped away.
    if (j > 1.5) this.grip = Math.min(this.grip, Math.max(2.2, GRIP - j * 0.9));
    this.contactAt.set(t.id, this.time);
    // The other car's half, at its own contact point.
    const qx = this.pos.x + rx - t.x, qz = this.pos.z + rz - t.z;
    const dw = clamp((-(qz * nx - qx * nz) * j) / INERTIA, -3, 3);
    t.kvx -= j * nx;
    t.kvz -= j * nz;
    this.bumps.push({ id: t.id, dvx: -j * nx, dvz: -j * nz, dw });
    if (fresh || j > 2) {
      this.hits++;
      this.events.push({ type: 'bump', power: -rel, x: this.pos.x + rx, y: this.pos.y - 0.15, z: this.pos.z + rz });
    }
  }

  // Another player's report that they knocked into us: their half of the impulse, in road terms
  // (along the road, across it, and a spin), unless we already resolved that hit ourselves.
  applyBump(from, dvs, dvd, dw) {
    if (this.wrecked || !this.started) return;
    if (this.time - (this.contactAt.get(from) ?? -1e9) < 0.3) return;
    this.bumpedAt.set(from, this.time);
    const f = this.road.frame(this.s);
    const dvx = f.fx * dvs + f.rx * dvd, dvz = f.fz * dvs + f.rz * dvd;
    this.vx += dvx;
    this.vz += dvz;
    this.spin = clamp(this.spin + dw, -3, 3);
    const j = Math.hypot(dvx, dvz);
    if (j > 1.5) this.grip = Math.min(this.grip, Math.max(2.2, GRIP - j * 0.9));
    if (j > 0.3) {
      // Sparks on the side the hit came from.
      const k = HALF_W / j;
      this.events.push({ type: 'bump', power: j * 1.5, x: this.pos.x - dvx * k, y: this.pos.y - 0.15, z: this.pos.z - dvz * k });
    }
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
    if (!inp.lift) this.liftLock = false;
    if (this.airborne) {
      let ay = -G;
      if (inp.lift && !this.liftLock && this.fuel > 0) {
        ay += G * 0.85;
        this.fuel -= 28 * dt;
        if (this.fuel <= 0) {
          this.fuel = 0;
          this.liftLock = true;
        }
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
    this.grade = fr.slope * Math.cos(this.yaw - fr.h);
    this.pitch += (Math.atan(fr.slope) + (this.airborne ? this.vy * 0.01 : 0) - this.pitch) * Math.min(1, dt * 8);
    // The body on its springs (the wheels stay on the road): roll in corners, squat and dive.
    const leanTarget = clamp(this.yawRate * this.v * 0.009 + this.vlat * 0.008, -0.065, 0.065);
    this.lean += (leanTarget - this.lean) * Math.min(1, dt * 8);
    const accel = this.airborne ? 0 : (this.v - this.vPrev) / dt;
    this.vPrev = this.v;
    this.squat += (clamp(accel * 0.0032, -0.035, 0.03) - this.squat) * Math.min(1, dt * 6);
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
