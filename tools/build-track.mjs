// Builds a race course for Mission T from free public data:
//   shape + widths  TUMFTM racetrack-database (LGPL-3.0)   5 m centreline, left/right widths
//   geo position    bacinger/f1-circuits (MIT)             GeoJSON line in lat/lon
//   heights         OpenTopoData public API, EU-DEM 25 m   (100 points per call, 1 call/s)
// The TUMFTM line is in a local metric frame, so it is fitted onto the GeoJSON line (rotation +
// shift, mirror allowed) to learn where each point is on Earth, then heights are looked up there.
//
// usage: node tools/build-track.mjs <tumftm name> <geojson id> <out id> "<display name>" [dataset]
//   e.g. node tools/build-track.mjs Spa be-1925 ridgeline "Ridgeline" eudem25m
import { writeFile, mkdir } from 'node:fs/promises';

const [tum = 'Spa', geoId = 'be-1925', outId = 'ridgeline', title = 'Ridgeline', dataset = 'eudem25m'] = process.argv.slice(2);
const TUM = `https://raw.githubusercontent.com/TUMFTM/racetrack-database/master/tracks/${tum}.csv`;
const GEO = `https://raw.githubusercontent.com/bacinger/f1-circuits/master/circuits/${geoId}.geojson`;
const ELEV = `https://api.opentopodata.org/v1/${dataset}`;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

const csv = (await (await fetch(TUM)).text()).trim().split('\n').filter((l) => !l.startsWith('#')).map((l) => l.split(',').map(Number));
const geo = await (await fetch(GEO)).json();
const ll = geo.features[0].geometry.coordinates; // [lon, lat]
const props = geo.features[0].properties;

// GeoJSON → local metres (east, north) around its centroid.
const lat0 = ll.reduce((a, p) => a + p[1], 0) / ll.length, lon0 = ll.reduce((a, p) => a + p[0], 0) / ll.length;
const KX = 111320 * Math.cos((lat0 * Math.PI) / 180), KY = 110540;
const gl = ll.map(([lon, lat]) => [(lon - lon0) * KX, (lat - lat0) * KY]);

// Distance from a point to the GeoJSON polyline.
function distToLine(x, y) {
  let best = Infinity;
  for (let i = 1; i < gl.length; i++) {
    const [ax, ay] = gl[i - 1], [bx, by] = gl[i];
    const ex = bx - ax, ey = by - ay;
    const t = Math.max(0, Math.min(1, ((x - ax) * ex + (y - ay) * ey) / (ex * ex + ey * ey || 1)));
    best = Math.min(best, Math.hypot(x - ax - ex * t, y - ay - ey * t));
  }
  return best;
}

// Fit the TUMFTM line onto the GeoJSON one: try every rotation (and a mirror), centroids matched,
// then refine rotation and shift by small steps.
const pts = csv.map((r) => [r[0], r[1]]);
const cx = pts.reduce((a, p) => a + p[0], 0) / pts.length, cy = pts.reduce((a, p) => a + p[1], 0) / pts.length;
const sample = pts.filter((_, i) => i % 10 === 0);
const place = (p, a, m, tx, ty) => {
  const x = (p[0] - cx) * m, y = p[1] - cy;
  return [x * Math.cos(a) - y * Math.sin(a) + tx, x * Math.sin(a) + y * Math.cos(a) + ty];
};
const score = (a, m, tx, ty) => sample.reduce((s, p) => s + distToLine(...place(p, a, m, tx, ty)), 0) / sample.length;
let fit = { err: Infinity };
for (const m of [1, -1]) for (let deg = 0; deg < 360; deg += 2) {
  const a = (deg * Math.PI) / 180, err = score(a, m, 0, 0);
  if (err < fit.err) fit = { err, a, m, tx: 0, ty: 0 };
}
for (let step = 8; step > 0.05; step /= 2) {
  let moved = true;
  while (moved) {
    moved = false;
    for (const [da, dx, dy] of [[step / 200, 0, 0], [-step / 200, 0, 0], [0, step, 0], [0, -step, 0], [0, 0, step], [0, 0, -step]]) {
      const err = score(fit.a + da, fit.m, fit.tx + dx, fit.ty + dy);
      if (err < fit.err - 1e-6) { fit = { ...fit, err, a: fit.a + da, tx: fit.tx + dx, ty: fit.ty + dy }; moved = true; }
    }
  }
}
console.log(`fit: mean offset ${fit.err.toFixed(1)} m, rotation ${((fit.a * 180) / Math.PI).toFixed(1)}°, mirror ${fit.m < 0}`);

// Heights: every 4th point (20 m) looked up, then interpolated and smoothed (DEM noise, trees).
const world = pts.map((p) => place(p, fit.a, fit.m, fit.tx, fit.ty)); // east, north (m)
const toLatLon = ([e, n]) => [lat0 + n / KY, lon0 + e / KX];
const idx = world.map((_, i) => i).filter((i) => i % 4 === 0);
const raw = new Map();
for (let k = 0; k < idx.length; k += 100) {
  const chunk = idx.slice(k, k + 100);
  const locs = chunk.map((i) => toLatLon(world[i]).map((v) => v.toFixed(6)).join(',')).join('|');
  for (let attempt = 0; ; attempt++) {
    const res = await fetch(`${ELEV}?locations=${locs}`);
    if (res.ok) {
      const body = await res.json();
      body.results.forEach((r, j) => raw.set(chunk[j], r.elevation));
      break;
    }
    if (attempt > 4) throw new Error(`elevation lookup failed: ${res.status}`);
    await sleep(2000);
  }
  process.stdout.write(`heights ${Math.min(idx.length, k + 100)}/${idx.length}\r`);
  await sleep(1100);
}
console.log('');
const n = pts.length;
let h = pts.map((_, i) => {
  const a = Math.floor(i / 4) * 4, b = (a + 4) % n;
  const ha = raw.get(a), hb = raw.get(b) ?? raw.get(0);
  return ha + (hb - ha) * ((i - a) / 4);
});
// Closed loop: smooth over ±40 m, twice.
for (let pass = 0; pass < 2; pass++) {
  h = h.map((_, i) => {
    let s = 0;
    for (let k = -8; k <= 8; k++) s += h[(i + k + n) % n];
    return s / 17;
  });
}
const base = Math.min(...h);

// Course frame used by the game: x east, z south (three.js: -z is north), y up; start at index 0.
const ox = world[0][0], oz = -world[0][1];
const out = {
  id: outId,
  name: title,
  closed: true,
  step: 5,
  // [x, y, z, widthRight, widthLeft] per point, metres; widths measured looking along the course
  points: world.map(([e, nn], i) => [+(e - ox).toFixed(2), +(h[i] - base).toFixed(2), +(-nn - oz).toFixed(2), csv[i][2], csv[i][3]]),
  length: Math.round(pts.reduce((L, p, i) => L + (i ? Math.hypot(p[0] - pts[i - 1][0], p[1] - pts[i - 1][1]) : 0), 0) + Math.hypot(pts[0][0] - pts[n - 1][0], pts[0][1] - pts[n - 1][1])),
  climb: +(Math.max(...h) - base).toFixed(1),
  origin: { lat: +toLatLon(world[0])[0].toFixed(6), lon: +toLatLon(world[0])[1].toFixed(6) },
  sources: {
    shape: `TUMFTM racetrack-database (${tum}.csv), LGPL-3.0`,
    geo: `bacinger/f1-circuits (${geoId}), MIT`,
    heights: `OpenTopoData ${dataset}`,
    reference: `${props.Name}, ${props.length} m`,
  },
};
await mkdir('assets/tracks', { recursive: true });
await writeFile(`assets/tracks/${outId}.json`, JSON.stringify(out));
const grades = out.points.map((p, i) => {
  const q = out.points[(i + 4) % n];
  return ((q[1] - p[1]) / Math.hypot(q[0] - p[0], q[2] - p[2])) * 100;
});
console.log(`wrote assets/tracks/${outId}.json: ${out.length} m, ${n} points, climb ${out.climb} m, grade ${Math.min(...grades).toFixed(1)}%..${Math.max(...grades).toFixed(1)}%`);
