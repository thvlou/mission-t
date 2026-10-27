// One race room: up to 5 players share a room code, a road seed and a start signal. The room only
// relays car states and keeps the standings; each browser simulates its own car. Transport-free:
// a peer is anything with send(text), so the same room runs in Node (server/rooms.js) and in a
// Cloudflare Durable Object (worker/index.js).
//
// Flow: players join with a nickname and a car, press Ready, and the host (first in, handed on if
// they leave) presses Start once everyone else is ready. After the race everyone is un-readied.
export const MAX_PLAYERS = 5;
const COUNTDOWN_MS = 3000;
const FINISH_GRACE_MS = 60000; // after the first finisher, others get this long
import { COURSES } from '../src/race/courses.js';

export const roomCode = () => Array.from({ length: 4 }, () => 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random() * 32)]).join('');
export const validCode = (c) => /^[A-Z0-9]{4,6}$/.test(c || '');

// Nicknames: printable, trimmed, up to 14 characters. Cars: a registry id (checked by the client).
const cleanNick = (nick, fallback) => {
  const s = String(nick ?? '').replace(/[\u0000-\u001f\u007f<>]/g, '').trim().slice(0, 14);
  return s || fallback;
};
const cleanCar = (car) => (/^[a-z0-9-]{1,24}$/.test(car || '') ? car : 'vertigo-gt');

export class Room {
  constructor(name) {
    this.name = name;
    this.players = new Map();
    this.hostId = null;
    this.phase = 'lobby';
    this.race = null;
    this.course = 'highway'; // picked by the host in the lobby
    this.timer = null;
    this.seed = Math.floor(Math.random() * 1e9); // the road everyone is on (fresh for every race)
    this.limited = false; // set by the host when today's free allowance is nearly used up
    this.onChange = null; // (summary | null) => void, for the public room list
  }

  get size() {
    return this.players.size;
  }

  // What the room list shows; null once the room is empty.
  summary() {
    if (!this.players.size) return null;
    const host = this.players.get(this.hostId);
    return { code: this.name, host: host ? host.name : '', players: this.players.size, max: MAX_PLAYERS, phase: this.phase, course: this.course };
  }

  changed() {
    this.onChange?.(this.summary());
  }

  // Returns the new player, or null when the room is full or paused (the peer is told so).
  join(peer, profile = {}) {
    if (this.limited) {
      peer.send(JSON.stringify({ t: 'limit' }));
      return null;
    }
    if (this.players.size >= MAX_PLAYERS) {
      peer.send(JSON.stringify({ t: 'full', room: this.name, max: MAX_PLAYERS }));
      return null;
    }
    const used = new Set([...this.players.values()].map((p) => p.slot));
    let slot = 0;
    while (used.has(slot)) slot++;
    const me = {
      id: Math.random().toString(36).slice(2, 10), slot, peer, ready: false,
      name: cleanNick(profile.nick, `P${slot + 1}`), car: cleanCar(profile.car),
    };
    this.players.set(me.id, me);
    if (!this.hostId) this.hostId = me.id;
    peer.send(JSON.stringify({ t: 'welcome', id: me.id, slot, room: this.name, seed: this.seed, phase: this.phase, max: MAX_PLAYERS, host: this.hostId, players: this.roster(), course: this.course }));
    this.broadcastRoster(me.id);
    if (this.race) peer.send(JSON.stringify(this.standings()));
    this.changed();
    return me;
  }

  message(me, msg) {
    if (msg.t === 'state') this.broadcast({ ...msg, id: me.id }, me.id);
    else if (msg.t === 'bump') this.bump(me, msg);
    else if (msg.t === 'course' && this.phase === 'lobby' && me.id === this.hostId && Object.hasOwn(COURSES, msg.course)) {
      this.course = msg.course;
      this.broadcastRoster();
      this.changed();
    }
    else if (msg.t === 'start') this.start(me);
    else if (msg.t === 'ready' && this.phase === 'lobby') {
      me.ready = !!msg.ready;
      this.broadcastRoster();
    } else if (msg.t === 'profile' && this.phase === 'lobby') {
      me.name = cleanNick(msg.nick, me.name);
      me.car = cleanCar(msg.car);
      this.broadcastRoster();
      if (me.id === this.hostId) this.changed();
    } else if ((msg.t === 'finish' || msg.t === 'wreck') && this.race) this.result(me, msg);
  }

  // A knock one car gave another: passed to that player only (each browser owns its own car).
  bump(me, msg) {
    const to = this.players.get(msg.to);
    if (!to || to === me || !this.race) return;
    const num = (v) => Math.max(-30, Math.min(30, Number(v) || 0));
    try { to.peer.send(JSON.stringify({ t: 'bump', id: me.id, s: num(msg.s), d: num(msg.d), w: num(msg.w) })); } catch { /* closing socket */ }
  }

  leave(me) {
    if (!this.players.delete(me.id)) return;
    if (this.hostId === me.id) {
      // Hand the room to whoever has been here longest (lowest slot).
      const next = [...this.players.values()].sort((a, b) => a.slot - b.slot)[0];
      this.hostId = next ? next.id : null;
    }
    this.broadcast({ t: 'left', id: me.id });
    this.broadcastRoster();
    const race = this.race;
    if (race && race.entrants.has(me.id) && !race.results.has(me.id)) {
      race.results.set(me.id, { status: 'left', name: me.name, dist: 0 });
      this.settle();
    }
    if (!this.players.size) clearTimeout(this.timer);
    this.changed();
  }

  roster() {
    return [...this.players.values()].map((p) => ({ id: p.id, slot: p.slot, name: p.name, car: p.car, ready: p.ready, host: p.id === this.hostId }));
  }

  broadcastRoster(except = null) {
    this.broadcast({ t: 'players', host: this.hostId, players: this.roster(), course: this.course }, except);
  }

  broadcast(msg, except = null) {
    const text = JSON.stringify(msg);
    for (const p of this.players.values()) {
      if (p.id === except) continue;
      try { p.peer.send(text); } catch { /* closing socket */ }
    }
  }

  // Only the host can start, and only once every other player is ready.
  start(me) {
    if (this.phase !== 'lobby' || me.id !== this.hostId) return;
    if (this.limited) {
      this.broadcast({ t: 'limit' });
      return;
    }
    const waiting = [...this.players.values()].filter((p) => p.id !== this.hostId && !p.ready);
    if (waiting.length) {
      me.peer.send(JSON.stringify({ t: 'notready', names: waiting.map((p) => p.name) }));
      return;
    }
    this.phase = 'countdown';
    this.seed = Math.floor(Math.random() * 1e9);
    this.race = {
      seed: this.seed,
      entrants: new Set(this.players.keys()),
      names: new Map([...this.players.values()].map((p) => [p.id, p.name])),
      results: new Map(),
      firstFinish: 0,
    };
    this.broadcast({ t: 'countdown', seed: this.seed, delay: COUNTDOWN_MS, grid: this.roster(), course: this.course });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.phase = 'racing'; this.changed(); }, COUNTDOWN_MS);
    this.changed();
  }

  result(me, msg) {
    const race = this.race;
    if (!race.entrants.has(me.id) || race.results.has(me.id)) return;
    if (msg.t === 'finish') {
      race.results.set(me.id, { status: 'finished', name: me.name, time: Number(msg.time) || 0 });
      if (!race.firstFinish) {
        race.firstFinish = Date.now();
        clearTimeout(this.timer);
        this.timer = setTimeout(() => this.close(), FINISH_GRACE_MS);
      }
    } else {
      race.results.set(me.id, { status: 'wrecked', name: me.name, dist: Number(msg.dist) || 0 });
    }
    this.settle();
  }

  // Everyone done (finished, wrecked or gone)? Then the race is over and the room goes back to the lobby.
  settle() {
    const race = this.race;
    if ([...race.entrants].every((id) => race.results.has(id))) this.close();
    else this.broadcast(this.standings());
  }

  close() {
    if (!this.race) return;
    clearTimeout(this.timer);
    for (const id of this.race.entrants) {
      if (!this.race.results.has(id)) this.race.results.set(id, { status: 'dnf', name: this.race.names.get(id), dist: 0 });
    }
    this.phase = 'lobby';
    for (const p of this.players.values()) p.ready = false;
    this.broadcast({ ...this.standings(), done: true });
    this.broadcastRoster();
    this.changed();
  }

  standings() {
    const race = this.race;
    const rank = { finished: 0, racing: 1, wrecked: 2, dnf: 3, left: 4 };
    const list = [...race.entrants].map((id) => ({ id, name: race.names.get(id), status: 'racing', ...race.results.get(id) }));
    list.sort((a, b) => rank[a.status] - rank[b.status] || (a.time ?? 0) - (b.time ?? 0) || (b.dist ?? 0) - (a.dist ?? 0));
    return { t: 'standings', results: list, done: false, phase: this.phase };
  }
}
