// One race room: up to 5 players share a room code, a road seed and a start signal. The room only
// relays car states and keeps the standings; each browser simulates its own car. Transport-free:
// a peer is anything with send(text), so the same room runs in Node (server/rooms.js) and in a
// Cloudflare Durable Object (worker/index.js).
export const MAX_PLAYERS = 5;
const COUNTDOWN_MS = 3000;
const FINISH_GRACE_MS = 60000; // after the first finisher, others get this long

export const roomCode = () => Array.from({ length: 4 }, () => 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random() * 32)]).join('');
export const validCode = (c) => /^[A-Z0-9]{4,6}$/.test(c || '');

export class Room {
  constructor(name) {
    this.name = name;
    this.players = new Map();
    this.phase = 'lobby';
    this.race = null;
    this.timer = null;
    this.seed = Math.floor(Math.random() * 1e9); // the road everyone is on (fresh for every race)
    this.limited = false; // set by the host when today's free allowance is nearly used up
  }

  get size() {
    return this.players.size;
  }

  // Returns the new player, or null when the room is full (the peer is told so).
  join(peer) {
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
    const me = { id: Math.random().toString(36).slice(2, 10), slot, name: `P${slot + 1}`, peer };
    this.players.set(me.id, me);
    peer.send(JSON.stringify({ t: 'welcome', id: me.id, slot, room: this.name, seed: this.seed, phase: this.phase, max: MAX_PLAYERS, players: this.roster() }));
    this.broadcast({ t: 'players', players: this.roster() }, me.id);
    if (this.race) peer.send(JSON.stringify(this.standings()));
    return me;
  }

  message(me, msg) {
    if (msg.t === 'start') this.start();
    else if (msg.t === 'state') this.broadcast({ ...msg, id: me.id }, me.id);
    else if ((msg.t === 'finish' || msg.t === 'wreck') && this.race) this.result(me, msg);
  }

  leave(me) {
    if (!this.players.delete(me.id)) return;
    this.broadcast({ t: 'left', id: me.id });
    this.broadcast({ t: 'players', players: this.roster() });
    const race = this.race;
    if (race && race.entrants.has(me.id) && !race.results.has(me.id)) {
      race.results.set(me.id, { status: 'left', name: me.name, dist: 0 });
      this.settle();
    }
    if (!this.players.size) clearTimeout(this.timer);
  }

  roster() {
    return [...this.players.values()].map((p) => ({ id: p.id, slot: p.slot, name: p.name }));
  }

  broadcast(msg, except = null) {
    const text = JSON.stringify(msg);
    for (const p of this.players.values()) {
      if (p.id === except) continue;
      try { p.peer.send(text); } catch { /* closing socket */ }
    }
  }

  start() {
    if (this.phase !== 'lobby') return;
    if (this.limited) {
      this.broadcast({ t: 'limit' });
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
    this.broadcast({ t: 'countdown', seed: this.seed, delay: COUNTDOWN_MS, grid: this.roster() });
    clearTimeout(this.timer);
    this.timer = setTimeout(() => { this.phase = 'racing'; }, COUNTDOWN_MS);
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
    this.broadcast({ ...this.standings(), done: true });
  }

  standings() {
    const race = this.race;
    const rank = { finished: 0, racing: 1, wrecked: 2, dnf: 3, left: 4 };
    const list = [...race.entrants].map((id) => ({ id, name: race.names.get(id), status: 'racing', ...race.results.get(id) }));
    list.sort((a, b) => rank[a.status] - rank[b.status] || (a.time ?? 0) - (b.time ?? 0) || (b.dist ?? 0) - (a.dist ?? 0));
    return { t: 'standings', results: list, done: false, phase: this.phase };
  }
}
