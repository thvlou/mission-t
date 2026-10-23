import { BURN_SHARE, DECK, OBSTACLES } from './config.js';

export const STEP = 1 / 120;
export const RIDE = 0.6;             // car centre above the riding surface
export const BACK = DECK + RIDE;     // car centre below the deck line when riding the outside

// Contact points around the body, in local coordinates (x forward, y up).
export const HULL = [
  { x: 1.38, y: -0.6, wheel: true },
  { x: -1.38, y: -0.6, wheel: true },
  { x: 2.3, y: -0.2 },
  { x: -2.25, y: -0.05 },
  { x: 2.1, y: -0.32 },
  { x: -2.1, y: -0.32 },
  { x: -0.35, y: 0.6 },
  { x: -1.55, y: 0.45 },
];
const HALF_LENGTH = 2.25;
const INERTIA = (4.5 * 4.5 + 1.2 * 1.2) / 12;
const DRAG = 0.004;

const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
export const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const deg = (r) => (r * 180) / Math.PI;

// Side-plane stunt simulation.
// state: ready → track (driving, either face of the deck) → air → landed | crashed
// side: +1 rides the inside of the curve, -1 rides the outside/top.
export class Sim {
  constructor(track, challenge, params) {
    this.track = track;
    this.p = params;
    this.obstacles = OBSTACLES;
    this.input = { throttle: 0, spin: 0, lift: false, boost: false };
    this.events = [];
    this.acc = 0;
    this.setChallenge(challenge);
  }

  setChallenge(challenge) {
    this.challenge = challenge;
    this.reset();
  }

  reset() {
    this.state = 'ready';
    this.side = 1;
    this.s = this.challenge.startS;
    this.v = 0;
    this.omega = 0;
    this.fuel = this.p.fuel;
    this.t = 0;
    this.endT = 0;
    this.turned = 0;
    this.peak = 0;
    this.releaseH = 0;
    this.launchT = 0;
    this.launchX = 0;
    this.fromRamp = false;
    this.progress = -1;
    this.result = null;
    this.rest = 0;
    this.roll = 0;
    this.gForce = 1;
    this.jets = { lift: false, boost: false, spin: 0, grip: false };
    this.place();
  }

  get done() {
    return this.state === 'landed' || this.state === 'crashed';
  }

  get height() {
    return Math.max(0, this.y - RIDE);
  }

  // True when lift has to start now to get the sink rate under the limit before touchdown.
  get brakeCue() {
    if (this.state !== 'air' || this.fuel <= 0 || this.vy > -2) return false;
    const upright = Math.cos(this.theta);
    const net = (this.p.lift * upright - 1) * this.p.gravity;
    if (upright < 0.5 || net <= 0) return false;
    const goal = this.p.landSpeed * 0.5;
    const distance = Math.max(0, this.vy * this.vy - goal * goal) / (2 * net);
    return this.height < distance * 1.25 + 2;
  }

  update(dt) {
    this.acc += dt;
    let n = 0;
    while (this.acc >= STEP && n < 60) {
      this.acc -= STEP;
      n++;
      const vx = this.vx, vy = this.vy;
      this.step(STEP);
      const ax = (this.vx - vx) / STEP;
      const ay = (this.vy - vy) / STEP + this.p.gravity;
      const g = Math.min(9, Math.hypot(ax, ay) / this.p.gravity);
      this.gForce += (g - this.gForce) * 0.06;
    }
  }

  // Put the car on the deck at arc length s, wheels against the current face.
  place() {
    const q = this.track.at(this.s);
    const off = this.side > 0 ? RIDE : -BACK;
    this.x = q.x - Math.sin(q.a) * off;
    this.y = q.y + Math.cos(q.a) * off;
    this.theta = q.a + (this.side > 0 ? 0 : Math.PI);
    this.vx = this.v * Math.cos(q.a);
    this.vy = this.v * Math.sin(q.a);
  }

  burn(kind, dt) {
    this.fuel = Math.max(0, this.fuel - this.p.burn * BURN_SHARE[kind] * dt);
  }

  step(dt) {
    const inp = this.input;
    this.t += dt;
    this.jets = { lift: false, boost: false, spin: 0, grip: false };
    if (this.state === 'ready') {
      if (!inp.throttle && !inp.lift && !inp.boost) return;
      this.state = 'track';
      this.events.push('go');
    }
    if (this.state === 'track' || this.state === 'landed') this.stepTrack(dt);
    else if (this.state === 'air') this.stepAir(dt);
    else this.stepWreck(dt);
  }

  stepTrack(dt) {
    const p = this.p, g = p.gravity, inp = this.input, T = this.track, side = this.side;
    const q = T.at(this.s);
    const cos = Math.cos(q.a), sin = Math.sin(q.a);
    const flat = side > 0 && cos > 0.97;
    const landed = this.state === 'landed';

    if (landed) {
      // Braking to a stop after a scored landing.
      this.v -= Math.sign(this.v) * Math.min(Math.abs(this.v), 12 * dt);
    } else {
      const driving = inp.throttle !== 0;
      const boosting = inp.boost && this.fuel > 0;
      if (driving) {
        // Holding the throttle keeps the electro-grip on, at any angle.
        this.jets.grip = !flat;
        const target = inp.throttle * side * (flat ? p.cruise : p.climb);
        const pull = target - this.v;
        const motorBrakes = pull * side < 0;
        if (!(boosting && inp.throttle > 0 && motorBrakes)) this.v += clamp(pull * 2.5, -9, 9) * dt;
      } else {
        this.v -= g * sin * dt;
        this.v -= Math.sign(this.v) * Math.min(Math.abs(this.v), 0.4 * dt);
      }
      if (boosting) {
        this.v += side * p.boost * g * dt;
        this.burn('boost', dt);
        this.jets.boost = true;
      }

      // Without grip the deck must push on the wheels, or the car peels away.
      const k = q.k;
      const support = side > 0 ? this.v * this.v * k + g * cos : -(this.v * this.v * k) / (1 + BACK * k) - g * cos;
      if (!driving && support < 0.25 * g) return this.leave(1.4);
      if (inp.lift && this.fuel > 0) return this.leave(0.3);
    }

    this.s += this.v * dt;
    this.roll += this.v * side * dt;

    if (side < 0) {
      // The outside is only rideable along the overhang roof; past its edge the car drops off.
      const lo = T.breaks[2];
      if (this.s >= T.length || this.s <= lo) {
        this.s = clamp(this.s, lo, T.length);
        if (landed) this.v = 0;
        else return this.leave(0.2);
      }
    } else if (landed) {
      if (this.s > T.curveStart) {
        this.s = T.curveStart;
        this.v = 0;
      }
    } else if (this.s >= T.length) {
      this.s = T.length;
      this.events.push('lip');
      return this.leave(0.4);
    }
    if (this.s < 0) {
      this.s = 0;
      this.v = 0;
    }
    if (!landed && side > 0 && this.s > T.curveStart) this.progress = Math.max(this.progress, this.s);
    this.place();
    if (flat) this.checkDriveInto();
    if (landed && Math.abs(this.v) < 0.05) this.rest += dt;
  }

  checkDriveInto() {
    for (const o of this.obstacles) {
      if (this.x + HALF_LENGTH > o.x0 && this.x - HALF_LENGTH < o.x1) {
        const v = this.v;
        this.vx = -Math.sign(v || 1) * Math.min(6, Math.abs(v) * 0.3);
        this.vy = Math.min(5, Math.abs(v) * 0.25);
        this.x += this.vx > 0 ? 0.2 : -0.2;
        return this.crash(`Drove into the ${o.label}`);
      }
    }
  }

  leave(push) {
    const q = this.track.at(this.s);
    const nx = -Math.sin(q.a) * this.side, ny = Math.cos(q.a) * this.side;
    this.vx = this.v * Math.cos(q.a) + nx * push;
    this.vy = this.v * Math.sin(q.a) + ny * push;
    this.omega = this.v * q.k;
    this.state = 'air';
    this.launchT = this.t;
    this.launchX = this.x;
    this.releaseH = this.height;
    this.peak = this.releaseH;
    this.turned = 0;
    this.fromRamp = this.s > this.track.curveStart + 0.5;
    this.events.push('launch');
  }

  stepAir(dt) {
    const p = this.p, g = p.gravity, inp = this.input;
    const c = Math.cos(this.theta), s = Math.sin(this.theta);
    let ax = 0, ay = -g;
    const hasFuel = this.fuel > 0;
    if (inp.lift && hasFuel) {
      ax -= s * p.lift * g;
      ay += c * p.lift * g;
      this.burn('lift', dt);
      this.jets.lift = true;
    }
    if (inp.boost && hasFuel) {
      ax += c * p.boost * g;
      ay += s * p.boost * g;
      this.burn('boost', dt);
      this.jets.boost = true;
    }
    if (inp.spin && hasFuel) {
      this.omega += inp.spin * p.spin * dt;
      this.burn('spin', dt);
      this.jets.spin = inp.spin;
    }
    // Attitude jets hold the angle while there is fuel; otherwise only air damps the spin.
    const damping = !inp.spin && hasFuel ? p.steady : 0.25;
    this.omega *= Math.max(0, 1 - damping * dt);

    const sp = Math.hypot(this.vx, this.vy);
    ax -= this.vx * sp * DRAG;
    ay -= this.vy * sp * DRAG;
    this.vx += ax * dt;
    this.vy += ay * dt;
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.theta += this.omega * dt;
    this.turned += this.omega * dt;
    this.peak = Math.max(this.peak, this.height);
    this.airContacts();
  }

  hullPoint(h) {
    const c = Math.cos(this.theta), s = Math.sin(this.theta);
    const rx = h.x * c - h.y * s, ry = h.x * s + h.y * c;
    return { x: this.x + rx, y: this.y + ry, rx, ry };
  }

  obstacleAt(x, y) {
    return this.obstacles.find((o) => x > o.x0 && x < o.x1 && y < o.h) || null;
  }

  airContacts() {
    const p = this.p, T = this.track;
    const q = T.closest(this.x, this.y, T.curveStart);
    const onDeck = q && q.inside && q.s > T.curveStart + 0.3;

    if (onDeck && q.d <= -DECK / 2 && q.d > -(BACK - 0.03)) return this.touchOutside(q);
    if (onDeck && q.d < RIDE - 0.03 && q.d > -DECK / 2) {
      const up = -Math.sin(this.theta) * q.nx + Math.cos(this.theta) * q.ny;
      const into = -(this.vx * q.nx + this.vy * q.ny);
      if (up > Math.cos(Math.PI / 6) && into < p.landSpeed) {
        this.state = 'track';
        this.side = 1;
        this.s = q.s;
        this.v = this.vx * Math.cos(q.a) + this.vy * Math.sin(q.a);
        this.omega = 0;
        this.place();
        this.events.push('reattach');
        return;
      }
      this.x += q.nx * (RIDE - q.d);
      this.y += q.ny * (RIDE - q.d);
      return this.crash('Hit the ramp face');
    }

    const pts = HULL.map((h) => this.hullPoint(h));
    for (const pt of pts) {
      const o = this.obstacleAt(pt.x, pt.y);
      if (o) {
        this.vx *= -0.2;
        this.vy = Math.max(this.vy, 2);
        return this.crash(`Clipped the ${o.label}`);
      }
    }

    let low = Infinity;
    for (const pt of pts) low = Math.min(low, pt.y);
    if (low > 0) return;
    const tilt = deg(Math.abs(wrap(this.theta)));
    const wheels = pts.some((pt, i) => HULL[i].wheel && pt.y - low < 0.12);
    const sink = -this.vy;
    if (tilt <= p.landAngle && wheels && sink <= p.landSpeed) return this.land(sink, tilt, false);
    this.y -= low;
    if (tilt <= p.landAngle && wheels) this.crash('Came down too hard');
    else if (tilt > 100) this.crash('Landed on the roof');
    else this.crash(Math.sin(wrap(this.theta)) < 0 ? 'Nosed in' : 'Tail-first impact');
  }

  // Contact with the outside of the deck: the back of the wall or the top of the overhang.
  touchOutside(q) {
    const p = this.p;
    const ox = -q.nx, oy = -q.ny; // outward normal of this face
    const up = -Math.sin(this.theta) * ox + Math.cos(this.theta) * oy;
    const tilt = deg(Math.acos(clamp(up, -1, 1)));
    const into = -(this.vx * ox + this.vy * oy);
    if (tilt <= p.landAngle && into <= p.landSpeed) {
      this.side = -1;
      this.s = q.s;
      this.v = this.vx * Math.cos(q.a) + this.vy * Math.sin(q.a);
      this.omega = 0;
      if (oy > 0.85) return this.land(into, tilt, true);
      this.state = 'track';
      this.place();
      this.events.push('reattach');
      return;
    }
    const push = BACK + q.d;
    this.x += ox * push;
    this.y += oy * push;
    const vn = this.vx * ox + this.vy * oy;
    if (vn < 0) {
      this.vx -= 1.3 * vn * ox;
      this.vy -= 1.3 * vn * oy;
    }
    if (oy < 0.5) this.crash('Hit the back of the ramp');
    else if (tilt > 100) this.crash('Upside down on the roof');
    else this.crash('Hit the roof too hard');
  }

  cleared() {
    const lo = Math.min(this.launchX, this.x), hi = Math.max(this.launchX, this.x);
    return this.obstacles.filter((o) => o.x0 > lo && o.x1 < hi - HALF_LENGTH / 2).length;
  }

  land(sink, tilt, onTop) {
    const air = this.t - this.launchT;
    const cleared = this.cleared();
    const kind = onTop || this.fromRamp ? 'ramp' : cleared > 0 ? 'jump' : null;
    this.omega = 0;
    if (!onTop) {
      this.side = 1;
      this.s = clamp(this.x - this.track.x0, 0, this.track.curveStart);
      this.v = this.vx;
    }
    this.place();
    if (!kind) {
      // A hop on the run-in that cleared nothing: just keep driving.
      this.state = 'track';
      this.events.push('hop');
      return;
    }
    this.state = 'landed';
    this.endT = this.t;
    this.rest = 0;
    this.events.push('land');
    this.result = this.score({ sink, tilt, air, onTop, kind, cleared });
  }

  score({ sink, tilt, air, onTop, kind, cleared }) {
    const p = this.p, zone = this.challenge.zone;
    const soft = clamp(1 - sink / p.landSpeed, 0, 1);
    const level = clamp(1 - tilt / p.landAngle, 0, 1);
    const turns = Math.abs(this.turned) / (2 * Math.PI);
    // Leaving the inside of the overhang means half a turn is spent just getting upright.
    const owed = kind === 'ramp' && !onTop ? 0.5 : 0;
    const flips = Math.max(0, Math.floor(turns - owed + 0.08));
    const miss = Math.abs(this.x - zone.x);
    const inZone = !onTop && miss <= zone.half;
    const bull = inZone && miss <= zone.half * 0.3;
    const fuelPct = (this.fuel / p.fuel) * 100;
    const lines = [];
    if (kind === 'jump') {
      lines.push(
        { label: 'Cleared', value: `${cleared} / ${this.obstacles.length}`, pts: cleared * 600 },
        { label: 'Peak height', value: `${this.peak.toFixed(1)} m`, pts: Math.round(this.peak * 40) },
      );
    } else {
      lines.push({ label: 'Release height', value: `${this.releaseH.toFixed(1)} m`, pts: Math.round(this.releaseH * 60) });
    }
    lines.push(
      { label: 'Air time', value: `${air.toFixed(2)} s`, pts: Math.round(air * 150) },
      { label: 'Flips', value: `${flips}`, pts: flips * 800 },
      { label: 'Touchdown', value: `${Math.round((soft + level) * 50)}%`, pts: Math.round((soft + level) * 200) },
    );
    if (onTop) lines.push({ label: 'Roof landing', value: 'Yes', pts: 1500 });
    else lines.push({ label: 'Target zone', value: bull ? 'Bullseye' : inZone ? 'Inside' : `${(miss - zone.half).toFixed(1)} m off`, pts: bull ? 800 : inZone ? 400 : 0 });
    lines.push({ label: 'Fuel left', value: `${Math.round(fuelPct)}%`, pts: Math.round(fuelPct * 3) });
    const total = 10 * Math.round(lines.reduce((sum, l) => sum + l.pts, 0) / 10);

    const clean = soft > 0.75 && level > 0.75;
    const complete = kind === 'ramp' || cleared === this.obstacles.length;
    let title;
    if (onTop) title = clean ? 'Perfect Roof' : 'Roof Landing';
    else if (!complete) title = 'Too Short';
    else if (clean && inZone) title = 'Perfect';
    else if (soft > 0.5 && level > 0.5) title = 'Clean Landing';
    else title = 'Landed';
    return { ok: true, title, reason: '', total, lines, flips, inZone, kind };
  }

  crash(reason) {
    this.state = 'crashed';
    this.endT = this.t;
    this.omega += (Math.random() - 0.5) * 3;
    this.rest = 0;
    this.events.push('crash');
    this.result = { ok: false, title: 'Crashed', reason, total: 0, lines: [] };
  }

  // Tumbling wreck: a rigid body bouncing on its hull points.
  stepWreck(dt) {
    const g = this.p.gravity, T = this.track;
    this.vy -= g * dt;
    const sp = Math.hypot(this.vx, this.vy);
    this.vx -= this.vx * sp * DRAG * dt;
    this.vy -= this.vy * sp * DRAG * dt;
    this.x += this.vx * dt;
    this.y += this.vy * dt;
    this.theta += this.omega * dt;

    let low = 0;
    for (const h of HULL) {
      const pt = this.hullPoint(h);
      if (pt.y >= 0) continue;
      low = Math.min(low, pt.y);
      const px = this.vx - this.omega * pt.ry;
      const py = this.vy + this.omega * pt.rx;
      if (py >= 0) continue;
      const jn = (-1.25 * py) / (1 + (pt.rx * pt.rx) / INERTIA);
      this.vy += jn;
      this.omega += (pt.rx * jn) / INERTIA;
      const jt = clamp(-px / (1 + (pt.ry * pt.ry) / INERTIA), -0.6 * jn, 0.6 * jn);
      this.vx += jt;
      this.omega -= (pt.ry * jt) / INERTIA;
    }
    if (low < 0) this.y -= low * 0.5;

    for (const o of this.obstacles) {
      if (this.x > o.x0 - 1 && this.x < o.x1 + 1 && this.y < o.h + RIDE) {
        if (this.y > o.h - 0.2 && this.vy <= 0) {
          this.y = o.h + RIDE;
          this.vy *= -0.25;
          this.vx *= 0.8;
        } else {
          const left = this.x - (o.x0 - 1) < o.x1 + 1 - this.x;
          this.x = left ? o.x0 - 1 : o.x1 + 1;
          this.vx = (left ? -1 : 1) * Math.abs(this.vx) * 0.25;
        }
      }
    }

    const q = T.closest(this.x, this.y, T.curveStart);
    if (q && q.inside && q.s > T.curveStart + 0.3 && q.d < RIDE && q.d > -BACK) {
      const front = q.d > -DECK / 2;
      const goal = front ? RIDE : -BACK;
      this.x += q.nx * (goal - q.d);
      this.y += q.ny * (goal - q.d);
      const sign = front ? 1 : -1;
      const vn = (this.vx * q.nx + this.vy * q.ny) * sign;
      if (vn < 0) {
        this.vx -= 1.3 * vn * q.nx * sign;
        this.vy -= 1.3 * vn * q.ny * sign;
      }
    }

    const still = Math.hypot(this.vx, this.vy) < 0.4 && Math.abs(this.omega) < 0.4 && this.y < 5;
    this.rest = still ? this.rest + dt : 0;
  }
}
