// Race rooms: up to 5 players share a room code, a road seed and a start signal. The server only
// relays car states and keeps the standings; each browser simulates its own car.
const MAX_PLAYERS = 5;
const COUNTDOWN_MS = 3000;
const FINISH_GRACE_MS = 60000; // after the first finisher, others get this long

const rooms = new Map();

const code = () => Array.from({ length: 4 }, () => 'ABCDEFGHJKLMNPQRSTUVWXYZ23456789'[Math.floor(Math.random() * 32)]).join('');

export function handlePeer(peer) {
  let room = null, me = null;

  peer.on('message', (text) => {
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    if (msg.t === 'join' && !room) {
      const name = /^[A-Z0-9]{4,6}$/.test(msg.room || '') ? msg.room : code();
      room = rooms.get(name) || newRoom(name);
      if (room.players.size >= MAX_PLAYERS) {
        peer.send(JSON.stringify({ t: 'full', room: name, max: MAX_PLAYERS }));
        if (!room.players.size) rooms.delete(name);
        room = null;
        return;
      }
      const used = new Set([...room.players.values()].map((p) => p.slot));
      let slot = 0;
      while (used.has(slot)) slot++;
      me = { id: Math.random().toString(36).slice(2, 10), slot, name: `P${slot + 1}`, peer };
      room.players.set(me.id, me);
      peer.send(JSON.stringify({ t: 'welcome', id: me.id, slot, room: room.name, seed: room.seed, phase: room.phase, max: MAX_PLAYERS, players: roster(room) }));
      broadcast(room, { t: 'players', players: roster(room) }, me.id);
      if (room.race) peer.send(JSON.stringify(standings(room)));
      return;
    }
    if (!room || !me) return;
    if (msg.t === 'start') startRace(room);
    else if (msg.t === 'state') broadcast(room, { ...msg, id: me.id }, me.id);
    else if ((msg.t === 'finish' || msg.t === 'wreck') && room.race) result(room, me, msg);
  });

  peer.on('close', () => {
    if (!room || !me) return;
    room.players.delete(me.id);
    broadcast(room, { t: 'left', id: me.id });
    broadcast(room, { t: 'players', players: roster(room) });
    if (room.race && room.race.entrants.has(me.id) && !room.race.results.has(me.id)) {
      room.race.results.set(me.id, { status: 'left', name: me.name, dist: 0 });
      settle(room);
    }
    if (!room.players.size) {
      clearTimeout(room.timer);
      rooms.delete(room.name);
    }
  });
}

function newRoom(name) {
  // seed: the road everyone in the room is on (a fresh one for every race).
  const room = { name, players: new Map(), phase: 'lobby', race: null, timer: null, seed: Math.floor(Math.random() * 1e9) };
  rooms.set(name, room);
  return room;
}

function roster(room) {
  return [...room.players.values()].map((p) => ({ id: p.id, slot: p.slot, name: p.name }));
}

function broadcast(room, msg, except = null) {
  const text = JSON.stringify(msg);
  for (const p of room.players.values()) if (p.id !== except) p.peer.send(text);
}

function startRace(room) {
  if (room.phase !== 'lobby') return;
  room.phase = 'countdown';
  room.seed = Math.floor(Math.random() * 1e9);
  room.race = {
    seed: room.seed,
    entrants: new Set(room.players.keys()),
    names: new Map([...room.players.values()].map((p) => [p.id, p.name])),
    results: new Map(),
    firstFinish: 0,
  };
  broadcast(room, { t: 'countdown', seed: room.race.seed, delay: COUNTDOWN_MS, grid: roster(room) });
  clearTimeout(room.timer);
  room.timer = setTimeout(() => { room.phase = 'racing'; }, COUNTDOWN_MS);
}

function result(room, me, msg) {
  const race = room.race;
  if (!race.entrants.has(me.id) || race.results.has(me.id)) return;
  if (msg.t === 'finish') {
    race.results.set(me.id, { status: 'finished', name: me.name, time: Number(msg.time) || 0 });
    if (!race.firstFinish) {
      race.firstFinish = Date.now();
      clearTimeout(room.timer);
      room.timer = setTimeout(() => close(room), FINISH_GRACE_MS);
    }
  } else {
    race.results.set(me.id, { status: 'wrecked', name: me.name, dist: Number(msg.dist) || 0 });
  }
  settle(room);
}

// Everyone done (finished, wrecked or gone)? Then the race is over and the room goes back to the lobby.
function settle(room) {
  const race = room.race;
  const done = [...race.entrants].every((id) => race.results.has(id));
  if (done) close(room);
  else broadcast(room, standings(room));
}

function close(room) {
  if (!room.race) return;
  clearTimeout(room.timer);
  for (const id of room.race.entrants) {
    if (!room.race.results.has(id)) room.race.results.set(id, { status: 'dnf', name: room.race.names.get(id), dist: 0 });
  }
  room.phase = 'lobby';
  broadcast(room, { ...standings(room), done: true });
}

function standings(room) {
  const race = room.race;
  const rank = { finished: 0, racing: 1, wrecked: 2, dnf: 3, left: 4 };
  const list = [...race.entrants].map((id) => ({ id, name: race.names.get(id), status: 'racing', ...race.results.get(id) }));
  list.sort((a, b) => rank[a.status] - rank[b.status] || (a.time ?? 0) - (b.time ?? 0) || (b.dist ?? 0) - (a.dist ?? 0));
  return { t: 'standings', results: list, done: false, phase: room.phase };
}
