// Engines are engine-sim recordings (tools/engine-sim): for each car an idle loop plus dyno-held RPM
// loops at full throttle (on-load) and closed throttle (off-load), listed in assets/audio/engines.json.
// The mixer plays the two recordings either side of the current revs, pitched to match, and blends the
// on- and off-load sets by throttle. Boost and the hover jets share one rocket loop with an ignition
// burst, and drift is one real tyre recording for every car. Hits, chimes and the attitude puffs are
// synthesised, as are the motor and squeal that stand in until the recordings arrive.
const VOLUME = 0.8;
const AUDIO = (path) => new URL(`../assets/audio/${path}`, import.meta.url);
// Speed (m/s) at which each gear reaches the redline; the game's top speed is the last one.
const GEARS = [14, 27, 41, 56, 72, 92];
const UPSHIFT = 0.97;     // share of a gear's top speed at which it shifts up
const DOWNSHIFT = 0.6;    // share of the lower gear's top speed below which it shifts down
const SHIFT_CUT = 0.11;   // seconds the throttle is cut while a gear changes

const clamp = (v, lo, hi) => Math.min(hi, Math.max(lo, v));
let manifest = null;

export class Sound {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this.vehicle = null;
    this.set = null;     // the current car's playing layers
    this.shared = null;  // rocket and drift, the same for every car
    this.loadToken = 0;
    this.rpm = 0;
    this.gear = 0;
    this.load = 0;
    this.shiftUntil = 0;
    this.lastT = 0;
    this.jetting = false;
  }

  // Swaps in a car's engine; safe to call before audio has started.
  setVehicle(id) {
    if (id === this.vehicle) return;
    this.vehicle = id;
    if (this.ctx) this.loadSet();
  }

  // The engine set for the car currently chosen, once it is playing.
  get current() {
    return this.set?.id === this.vehicle ? this.set : null;
  }

  async decode(path) {
    const res = await fetch(AUDIO(path));
    if (!res.ok) throw new Error(`${res.status} for ${path}`);
    return this.ctx.decodeAudioData(await res.arrayBuffer());
  }

  loop(buffer, gain, t) {
    const s = this.ctx.createBufferSource();
    s.buffer = buffer;
    s.loop = true;
    s.connect(gain);
    s.start(t, Math.random() * buffer.duration);
    return s;
  }

  async loadSet() {
    const id = this.vehicle, token = ++this.loadToken, ctx = this.ctx;
    if (!id) return;
    try {
      manifest ||= fetch(AUDIO('engines.json')).then((r) => r.json());
      const spec = (await manifest)[id];
      if (!spec) throw new Error(`no engine recordings for ${id}`);
      // Both sets start from the idle loop; it is fetched once and played twice.
      const decoded = new Map();
      const layer = async (rpm, file, bus) => {
        if (!decoded.has(file)) decoded.set(file, this.decode(`engines/${id}/${file}`));
        return { rpm, file, bus, buffer: await decoded.get(file) };
      };
      const [on, off] = await Promise.all([
        Promise.all([layer(spec.idle, 'idle.wav', 'on'), ...spec.on.map((r) => layer(r, `on-${r}.wav`, 'on'))]),
        Promise.all([layer(spec.idle, 'idle.wav', 'off'), ...spec.off.map((r) => layer(r, `off-${r}.wav`, 'off'))]),
      ]);
      if (token !== this.loadToken) return;
      const t = ctx.currentTime;
      if (this.set) for (const l of [...this.set.on, ...this.set.off]) { try { l.src.stop(t + 0.15); } catch { /* stopped */ } }
      const start = (l) => {
        l.gain = ctx.createGain();
        l.gain.gain.value = 0;
        l.gain.connect(l.bus === 'on' ? this.onBus : this.offBus);
        l.src = this.loop(l.buffer, l.gain, t);
        return l;
      };
      this.set = { id, spec, on: on.map(start), off: off.map(start) };
      this.rpm = spec.idle;
    } catch (err) {
      if (token === this.loadToken) console.warn('Engine recordings failed to load; using the synthesised motor.', err);
    }
  }

  async loadShared() {
    try {
      const [rocket, ignite, drift] = await Promise.all(['rocket-loop.wav', 'rocket-ignite.wav', 'drift.wav'].map((f) => this.decode(f)));
      const t = this.ctx.currentTime;
      this.shared = { ignite, rocket: this.loop(rocket, this.rocketGain, t), drift: this.loop(drift, this.driftGain, t) };
    } catch (err) {
      console.warn('Rocket and tyre recordings failed to load; using synthesised ones.', err);
    }
  }

  get running() {
    return !!this.ctx && this.ctx.state === 'running';
  }

  // Browsers only let audio start from a user gesture, and may hand back a suspended context even
  // then (or suspend it when the tab is hidden), so every gesture also resumes it.
  start() {
    if (this.muted) return;
    if (this.ctx) {
      if (this.ctx.state !== 'running') this.ctx.resume().catch(() => {});
      return;
    }
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) return;
    const ctx = (this.ctx = new Ctx());
    if (ctx.state !== 'running') ctx.resume().catch(() => {});
    this.out = ctx.createGain();
    this.out.gain.value = VOLUME;
    // Engine, rocket and tyres can all peak together; a gentle limiter keeps that from clipping.
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -10;
    limiter.knee.value = 8;
    limiter.ratio.value = 6;
    this.out.connect(limiter).connect(ctx.destination);

    const bus = (to, value = 0) => { const g = ctx.createGain(); g.gain.value = value; g.connect(to); return g; };
    this.engineGain = bus(this.out);
    this.onBus = bus(this.engineGain);
    this.offBus = bus(this.engineGain);
    this.rocketGain = bus(this.out);
    this.driftGain = bus(this.out);

    const len = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;
    const noise = () => { const s = ctx.createBufferSource(); s.buffer = this.noise; s.loop = true; s.start(0, Math.random() * 2); return s; };

    // Forced induction the recordings lack: turbo intake whoosh and supercharger whine, both following revs.
    this.turboFilter = ctx.createBiquadFilter();
    this.turboFilter.type = 'bandpass';
    this.turboFilter.Q.value = 1.2;
    this.turboGain = bus(this.engineGain);
    noise().connect(this.turboFilter).connect(this.turboGain);
    this.whine = ctx.createOscillator();
    this.whine.type = 'triangle';
    this.whineGain = bus(this.engineGain);
    this.whine.connect(this.whineGain);
    this.whine.start();

    // Electric motor whine, until the engine recordings arrive
    this.motor = ctx.createOscillator();
    this.motor.type = 'sawtooth';
    const motorFilter = ctx.createBiquadFilter();
    motorFilter.type = 'lowpass';
    motorFilter.frequency.value = 900;
    this.motorGain = bus(this.out);
    this.motor.connect(motorFilter).connect(this.motorGain);
    this.motor.start();

    // Jet roar: the attitude puffs, and lift and boost until the rocket recording arrives
    this.jetFilter = ctx.createBiquadFilter();
    this.jetFilter.type = 'bandpass';
    this.jetFilter.Q.value = 0.8;
    this.jetGain = bus(this.out);
    noise().connect(this.jetFilter).connect(this.jetGain);

    // Tyre squeal: narrow-band noise around 1–2 kHz plus a faint wavering tone, until the recording arrives.
    this.squealFilter = ctx.createBiquadFilter();
    this.squealFilter.type = 'bandpass';
    this.squealFilter.frequency.value = 1400;
    this.squealFilter.Q.value = 9;
    this.squealTone = ctx.createOscillator();
    this.squealTone.type = 'triangle';
    this.squealTone.frequency.value = 1100;
    this.squealGain = bus(this.out);
    const toneGain = bus(this.squealGain, 0.05);
    noise().connect(this.squealFilter).connect(this.squealGain);
    this.squealTone.connect(toneGain);
    this.squealTone.start();

    this.loadShared();
    this.loadSet();
  }

  // level 0..1 from how hard the tyres slide; speed in m/s bends the pitch.
  skid(level, speed = 0) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime, on = level > 0.02;
    if (this.shared) {
      this.shared.drift.playbackRate.setTargetAtTime(0.92 + Math.min(speed, 60) / 60 * 0.12, t, 0.08);
      this.driftGain.gain.setTargetAtTime(on ? 0.18 + level * 0.5 : 0, t, on ? 0.05 : 0.12);
      this.squealGain.gain.setTargetAtTime(0, t, 0.05);
      return;
    }
    const wobble = Math.sin(t * 23) * 60 + Math.sin(t * 7.3) * 40;
    this.squealFilter.frequency.setTargetAtTime(1100 + Math.min(speed, 60) * 9 + wobble, t, 0.03);
    this.squealTone.frequency.setTargetAtTime(900 + Math.min(speed, 60) * 6 + wobble, t, 0.03);
    this.squealGain.gain.setTargetAtTime(on ? 0.12 + level * 0.32 : 0, t, on ? 0.04 : 0.09);
  }

  toggle() {
    this.muted = !this.muted;
    if (this.ctx) this.out.gain.value = this.muted ? 0 : VOLUME;
    if (!this.muted) this.start();
    return this.muted;
  }

  // Revs from road speed through a six-speed box. Upshifts cut the throttle for a moment, as a
  // real car does, instead of jumping straight to the lower revs.
  revsFor(speed, throttle, rolling, spec, t) {
    const { idle, redline } = spec;
    if (rolling) {
      const top = GEARS[this.gear];
      if (this.gear < GEARS.length - 1 && speed > top * UPSHIFT) { this.gear++; this.shiftUntil = t + SHIFT_CUT; }
      else if (this.gear > 0 && speed < GEARS[this.gear - 1] * DOWNSHIFT) this.gear--;
    }
    const geared = speed / GEARS[this.gear] * redline;
    // Pulling away the clutch slips, so the engine sits above idle with the throttle down.
    const slip = idle + Math.max(0, throttle) * (redline - idle) * 0.32;
    if (!rolling) return idle + Math.max(0, throttle) * (redline - idle) * 0.8;
    return clamp(Math.max(geared, this.gear === 0 ? slip : idle), idle, redline);
  }

  update(sim, throttle) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime, dt = clamp(t - this.lastT, 0, 0.1);
    this.lastT = t;
    const speed = Math.hypot(sim.vx, sim.vy);
    const rolling = sim.state === 'track' || sim.state === 'landed';
    const j = sim.jets;
    const set = this.current;
    if (set) {
      const { spec } = set;
      const target = this.revsFor(speed, throttle, rolling, spec, t);
      this.rpm += (target - this.rpm) * (1 - Math.exp(-dt / (target > this.rpm ? 0.09 : 0.14)));
      const pressing = (j.boost || throttle > 0) && t >= this.shiftUntil;
      const wanted = pressing ? Math.max(throttle, j.boost ? 1 : 0) : 0;
      this.load += (wanted - this.load) * (1 - Math.exp(-dt / 0.06));
      mixLayers(set.on, this.rpm, t);
      mixLayers(set.off, this.rpm, t);
      this.onBus.gain.setTargetAtTime(Math.sin(this.load * Math.PI / 2), t, 0.03);
      this.offBus.gain.setTargetAtTime(Math.cos(this.load * Math.PI / 2), t, 0.03);
      this.engineGain.gain.setTargetAtTime(0.85, t, 0.1);
      const x = this.rpm / spec.redline;
      this.turboFilter.frequency.setTargetAtTime(1400 + this.rpm * 0.45, t, 0.05);
      this.turboGain.gain.setTargetAtTime((spec.turbo || 0) * this.load * x * x * 0.12, t, 0.08);
      this.whine.frequency.setTargetAtTime(this.rpm * 0.42, t, 0.04);
      this.whineGain.gain.setTargetAtTime((spec.supercharger || 0) * (0.004 + this.load * 0.02) * x, t, 0.06);
      this.motorGain.gain.setTargetAtTime(0, t, 0.08);
    } else {
      this.motor.frequency.setTargetAtTime(70 + speed * 14, t, 0.05);
      this.motorGain.gain.setTargetAtTime(rolling ? 0.06 + Math.abs(throttle) * 0.08 + Math.min(speed, 90) * 0.0008 : 0.012, t, 0.08);
      this.engineGain.gain.setTargetAtTime(0, t, 0.08);
    }

    // Boost and the hover jets are the same rocket: an ignition burst, then the sustained thrust.
    const jetting = j.boost || j.lift;
    if (this.shared) {
      this.rocketGain.gain.setTargetAtTime(jetting ? (j.boost && j.lift ? 0.8 : 0.65) : 0, t, jetting ? 0.03 : 0.12);
      if (jetting && !this.jetting && !this.muted) {
        const s = this.ctx.createBufferSource();
        s.buffer = this.shared.ignite;
        const g = this.ctx.createGain();
        g.gain.value = 0.7;
        s.connect(g).connect(this.out);
        s.start(t);
      }
    }
    this.jetting = jetting;
    const level = (this.shared ? 0 : (j.lift ? 0.35 : 0) + (j.boost ? 0.3 : 0)) + (j.spin ? 0.08 : 0);
    this.jetFilter.frequency.setTargetAtTime(j.boost ? 520 : 340, t, 0.05);
    this.jetGain.gain.setTargetAtTime(level, t, 0.04);
  }

  hit(strength = 1, cutoff = 300) {
    if (!this.ctx || this.muted) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const src = ctx.createBufferSource();
    src.buffer = this.noise;
    const f = ctx.createBiquadFilter();
    f.type = 'lowpass';
    f.frequency.value = cutoff;
    const g = ctx.createGain();
    g.gain.setValueAtTime(0.9 * strength, t);
    g.gain.exponentialRampToValueAtTime(0.001, t + 0.5);
    src.connect(f).connect(g).connect(this.out);
    src.start(t, Math.random());
    src.stop(t + 0.6);
  }

  chime(good) {
    if (!this.ctx || this.muted) return;
    const ctx = this.ctx, t = ctx.currentTime;
    const notes = good ? [660, 880, 1320] : [520, 390];
    notes.forEach((freq, i) => {
      const o = ctx.createOscillator();
      o.type = 'triangle';
      o.frequency.value = freq;
      const g = ctx.createGain();
      g.gain.setValueAtTime(0, t + i * 0.11);
      g.gain.linearRampToValueAtTime(0.18, t + i * 0.11 + 0.02);
      g.gain.exponentialRampToValueAtTime(0.001, t + i * 0.11 + 0.5);
      o.connect(g).connect(this.out);
      o.start(t + i * 0.11);
      o.stop(t + i * 0.11 + 0.6);
    });
  }
}

// Plays the two recordings either side of rpm, each pitched to rpm, crossfaded by where rpm sits
// between them on a log scale (pitch is heard logarithmically). layers are sorted by rpm.
function mixLayers(layers, rpm, t) {
  let i = 0;
  while (i < layers.length - 2 && rpm >= layers[i + 1].rpm) i++;
  const a = layers[i], b = layers[i + 1] || a;
  const x = b === a ? 0 : clamp(Math.log(rpm / a.rpm) / Math.log(b.rpm / a.rpm), 0, 1);
  layers.forEach((l, k) => {
    const w = k === i ? Math.cos(x * Math.PI / 2) : k === i + 1 ? Math.sin(x * Math.PI / 2) : 0;
    l.gain.gain.setTargetAtTime(w, t, 0.03);
    l.src.playbackRate.setTargetAtTime(clamp(rpm / l.rpm, 0.5, 2), t, 0.03);
  });
}
