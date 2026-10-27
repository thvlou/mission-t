// Generates the rocket used for boost and the hover jets (one sound for every car) with ElevenLabs
// sound effects: a seamless thrust loop and the ignition burst that starts it.
//
//   npm run audio:rocket                 (only files that are missing)
//   npm run audio:rocket -- --force      (regenerate both)
//   npm run audio:rocket -- --force --out <dir>   (write candidates somewhere else to compare)
//
// The key lives in .env.local (from `npx @elevenlabs/cli onboard init`); the SDK reads
// ELEVENLABS_API_KEY from the environment. Prompts avoid voice words (scream, shriek, wail, howl):
// the model renders those as a human voice.
import { ElevenLabsClient } from '@elevenlabs/elevenlabs-js';
import { mkdir, writeFile, access } from 'node:fs/promises';
import { Readable } from 'node:stream';
import { pathToFileURL } from 'node:url';

const SOUNDS = {
  'rocket-loop': {
    seconds: 5, loop: true,
    text: 'Video game rocket thruster firing continuously: powerful pressurized gas jet blasting out of a nozzle, deep rumbling roar under a dense hiss of high-pressure exhaust gas. Steady and even for the whole clip, sci-fi vehicle thruster sound effect, no music.',
  },
  'rocket-ignite': {
    seconds: 1.2, loop: false,
    text: 'Video game rocket thruster ignition: a sharp pressurized gas burst and whoosh as the nozzle lights, quickly settling into a roaring jet. Short sci-fi vehicle thruster sound effect, no music.',
  },
};

const args = process.argv.slice(2);
const force = args.includes('--force');
const outArg = args.indexOf('--out');
const OUT = outArg >= 0 ? pathToFileURL(args[outArg + 1].replace(/[\\/]?$/, '/')) : new URL('../assets/audio/', import.meta.url);

const client = new ElevenLabsClient();
await mkdir(OUT, { recursive: true });
const exists = (url) => access(url).then(() => true, () => false);

// One source, so stereo only doubles the download. Folds 16-bit PCM WAV to mono.
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

for (const [name, spec] of Object.entries(SOUNDS)) {
  const file = new URL(`${name}.wav`, OUT);
  if (!force && await exists(file)) { console.log(`skip  ${name}.wav (exists)`); continue; }
  // WAV, not MP3: MP3 encoder padding leaves a click at every loop point.
  const audio = await client.textToSoundEffects.convert({
    text: spec.text,
    modelId: 'eleven_text_to_sound_v2',
    loop: spec.loop,
    durationSeconds: spec.seconds,
    promptInfluence: 0.6,
    outputFormat: 'wav_44100',
  });
  const chunks = [];
  for await (const chunk of Readable.from(audio)) chunks.push(chunk);
  const buf = toMono(Buffer.concat(chunks));
  await writeFile(file, buf);
  console.log(`wrote ${name}.wav (${(buf.length / 1024).toFixed(0)} KB)`);
}
