// A tiny WebSocket server (RFC 6455, text frames only) so the game needs no npm dependencies.
import { createHash } from 'node:crypto';

const GUID = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11';
const MAX_PAYLOAD = 64 * 1024;

export function acceptWebSocket(req, socket, onConnection) {
  const key = req.headers['sec-websocket-key'];
  if (!key || (req.headers.upgrade || '').toLowerCase() !== 'websocket') {
    socket.end('HTTP/1.1 400 Bad Request\r\n\r\n');
    return;
  }
  const accept = createHash('sha1').update(key + GUID).digest('base64');
  socket.write(
    'HTTP/1.1 101 Switching Protocols\r\n' +
    'Upgrade: websocket\r\nConnection: Upgrade\r\n' +
    `Sec-WebSocket-Accept: ${accept}\r\n\r\n`,
  );
  socket.setNoDelay(true);
  onConnection(new Peer(socket));
}

class Peer {
  constructor(socket) {
    this.socket = socket;
    this.open = true;
    this.handlers = { message: [], close: [] };
    this.buf = Buffer.alloc(0);
    socket.on('data', (chunk) => this.read(chunk));
    socket.on('close', () => this.closed());
    socket.on('error', () => this.closed());
  }

  on(type, fn) {
    this.handlers[type].push(fn);
  }

  send(text) {
    if (!this.open) return;
    const data = Buffer.from(text);
    let head;
    if (data.length < 126) head = Buffer.from([0x81, data.length]);
    else if (data.length < 65536) {
      head = Buffer.alloc(4);
      head[0] = 0x81; head[1] = 126; head.writeUInt16BE(data.length, 2);
    } else {
      head = Buffer.alloc(10);
      head[0] = 0x81; head[1] = 127; head.writeBigUInt64BE(BigInt(data.length), 2);
    }
    this.socket.write(Buffer.concat([head, data]));
  }

  close() {
    if (!this.open) return;
    try { this.socket.end(Buffer.from([0x88, 0])); } catch { /* already gone */ }
    this.closed();
  }

  closed() {
    if (!this.open) return;
    this.open = false;
    for (const fn of this.handlers.close) fn();
  }

  read(chunk) {
    this.buf = Buffer.concat([this.buf, chunk]);
    while (this.buf.length >= 2) {
      const op = this.buf[0] & 0x0f;
      const masked = this.buf[1] & 0x80;
      let len = this.buf[1] & 0x7f, at = 2;
      if (len === 126) {
        if (this.buf.length < 4) return;
        len = this.buf.readUInt16BE(2); at = 4;
      } else if (len === 127) {
        if (this.buf.length < 10) return;
        len = Number(this.buf.readBigUInt64BE(2)); at = 10;
      }
      if (len > MAX_PAYLOAD) return this.close();
      const need = at + (masked ? 4 : 0) + len;
      if (this.buf.length < need) return;
      const mask = masked ? this.buf.subarray(at, at + 4) : null;
      const payload = Buffer.from(this.buf.subarray(at + (masked ? 4 : 0), need));
      if (mask) for (let i = 0; i < payload.length; i++) payload[i] ^= mask[i & 3];
      this.buf = this.buf.subarray(need);
      if (op === 0x1) for (const fn of this.handlers.message) fn(payload.toString('utf8'));
      else if (op === 0x8) return this.close();
      else if (op === 0x9) this.socket.write(Buffer.concat([Buffer.from([0x8a, payload.length]), payload])); // pong
    }
  }
}
