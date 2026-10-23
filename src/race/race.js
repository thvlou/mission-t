import * as THREE from 'three';
import { HALF_L, HALF_W, RIDE } from '../highway/car.js';
import { LAYOUT } from '../highway/road.js';

// Online race on the highway: up to 5 players share a room, a road seed and a start signal.
// Each browser simulates its own car and sends its road position 20 times a second; opponents are
// drawn (and collided with) from those snapshots, interpolated 100 ms in the past.
export const RACE_LENGTH = 5000;           // m from the start line to the finish
const START_S = 60;
const GRID = [[0, -1.85], [0, 1.85], [-12, -3.7], [-12, 0], [-12, 3.7]]; // [s offset, d] per slot
const SEND_EVERY = 0.05;
const DELAY = 100;                          // ms of interpolation buffer
const PAINT = ['#e9e9e6', '#d23437', '#2b2d31', '#8e9196', '#a59a8c'];
const wrap = (a) => Math.atan2(Math.sin(a), Math.cos(a));
const lerp = (a, b, t) => a + (b - a) * t;

export class Race {
  // hooks: { onLobby(), onCountdown(), onStandings(results, done), onStatus() }
  constructor(highway, rover, hooks) {
    this.highway = highway;
    this.rover = rover;
    this.hooks = hooks;
    this.group = new THREE.Group();
    highway.group.add(this.group);
    this.finishGroup = buildFinish();
    this.group.add(this.finishGroup);
    this.ws = null;
    this.reset();
  }

  reset() {
    this.phase = 'offline';   // offline · connecting · lobby · countdown · racing · finished · error · full
    this.id = null;
    this.slot = 0;
    this.room = null;
    this.max = 5;
    this.roster = [];
    this.others = new Map();
    this.goAt = 0;
    this.sendT = 0;
    this.myResult = null;
    this.results = [];
    this.inRace = false;
    this.wreckSent = false;
  }

  get startS() {
    return START_S;
  }

  get finishS() {
    return START_S + RACE_LENGTH;
  }

  // Open the room from the URL (?room=CODE) or let the server make one.
  enter(roomCode) {
    this.leave();
    this.phase = 'connecting';
    this.hooks.onStatus();
    // The room code rides on the URL so a Cloudflare Worker can route us to that room's Durable Object.
    const code = (roomCode || '').toUpperCase();
    const url = `${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws${code ? `?room=${encodeURIComponent(code)}` : ''}`;
    let ws;
    try {
      ws = new WebSocket(url);
    } catch {
      this.phase = 'error';
      this.hooks.onStatus();
      return;
    }
    this.ws = ws;
    ws.onopen = () => ws.send(JSON.stringify({ t: 'join', room: roomCode || '' }));
    ws.onmessage = (e) => this.receive(JSON.parse(e.data));
    ws.onclose = () => {
      if (this.ws !== ws) return;
      if (this.phase !== 'full') this.phase = 'error';
      this.hooks.onStatus();
    };
  }

  leave() {
    if (this.ws) {
      const ws = this.ws;
      this.ws = null;
      ws.close();
    }
    for (const o of this.others.values()) this.group.remove(o.mesh);
    this.highway.extraCars = [];
    this.reset();
    this.finishGroup.visible = false;
  }

  send(msg) {
    if (this.ws && this.ws.readyState === 1) this.ws.send(JSON.stringify(msg));
  }

  requestStart() {
    if (this.phase === 'lobby' || this.phase === 'finished') this.send({ t: 'start' });
  }

  receive(m) {
    if (m.t === 'welcome') {
      this.id = m.id;
      this.slot = m.slot;
      this.room = m.room;
      this.max = m.max;
      this.roster = m.players;
      this.phase = 'lobby';
      const url = new URL(location.href);
      url.searchParams.set('room', m.room);
      history.replaceState(null, '', url);
      this.spawn(m.seed);
      this.hooks.onLobby();
    } else if (m.t === 'full') {
      this.phase = 'full';
      this.room = m.room;
      this.hooks.onStatus();
    } else if (m.t === 'players') {
      this.roster = m.players;
      for (const id of [...this.others.keys()]) if (!m.players.some((p) => p.id === id)) this.drop(id);
      this.hooks.onStatus();
    } else if (m.t === 'left') {
      this.drop(m.id);
    } else if (m.t === 'countdown') {
      this.roster = m.grid;
      const me = m.grid.find((p) => p.id === this.id);
      this.inRace = !!me;
      if (me) this.slot = me.slot;
      this.spawn(m.seed);
      for (const o of this.others.values()) o.snaps = [];
      this.goAt = performance.now() + m.delay;
      this.phase = 'countdown';
      this.myResult = null;
      this.results = [];
      this.wreckSent = false;
      this.hooks.onCountdown();
    } else if (m.t === 'state') {
      this.snapshot(m);
    } else if (m.t === 'standings') {
      this.results = m.results;
      if (m.done && this.phase !== 'offline') this.phase = 'finished';
      this.hooks.onStandings(m.results, m.done);
    }
  }

  // Put our car on the shared road at our grid slot.
  spawn(seed) {
    const [ds, d] = GRID[this.slot] || GRID[0];
    this.highway.reset({ seed, traffic: false, s: START_S + ds, d });
  }

  drop(id) {
    const o = this.others.get(id);
    if (!o) return;
    this.group.remove(o.mesh);
    this.others.delete(id);
  }

  opponent(id) {
    let o = this.others.get(id);
    if (o) return o;
    const info = this.roster.find((p) => p.id === id) || { slot: 1, name: '?' };
    const mesh = this.rover.root.clone(true);
    const strip = [];
    mesh.traverse((n) => { if (n.isLight) strip.push(n); });
    for (const n of strip) n.parent.remove(n);
    const paint = new THREE.Color(PAINT[info.slot % PAINT.length]);
    mesh.traverse((n) => {
      if (!n.isMesh) return;
      // Thruster flames are animated only on our own car; hide the copies.
      if (n.material?.transparent && n.material.color?.getHexString() === 'e8484b') n.visible = false;
      if (n.material?.name === 'Paint') {
        n.material = n.material.clone();
        n.material.color.copy(paint);
      }
    });
    mesh.rotation.order = 'YZX';
    const tag = nameTag(info.name, PAINT[info.slot % PAINT.length]);
    tag.position.set(0, 1.9, 0);
    mesh.add(tag);
    this.group.add(mesh);
    o = { id, name: info.name, slot: info.slot, mesh, snaps: [], pose: null,
      proxy: { s: 1e9, x: 0, z: 0, yaw: 0, v: 0, hl: HALF_L, hw: HALF_W, hgt: 1.25, kind: info.name } };
    this.others.set(id, o);
    return o;
  }

  snapshot(m) {
    const o = this.opponent(m.id);
    o.snaps.push({ at: performance.now(), s: m.s, d: m.d, o: m.o, y: m.y, v: m.v, l: m.l, p: m.p, w: m.w });
    if (o.snaps.length > 30) o.snaps.shift();
  }

  // Input gate: frozen on the grid until the lights go out, and after the race is over.
  filter(input) {
    const frozen = this.phase === 'countdown' || (this.inRace && this.myResult) || this.phase === 'connecting';
    return frozen ? { throttle: 0, spin: 0, lift: false, boost: false, ebrake: false } : input;
  }

  get countdown() {
    return this.phase === 'countdown' ? Math.max(0, (this.goAt - performance.now()) / 1000) : 0;
  }

  get raceTime() {
    return this.goAt ? Math.max(0, (performance.now() - this.goAt) / 1000) : 0;
  }

  // Per frame, before the highway steps: lights, our state out, opponents in.
  update(dt) {
    if (this.phase === 'countdown' && performance.now() >= this.goAt) {
      this.phase = this.inRace ? 'racing' : 'lobby';
      this.hooks.onStatus();
    }
    const car = this.highway.car;
    const road = this.highway.road;

    // Our result
    if (this.phase === 'racing' && this.inRace && !this.myResult) {
      if (car.s >= this.finishS) {
        this.myResult = { status: 'finished', time: this.raceTime };
        this.send({ t: 'finish', time: this.myResult.time });
        this.hooks.onFinish(this.myResult);
      } else if (car.wrecked && !this.wreckSent) {
        this.wreckSent = true;
        this.myResult = { status: 'wrecked', dist: Math.max(0, car.s - START_S) };
        this.send({ t: 'wreck', dist: this.myResult.dist });
      }
    }

    // Our state out
    this.sendT += dt;
    if (this.sendT >= SEND_EVERY && this.id && this.phase !== 'connecting') {
      this.sendT = 0;
      const f = road.frame(car.s);
      this.send({
        t: 'state', s: +car.s.toFixed(2), d: +car.d.toFixed(2), o: +wrap(car.yaw - f.h).toFixed(3),
        y: +car.height.toFixed(2), v: +car.v.toFixed(2), l: +car.lean.toFixed(3),
        p: +(car.pitch - Math.atan(f.slope)).toFixed(3), w: car.wrecked ? 1 : 0,
      });
    }

    // Opponents in: interpolate, pose the mesh, refresh the collision proxy
    const now = performance.now() - DELAY;
    const extra = [];
    for (const o of this.others.values()) {
      const pose = sample(o.snaps, now);
      // Far-off opponents are skipped so the road isn't generated out to them every frame.
      if (!pose || Math.abs(pose.s - car.s) > 1500) {
        o.pose = pose;
        o.proxy.s = 1e9;
        o.mesh.visible = false;
        continue;
      }
      o.pose = pose;
      const f = road.frame(pose.s);
      const x = f.x + f.rx * pose.d, z = f.z + f.rz * pose.d;
      const yaw = f.h + pose.o;
      o.mesh.visible = true;
      o.mesh.position.set(x, f.y + RIDE + pose.y, z);
      o.mesh.rotation.set(pose.l, yaw, Math.atan(f.slope) + pose.p);
      const px = o.proxy;
      // Only collide with cars at about our height (no hitting someone hovering overhead).
      px.s = Math.abs(pose.y - car.height) < 1.1 ? pose.s : 1e9;
      px.x = x; px.z = z; px.yaw = yaw; px.v = pose.v;
      px.wrecked = false;
      extra.push(px);
    }
    this.highway.extraCars = extra;

    // Finish gantry, only once it is within reach of the streamed road
    const near = Math.abs(this.finishS - car.s) < 1600;
    this.finishGroup.visible = near && this.phase !== 'lobby';
    if (this.finishGroup.visible) {
      const f = road.frame(this.finishS);
      this.finishGroup.position.set(f.x, f.y, f.z);
      this.finishGroup.rotation.set(0, f.h, 0);
    }
  }

  // Live order by distance along the road (finishers first, in finishing order).
  standing() {
    const me = this.highway.car;
    const rows = [{ id: this.id, s: me.s, mine: true }];
    for (const o of this.others.values()) if (o.pose) rows.push({ id: o.id, s: o.pose.s });
    const done = new Map(this.results.map((r, i) => [r.id, r]));
    const score = (r) => {
      const res = done.get(r.id);
      if (res?.status === 'finished') return 1e7 - (res.time || 0);
      if (res && res.status !== 'racing') return -1e7 + r.s;
      return r.s;
    };
    rows.sort((a, b) => score(b) - score(a));
    return { place: rows.findIndex((r) => r.mine) + 1, of: rows.length };
  }
}

function sample(snaps, at) {
  if (!snaps.length) return null;
  let i = snaps.length - 1;
  while (i > 0 && snaps[i - 1].at > at) i--;
  const b = snaps[i], a = snaps[i - 1];
  if (!a || at >= b.at) {
    // Past the newest snapshot: carry it forward for at most 0.25 s.
    const t = Math.min(0.25, Math.max(0, (at - b.at) / 1000));
    return { ...b, s: b.s + b.v * Math.cos(b.o) * t };
  }
  const t = (at - a.at) / Math.max(1, b.at - a.at);
  return {
    s: lerp(a.s, b.s, t), d: lerp(a.d, b.d, t), o: a.o + wrap(b.o - a.o) * t, y: lerp(a.y, b.y, t),
    v: lerp(a.v, b.v, t), l: lerp(a.l, b.l, t), p: lerp(a.p, b.p, t), w: b.w,
  };
}

function nameTag(text, color) {
  const c = document.createElement('canvas');
  c.width = 256; c.height = 96;
  const ctx = c.getContext('2d');
  ctx.fillStyle = 'rgba(251,251,249,0.92)';
  ctx.beginPath();
  ctx.roundRect(8, 8, 240, 80, 40);
  ctx.fill();
  ctx.fillStyle = color === '#e9e9e6' ? '#121316' : color;
  ctx.font = '400 54px Crosner, Pretendard, sans-serif';
  ctx.textAlign = 'center';
  ctx.textBaseline = 'middle';
  ctx.fillText(text, 128, 52);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const sprite = new THREE.Sprite(new THREE.SpriteMaterial({ map: tex, depthWrite: false }));
  sprite.scale.set(1.6, 0.6, 1);
  return sprite;
}

// Checkered line across our carriageway and a gantry with a FINISH board.
function buildFinish() {
  const g = new THREE.Group();
  g.visible = false;
  const width = LAYOUT.roadR - LAYOUT.roadL;
  const c = document.createElement('canvas');
  c.width = 512; c.height = 64;
  const ctx = c.getContext('2d');
  for (let x = 0; x < 32; x++) for (let y = 0; y < 4; y++) {
    ctx.fillStyle = (x + y) % 2 ? '#121316' : '#fbfaf8';
    ctx.fillRect(x * 16, y * 16, 16, 16);
  }
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  const line = new THREE.Mesh(new THREE.PlaneGeometry(width, 3), new THREE.MeshStandardMaterial({ map: tex, roughness: 0.8, polygonOffset: true, polygonOffsetFactor: -2 }));
  // Plane lies across the road: its width runs along the road's right axis (local z after the group's yaw).
  line.rotation.set(-Math.PI / 2, 0, Math.PI / 2);
  line.position.set(0, 0.03, (LAYOUT.roadL + LAYOUT.roadR) / 2);
  g.add(line);
  const steel = new THREE.MeshStandardMaterial({ color: '#9fa3a8', roughness: 0.35, metalness: 0.7 });
  for (const d of [LAYOUT.roadL - 0.4, LAYOUT.roadR + 0.4]) {
    const post = new THREE.Mesh(new THREE.BoxGeometry(0.3, 7.6, 0.3), steel);
    post.position.set(0, 3.8, d);
    g.add(post);
  }
  const beam = new THREE.Mesh(new THREE.BoxGeometry(0.35, 0.35, width + 0.8), steel);
  beam.position.set(0, 7.4, (LAYOUT.roadL + LAYOUT.roadR) / 2);
  g.add(beam);
  const b = document.createElement('canvas');
  b.width = 1024; b.height = 192;
  const bc = b.getContext('2d');
  bc.fillStyle = '#d23437';
  bc.fillRect(0, 0, 1024, 192);
  bc.fillStyle = '#fbfaf8';
  bc.font = '400 120px Crosner, Pretendard, sans-serif';
  bc.textAlign = 'center';
  bc.textBaseline = 'middle';
  bc.fillText('FINISH', 512, 104);
  const btex = new THREE.CanvasTexture(b);
  btex.colorSpace = THREE.SRGBColorSpace;
  const board = new THREE.Mesh(new THREE.PlaneGeometry(9, 1.7), new THREE.MeshStandardMaterial({ map: btex, roughness: 0.6 }));
  board.position.set(-0.2, 7.4, (LAYOUT.roadL + LAYOUT.roadR) / 2);
  board.rotation.y = -Math.PI / 2; // face drivers coming along +s
  g.add(board);
  return g;
}
