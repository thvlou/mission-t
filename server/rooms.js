// Node side of the race rooms: one Room per code, kept in memory while anyone is in it, plus the
// public room list pushed to everyone browsing it (/ws?lobby=1).
import { Room, roomCode, validCode } from './room-core.js';

const rooms = new Map();
const browsers = new Set();

const listing = () => [...rooms.values()].map((r) => r.summary()).filter(Boolean);
let pushTimer = null;
function pushList() {
  clearTimeout(pushTimer);
  pushTimer = setTimeout(() => {
    const text = JSON.stringify({ t: 'rooms', rooms: listing() });
    for (const peer of browsers) peer.send(text);
  }, 100);
}

export function handleLobbyPeer(peer) {
  browsers.add(peer);
  peer.send(JSON.stringify({ t: 'rooms', rooms: listing() }));
  peer.on('close', () => browsers.delete(peer));
}

export function handlePeer(peer, requested = '') {
  let room = null, me = null;

  peer.on('message', (text) => {
    let msg;
    try { msg = JSON.parse(text); } catch { return; }
    if (msg.t === 'join' && !room) {
      const name = validCode(requested) ? requested : validCode(msg.room) ? msg.room : roomCode();
      room = rooms.get(name);
      if (!room) {
        room = new Room(name);
        room.onChange = pushList;
        rooms.set(name, room);
      }
      me = room.join(peer, msg);
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
    pushList();
  });
}
