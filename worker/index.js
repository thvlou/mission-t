// Cloudflare Worker: serves the game files as static assets and runs each race room in its own
// Durable Object, so races work on <name>.workers.dev with no PC or server of our own.
// A single Usage object keeps an estimate of today's free-plan use; near the limit, rooms stop
// taking new players and races (the owner's browser shows the figure, see /usage).
import { Room, roomCode, validCode } from '../server/room-core.js';

// Workers Free plan daily allowances for Durable Objects (reset 00:00 UTC). Incoming WebSocket
// messages count 20:1 as requests; outgoing ones are free.
const FREE = { requests: 100000, gbSeconds: 13000 };
const DO_GB = 0.128;          // a Durable Object is billed at 128 MB while active
const BLOCK_AT = 0.95;        // stop new races here, leaving headroom for races already running
const REPORT_MS = 30000;      // how often a busy room reports its use
const today = () => new Date().toISOString().slice(0, 10);
const usage = (env) => env.USAGE.get(env.USAGE.idFromName('global'));
const lobby = (env) => env.LOBBY.get(env.LOBBY.idFromName('global'));
const LIST_STALE_MS = 150000;  // rooms refresh their list entry at every report; drop silent ones

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (url.pathname === '/ws') {
      if ((request.headers.get('Upgrade') || '').toLowerCase() !== 'websocket') {
        return new Response('Expected a WebSocket upgrade', { status: 426 });
      }
      let code = (url.searchParams.get('room') || '').toUpperCase();
      if (!validCode(code)) code = roomCode();
      url.searchParams.set('room', code);
      // Every room code maps to one Durable Object instance, wherever its players connect from.
      const stub = env.ROOMS.get(env.ROOMS.idFromName(code));
      return stub.fetch(new Request(url, request));
    }
    if (url.pathname === '/lobby') {
      if ((request.headers.get('Upgrade') || '').toLowerCase() !== 'websocket') {
        return new Response('Expected a WebSocket upgrade', { status: 426 });
      }
      return lobby(env).fetch(request);
    }
    if (url.pathname === '/usage') {
      // Owner only: anyone else gets a plain 404.
      if (!env.OWNER_KEY || url.searchParams.get('key') !== env.OWNER_KEY) return new Response('Not found', { status: 404 });
      const r = await usage(env).fetch('https://usage/read');
      return new Response(r.body, { headers: { 'Content-Type': 'application/json', 'Cache-Control': 'no-store' } });
    }
    return env.ASSETS.fetch(request);
  },
};

export class RaceRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.room = null;
    this.sockets = 0;
    this.connections = 0;   // since the last report
    this.messages = 0;      // incoming, since the last report
    this.activeSince = 0;   // when the current active stretch started (ms)
    this.timer = null;
    this.listTimer = null;
  }

  // Keep this room's line in the public room list current (debounced; null removes it).
  listRoom() {
    clearTimeout(this.listTimer);
    this.listTimer = setTimeout(() => {
      this.connections++; // the list update is a Durable Object request as well
      const body = JSON.stringify({ code: this.room.name, summary: this.room.summary() });
      lobby(this.env).fetch('https://lobby/update', { method: 'POST', body }).catch(() => {});
    }, 300);
  }

  // Tell the Usage object what we used since last time and learn whether races are paused.
  async report() {
    const now = Date.now();
    let activeSeconds = 0;
    if (this.activeSince) {
      activeSeconds = (now - this.activeSince) / 1000;
      this.activeSince = now;
    }
    const body = JSON.stringify({ connections: this.connections, messages: this.messages, activeSeconds });
    this.connections = 0;
    this.messages = 0;
    try {
      const r = await usage(this.env).fetch('https://usage/report', { method: 'POST', body });
      const u = await r.json();
      if (this.room) this.room.limited = u.blocked;
    } catch { /* keep the last known state */ }
    if (this.room) this.listRoom();
  }

  async fetch(request) {
    const code = new URL(request.url).searchParams.get('room');
    if (!this.room) {
      this.room = new Room(code);
      this.room.onChange = () => this.listRoom();
    }
    this.connections++;
    if (!this.activeSince) this.activeSince = Date.now();
    await this.report();

    const { 0: client, 1: server } = new WebSocketPair();
    server.accept();
    this.sockets++;
    if (!this.timer) this.timer = setInterval(() => this.report(), REPORT_MS);
    const peer = { send: (text) => server.send(text) };
    let me = null, gone = false;
    server.addEventListener('message', (event) => {
      this.messages++;
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.t === 'join' && !me) {
        me = this.room.join(peer, msg);
        if (!me) server.close(1000, this.room.limited ? 'Paused for today' : 'Room full');
        return;
      }
      if (me) this.room.message(me, msg);
    });
    const leave = () => {
      if (gone) return;
      gone = true;
      if (me) this.room.leave(me);
      me = null;
      this.sockets--;
      if (this.sockets <= 0) {
        this.sockets = 0;
        clearInterval(this.timer);
        this.timer = null;
        this.report().then(() => { if (!this.sockets) this.activeSince = 0; });
      }
    };
    server.addEventListener('close', leave);
    server.addEventListener('error', leave);
    return new Response(null, { status: 101, webSocket: client });
  }
}

// The public room list. Browsers looking at it hold hibernating WebSockets, which cost nothing
// while idle; rooms post updates and every browser gets the fresh list.
export class Lobby {
  constructor(state, env) {
    this.state = state;
    this.env = env;
  }

  async list() {
    const now = Date.now();
    const out = [];
    for (const [key, entry] of await this.state.storage.list({ prefix: 'room:' })) {
      if (now - entry.at > LIST_STALE_MS) await this.state.storage.delete(key);
      else out.push(entry.summary);
    }
    return out;
  }

  async fetch(request) {
    const url = new URL(request.url);
    if (url.pathname === '/update') {
      const { code, summary } = await request.json();
      if (summary) await this.state.storage.put(`room:${code}`, { summary, at: Date.now() });
      else await this.state.storage.delete(`room:${code}`);
      const text = JSON.stringify({ t: 'rooms', rooms: await this.list() });
      for (const ws of this.state.getWebSockets()) {
        try { ws.send(text); } catch { /* closing */ }
      }
      return new Response('ok');
    }
    const { 0: client, 1: server } = new WebSocketPair();
    this.state.acceptWebSocket(server);
    server.send(JSON.stringify({ t: 'rooms', rooms: await this.list() }));
    usage(this.env).fetch('https://usage/report', { method: 'POST', body: JSON.stringify({ connections: 1 }) }).catch(() => {});
    return new Response(null, { status: 101, webSocket: client });
  }

  webSocketMessage() { /* browsers only listen */ }

  webSocketClose(ws) {
    try { ws.close(); } catch { /* already closed */ }
  }
}

// Today's estimated use, one counter for the whole site.
export class Usage {
  constructor(state, env) {
    this.state = state;
    // BLOCK_AT can be lowered in .dev.vars to try the pause locally.
    this.blockAt = Number(env.BLOCK_AT) || BLOCK_AT;
  }

  async fetch(request) {
    const url = new URL(request.url);
    const key = `day:${today()}`;
    const day = (await this.state.storage.get(key)) || { requests: 0, gbSeconds: 0 };
    day.requests += 1; // this call is a Durable Object request too
    if (url.pathname === '/report') {
      const r = await request.json();
      day.requests += (r.connections || 0) + (r.messages || 0) / 20;
      day.gbSeconds += (r.activeSeconds || 0) * DO_GB;
    }
    await this.state.storage.put(key, day);
    const pct = Math.max(day.requests / FREE.requests, day.gbSeconds / FREE.gbSeconds);
    return Response.json({ day: today(), pct, blocked: pct >= this.blockAt, requests: Math.round(day.requests), gbSeconds: Math.round(day.gbSeconds) });
  }
}
