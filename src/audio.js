// All sound is synthesised with WebAudio; there are no audio files.
const VOLUME = 0.8;

export class Sound {
  constructor() {
    this.ctx = null;
    this.muted = false;
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
    this.out.connect(ctx.destination);

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
    this.motor.frequency.setTargetAtTime(70 + speed * 14, t, 0.05);
    this.motorGain.gain.setTargetAtTime(rolling ? 0.06 + Math.abs(throttle) * 0.08 + Math.min(speed, 90) * 0.0008 : 0.012, t, 0.08);
    const j = sim.jets;
    const level = (j.lift ? 0.35 : 0) + (j.boost ? 0.3 : 0) + (j.spin ? 0.08 : 0);
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
