import * as THREE from 'three';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { exportTrackGLB } from './highway/track-export.js';
import { HighwayMode } from './highway/index.js';
import { loadCircuit } from './highway/circuit.js';
import { courseInput } from './highway/course-driver.js';
import { buildRover } from './rover.js';
import { loadCarModel } from './car-model.js';
import { createInput } from './input.js';

const $=id=>document.getElementById(id),query=new URLSearchParams(location.search);
const renderer=new THREE.WebGLRenderer({antialias:true,preserveDrawingBuffer:true});renderer.setPixelRatio(Math.min(devicePixelRatio,1.5));renderer.setSize(innerWidth,innerHeight);renderer.shadowMap.enabled=true;renderer.shadowMap.type=THREE.PCFSoftShadowMap;renderer.toneMapping=THREE.ACESFilmicToneMapping;renderer.toneMappingExposure=.95;document.body.prepend(renderer.domElement);
const scene=new THREE.Scene();scene.background=new THREE.Color('#f4f3f0');scene.add(new THREE.HemisphereLight('#ffffff','#b5b6a9',1.3));
const pmrem=new THREE.PMREMGenerator(renderer);scene.environment=pmrem.fromScene(new RoomEnvironment(),.04).texture;
const sun=new THREE.DirectionalLight('#fffaf0',2.5);sun.position.set(200,450,220);sun.castShadow=true;sun.shadow.mapSize.set(2048,2048);sun.shadow.camera.left=sun.shadow.camera.bottom=-650;sun.shadow.camera.right=sun.shadow.camera.top=650;sun.shadow.camera.far=1500;sun.shadow.normalBias=.15;scene.add(sun);
const camera=new THREE.PerspectiveCamera(43,innerWidth/innerHeight,.1,5000),mapCamera=new THREE.OrthographicCamera(-600,600,400,-400,.1,4000);
const world=new HighwayMode(scene);world.setActive(true);
const rover=buildRover();scene.add(rover.root);loadCarModel(rover,'vertigo-r').catch(e=>{$('error').textContent='차량 미리보기: '+e.message;});
const input=createInput(cmd=>{if(cmd==='restart')reset();if(cmd==='pause'){$('pause').click();}if(cmd==='camera')$('view').click();});
let data,token=0,overview=query.get('view')!=='chase',auto=query.get('auto')==='1',shortcut=query.get('shortcut')==='1',paused=false,finished=false,lastLap=0,lastUi=0;
$('auto').setAttribute('aria-pressed',String(auto));$('shortcut').setAttribute('aria-pressed',String(shortcut));
async function select(id){
 const mine=++token;$('status').textContent='실제 주행 지형을 생성 중…';
 try{
  const loaded=await loadCircuit(id);if(mine!==token)return;data=loaded;world.reset({track:data,traffic:false,s:0,d:0});
  $('name').textContent=data.name;$('description').textContent=data.description;$('spec').textContent=`${(world.road.length/1000).toFixed(2)} km · 도로 12m / 3열 · 목표 약 1분/랩`;
  $('track').value=id;history.replaceState(null,'',`?track=${id}&view=${overview?'overview':'chase'}`);
  finished=false;lastLap=0;$('error').textContent='';$('status').textContent='준비 완료 · 멀티플레이에서는 Race 방의 Course에서 선택';
  const c=world.road,cx=(Math.min(...c.x)+Math.max(...c.x))/2,cz=(Math.min(...c.z)+Math.max(...c.z))/2;
  mapCamera.position.set(cx+260,1100,cz+600);mapCamera.lookAt(cx,0,cz);fitMap();drawMap();
 }catch(e){$('error').textContent=e.stack;console.error(e);}
}
function fitMap(){const c=world.road;if(!c.closed)return;const span=Math.max(Math.max(...c.x)-Math.min(...c.x),Math.max(...c.z)-Math.min(...c.z))+210,aspect=innerWidth/innerHeight;mapCamera.left=-span*aspect/2;mapCamera.right=span*aspect/2;mapCamera.top=span/2;mapCamera.bottom=-span/2;mapCamera.updateProjectionMatrix();}
function reset(s=0){world.car.reset(s,0);world.camReady=false;finished=false;lastLap=world.car.time;$('status').textContent='차량을 안전한 접근 구간으로 이동했습니다.';}
function drawMap(){
 const c=world.road,ctx=$('mapCanvas').getContext('2d'),W=400,H=380,pad=35;
 const minX=Math.min(...c.x),maxX=Math.max(...c.x),minZ=Math.min(...c.z),maxZ=Math.max(...c.z),k=Math.min((W-pad*2)/(maxX-minX),(H-pad*2)/(maxZ-minZ));
 const map=(x,z)=>[W/2+(x-(minX+maxX)/2)*k,H/2+(z-(minZ+maxZ)/2)*k];
 ctx.clearRect(0,0,W,H);ctx.lineCap='round';ctx.lineJoin='round';ctx.beginPath();c.x.forEach((x,i)=>{const p=map(x,c.z[i]);i?ctx.lineTo(...p):ctx.moveTo(...p);});ctx.closePath();ctx.strokeStyle='#7b8682';ctx.lineWidth=7;ctx.stroke();
 for(const r of c.routes){ctx.beginPath();r.path.x.forEach((x,i)=>{const p=map(x,r.path.z[i]);i?ctx.lineTo(...p):ctx.moveTo(...p);});ctx.strokeStyle=c.data.palette.accent;ctx.setLineDash([8,5]);ctx.lineWidth=5;ctx.stroke();ctx.setLineDash([]);}
 const p=map(world.car.pos.x,world.car.pos.z);ctx.beginPath();ctx.arc(...p,7,0,Math.PI*2);ctx.fillStyle='#d23437';ctx.fill();
 const start=map(c.x[0],c.z[0]);ctx.fillStyle='#20282b';ctx.fillRect(start[0]-5,start[1]-5,10,10);
}
function save(blob,name){const a=document.createElement('a');a.href=URL.createObjectURL(blob);a.download=name;a.click();setTimeout(()=>URL.revokeObjectURL(a.href),1000);}
async function deliver(blob,type,id=data.id,view=overview){
 if(query.get('delivery')!=='1'){save(blob,`${id}-${type==='glb'?'visual':view?'overview':'drive'}.${type}`);return;}
 const res=await fetch(`http://127.0.0.1:5182/?track=${id}&type=${type}&view=${view?'overview':'drive'}`,{method:'POST',body:blob});
 if(!res.ok)throw Error('Local export '+res.status);
 $('status').textContent='저장 완료 · '+await res.text();
}
$('track').addEventListener('change',()=>select($('track').value));$('auto').onclick=()=>{auto=!auto;$('auto').setAttribute('aria-pressed',String(auto));};$('shortcut').onclick=()=>{shortcut=!shortcut;$('shortcut').setAttribute('aria-pressed',String(shortcut));};
$('pause').onclick=()=>{paused=!paused;$('pause').setAttribute('aria-pressed',String(paused));};
$('view').onclick=()=>{overview=!overview;$('view').textContent=overview?'추적 시점':'전체 시점';};
$('restart').onclick=()=>reset();$('jump').onclick=()=>{reset(data.gaps[0].from-75);overview=false;$('view').textContent='전체 시점';};$('fork').onclick=()=>{reset(data.shortcuts[0].from-65);overview=false;$('view').textContent='전체 시점';};
$('png').onclick=()=>{const id=data.id,view=overview;renderer.domElement.toBlob(blob=>deliver(blob,'png',id,view).catch(e=>$('error').textContent=e.message));};
$('glb').onclick=async()=>{
 const id=data.id;
 $('status').textContent='표시용 GLB를 내보내는 중…';
 try{
  const glb=await exportTrackGLB(world.scenery.group);await deliver(new Blob([glb],{type:'model/gltf-binary'}),'glb',id);
  $('status').textContent='표시용 GLB 저장 완료 · 주행/점프 판정은 JSON 파일을 사용합니다.';
 }catch(e){$('error').textContent=e.message;}
};
addEventListener('resize',()=>{renderer.setSize(innerWidth,innerHeight);camera.aspect=innerWidth/innerHeight;camera.updateProjectionMatrix();fitMap();});
const clock=new THREE.Clock();let elapsed=0;
renderer.setAnimationLoop(()=>{
 const dt=Math.min(clock.getDelta(),.05);elapsed+=dt;if(!data)return;
 const c=world.car,manual=input.read(),inp=auto?courseInput(c,{shortcut}):{...manual,ebrake:manual.shift};
 if(!paused&&!finished)world.update(dt,inp);world.poseRover(rover,elapsed);world.updateCamera(camera,dt,'chase',43);
 if(c.s>=world.road.length&&!finished){finished=true;const time=c.time-lastLap;$('status').textContent=`1 LAP COMPLETE · ${time.toFixed(2)}초 · ${shortcut?'지름길 사용':'기본 루트'} · 출발점 버튼으로 다시 주행`;}
 if(elapsed-lastUi>.15){lastUi=elapsed;drawMap();$('telemetry').textContent=`${Math.round(c.speed*3.6)} km/h · ${c.time.toFixed(1)} s · ${Math.round(world.road.localS(c.s))} / ${Math.round(world.road.length)} m · FUEL ${Math.round(c.fuel)}`;
 const zone=data.zones.find(z=>world.road.localS(c.s)>=z.from&&world.road.localS(c.s)<z.to);$('feature').textContent=c.route?'SHORTCUT · '+world.road.routeAt(c.route).name:zone?`${zone.label} · ${zone.hint}`:'';}
 c.events.length=0;renderer.render(scene,overview?mapCamera:camera);
});
await select(query.get('track')||'harbor-run');
