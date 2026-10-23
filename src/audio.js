// Each car's engine and boost are recorded loops (assets/audio/<id>-engine.wav / -boost.wav, made by
// tools/generate-car-audio.mjs); jets, tyres, hits and chimes are synthesised with WebAudio. Until a
// car's loops arrive (or if they fail to load) the synthesised motor stands in.
const VOLUME = 0.8;
const LOOP_FADE = 0.06;   // seconds blended across each loop point
const LOOP_RMS = 0.22;    // every loop is levelled to this before mixing
// Speed (m/s) at which each gear tops out; the engine loop is pitched by revs within the gear.
const GEARS = [14, 27, 41, 56, 72, 92];
const RATE_IDLE = 0.62, RATE_RED = 1.42;

export class Sound {
  constructor() {
    this.ctx = null;
    this.muted = false;
    this.vehicle = null;
    this.loops = null;   // { id, engine, boost } once the current car's loops are playing
    this.loadToken = 0;
    this.revs = 0;
  }

  // Swaps in a car's engine and boost loops; safe to call before audio has started.
  setVehicle(id) {
    if (id === this.vehicle) return;
    this.vehicle = id;
    if (this.ctx) this.loadLoops();
  }

  async loadLoops() {
    const id = this.vehicle, token = ++this.loadToken, ctx = this.ctx;
    if (!id) return;
    try {
      const [engine, boost] = await Promise.all(['engine', 'boost'].map(async (kind) => {
        const res = await fetch(`assets/audio/${id}-${kind}.wav`);
        if (!res.ok) throw new Error(`${res.status} for ${id}-${kind}.wav`);
        return prepareLoop(ctx, await ctx.decodeAudioData(await res.arrayBuffer()));
      }));
      if (token !== this.loadToken) return;
      const t = ctx.currentTime;
      if (this.loops) {
        for (const s of [this.loops.engine, this.loops.boost]) { try { s.stop(t + 0.15); } catch { /* already stopped */ } }
      }
      const play = (buffer, gain) => {
        const s = ctx.createBufferSource();
        s.buffer = buffer;
        s.loop = true;
        s.connect(gain);
        s.start(t, Math.random() * buffer.duration);
        return s;
      };
      this.loops = { id, engine: play(engine, this.engineGain), boost: play(boost, this.boostGain) };
    } catch (err) {
      if (token === this.loadToken) console.warn('Engine sound failed to load; using the synthesised motor.', err);
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
    // Engine, boost and jets can all peak together; a gentle limiter keeps that from clipping.
    const limiter = ctx.createDynamicsCompressor();
    limiter.threshold.value = -10;
    limiter.knee.value = 8;
    limiter.ratio.value = 6;
    this.out.connect(limiter).connect(ctx.destination);

    this.engineGain = ctx.createGain();
    this.engineGain.gain.value = 0;
    this.engineGain.connect(this.out);
    this.boostGain = ctx.createGain();
    this.boostGain.gain.value = 0;
    this.boostGain.connect(this.out);
    this.loadLoops();

    const len = ctx.sampleRate * 2;
    this.noise = ctx.createBuffer(1, len, ctx.sampleRate);
    const data = this.noise.getChannelData(0);
    for (let i = 0; i < len; i++) data[i] = Math.random() * 2 - 1;

    // Electric motor whine
    this.motor = ctx.createOscillator();
    this.motor.type = 'sawtooth';
    const motorFilter = ctx.createBiquadFilter();
    motorFilter.type = 'lowpass';
    motorFilter.frequency.value = 900;
    this.motorGain = ctx.createGain();
    this.motorGain.gain.value = 0;
    this.motor.connect(motorFilter).connect(this.motorGain).connect(this.out);
    this.motor.start();

    // Jet roar
    const jet = ctx.createBufferSource();
    jet.buffer = this.noise;
    jet.loop = true;
    this.jetFilter = ctx.createBiquadFilter();
    this.jetFilter.type = 'bandpass';
    this.jetFilter.Q.value = 0.8;
    this.jetGain = ctx.createGain();
    this.jetGain.gain.value = 0;
    jet.connect(this.jetFilter).connect(this.jetGain).connect(this.out);
    jet.start();

    // Tyre squeal: narrow-band noise around 1–2 kHz plus a faint wavering tone.
    const squeal = ctx.createBufferSource();
    squeal.buffer = this.noise;
    squeal.loop = true;
    this.squealFilter = ctx.createBiquadFilter();
    this.squealFilter.type = 'bandpass';
    this.squealFilter.frequency.value = 1400;
    this.squealFilter.Q.value = 9;
    this.squealTone = ctx.createOscillator();
    this.squealTone.type = 'triangle';
    this.squealTone.frequency.value = 1100;
    const toneGain = ctx.createGain();
    toneGain.gain.value = 0.05;
    this.squealGain = ctx.createGain();
    this.squealGain.gain.value = 0;
    squeal.connect(this.squealFilter).connect(this.squealGain);
    this.squealTone.connect(toneGain).connect(this.squealGain);
    this.squealGain.connect(this.out);
    squeal.start();
    this.squealTone.start();
  }

  // level 0..1 from how hard the tyres slide; speed in m/s bends the pitch.
  skid(level, speed = 0) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    const wobble = Math.sin(t * 23) * 60 + Math.sin(t * 7.3) * 40;
    this.squealFilter.frequency.setTargetAtTime(1100 + Math.min(speed, 60) * 9 + wobble, t, 0.03);
    this.squealTone.frequency.setTargetAtTime(900 + Math.min(speed, 60) * 6 + wobble, t, 0.03);
    this.squealGain.gain.setTargetAtTime(level > 0.02 ? 0.12 + level * 0.32 : 0, t, level > 0.02 ? 0.04 : 0.09);
  }

  toggle() {
    this.muted = !this.muted;
    if (this.ctx) this.out.gain.value = this.muted ? 0 : VOLUME;
    if (!this.muted) this.start();
    return this.muted;
  }

  update(sim, throttle) {
    if (!this.ctx) return;
    const t = this.ctx.currentTime;
    const speed = Math.hypot(sim.vx, sim.vy);
    const rolling = sim.state === 'track' || sim.state === 'landed';
    const j = sim.jets;
    const loops = this.loops?.id === this.vehicle ? this.loops : null;
    if (loops) {
      // Revs climb through each gear and drop at the shift; a pressed throttle adds a little load.
      const g = GEARS.findIndex(top => speed < top);
      const lo = g > 0 ? GEARS[g - 1] : 0, hi = g >= 0 ? GEARS[g] : GEARS[GEARS.length - 1];
      const inGear = g < 0 ? 1 : (speed - lo) / (hi - lo);
      const target = g === 0 ? inGear * 0.85 : 0.3 + inGear * 0.7;
      this.revs += (Math.min(1, target + Math.max(0, throttle) * 0.08) - this.revs) * 0.25;
      const rate = RATE_IDLE + (RATE_RED - RATE_IDLE) * this.revs;
      loops.engine.playbackRate.setTargetAtTime(rate, t, 0.06);
      this.engineGain.gain.setTargetAtTime(rolling ? 0.32 + Math.abs(throttle) * 0.4 + this.revs * 0.15 : 0.25, t, 0.08);
      loops.boost.playbackRate.setTargetAtTime(0.9 + this.revs * 0.25, t, 0.08);
      this.boostGain.gain.setTargetAtTime(j.boost ? 0.85 : 0, t, j.boost ? 0.03 : 0.12);
      this.motorGain.gain.setTargetAtTime(0, t, 0.08);
    } else {
      this.motor.frequency.setTargetAtTime(70 + speed * 14, t, 0.05);
      this.motorGain.gain.setTargetAtTime(rolling ? 0.06 + Math.abs(throttle) * 0.08 + Math.min(speed, 90) * 0.0008 : 0.012, t, 0.08);
      this.engineGain.gain.setTargetAtTime(0, t, 0.08);
      this.boostGain.gain.setTargetAtTime(0, t, 0.08);
    }
    // With a recorded boost the jet only adds a little air rush under it.
    const level = (j.lift ? 0.35 : 0) + (j.boost ? (loops ? 0.08 : 0.3) : 0) + (j.spin ? 0.08 : 0);
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

// Folds the tail of a loop into its head so the wrap point is seamless, and levels it to LOOP_RMS.
function prepareLoop(ctx, buf) {
  const fade = Math.min(Math.floor(LOOP_FADE * buf.sampleRate), buf.length >> 2);
  const len = buf.length - fade;
  const out = ctx.createBuffer(buf.numberOfChannels, len, buf.sampleRate);
  let sum = 0;
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const src = buf.getChannelData(c), dst = out.getChannelData(c);
    dst.set(src.subarray(0, len));
    for (let i = 0; i < fade; i++) {
      const x = i / fade;
      dst[i] = src[i] * Math.sin(x * Math.PI / 2) + src[len + i] * Math.cos(x * Math.PI / 2);
    }
    for (let i = 0; i < len; i++) sum += dst[i] * dst[i];
  }
  const gain = LOOP_RMS / Math.max(1e-4, Math.sqrt(sum / (len * buf.numberOfChannels)));
  for (let c = 0; c < buf.numberOfChannels; c++) {
    const dst = out.getChannelData(c);
    for (let i = 0; i < len; i++) dst[i] *= gain;
  }
  return out;
}
