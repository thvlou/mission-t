// Ephemeral loopback-only receiver for the three authored track exports, never deployed.
import { createServer } from 'node:http';
import { mkdir, writeFile } from 'node:fs/promises';
const ids=['harbor-run','canyon-flight','alpine-ring'];
createServer(async(req,res)=>{
 const origin=req.headers.origin;
 if(origin&&!/^http:\/\/(localhost|127\.0\.0\.1):5174$/.test(origin)){res.writeHead(403).end();return;}
 res.setHeader('Access-Control-Allow-Origin',origin||'http://localhost:5174');
 res.setHeader('Access-Control-Allow-Methods','POST, OPTIONS');res.setHeader('Access-Control-Allow-Headers','Content-Type');
 if(req.method==='OPTIONS'){res.end();return;}
 const url=new URL(req.url,'http://127.0.0.1:5182'),id=url.searchParams.get('track'),type=url.searchParams.get('type'),view=url.searchParams.get('view');
 if(req.method!=='POST'||!ids.includes(id)||!['glb','png'].includes(type)||!['overview','drive'].includes(view)){res.writeHead(400).end('Invalid export');return;}
 const chunks=[];let size=0;
 for await(const chunk of req){size+=chunk.length;if(size>64*1024*1024){res.writeHead(413).end();req.destroy();return;}chunks.push(chunk);}
 const body=Buffer.concat(chunks);if(type==='glb'&&body.toString('ascii',0,4)!=='glTF'){res.writeHead(400).end('Invalid GLB');return;}
 if(type==='png'&&body.readUInt32BE(0)!==0x89504e47){res.writeHead(400).end('Invalid PNG');return;}
 const folder=type==='glb'?'assets/tracks/visual':'renders/tracks';await mkdir(folder,{recursive:true});
 const path=type==='glb'?`${folder}/${id}-visual.glb`:`${folder}/${id}-${view}.png`;
 await writeFile(path,body);console.log('Saved',path,body.length);res.end(path);
}).listen(5182,'127.0.0.1',()=>console.log('Loopback track export receiver: 5182'));
