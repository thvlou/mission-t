// Turns engine-sim takes (tools/engine-sim/record_all.py) into the game's engine loops:
// assets/audio/engines/<car>/{idle,on-<rpm>,off-<rpm>}.wav plus assets/audio/engines.json.
//
//   node tools/build-engine-audio.mjs <takes dir>
//
// Each take is 4 s of a dyno-held RPM. The first second (settling) is skipped, the loop length is a
// whole number of engine cycles so the seam lands in step, and the seam gets a short crossfade.
// engine-sim levels its own output as it runs (the LVL gauge), so recorded loudness means nothing:
// every loop is levelled on its own, full throttle loudest, closed throttle and idle a step below.
import { readFileSync, writeFileSync, mkdirSync, readdirSync } from 'node:fs';
import { join } from 'node:path';

const takes = process.argv[2];
if (!takes) throw new Error('usage: node tools/build-engine-audio.mjs <takes dir>');
const OUT = new URL('../assets/audio/', import.meta.url);

// Redline, and the forced induction the recordings lack (the game adds it as a synthesised layer).
const CARS = {
  'vertigo-gt': { redline: 9000, turbo: 0.6 },
  'vertigo-arc': { redline: 9000 },
  'vertigo-apex': { redline: 8500 },
  'vertigo-grand': { redline: 7000, turbo: 1 },
  'vertigo-terra': { redline: 6500, supercharger: 1 },
  'vertigo-r': { redline: 9000 },
};
const IDLE = 1000;   // the idle take is the dyno holding 1000 rpm on a crack of throttle
const SKIP = 1.0, LENGTH = 2.4, FADE = 0.08;
const LEVEL = { on: 0.24, off: 0.16, idle: 0.17 };

function readWav(path) {
  const b = readFileSync(path);
  let o = 12, fmt = null, data = null;
  while (o + 8 <= b.length) {
    const id = b.toString('ascii', o, o + 4), size = b.readUInt32LE(o + 4);
    if (id === 'fmt ') fmt = { channels: b.readUInt16LE(o + 10), rate: b.readUInt32LE(o + 12) };
    if (id === 'data') data = b.subarray(o + 8, o + 8 + size);
    o += 8 + size + (size & 1);
  }
  const n = data.length / 2 / fmt.channels, x = new Float32Array(n);
  for (let i = 0; i < n; i++) x[i] = data.readInt16LE(i * 2 * fmt.channels) / 32768;
  return { rate: fmt.rate, x };
}

function writeWav(path, x, rate) {
  const b = Buffer.alloc(44 + x.length * 2);
  b.write('RIFF', 0); b.writeUInt32LE(36 + x.length * 2, 4); b.write('WAVEfmt ', 8);
  b.writeUInt32LE(16, 16); b.writeUInt16LE(1, 20); b.writeUInt16LE(1, 22); b.writeUInt32LE(rate, 24);
  b.writeUInt32LE(rate * 2, 28); b.writeUInt16LE(2, 32); b.writeUInt16LE(16, 34); b.write('data', 36); b.writeUInt32LE(x.length * 2, 40);
  for (let i = 0; i < x.length; i++) b.writeInt16LE(Math.round(Math.max(-1, Math.min(1, x[i])) * 32767), 44 + i * 2);
  writeFileSync(path, b);
}

const rms = (x) => Math.sqrt(x.reduce((a, v) => a + v * v, 0) / x.length);

// A loop of whole engine cycles (two crank turns) with the tail crossfaded into the head.
function makeLoop(x, rate, rpm) {
  const cycle = 120 / rpm * rate;
  const len = Math.round(Math.round(LENGTH * rate / cycle) * cycle);
  const fade = Math.round(FADE * rate), start = Math.round(SKIP * rate);
  const src = x.subarray(start, start + len + fade);
  if (src.length < len + fade) throw new Error('take too short');
  const out = new Float32Array(len);
  out.set(src.subarray(0, len));
  for (let i = 0; i < fade; i++) {
    const t = i / fade;
    out[i] = src[i] * Math.sin(t * Math.PI / 2) + src[len + i] * Math.cos(t * Math.PI / 2);
  }
  return out;
}

const manifest = {};
const files = readdirSync(takes);
for (const [car, info] of Object.entries(CARS)) {
  const mine = files.filter((f) => f.startsWith(car + '_') && f.endsWith('.wav'));
  if (!mine.length) { console.log(`skip  ${car} (no takes)`); continue; }
  const idle = IDLE;
  const loops = [{ name: 'idle', rpm: idle, ...readWav(join(takes, `${car}_idle.wav`)) }];
  const on = [], off = [];
  for (const f of mine) {
    const m = f.match(/_(on|off)_(\d+)\.wav$/);
    if (!m) continue;
    const rpm = Number(m[2]);
    (m[1] === 'on' ? on : off).push(rpm);
    loops.push({ name: `${m[1]}-${rpm}`, rpm, ...readWav(join(takes, f)) });
  }
  const made = loops.map((l) => ({ ...l, loop: makeLoop(l.x, l.rate, l.rpm) }));
  const dir = new URL(`engines/${car}/`, OUT);
  mkdirSync(dir, { recursive: true });
  for (const l of made) {
    const gain = LEVEL[l.name.split('-')[0]] / Math.max(1e-4, rms(l.loop));
    for (let i = 0; i < l.loop.length; i++) l.loop[i] *= gain;
    writeWav(new URL(`${l.name}.wav`, dir), l.loop, l.rate);
  }
  manifest[car] = {
    idle, redline: info.redline,
    on: on.sort((a, b) => a - b), off: off.sort((a, b) => a - b),
    ...(info.turbo && { turbo: info.turbo }), ...(info.supercharger && { supercharger: info.supercharger }),
  };
  console.log(`wrote ${car}: ${made.length} loops (on ${on.join('/')}, off ${off.join('/')})`);
}
writeFileSync(new URL('engines.json', OUT), JSON.stringify(manifest, null, 2) + '\n');
