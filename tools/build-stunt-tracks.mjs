// Original, deterministic stunt circuits. No external data or 3D downloads required.
import { mkdir, writeFile } from 'node:fs/promises';
import { Circuit } from '../src/highway/circuit-path.js';

const OUT = new URL('../assets/tracks/', import.meta.url);
await mkdir(OUT, { recursive: true });
const specs = [
  { id: 'harbor-run', name: 'Harbor Run', length: 2050, theme: 'harbor', seed: 711,
    color: '#168e9d', description: '항만의 넓은 드리프트 코너와 컨테이너 부두 점프 지름길',
    keys: [[0,0],[230,0],[340,35],[390,145],[350,245],[190,265],[140,380],[-70,405],[-205,315],[-205,160],[-110,130],[-110,20]],
    branch: [.37,.56], branchName: 'Dock Hop', gap: 22, rise: 2.5, mainGap: 14, mainNear: .12,
    palette: { ground: '#e6e3dc', canopy: '#b8d1bf', asphalt: '#929b9b', gravel: '#c6d2ce', accent: '#168e9d', water: '#8fc9cc' } },
  { id: 'canyon-flight', name: 'Canyon Flight', length: 2150, theme: 'canyon', seed: 933,
    color: '#c86e43', description: '붉은 협곡의 부스터 직선과 길게 활강하는 고가 지름길',
    keys: [[0,0],[270,0],[400,100],[420,260],[280,330],[160,250],[100,345],[-100,430],[-270,310],[-220,120],[-110,120],[-80,0]],
    branch: [.34,.55], branchName: 'Glide Cut', gap: 58, rise: 3.5, mainGap: 24, mainNear: .70,
    palette: { ground: '#d8b69b', canopy: '#b2b79a', asphalt: '#9c9188', gravel: '#c5a187', concrete: '#e3c9b3', accent: '#c86e43', water: '#c0aa93' } },
  { id: 'alpine-ring', name: 'Alpine Ring', length: 2000, theme: 'alpine', seed: 1157,
    color: '#48856c', description: '침엽수 숲의 연속 S 드리프트와 능선 점프 지름길',
    keys: [[0,0],[230,0],[330,70],[330,200],[210,260],[265,370],[100,450],[-140,400],[-260,270],[-220,140],[-90,180],[-100,30]],
    branch: [.27,.48], branchName: 'Ridge Leap', gap: 30, rise: 3, mainGap: 16, mainNear: .78,
    palette: { ground: '#dce2d6', canopy: '#6f9985', asphalt: '#959c99', gravel: '#c8cfc3', accent: '#48856c', water: '#a6c6c4' } },
];
const dist = (a,b) => Math.hypot(a[0]-b[0], a[2]-b[2]);
const smooth = t => { t=Math.max(0,Math.min(1,t));return t*t*(3-2*t); };
function spline(keys) {
 const dense=[], n=keys.length;
 for(let i=0;i<n;i++)for(let j=0;j<100;j++){
  const t=j/100,p0=keys[(i-1+n)%n],p1=keys[i],p2=keys[(i+1)%n],p3=keys[(i+2)%n];
  const v=[0,0,0];for(const [k,dim] of [[0,0],[2,1]])v[k]=.5*((2*p1[dim])+(-p0[dim]+p2[dim])*t+(2*p0[dim]-5*p1[dim]+4*p2[dim]-p3[dim])*t*t+(-p0[dim]+3*p1[dim]-3*p2[dim]+p3[dim])*t*t*t);
  dense.push(v);
 }
 return dense;
}
function resample(input, step=3, closed=true) {
 const points=closed?[...input,input[0]]:input,cum=[0];
 for(let i=1;i<points.length;i++)cum.push(cum.at(-1)+dist(points[i],points[i-1]));
 const length=cum.at(-1),out=[];let k=0;
 for(let s=0;s<(closed?length:length+step*.5);s+=step){
  const u=Math.min(s,length);while(k<points.length-2&&cum[k+1]<u)k++;
  const t=(u-cum[k])/(cum[k+1]-cum[k]);out.push([points[k][0]+(points[k+1][0]-points[k][0])*t,points[k][1]+(points[k+1][1]-points[k][1])*t,points[k][2]+(points[k+1][2]-points[k][2])*t,6,6]);
 }
 if(!closed && dist(out.at(-1),input.at(-1))>.01)out.push([...input.at(-1),6,6]);
 return out;
}
function ramp(y,u,gap,rise) {
 const {from,to}=gap;
 return y+rise*smooth((u-(from-36))/36)*(1-smooth((u-from)/(to-from)));
}
function splitBoundaries(points, positions, closed) {
 const edges = closed ? [...points,points[0]] : points;
 let u=0;const out=[];
 for(let i=0;i<edges.length-1;i++){
  const a=edges[i],b=edges[i+1],len=dist(a,b);out.push(a);
  for(const s of positions.filter(s=>s>u+.001&&s<u+len-.001).sort((a,b)=>a-b)){
   const t=(s-u)/len;out.push(a.map((v,k)=>v+(b[k]-v)*t));
  }
  u+=len;
 }
 if(!closed)out.push(points.at(-1));
 points.splice(0,points.length,...out);
}
const manifest=[];
for(const spec of specs){
 const dense=spline(spec.keys),rawLength=dense.reduce((L,p,i)=>L+dist(p,dense[(i+1)%dense.length]),0),scale=spec.length/rawLength;
 const pts=resample(dense.map(p=>[p[0]*scale,0,p[2]*scale]));
 const data={version:2,id:spec.id,name:spec.name,closed:true,step:3,theme:spec.theme,seed:spec.seed,palette:spec.palette,description:spec.description,
  targetLapSeconds:60,roadWidth:12,lanes:3,laps:2,points:pts,gaps:[],shortcuts:[],zones:[],sources:{author:'Mission T original procedural design',generator:'tools/build-stunt-tracks.mjs'}};
 let path=new Circuit(data),L=path.length;
 // Gentle hills with no grade discontinuity at the start/finish.
 pts.forEach((p,i)=>{const u=path.cum[i]/L;p[1]=spec.theme==='canyon'?10+7*Math.sin(2*Math.PI*u)+3*Math.sin(4*Math.PI*u):spec.theme==='alpine'?8+5*Math.sin(2*Math.PI*u)+2*Math.sin(6*Math.PI*u):4+1.4*Math.sin(4*Math.PI*u);});
 // Put the mandatory jump on a locally straight, well separated part of the course.
 const candidates=pts.map((p,i)=>({s:path.cum[i],k:Math.abs(path.curvature(path.cum[i]))})).filter(p=>p.s>110&&p.s<L-100&&Math.abs(p.s-spec.mainNear*L)<L*.13);
 const takeoff=candidates.sort((a,b)=>(a.k*500+Math.abs(a.s-spec.mainNear*L)/L)-(b.k*500+Math.abs(b.s-spec.mainNear*L)/L))[0].s;
 data.gaps=[{id:'main-jump',from:takeoff,to:takeoff+spec.mainGap,label:'JUMP',required:true}];
 pts.forEach((p,i)=>{p[1]=ramp(p[1],path.cum[i],data.gaps[0],spec.rise);});
 path=new Circuit(data);L=path.length;
 const from=spec.branch[0]*L,to=spec.branch[1]*L,a=path.frame(from),b=path.frame(to),span=to-from;
 const chord=Math.hypot(b.x-a.x,b.z-a.z),handle=Math.min(85,chord*.3);
 const controls=[[a.x+path.offset.x,a.y,a.z+path.offset.z],[a.x+a.fx*handle+path.offset.x,a.y,a.z+a.fz*handle+path.offset.z],[b.x-b.fx*handle+path.offset.x,b.y,b.z-b.fz*handle+path.offset.z],[b.x+path.offset.x,b.y,b.z+path.offset.z]];
 const bd=[];
 for(let i=0;i<=300;i++){
  const t=i/300,w=[(1-t)**3,3*(1-t)**2*t,3*(1-t)*t*t,t**3];
  bd.push([0,1,2].map(k=>controls.reduce((sum,p,j)=>sum+p[k]*w[j],0)));
 }
 const branch=resample(bd,3,false),branchL=branch.reduce((sum,p,i)=>sum+(i?dist(p,branch[i-1]):0),0);
 const gap={from:branchL*.40,to:branchL*.40+spec.gap,id:'shortcut-gap',label:spec.theme==='canyon'?'HOLD SPACE · GLIDE':'JUMP CUT'};
 let u=0;branch.forEach((p,i)=>{if(i)u+=dist(p,branch[i-1]);p[1]=ramp(p[1]+9*Math.sin(Math.PI*u/branchL)**2,u,gap,spec.rise+1);});
 data.shortcuts=[{id:spec.id+'-cut',name:spec.branchName,from,to,width:12,points:branch,gaps:[gap],savingMeters:Math.round(span-branchL),hint:spec.theme==='canyon'?'E approach · hold SPACE across canyon':'SPACE at ramp · merge after landing'}];
 data.zones=[
  {type:'boost',from:25,to:Math.min(190,takeoff-50),label:'BOOST STRAIGHT',hint:'E · boost'},
  {type:'jump',from:takeoff-70,to:takeoff+spec.mainGap+40,label:'GAP JUMP',hint:'SPACE · jump / hold to glide'},
  {type:'shortcut',from:from-60,to:from+20,label:spec.branchName.toUpperCase(),hint:data.shortcuts[0].hint},
  ...[.23,.62,.88].map(t=>{
   const peak=path.cum.slice(0,-1).filter(s=>Math.abs(s-t*L)<L*.065).sort((a,b)=>Math.abs(path.curvature(b))-Math.abs(path.curvature(a)))[0];
   return {type:'drift',from:peak-45,to:peak+65,label:'DRIFT ZONE',hint:'SHIFT + steer · release to boost'};
  }),
 ];
 data.length=+L.toFixed(3);data.climb=+(Math.max(...pts.map(p=>p[1]))-Math.min(...pts.map(p=>p[1]))).toFixed(2);
 splitBoundaries(pts,data.gaps.flatMap(g=>[g.from,g.to]),true);
 splitBoundaries(branch,[gap.from,gap.to],false);
 // Quantize only after geometry is authored, then use that same data for all deliverables.
 for(const list of [pts,branch])for(const p of list)for(let k=0;k<p.length;k++)p[k]=+p[k].toFixed(3);
 await writeFile(new URL(`${spec.id}.json`,OUT),JSON.stringify(data));
 manifest.push({id:spec.id,name:spec.name,length:data.length,width:12,lanes:3,targetLapSeconds:60,shortcutSavingMeters:data.shortcuts[0].savingMeters,mainGapMeters:spec.mainGap,shortcutGapMeters:spec.gap});
 console.log(spec.id,`${L.toFixed(0)}m`,`${branchL.toFixed(0)}m shortcut, saves ${(span-branchL).toFixed(0)}m`);
}
await writeFile(new URL('stunt-manifest.json',OUT),JSON.stringify(manifest,null,2));
