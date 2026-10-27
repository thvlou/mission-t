import assert from 'node:assert/strict';
import { readFile, writeFile, mkdir } from 'node:fs/promises';
import { Circuit } from '../src/highway/circuit-path.js';
import { HighwayCar } from '../src/highway/car.js';
import { courseInput } from '../src/highway/course-driver.js';
import { Room } from '../server/room-core.js';
import { COURSES } from '../src/race/courses.js';

const ids=['harbor-run','canyon-flight','alpine-ring'], report=[];
function crossing(a,b,c,d){
 const ex=b[0]-a[0],ez=b[2]-a[2],fx=d[0]-c[0],fz=d[2]-c[2],den=ex*fz-ez*fx;
 if(Math.abs(den)<1e-8)return null;
 const dx=c[0]-a[0],dz=c[2]-a[2],t=(dx*fz-dz*fx)/den,u=(dx*ez-dz*ex)/den;
 return t>0&&t<1&&u>0&&u<1?[t,u]:null;
}
for(const id of ids){
 const data=JSON.parse(await readFile(new URL(`../assets/tracks/${id}.json`,import.meta.url)));
 const c=new Circuit(data);
 assert(c.length>1800&&c.length<2300,id+' lap distance');
 assert(data.points.every(p=>p.every(Number.isFinite)&&p[3]+p[4]>=12),id+' three 4m lanes');
 assert.equal(c.routes.length,1);
 const start=c.frame(0),end=c.frame(c.length);
 assert(Math.hypot(start.x-end.x,start.z-end.z,start.y-end.y)<.001,'closed seam');
 for(const g of data.gaps){assert(!c.surfaceAt((g.from+g.to)/2).exists,'real main gap');assert(c.surfaceAt(g.from-4).exists,'takeoff surface');assert(c.surfaceAt(g.to+4).exists,'landing surface');}
 for(const r of c.routes){
  assert(r.path.wr.every((w,i)=>w+r.path.wl[i]>=12),'shortcut is also three cars wide');
  for(let u=12;u<r.path.length-12;u+=12){
   const s=r.from+u/r.path.length*(r.to-r.from),f=c.drivingFrame(s,r.id),p=c.project(f.x,f.z,s,r.id);
   assert.equal(p.route,r.id,'route identity stays stable');assert(Math.abs(p.s-s)<1,'canonical progress round trip');
  }
  const gap=r.gaps[0],s=r.from+(gap.from+gap.to)/2/r.path.length*(r.to-r.from);
  assert(!c.surfaceAt(s,0,r.id).exists,'real shortcut gap');
  assert(r.to-r.from>r.path.length+25,'shortcut actually shortens the road');
  for(let i=0;i<r.points.length-1;i++)for(let j=0;j<data.points.length;j++){
   const h=crossing(r.points[i],r.points[i+1],data.points[j],data.points[(j+1)%data.points.length]);
   if(!h||Math.abs(c.cum[j]-r.from)<45||Math.abs(c.cum[j]-r.to)<45)continue;
   const deck=r.points[i][1]+h[0]*(r.points[i+1][1]-r.points[i][1]);
   const road=data.points[j][1]+h[1]*(data.points[(j+1)%data.points.length][1]-data.points[j][1]);
   assert(deck-road>4.5,id+' bridge clears the main road by >4.5m');
  }
 }
 // A missed hop really falls and returns to a safe approach, preserving the running clock.
 const failed=new HighwayCar(c),g=data.gaps[0];failed.reset((g.from+g.to)/2,0);failed.fuel=0;failed.started=true;
 let recovered=false;
 for(let k=0;k<480;k++){failed.step(1/120,{throttle:0,spin:0,lift:false,boost:false,ebrake:false},null);if(failed.events.some(e=>e.type==='recover')){recovered=true;break;}}
 assert(recovered,id+' missed jump recovers');assert(failed.s<g.from-30,id+' respawn before ramp');assert(failed.time>1,id+' race clock is not reset');
 const laps=[];
 for(const shortcut of [false,true]){
  const car=new HighwayCar(c);car.reset(0,0);let time=0,jumps=0,recoveries=0,branchSteps=0,offroad=0,maxAir=0;
  const trace=[];
  while(time<150&&car.s<c.length){
   const input=courseInput(car,{shortcut});car.step(1/120,input,null);time+=1/120;
   for(const e of car.events){if(e.type==='hop')jumps++;if(e.type==='recover')recoveries++;}car.events.length=0;
   if(car.route)branchSteps++;if(car.offroad)offroad++;maxAir=Math.max(maxAir,car.height);
   if(Math.round(time*120)%60===0)trace.push({t:+time.toFixed(2),s:+car.s.toFixed(1),d:+car.d.toFixed(2),v:+car.speed.toFixed(1),route:car.route,y:+car.height.toFixed(2)});
  }
  const lap={shortcut,seconds:+time.toFixed(2),finished:car.s>=c.length,jumps,recoveries,branchSeconds:+(branchSteps/120).toFixed(2),offroadSeconds:+(offroad/120).toFixed(2),maxAir:+maxAir.toFixed(2)};
  laps.push(lap);
  await mkdir(new URL('../renders/tracks/',import.meta.url),{recursive:true});
  await writeFile(new URL(`../renders/tracks/${id}-${shortcut?'cut':'main'}-trace.json`,import.meta.url),JSON.stringify(trace));
  console.log(id,lap);
 }
 report.push({id,length:+c.length.toFixed(2),minimumWidth:Math.min(...c.wr.map((w,i)=>w+c.wl[i])),laps,missedJumpRecovery:'passed',bridgeClearance:'>4.5m',twoLapContinuity:'passed'});
 // Crossing the finish seam and a second lap keep unwrapped race progress increasing.
 const two=new HighwayCar(c);two.reset(0,0);let elapsed=0;
 while(elapsed<180&&two.s<2*c.length){two.step(1/120,courseInput(two),null);elapsed+=1/120;two.events.length=0;}
 assert(two.s>=2*c.length,id+' two-lap continuity');
}
// Both clients receive the chosen course and route state from the same Room code as production.
const room=new Room('TEST'),messages=[[],[]],peers=messages.map(log=>({send:text=>log.push(JSON.parse(text))}));
const a=room.join(peers[0]),b=room.join(peers[1]);
for(const id of ids){room.message(a,{t:'course',course:id});assert.equal(room.course,id);assert(messages[1].at(-1).course===id);}
room.message(b,{t:'course',course:'harbor-run'});assert.equal(room.course,'alpine-ring','only host changes course');
room.message(a,{t:'state',route:'alpine-ring-cut',s:800,d:1,y:8});assert.equal(messages[1].at(-1).route,'alpine-ring-cut');
assert(ids.every(id=>COURSES[id].track===id));
await writeFile(new URL('../assets/tracks/stunt-validation.json',import.meta.url),JSON.stringify({driver:'real HighwayCar physics, dt=1/120; standing start; pure pursuit, no forced vehicle poses',tracks:report,roomRelay:'passed'},null,2));
if(!process.argv.includes('--report-only'))for(const r of report)for(const lap of r.laps){assert(lap.finished,r.id+' completion');assert(lap.recoveries===0,r.id+' clean jump/landing');assert(lap.seconds>=45&&lap.seconds<=80,r.id+' approximately one minute');if(lap.shortcut)assert(lap.branchSeconds>1,r.id+' used optional route');else assert(lap.branchSeconds===0,r.id+' base lap stays on the main road');}
