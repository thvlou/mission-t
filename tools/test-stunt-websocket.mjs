// Real WebSocket clients against the same local server used by the browser.
import assert from 'node:assert/strict';
const base=process.argv[2]||'ws://127.0.0.1:5174';
const room='T'+Math.random().toString(36).slice(2,5).toUpperCase();
function client(nick){
 const ws=new WebSocket(`${base}/ws?room=${room}`),messages=[],waiting=[];
 ws.addEventListener('message',e=>{const m=JSON.parse(e.data);messages.push(m);for(const w of [...waiting])if(w.match(m)){waiting.splice(waiting.indexOf(w),1);clearTimeout(w.timer);w.resolve(m);}});
 const next=match=>new Promise((resolve,reject)=>{const w={match,resolve};w.timer=setTimeout(()=>{waiting.splice(waiting.indexOf(w),1);reject(Error('WebSocket message timeout: '+nick));},6000);waiting.push(w);});
 const open=new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true});});
 return {ws,next,open,messages,send:m=>ws.send(JSON.stringify(m)),nick};
}
const a=client('Track Host'),b=client('Track Guest');
try{
 await Promise.all([a.open,b.open]);
 const aw=a.next(m=>m.t==='welcome');a.send({t:'join',nick:a.nick,car:'vertigo-gt'});const host=await aw;
 const bw=b.next(m=>m.t==='welcome');b.send({t:'join',nick:b.nick,car:'vertigo-r'});const guest=await bw;
 for(const id of ['harbor-run','canyon-flight','alpine-ring']){
  const changed=b.next(m=>m.t==='players'&&m.course===id);a.send({t:'course',course:id});await changed;
  const route=id+'-cut',state=b.next(m=>m.t==='state'&&m.id===host.id&&m.route===route);
  a.send({t:'state',s:800,d:1.2,y:8,v:55,route,steer:.2});const got=await state;assert.equal(got.y,8);assert.equal(got.d,1.2);
  console.log('PASS WS course + shortcut relay',id);
 }
 const ready=a.next(m=>m.t==='players'&&m.players.some(p=>p.id===guest.id&&p.ready));b.send({t:'ready',ready:true});await ready;
 const countdown=b.next(m=>m.t==='countdown'&&m.course==='alpine-ring');a.send({t:'start'});const go=await countdown;assert.equal(go.grid.length,2);console.log('PASS two-player ready/countdown on Alpine Ring');
}finally{a.ws.close();b.ws.close();}
