// Static file server plus the race-room WebSocket at /ws: node server.js [port]
import { createServer } from 'node:http';
import { acceptWebSocket } from './server/ws.js';
import { handlePeer, handleLobbyPeer } from './server/rooms.js';
import { readFile } from 'node:fs/promises';
import { extname, join, normalize } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = fileURLToPath(new URL('.', import.meta.url));
const port = Number(process.env.PORT || process.argv[2] || 5173);
const types = {
  '.html': 'text/html; charset=utf-8',
  '.js': 'text/javascript; charset=utf-8',
  '.css': 'text/css; charset=utf-8',
  '.json': 'application/json',
  '.woff2': 'font/woff2',
  '.woff': 'font/woff',
  '.glb': 'model/gltf-binary',
  '.png': 'image/png',
  '.wav': 'audio/wav',
};

const server = createServer(async (req, res) => {
  const path = decodeURIComponent(new URL(req.url, 'http://x').pathname);
  const file = normalize(join(root, path === '/' ? 'index.html' : path));
  // Only game files: no server code, dotfiles, Blender sources or anything without a known type.
  if (!file.startsWith(root) || /(^|[\\/])\.|^[\\/]?server([\\/]|\.js$)/.test(file.slice(root.length)) || !types[extname(file)]) {
    res.writeHead(404).end('Not found');
    return;
  }
  try {
    const body = await readFile(file);
    res.writeHead(200, { 'Content-Type': types[extname(file)], 'Cache-Control': 'no-store' });
    res.end(body);
  } catch {
    res.writeHead(404).end('Not found');
  }
});
server.on('upgrade', (req, socket) => {
  const url = new URL(req.url, 'http://x');
  if (url.pathname === '/ws') acceptWebSocket(req, socket, (peer) => handlePeer(peer, (url.searchParams.get('room') || '').toUpperCase()));
  else if (url.pathname === '/lobby') acceptWebSocket(req, socket, handleLobbyPeer);
  else socket.destroy();
});
server.listen(port, () => console.log(`Mission T → http://localhost:${port}`));
