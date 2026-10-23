// Node side of the race rooms: one Room per code, kept in memory while anyone is in it.
import { Room, roomCode, validCode } from './room-core.js';

const rooms = new Map();

export function handlePeer(peer, requested = '') {
  let room = null, me = null;

  peer.on('message', (text) => {
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    if (msg.t === 'join' && !room) {
      const name = validCode(requested) ? requested : validCode(msg.room) ? msg.room : roomCode();
      room = rooms.get(name) || new Room(name);
      rooms.set(name, room);
      me = room.join(peer);
      if (!me) {
        if (!room.size) rooms.delete(name);
        room = null;
      }
      return;
    }
    if (room && me) room.message(me, msg);
  });

  peer.on('close', () => {
    if (!room || !me) return;
    room.leave(me);
    if (!room.size) rooms.delete(room.name);
  });
}
