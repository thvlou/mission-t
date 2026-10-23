// Generates each Vertigo car's engine and boost loops with ElevenLabs sound effects.
// Every car gets a different petrol supercar voice; the game pitches the engine loop with speed
// and layers the boost loop while E is held (src/audio.js).
//
//   npm run audio            (only cars whose files are missing)
//   npm run audio -- --force vertigo-r vertigo-apex
//
// The key lives in .env.local (from `npx @elevenlabs/cli onboard init`); the SDK reads
// ELEVENLABS_API_KEY from the environment.
import { ElevenLabsClient } from '@elevenlabs/elevenlabs-js';
import { mkdir, writeFile, access } from 'node:fs/promises';
import { Readable } from 'node:stream';

const OUT = new URL('../assets/audio/', import.meta.url);

const ENGINE = 'Close-miked exhaust recording, constant steady RPM held around 4000 rpm, continuous, no gear shifts, no revving up or down, no tyre noise, no music.';
const BOOST = 'Sustained flat-out full throttle at high RPM, continuous, no gear shifts, no tyre noise, no music.';

const CARS = {
  'vertigo-gt': {
    engine: `Mid-engine twin-turbocharged 4.0 litre V8 supercar cruising: smooth deep baritone growl with a soft turbo hiss. ${ENGINE}`,
    boost: `Twin-turbo V8 supercar at full boost: turbo spool whistle, wastegate flutter and a hard aggressive roar with exhaust crackles. ${BOOST}`,
  },
  'vertigo-arc': {
    engine: `Naturally aspirated flat-six sports car: metallic raspy boxer howl, mechanical and buzzy, clear intake induction noise. ${ENGINE}`,
    boost: `Naturally aspirated flat-six screaming near a 9000 rpm redline: piercing metallic howl with intake wail. ${BOOST}`,
  },
  'vertigo-apex': {
    engine: `Front-engine naturally aspirated V12 supercar: silky smooth high-pitched operatic tone, refined and rich. ${ENGINE}`,
    boost: `Naturally aspirated V12 supercar shrieking at high RPM: soaring operatic F1-like scream, very loud and pure. ${BOOST}`,
  },
  'vertigo-grand': {
    engine: `Quad-turbocharged W16 hypercar: massive deep bassy rumble, heavy and muffled, with a constant turbo whoosh. ${ENGINE}`,
    boost: `Quad-turbo W16 hypercar at full boost: thunderous deep roar with huge turbo whoosh and jet-like air intake rush. ${BOOST}`,
  },
  'vertigo-terra': {
    engine: `Supercharged 6.2 litre American V8 muscle supercar: lumpy loud cross-plane burble with a high supercharger whine on top. ${ENGINE}`,
    boost: `Supercharged American V8 at wide open throttle: screaming supercharger whine over a brutal thundering V8 roar. ${BOOST}`,
  },
  'vertigo-r': {
    engine: `Naturally aspirated V10 track supercar: sharp angular high-pitched wail, hard-edged and racy. ${ENGINE}`,
    boost: `Naturally aspirated V10 race car shrieking at redline: razor-sharp high-pitched scream with pops and bangs from the exhaust. ${BOOST}`,
  },
};

const args = process.argv.slice(2);
const force = args.includes('--force');
const only = args.filter(a => !a.startsWith('--'));
for (const id of only) if (!CARS[id]) throw new Error(`Unknown car "${id}". Known: ${Object.keys(CARS).join(', ')}`);

const client = new ElevenLabsClient();
await mkdir(OUT, { recursive: true });

const exists = (url) => access(url).then(() => true, () => false);

// The engine plays as one source behind the car, so stereo only doubles the download.
// Folds 16-bit PCM WAV to mono; anything else is passed through untouched.
function toMono(wav) {
  if (wav.toString('ascii', 0, 4) !== 'RIFF' || wav.readUInt16LE(20) !== 1 || wav.readUInt16LE(22) !== 2 || wav.readUInt16LE(34) !== 16) return wav;
  let o = 12, data = null;
  while (o + 8 <= wav.length) {
    const size = wav.readUInt32LE(o + 4);
    if (wav.toString('ascii', o, o + 4) === 'data') { data = wav.subarray(o + 8, o + 8 + size); break; }
    o += 8 + size + (size & 1);
  }
  if (!data) return wav;
  const frames = data.length >> 2, rate = wav.readUInt32LE(24);
  const out = Buffer.alloc(44 + frames * 2);
  out.write('RIFF', 0); out.writeUInt32LE(36 + frames * 2, 4); out.write('WAVE', 8);
  out.write('fmt ', 12); out.writeUInt32LE(16, 16); out.writeUInt16LE(1, 20); out.writeUInt16LE(1, 22);
  out.writeUInt32LE(rate, 24); out.writeUInt32LE(rate * 2, 28); out.writeUInt16LE(2, 32); out.writeUInt16LE(16, 34);
  out.write('data', 36); out.writeUInt32LE(frames * 2, 40);
  for (let i = 0; i < frames; i++) out.writeInt16LE((data.readInt16LE(i * 4) + data.readInt16LE(i * 4 + 2)) >> 1, 44 + i * 2);
  return out;
}

for (const [id, prompts] of Object.entries(CARS)) {
  if (only.length && !only.includes(id)) continue;
  for (const [kind, text] of Object.entries(prompts)) {
    const file = new URL(`${id}-${kind}.wav`, OUT);
    if (!force && await exists(file)) { console.log(`skip  ${id}-${kind}.wav (exists)`); continue; }
    // WAV, not MP3: MP3 encoder padding leaves a click at every loop point.
    const audio = await client.textToSoundEffects.convert({
      text,
      modelId: 'eleven_text_to_sound_v2',
      loop: true,
      durationSeconds: kind === 'engine' ? 6 : 4,
      promptInfluence: 0.6,
      outputFormat: 'wav_44100',
    });
    const chunks = [];
    for await (const chunk of Readable.from(audio)) chunks.push(chunk);
    const buf = toMono(Buffer.concat(chunks));
    await writeFile(file, buf);
    console.log(`wrote ${id}-${kind}.wav (${(buf.length / 1024).toFixed(0)} KB)`);
  }
}
