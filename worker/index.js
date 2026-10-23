// Cloudflare Worker: serves the game files as static assets and runs each race room in its own
// Durable Object, so races work on <name>.workers.dev with no PC or server of our own.
import { Room, roomCode, validCode } from '../server/room-core.js';

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
    return env.ASSETS.fetch(request);
  },
};

export class RaceRoom {
  constructor(state, env) {
    this.state = state;
    this.env = env;
    this.room = null;
  }

  async fetch(request) {
    const code = new URL(request.url).searchParams.get('room');
    if (!this.room) this.room = new Room(code);
    const { 0: client, 1: server } = new WebSocketPair();
    server.accept();
    const peer = { send: (text) => server.send(text) };
    let me = null;
    server.addEventListener('message', (event) => {
      let msg;
      try { msg = JSON.parse(event.data); } catch { return; }
      if (msg.t === 'join' && !me) {
        me = this.room.join(peer);
        if (!me) server.close(1000, 'Room full');
        return;
      }
      if (me) this.room.message(me, msg);
    });
    const leave = () => {
      if (!me) return;
      this.room.leave(me);
      me = null;
    };
    server.addEventListener('close', leave);
    server.addEventListener('error', leave);
    return new Response(null, { status: 101, webSocket: client });
  }
}
