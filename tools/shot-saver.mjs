// Tiny local receiver for course renders: tools/track-preview.js POSTs a PNG data URL here and it
// is written to renders/tracks/<name>.png. Only for local use while making renders.
//   node tools/shot-saver.mjs [port]
import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';

const port = +(process.argv[2] || 5181);
await mkdir('renders/tracks', { recursive: true });
createServer(async (req, res) => {
  res.setHeader('Access-Control-Allow-Origin', '*');
  res.setHeader('Access-Control-Allow-Methods', 'POST, OPTIONS');
  if (req.method === 'OPTIONS') return res.end();
  const url = new URL(req.url, `http://localhost:${port}`);
  const name = url.searchParams.get('name') || '';
  if (req.method !== 'POST' || url.pathname !== '/save' || !/^[a-z0-9-]{1,40}$/.test(name)) {
    res.statusCode = req.method === 'GET' ? 200 : 400;
    return res.end(req.method === 'GET' ? 'shot saver ready' : 'bad request');
  }
  let body = '';
  for await (const chunk of req) body += chunk;
  const m = body.match(/^data:image\/png;base64,(.+)$/);
  if (!m) { res.statusCode = 400; return res.end('not a png'); }
  await writeFile(`renders/tracks/${name}.png`, Buffer.from(m[1], 'base64'));
  console.log('saved', name);
  res.end('ok');
}).listen(port, () => console.log(`shot saver on ${port}`));
