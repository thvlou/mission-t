import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { DEFAULTS, SETTINGS, PRESETS, TRACK, CHALLENGES } from './config.js';
import { Track } from './track.js';
import { Sim, RIDE, wrap } from './sim.js';
import { buildRover } from './rover.js';
import { loadCarModel, linkedCarId } from './car-model.js';
import { buildWorld } from './world.js';
import { Particles, Forecast } from './fx.js';
import { Sound } from './audio.js';
import { getVehicle } from './vehicles.js';
import { createInput } from './input.js';
import { HighwayMode, HIGHWAY_VIEWS } from './highway/index.js';
import { Race, RACE_LENGTH } from './race/race.js';
import { RacePanel, loadProfile, saveProfile } from './race/panel.js';
import { Gauge } from './gauge.js';
import { CarsModal } from './cars-modal.js';

const $ = (id) => document.getElementById(id);

const store = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`vertigo:${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch {
      return fallback;
    }
  },
  set(key, value) {
    try {
      localStorage.setItem(`vertigo:${key}`, JSON.stringify(value));
    } catch { /* storage unavailable */ }
  },
};

// ---------- renderer & scene ----------
const renderer = new THREE.WebGLRenderer({ antialias: true });
renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
renderer.shadowMap.enabled = true;
renderer.shadowMap.type = THREE.PCFSoftShadowMap;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 0.95;
$('stage').appendChild(renderer.domElement);

const scene = new THREE.Scene();
scene.background = new THREE.Color('#f4f3f0');
scene.fog = new THREE.Fog('#f4f3f0', 90, 320);

// Soft studio reflections for the paint, glass and metal.
const pmrem = new THREE.PMREMGenerator(renderer);
scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
scene.add(new THREE.HemisphereLight('#ffffff', '#d9d6d0', 0.9));
const sun = new THREE.DirectionalLight('#ffffff', 2.2);
sun.castShadow = true;
sun.shadow.mapSize.set(4096, 4096);
sun.shadow.radius = 3;
sun.shadow.camera.left = -40;
sun.shadow.camera.right = 40;
sun.shadow.camera.top = 40;
sun.shadow.camera.bottom = -40;
sun.shadow.camera.far = 160;
sun.shadow.bias = -0.0005;
scene.add(sun, sun.target);
const rim = new THREE.DirectionalLight('#ffffff', 0.5);
rim.position.set(-30, 20, -40);
scene.add(rim);

const camera = new THREE.PerspectiveCamera(42, 1, 0.1, 600);
const controls = new OrbitControls(camera, renderer.domElement);
controls.enablePan = false;
controls.minDistance = 6;
controls.maxDistance = 120;
controls.maxPolarAngle = Math.PI * 0.495;

const rover = buildRover();
scene.add(rover.root);
const particles = new Particles();
scene.add(particles.points);
const forecast = new Forecast();
scene.add(forecast.group);
const sound = new Sound();
const highway = new HighwayMode(scene);
const race = new Race(highway, rover, {
  onLobby() { clearRun(); updateBest(); raceUi(true); },
  onCountdown() { clearRun(); raceUi(true); },
  onStatus() { raceUi(true); },
  onRooms() { panel.render(); },
  onFinish() { showRaceCard(); },
  onStandings(results, done) {
    // A race that closes without us finishing (time ran out) still ends our run.
    if (done && race.inRace && !race.myResult) race.myResult = { status: 'dnf' };
    if (done && race.inRace && !shownResult) showRaceCard();
    else if (shownResult?.race) renderRaceCard();
    raceUi(true);
  },
});
// Driver profile (nickname + car) is kept in this browser; a ?car= link wins for this visit.
race.profile = { nick: '', car: 'vertigo-gt', ...loadProfile() };
if (linkedCarId) race.profile.car = getVehicle(linkedCarId).id;
const gauge = new Gauge($('gauge'), $('dash'));
// Each car brings its own speedometer and boost / jump colours (theme in src/vehicles.js).
const hexRgb = (hex) => [0, 8, 16].map((b) => ((parseInt(hex.slice(1), 16) >> (16 - b)) & 255) / 255);
const jetColor = { boost: [0.82, 0.2, 0.22], lift: [0.7, 0.69, 0.67] };
const useCar = (id) => {
  const car = getVehicle(id);
  sound.setVehicle(car.id);
  rover.setTheme(car.theme);
  gauge.setTheme(car.theme);
  jetColor.boost = hexRgb(car.theme.flame);
  // Lift jets are mostly exhaust, tinted with the car's jump colour.
  jetColor.lift = hexRgb(car.theme.lift).map((c) => c * 0.7 + 0.69 * 0.3);
  $('carsName').textContent = car.name;
  return loadCarModel(rover, car.id).catch((err) => console.warn('Car model failed to load; using the built-in rover.', err));
};
useCar(race.profile.car);
const panel = new RacePanel($('race'), race, {
  onProfile(p) {
    race.setProfile(p);
    useCar(p.car);
  },
  onCopy(btn) {
    const url = new URL(location.origin + location.pathname);
    url.searchParams.set('room', race.room);
    navigator.clipboard?.writeText(url.href).then(() => {
      btn.textContent = 'Copied';
      setTimeout(() => { btn.textContent = 'Copy link'; }, 1400);
    }).catch(() => {});
  },
  fmtResult(res) {
    if (!res || res.status === 'racing') return null;
    return res.status === 'finished' ? fmtTime(res.time || 0) : STATUS[res.status];
  },
  fmtKm(id) {
    const s = id === race.id ? highway.car.s : race.others.get(id)?.pose?.s;
    return s === undefined ? null : `${Math.max(0, (s - race.startS) / 1000).toFixed(2)} km`;
  },
});
// The Cars viewer (top bar → Cars, or G). Picking a car saves it to the driver profile; the game
// pauses behind the viewer (an online race keeps running).
let pausedForCars = false;
const cars = new CarsModal({
  current: () => race.profile.car,
  onPick(id) {
    race.setProfile({ car: id });
    saveProfile({ nick: race.profile.nick, car: id });
    useCar(id);
    panel.render(true);
  },
  onOpen() {
    for (const k in input.held) input.held[k] = false;
    pausedForCars = !paused && !shownResult && !isRace();
    if (pausedForCars) setPaused(true);
    $('carsBtn').setAttribute('aria-expanded', 'true');
  },
  onClose() {
    if (pausedForCars && paused) setPaused(false);
    pausedForCars = false;
    $('carsBtn').setAttribute('aria-expanded', 'false');
  },
});
const MODES = ['ramp', 'jump', 'highway', 'race'];

// ---------- state ----------
const params = { ...DEFAULTS, ...store.get('params:v2', {}) };
// A shared room link (?room=CODE) always opens the race.
const linkRoom = new URLSearchParams(location.search).get('room');
let modeKey = linkRoom ? 'race' : store.get('mode', 'ramp');
if (!MODES.includes(modeKey)) modeKey = 'ramp';
const track = new Track(TRACK.pieces, TRACK.origin);
const world = buildWorld(track);
scene.add(world.group);
const sim = new Sim(track, CHALLENGES[modeKey] || CHALLENGES.ramp, params);
let challenge = CHALLENGES[modeKey] || CHALLENGES.ramp;
const isHighway = () => modeKey === 'highway' || modeKey === 'race';
const isRace = () => modeKey === 'race';
let attempts = 0;
let shownResult = null;
let started = false;
let paused = false;

const VIEWS = [
  { key: 'side', name: 'Side', offset: [0, 3, 34], orbit: true },
  { key: 'chase', name: 'Chase', orbit: false },
  { key: 'drone', name: 'Drone', offset: [-16, 24, 22], orbit: true },
  { key: 'ground', name: 'Ground', orbit: false },
];
let viewIndex = 0;
const camOffset = new THREE.Vector3();
const camTarget = new THREE.Vector3();

const views = () => (isHighway() ? HIGHWAY_VIEWS : VIEWS);
function nextView() {
  viewIndex = (viewIndex + 1) % views().length;
  resetView();
}
function resetView() {
  const v = views()[viewIndex % views().length];
  controls.enabled = !isHighway() && !!v.orbit;
  if (v.offset) camOffset.set(...v.offset);
  $('camBtn').innerHTML = `Camera <b>${v.name}</b>`;
}

// Telemetry labels differ per mode: stunt modes care about height and tilt, the highway about distance.
let gaugeMax = 240;
function setDash(hw) {
  const labels = isRace()
    ? [['To go', 'km'], ['G-force', 'g'], ['Place', ''], ['Boost', '%']]
    : hw
    ? [['Distance', 'km'], ['G-force', 'g'], ['Passed', ''], ['Boost', '%']]
    : [['Height', 'm'], ['G-force', 'g'], ['Tilt', '°'], ['Fuel', 'L']];
  ['A', 'B', 'C', 'D'].forEach((k, i) => {
    $(`k${k}`).textContent = labels[i][0];
    $(`u${k}`).textContent = labels[i][1];
  });
  gaugeMax = hw ? 320 : 240;
  gauge.setMax(gaugeMax);
  for (const key in shown) delete shown[key];
}

function loadLevel(key) {
  saveHighwayBest();
  if (modeKey === 'race' && key !== 'race') {
    race.exit();
    panel.closeDriver();
    const url = new URL(location.href);
    url.searchParams.delete('room');
    history.replaceState(null, '', url);
  }
  modeKey = key;
  store.set('mode', key);
  const hw = isHighway();
  document.body.classList.toggle('hw', hw);
  highway.setActive(hw);
  world.group.visible = !hw;
  forecast.group.visible = false;
  $('tuneBtn').hidden = hw;
  $('pauseBtn').hidden = isRace(); // an online race can't be paused
  $('race').hidden = !isRace();
  $('count').hidden = true;
  if (hw) { $('tune').hidden = true; $('tuneBtn').setAttribute('aria-expanded', 'false'); }
  if (!hw) {
    challenge = CHALLENGES[key];
    sim.setChallenge(challenge);
    world.setChallenge(key);
  }
  for (const b of document.querySelectorAll('[data-mode]')) b.setAttribute('aria-pressed', String(b.dataset.mode === key));
  setDash(hw);
  viewIndex = 0;
  resetView();
  resize();
  if (isRace()) {
    // Free drive with the room list; a shared ?room= link goes straight into that room.
    clearRun();
    const code = new URLSearchParams(location.search).get('room');
    race.browse();
    if (code) panel.ensureDriver(() => race.enter(code));
    else if (!race.profile.nick) panel.openDriver();
  } else {
    restart();
  }
  camTarget.set(sim.x, Math.max(2.5, sim.y), 0);
  updateBest();
}

function setPaused(on) {
  paused = on;
  $('pauseBtn').setAttribute('aria-pressed', String(on));
  $('pauseBtn').textContent = on ? 'Resume' : 'Pause';
  $('paused').hidden = !on;
}

function restart() {
  if (isRace()) {
    // Enter in a room: the host starts, everyone else toggles Ready. After a race it closes the
    // result card; after a failed join it goes back to the room list.
    if (race.phase === 'lobby') {
      if (race.isHost) race.start();
      else race.setReady(!race.me?.ready);
    } else if (race.phase === 'finished') {
      clearRun();
      race.backToRoom();
    } else if (['error', 'full', 'limit'].includes(race.phase)) {
      race.browse();
    }
    return;
  }
  if (isHighway()) {
    saveHighwayBest();
    highway.reset();
    runStartBest = store.get('best:highway', 0);
  } else {
    sim.reset();
  }
  clearRun();
}

function clearRun() {
  shownResult = null;
  started = false;
  $('card').hidden = true;
  particles.clear();
  setPaused(false);
}

function bestKey() {
  return `best:${modeKey}`;
}

function updateBest() {
  const best = store.get(bestKey(), 0);
  if (isRace()) $('best').textContent = best ? fmtTime(best) : '—';
  else if (isHighway()) $('best').textContent = best ? `${(best / 1000).toFixed(1)} km` : '—';
  else $('best').textContent = best ? best.toLocaleString('en-US') : '—';
  $('attempt').textContent = String(attempts).padStart(2, '0');
}

// ---------- UI ----------
const input = createInput((cmd) => {
  sound.start();
  if (panel.driverOpen) return; // typing a nickname
  if (cmd === 'restart') restart();
  else if (cmd === 'camera') nextView();
  else if (cmd === 'mode') loadLevel(MODES[(MODES.indexOf(modeKey) + 1) % MODES.length]);
  else if (cmd === 'pause') { if (!shownResult && !isRace()) setPaused(!paused); }
  else if (cmd === 'cars') cars.open();
  else if (cmd === 'any' && paused) setPaused(false);
});

for (const b of document.querySelectorAll('[data-mode]')) {
  b.addEventListener('click', () => { if (b.dataset.mode !== modeKey) loadLevel(b.dataset.mode); b.blur(); });
}
$('camBtn').addEventListener('click', (e) => { nextView(); e.currentTarget.blur(); });
$('carsBtn').addEventListener('click', (e) => { e.currentTarget.blur(); cars.open(); });
$('restartBtn').addEventListener('click', (e) => { restart(); e.currentTarget.blur(); });
$('againBtn').addEventListener('click', (e) => { restart(); e.currentTarget.blur(); });
// Any click, tap or key unlocks audio (browsers block it until the first gesture).
for (const type of ['pointerdown', 'keydown', 'touchend']) {
  window.addEventListener(type, () => { sound.start(); race.touch(); }, { capture: true });
}
document.addEventListener('visibilitychange', () => { if (!document.hidden) sound.start(); });
$('muteBtn').addEventListener('click', (e) => {
  const muted = sound.toggle();
  e.currentTarget.setAttribute('aria-pressed', String(muted));
  e.currentTarget.textContent = muted ? 'Sound Off' : 'Sound On';
  e.currentTarget.blur();
});
$('pauseBtn').addEventListener('click', (e) => { if (!shownResult) setPaused(!paused); e.currentTarget.blur(); });
$('tuneBtn').addEventListener('click', (e) => {
  const panel = $('tune');
  panel.hidden = !panel.hidden;
  e.currentTarget.setAttribute('aria-expanded', String(!panel.hidden));
  e.currentTarget.blur();
});
renderer.domElement.addEventListener('dblclick', resetView);

function buildTuning() {
  const rows = $('tuneRows');
  rows.innerHTML = '';
  for (const s of SETTINGS) {
    const row = document.createElement('label');
    row.className = 'row';
    row.innerHTML = `<span>${s.label}</span><output></output><input type="range" min="${s.min}" max="${s.max}" step="${s.step}">`;
    const out = row.querySelector('output');
    const range = row.querySelector('input');
    const show = () => { out.textContent = `${Number(params[s.key]).toFixed(s.step < 0.1 ? 2 : s.step < 1 ? 1 : 0)} ${s.unit}`; };
    range.value = params[s.key];
    show();
    range.addEventListener('input', () => {
      params[s.key] = Number(range.value);
      show();
      store.set('params:v2', params);
    });
    range.addEventListener('change', () => range.blur());
    rows.appendChild(row);
  }
}
function applyPreset(values) {
  Object.assign(params, DEFAULTS, values);
  store.set('params:v2', params);
  buildTuning();
  restart();
}
$('tuneReset').addEventListener('click', () => applyPreset({}));
for (const [name, values] of Object.entries(PRESETS)) {
  const b = document.createElement('button');
  b.className = 'preset';
  b.textContent = name;
  b.addEventListener('click', () => { applyPreset(values); b.blur(); });
  $('presets').appendChild(b);
}
buildTuning();

// ---------- per-frame helpers ----------
let lastHint = '';
function setHint(html, sub = '') {
  if (html !== lastHint) {
    $('hint').innerHTML = html;
    $('hint').style.opacity = html ? 1 : 0;
    lastHint = html;
  }
  $('sub').textContent = sub;
}

function hints() {
  const touch = matchMedia('(pointer: coarse)').matches;
  // Keyboard players see keys; touch players see the on-screen button names.
  const key = (k, button) => (touch ? `<b>${button}</b>` : `<kbd>${k}</kbd>`);
  const up = key('↑', '▲'), lift = key('Space', 'LIFT'), boost = key('E', 'BOOST');
  const drift = key('Shift', 'DRIFT');
  const turn = touch ? '<b>⟲ ⟳</b>' : '<kbd>←</kbd><kbd>→</kbd>';
  const cam = touch ? 'Drag to orbit · pinch to zoom' : 'Drag to orbit · scroll to zoom · double-click to reset · C camera · M mode';
  if (paused) return ['Paused — press <kbd>P</kbd> or any drive key to resume', ''];
  if (isRace()) {
    const p = race.phase;
    if (panel.driverOpen) return ['', ''];
    if (p === 'browse') return [`Free drive · ${up} ${turn} ${drift} ${boost} ${lift}`, 'Pick a room on the right, or create one and share its link'];
    if (p === 'connecting') return ['Joining the room…', ''];
    if (p === 'error') return ['Race server unavailable', 'Run the game with node server.js, or open the deployed site'];
    if (p === 'full') return [`Room ${race.room} is full (${race.max} players)`, 'Press <kbd>Enter</kbd> to go back to the room list'];
    if (p === 'limit') return ['Races are paused for today', 'The free server allowance is nearly used up · back at 09:00 (KST)'];
    if (p === 'lobby') {
      const km = (RACE_LENGTH / 1000).toFixed(0);
      if (race.isHost) {
        return race.waitingFor.length
          ? [`Waiting for ${race.waitingFor.length} player${race.waitingFor.length > 1 ? 's' : ''} to get ready`, `You're the host · ${km} km · cars collide · no traffic`]
          : [`Press <kbd>Enter</kbd> to start the race`, `You're the host · ${km} km · cars collide · no traffic`];
      }
      return race.me?.ready
        ? ['Ready · waiting for the host to start', 'Press <kbd>Enter</kbd> to cancel']
        : [`Press <kbd>Enter</kbd> when you're ready`, `${km} km · cars collide · no traffic`];
    }
    if (p === 'countdown') return [`${turn} steer · ${drift} drift · ${boost} boost · ${lift} hop`, ''];
    return ['', ''];
  }
  if (isHighway()) {
    const c = highway.car;
    const hwCam = touch ? '' : 'C camera · M mode · R new road';
    if (c.wrecked) return ['', ''];
    if (!c.started) return [`Hold ${up} to drive · ${turn} steer · ${drift} drift · ${boost} boost · ${lift} hop`, hwCam];
    if (c.distance < 600) return [`${drift} drift · ${boost} boost · ${lift} hop over traffic — or over the median`, 'A hard crash ends the run'];
    return ['', ''];
  }
  if (sim.state === 'ready') {
    return modeKey === 'ramp'
      ? [`Hold ${up} to climb — the grip keeps you on the wall`, cam]
      : [`Hold ${up} to build speed, then ${lift} to clear the vehicles and land in the zone`, cam];
  }
  if (sim.state === 'track') {
    if (sim.side < 0) return [`On the roof — ${up} ${key('↓', '▼')} to roll, past the edge you drop`, ''];
    if (sim.s > track.curveStart) return [`Release ${up} to let go of the wall · reach the lip to launch`, ''];
    return modeKey === 'jump' && sim.x < CHALLENGES.jump.zone.x
      ? [`${lift} before the vehicles · ${boost} pushes you forward`, '']
      : [`Keep accelerating · ${lift} to hop`, ''];
  }
  if (sim.state === 'air') {
    if (sim.brakeCue) return [`<span class="cue">${lift} now — brake the fall</span>`, ''];
    return [`${turn} rotate · ${lift} lift · ${boost} boost — land wheels first`, 'The dashed line is your current fall path'];
  }
  return ['', ''];
}

const shown = {};
const write = (id, text) => {
  if (shown[id] === text) return;
  shown[id] = text;
  $(id).textContent = text;
};
function updateGauges(dt) {
  const hw = isHighway() ? highway.telemetry() : null;
  const kmh = hw ? hw.kmh : Math.hypot(sim.vx, sim.vy) * 3.6;
  const jets = hw ? highway.car.jets : sim.jets;
  gauge.update(paused ? 0 : dt, kmh, !paused && !!jets.boost);
  if (hw) {
    if (isRace()) {
      const st = race.standing();
      write('gHeight', Math.max(0, (race.finishS - highway.car.s) / 1000).toFixed(2));
      write('gTilt', `${st.place}/${st.of}`);
    } else {
      write('gHeight', hw.km.toFixed(2));
      write('gTilt', String(hw.passed));
    }
    write('gG', hw.g.toFixed(1));
    write('gFuelTxt', String(Math.round(hw.fuel)));
    const boost = hw.fuel / highway.fuelMax;
    $('gFuel').style.transform = `scaleX(${boost.toFixed(3)})`;
    $('gFuel').classList.toggle('low', boost < 0.2);
    return;
  }
  write('gHeight', sim.height.toFixed(1));
  write('gG', sim.gForce.toFixed(1));
  write('gTilt', String(Math.round((wrap(sim.theta) * 180) / Math.PI)));
  write('gFuelTxt', String(Math.round(sim.fuel)));
  const fuel = sim.fuel / params.fuel;
  $('gFuel').style.transform = `scaleX(${fuel.toFixed(3)})`;
  $('gFuel').classList.toggle('low', fuel < 0.2);
}

function showResult(r) {
  shownResult = r;
  const card = $('card');
  card.className = `card ${r.ok ? 'ok' : 'bad'}`;
  $('cardTitle').textContent = r.title;
  $('cardReason').textContent = r.ok ? `${challenge.name} run` : r.reason;
  $('cardLines').className = '';
  $('cardTotalLabel').textContent = 'Total';
  $('cardLines').innerHTML = r.lines
    .map((l) => `<li><span>${l.label}</span><span>${l.value}</span><b>+${l.pts.toLocaleString('en-US')}</b></li>`)
    .join('');
  $('cardTotal').textContent = r.total.toLocaleString('en-US');
  const best = store.get(bestKey(), 0);
  if (r.ok && r.total > best) {
    store.set(bestKey(), r.total);
    $('cardBest').textContent = best ? `New best · previous ${best.toLocaleString('en-US')}` : 'First record on this course';
  } else {
    $('cardBest').textContent = best ? `Best ${best.toLocaleString('en-US')}` : '';
  }
  card.hidden = false;
  updateBest();
  sound.chime(r.ok);
}

function handleEvents() {
  for (const e of sim.events) {
    if (e === 'go' && !started) {
      started = true;
      attempts++;
      updateBest();
    } else if (e === 'land') {
      const speed = Math.abs(sim.vx);
      particles.burst(sim.x, 0.2, 40, { life: 1.1, size: 1.4, color: [0.62, 0.6, 0.57], drag: 2.5 }, 6 + speed * 0.3, 2);
      sound.hit(0.7, 260);
    } else if (e === 'crash') {
      particles.burst(sim.x, Math.max(0.3, sim.y - 0.3), 70, { life: 0.9, size: 0.35, color: [0.82, 0.2, 0.22], drag: 1, gravity: 9 }, 14, 9);
      particles.burst(sim.x, Math.max(0.3, sim.y - 0.3), 30, { life: 1.4, size: 1.6, color: [0.45, 0.44, 0.42], drag: 2 }, 5, 3);
      sound.hit(1, 900);
    } else if (e === 'reattach' || e === 'hop') {
      sound.hit(0.35, 400);
    } else if (e === 'lip') {
      particles.burst(sim.x, sim.y, 20, { life: 0.5, size: 0.3, color: [0.82, 0.2, 0.22] }, 4, 2);
    }
  }
  sim.events.length = 0;
}

// Highway game over: the car was wrecked in traffic.
const km = (m) => `${(m / 1000).toFixed(2)} km`;
function showWreck() {
  const r = highway.summary();
  shownResult = r;
  const card = $('card');
  card.className = 'card bad';
  $('cardTitle').textContent = 'Wrecked';
  $('cardReason').textContent = r.info ? `${r.info.kind} a ${r.info.other}` : 'Crashed';
  const mins = Math.floor(r.time / 60), secs = String(Math.floor(r.time % 60)).padStart(2, '0');
  const lines = [
    ['Top speed', `${Math.round(r.top)} km/h`],
    ['Cars passed', String(r.passed)],
    ['Time', `${mins}:${secs}`],
    ['Impact', r.info ? `${Math.round(r.info.closing * 3.6)} km/h` : '—'],
  ];
  $('cardLines').className = 'plain';
  $('cardLines').innerHTML = lines.map(([k, v]) => `<li><span>${k}</span><b>${v}</b></li>`).join('');
  $('cardTotalLabel').textContent = 'Distance';
  $('cardTotal').textContent = km(r.distance);
  saveHighwayBest();
  $('cardBest').textContent = r.distance > runStartBest + 1
    ? (runStartBest ? `New best · previous ${km(runStartBest)}` : 'First record on the highway')
    : `Best ${km(store.get('best:highway', 0))}`;
  card.hidden = false;
  sound.chime(false);
}

// ---------- owner usage badge ----------
// Only the owner's browser shows how much of today's free Cloudflare allowance the races have used.
// Open the site once with ?owner=<key>; the key is kept in this browser and removed from the URL.
const OWNER_STORE = 'vertigo:owner';
const ownerParam = new URLSearchParams(location.search).get('owner');
if (ownerParam) {
  try { localStorage.setItem(OWNER_STORE, ownerParam); } catch { /* storage unavailable */ }
  const url = new URL(location.href);
  url.searchParams.delete('owner');
  history.replaceState(null, '', url);
}
let ownerKey = null;
try { ownerKey = localStorage.getItem(OWNER_STORE); } catch { /* storage unavailable */ }
const usageEl = document.createElement('div');
usageEl.className = 'usage';
usageEl.hidden = true;
document.querySelector('.ident')?.append(usageEl);
async function pollUsage() {
  if (!ownerKey || document.hidden) return;
  try {
    const r = await fetch(`/usage?key=${encodeURIComponent(ownerKey)}`, { cache: 'no-store' });
    if (!r.ok) { usageEl.hidden = true; return; }
    const u = await r.json();
    const pct = Math.round(u.pct * 100);
    usageEl.hidden = false;
    usageEl.className = `usage${u.blocked ? ' stop' : pct >= 80 ? ' warn' : ''}`;
    usageEl.textContent = u.blocked
      ? `Free allowance ${pct}% · races paused until 09:00`
      : `Free allowance ${pct}% today${pct >= 80 ? ' · races pause at 95%' : ''}`;
  } catch { usageEl.hidden = true; }
}
if (ownerKey) {
  pollUsage();
  setInterval(pollUsage, 120000);
  document.addEventListener('visibilitychange', pollUsage);
}

// ---------- race ----------
const fmtTime = (sec) => `${Math.floor(sec / 60)}:${(sec % 60).toFixed(1).padStart(4, '0')}`;
const ordinal = (n) => `${n}${['th', 'st', 'nd', 'rd'][n % 100 > 10 && n % 100 < 14 ? 0 : Math.min(n % 10, 4) % 4] || 'th'}`;
const STATUS = { racing: 'Racing', wrecked: 'Wrecked', dnf: 'DNF', left: 'Left' };
const esc = (t) => String(t ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

// Result card for our race: our time or how we went out, plus the room's standings so far.
function showRaceCard() {
  if (!race.myResult) return;
  shownResult = { race: true };
  const r = race.myResult;
  if (r.status === 'finished') {
    const best = store.get('best:race', 0);
    $('cardBest').dataset.best = best && best <= r.time ? `Best ${fmtTime(best)}` : best ? `New best · previous ${fmtTime(best)}` : 'First race finished';
    if (!best || r.time < best) store.set('best:race', r.time);
    updateBest();
  } else {
    $('cardBest').dataset.best = '';
  }
  renderRaceCard();
  $('card').hidden = false;
  sound.chime(r.status === 'finished');
}

function renderRaceCard() {
  const r = race.myResult;
  if (!r) return;
  const card = $('card');
  card.className = `card ${r.status === 'finished' ? 'ok' : 'bad'}`;
  $('cardTitle').textContent = r.status === 'finished' ? 'Finished' : r.status === 'dnf' ? 'Out of time' : 'Wrecked';
  const rows = race.results.length ? race.results : [{ id: race.id, name: `P${race.slot + 1}`, ...r }];
  const place = rows.findIndex((x) => x.id === race.id) + 1;
  const info = highway.car.wreckInfo;
  $('cardReason').textContent = r.status === 'wrecked' && info
    ? `${info.kind} ${info.other}`
    : `Room ${race.room} · ${place ? ordinal(place) : '—'} of ${rows.length}`;
  $('cardLines').className = 'plain';
  $('cardLines').innerHTML = rows.map((x, i) => {
    const value = x.status === 'finished' ? fmtTime(x.time || 0)
      : x.status === 'wrecked' ? `Wrecked · ${((x.dist || 0) / 1000).toFixed(2)} km` : STATUS[x.status] || '';
    return `<li><span>${i + 1}. ${esc(x.name)}${x.id === race.id ? ' · you' : ''}</span><b>${value}</b></li>`;
  }).join('');
  $('cardTotalLabel').textContent = 'Time';
  $('cardTotal').textContent = r.status === 'finished' ? fmtTime(r.time) : '—';
  const waiting = race.phase !== 'finished' && rows.some((x) => x.status === 'racing');
  $('cardBest').textContent = [$('cardBest').dataset.best, waiting ? 'Waiting for the others…' : 'Enter to go back to the room'].filter(Boolean).join(' · ');
}

// Room panel (top right) and the countdown, refreshed a few times a second.
let raceUiAt = 0;
let goShownUntil = 0;
function raceUi(force = false) {
  const cd = race.countdown;
  const count = $('count');
  if (race.phase === 'countdown') {
    count.hidden = false;
    count.className = 'count';
    count.textContent = String(Math.ceil(cd) || 1);
    goShownUntil = race.goAt + 900;
  } else if (performance.now() < goShownUntil && race.inRace) {
    count.hidden = false;
    count.className = 'count go';
    count.textContent = 'GO';
  } else {
    count.hidden = true;
  }
  const now = performance.now();
  if (!force && now - raceUiAt < 200) return;
  raceUiAt = now;
  panel.render(force);
  // Live race line under the room list
  if (race.phase === 'racing' && race.inRace) {
    const st = race.standing();
    const live = $('race').querySelector('[data-live]');
    if (live) live.textContent = `${fmtTime(race.raceTime)} · ${ordinal(st.place)} of ${st.of}`;
  }
}

// A 3D burst around a point (the stunt-mode burst only spreads across the side plane).
function burst3(p, n, opts, spread, up, carry = null) {
  for (let k = 0; k < n; k++) {
    particles.emit(
      p.x + (Math.random() - 0.5), p.y + Math.random() * 0.6, p.z + (Math.random() - 0.5),
      (carry ? carry.x : 0) + (Math.random() - 0.5) * spread, Math.random() * up, (carry ? carry.z : 0) + (Math.random() - 0.5) * spread,
      opts,
    );
  }
}

// Tyre smoke from the rear wheels while drifting, locked up or sliding after a wreck.
function emitSmoke(dt) {
  const c = highway.car;
  if (c.airborne || dt <= 0) return;
  const k = highway.skidLevel * 0.8;
  if (k <= 0) return;
  const floor = c.groundY + 0.05;
  for (const p of highway.rearPatches()) {
    if (Math.random() > k * dt * 60) continue;
    particles.emit(p.x, p.y + 0.1, p.z, c.vx * 0.45 + (Math.random() - 0.5) * 1.5, 0.4 + Math.random() * 0.8, c.vz * 0.45 + (Math.random() - 0.5) * 1.5, {
      life: 1.1 + Math.random() * 0.6, size: 1.6 + k * 1.6, color: [0.7, 0.7, 0.69], drag: 1.6, floor,
    });
  }
}

let runStartBest = 0;
let bestSavedAt = 0;
function saveHighwayBest() {
  if (!highway.car || modeKey !== 'highway') return;
  const best = store.get('best:highway', 0);
  if (highway.car.distance > best + 1) {
    store.set('best:highway', Math.round(highway.car.distance));
    if (isHighway()) updateBest();
  }
}
function handleHighwayEvents() {
  const c = highway.car;
  for (const e of c.events) {
    if (e.type === 'go') {
      attempts++;
      updateBest();
    } else if (e.type === 'hit') {
      sound.hit(Math.min(1, 0.3 + e.power / 20), 800);
    } else if (e.type === 'scrape') {
      sound.hit(Math.min(0.6, 0.15 + e.power / 30), 1600);
    } else if (e.type === 'land') {
      sound.hit(Math.min(0.6, e.power / 12), 260);
    } else if (e.type === 'hop') {
      sound.hit(0.3, 400);
    } else if (e.type === 'wreck') {
      const p = { x: c.pos.x, y: c.pos.y - 0.2, z: c.pos.z };
      const floor = c.groundY + 0.05;
      const carry = { x: c.vx * 0.5, z: c.vz * 0.5 };
      burst3(p, 90, { life: 0.9, size: 0.35, color: [0.82, 0.2, 0.22], drag: 1, gravity: 9, floor }, 16, 9, carry);
      burst3(p, 40, { life: 1.6, size: 0.22, color: [0.16, 0.17, 0.19], drag: 0.6, gravity: 12, floor }, 12, 7, carry);
      burst3(p, 45, { life: 2.2, size: 2.4, color: [0.55, 0.54, 0.52], drag: 1.8, floor }, 6, 3, carry);
      highway.shake = 1;
      sound.hit(1, 900);
      sound.hit(0.9, 180);
    }
  }
  c.events.length = 0;
  if (elapsed - bestSavedAt > 1) {
    bestSavedAt = elapsed;
    saveHighwayBest();
  }
}

const tmp = new THREE.Vector3();
function emitJets(dt) {
  const j = sim.jets;
  const c = Math.cos(sim.theta), s = Math.sin(sim.theta);
  const emitFrom = (lx, ly, dx, dy, speed, count, color) => {
    for (let i = 0; i < count; i++) {
      const wx = sim.x + lx * c - ly * s;
      const wy = sim.y + lx * s + ly * c;
      const wdx = dx * c - dy * s, wdy = dx * s + dy * c;
      for (const z of [-1.12, 1.12]) {
        particles.emit(wx, wy, ly === -0.05 ? 0 : z, sim.vx + wdx * speed + (Math.random() - 0.5) * 2, sim.vy + wdy * speed + (Math.random() - 0.5) * 2, (Math.random() - 0.5) * 2, { life: 0.35, size: 0.55, color, drag: 3 });
        if (ly === -0.05) break;
      }
    }
  };
  const n = Math.max(1, Math.round(dt * 120));
  if (j.lift) for (const x of [1.7, -1.7]) emitFrom(x, -0.6, 0, -1, 14, n, jetColor.lift);
  if (j.boost) emitFrom(-2.6, -0.05, -1, 0, 16, n * 2, jetColor.boost);
  if (j.grip && Math.random() < 0.6) {
    tmp.set(sim.x - 1.35 * c + 0.62 * s, sim.y - 1.35 * s - 0.62 * c, (Math.random() - 0.5) * 2);
    particles.emit(tmp.x, tmp.y, tmp.z, (Math.random() - 0.5), (Math.random() - 0.5), (Math.random() - 0.5), { life: 0.3, size: 0.25, color: [0.82, 0.2, 0.22] });
  }
}

// Highway: the boost leaves a short trail in the car's colour, the lift pods a puff below.
const jetDir = new THREE.Vector3();
function emitHighwayJets(dt) {
  const c = highway.car;
  if (dt <= 0 || c.wrecked) return;
  const j = c.jets;
  if (!j.boost && !j.lift) return;
  rover.root.updateMatrixWorld(true);
  jetDir.setFromMatrixColumn(rover.root.matrixWorld, 0); // car forward
  const n = Math.max(1, Math.round(dt * 90));
  const floor = c.groundY + 0.05;
  const spark = (node, dx, dy, dz, speed, opts) => {
    node.getWorldPosition(tmp);
    for (let i = 0; i < n; i++) {
      // Mostly carried along with the car, so the plume stays short instead of streaming into the chase camera.
      particles.emit(tmp.x, tmp.y, tmp.z,
        c.vx * 0.88 + dx * speed + (Math.random() - 0.5) * 1.2,
        dy * speed + (Math.random() - 0.5) * 0.8,
        c.vz * 0.88 + dz * speed + (Math.random() - 0.5) * 1.2,
        { drag: 2, floor, ...opts });
    }
  };
  if (j.boost) spark(rover.nozzles.boost, -jetDir.x, 0, -jetDir.z, 5, { life: 0.18, size: 0.42, color: jetColor.boost });
  if (j.lift) for (const pod of rover.nozzles.lift) spark(pod, 0, -1, 0, 6, { life: 0.22, size: 0.4, color: jetColor.lift });
}

function updateCamera(dt) {
  const v = VIEWS[viewIndex];
  const k = 1 - Math.exp(-dt * 5);
  if (v.key === 'side' || v.key === 'drone') {
    const lead = THREE.MathUtils.clamp(sim.vx * 0.25, -6, 6);
    tmp.set(sim.x + lead, Math.max(2.5, sim.y * 0.8 + 1), 0);
    camTarget.lerp(tmp, k);
    camera.position.copy(camTarget).add(camOffset);
    controls.target.copy(camTarget);
    controls.update();
    camOffset.copy(camera.position).sub(camTarget);
  } else if (v.key === 'chase') {
    const sp = Math.hypot(sim.vx, sim.vy);
    let dx = Math.cos(sim.theta), dy = Math.sin(sim.theta);
    if (sp > 2) { dx = sim.vx / sp; dy = sim.vy / sp; }
    tmp.set(sim.x - dx * 11, Math.max(1.2, sim.y - dy * 11 + 3.5), 6);
    camera.position.lerp(tmp, k);
    camTarget.lerp(tmp.set(sim.x, sim.y, 0), 1 - Math.exp(-dt * 10));
    camera.lookAt(camTarget);
  } else {
    const side = modeKey === 'ramp' ? -1 : 1;
    camera.position.lerp(tmp.set(challenge.zone.x + side * 10, 1.4, 10), k);
    camTarget.lerp(tmp.set(sim.x, sim.y, 0), 1 - Math.exp(-dt * 8));
    camera.lookAt(camTarget);
  }
  sun.position.set(sim.x + 18, 40, 22);
  sun.target.position.set(sim.x, 0, 0);
}

const baseFov = () => {
  const portrait = window.innerWidth < window.innerHeight;
  if (isHighway()) return portrait ? 68 : 52;
  return portrait ? 60 : 42;
};
function resize() {
  const w = window.innerWidth, h = window.innerHeight;
  renderer.setSize(w, h);
  camera.aspect = w / h;
  camera.fov = baseFov();
  camera.updateProjectionMatrix();
}
window.addEventListener('resize', resize);
resize();

// ---------- loop ----------
loadLevel(modeKey);
resetView();
const clock = new THREE.Clock();
let elapsed = 0;

function frame() {
  tick(Math.min(0.1, clock.getDelta()));
  requestAnimationFrame(frame);
}

function tick(dt) {
  elapsed += dt;
  const controlsIn = input.read();
  if (isHighway()) {
    const hwDt = paused ? 0 : dt;
    if (isRace()) race.update(dt);
    // Shift is the e-brake here; E boosts as in every mode.
    let hwIn = shownResult && !isRace()
      ? { throttle: 0, spin: 0, lift: false, boost: false, ebrake: false }
      : { throttle: controlsIn.throttle, spin: controlsIn.spin, lift: controlsIn.lift, boost: controlsIn.boost, ebrake: controlsIn.shift };
    if (isRace()) hwIn = race.filter(hwIn);
    highway.update(hwDt, hwIn);
    if (highway.shift) {
      particles.shift(-highway.shift.dx, 0, -highway.shift.dz);
      highway.shift = null;
    }
    handleHighwayEvents();
    if (highway.car.wrecked && highway.car.wreckT > 1.6 && !shownResult) {
      if (isRace()) { if (race.inRace && race.myResult) showRaceCard(); } else showWreck();
    }
    if (isRace()) raceUi();
    highway.poseRover(rover, elapsed);
    highway.updateCamera(camera, dt, views()[viewIndex].key, baseFov());
    const p = highway.car.pos;
    sun.position.set(p.x + 18, p.y + 40, p.z + 22);
    sun.target.position.set(p.x, p.y, p.z);
    emitSmoke(hwDt);
    emitHighwayJets(hwDt);
    particles.update(hwDt);
    updateGauges(dt);
    const [h, sub] = hints();
    setHint(h, sub);
    sound.update(highway.soundState, controlsIn.throttle);
    sound.skid(paused ? 0 : highway.skidLevel, highway.car.speed);
    renderer.render(scene, camera);
    return;
  }
  sim.input = shownResult ? { throttle: 0, spin: 0, lift: false, boost: false } : controlsIn;
  const simDt = paused ? 0 : dt * params.timeScale;
  sim.update(simDt);
  handleEvents();

  if (sim.done && !shownResult) {
    const since = sim.t - sim.endT;
    const ready = sim.state === 'landed' ? since > 0.9 || sim.rest > 0.3 : since > 1.8 || sim.rest > 0.5;
    if (ready) showResult(sim.result);
  }

  rover.update(sim, elapsed);
  if (!paused) emitJets(simDt);
  particles.update(simDt);
  forecast.update(sim, RIDE, challenge.zone);
  world.setProgress(sim.progress, elapsed);
  updateCamera(dt);
  updateGauges(dt);
  const [h, sub] = hints();
  setHint(h, sub);
  sound.update(sim, controlsIn.throttle);
  sound.skid(0);

  renderer.render(scene, camera);
}

window.addEventListener('pagehide', saveHighwayBest);
$('loading').classList.add('gone');
requestAnimationFrame(frame);

// Exposed for automated checks in the browser console.
window.__vertigo = { get sim() { return sim; }, params, loadLevel, restart, tick, rover, camera, highway, sound, race, cars, gauge };
