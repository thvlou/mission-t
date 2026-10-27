// Deterministic reference driver used by the offline lap check and the track lab.
// It sends the same throttle/steer/Space/E inputs as a player, with no pose or speed overrides.
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const wrap=a=>Math.atan2(Math.sin(a),Math.cos(a));
export function courseInput(car, { shortcut = false } = {}) {
 const c=car.road,s=car.s,local=c.localS(s),speed=car.speed;
 const intended=shortcut?c.routes.find(r=>local>=r.from-30&&local<r.to-3):null;
 const routeId=car.route||intended?.id||null;
 const route=c.routeAt(routeId),ratio=route?(route.to-route.from)/route.path.length:1;
 const look=clamp(10+speed*.48,14,45),f=c.drivingFrame(s+look*ratio,routeId);
 if(!shortcut&&!car.route){
  const fork=c.routes.find(r=>local>r.from-35&&local<r.from+100);
  if(fork){const m=c.frame(fork.from+70),q=c.drivingFrame(fork.from+70,fork.id),side=Math.sign((q.x-m.x)*m.rx+(q.z-m.z)*m.rz)||1;
   f.x-=f.rx*side*2.7;f.z-=f.rz*side*2.7;}
 }
 const desired=Math.atan2(-(f.z-car.pos.z),f.x-car.pos.x),error=wrap(desired-car.yaw);
 const distance=Math.max(4,Math.hypot(f.x-car.pos.x,f.z-car.pos.z));
 const spin=clamp(Math.atan(2*2.76*Math.sin(error)/distance)/.72,-1,1);
 let target=63,maxCurve=0;
 for(let d=12;d<=150;d+=12){
  const a=c.drivingFrame(s+d*ratio-5,routeId),b=c.drivingFrame(s+d*ratio+5,routeId);
  const k=Math.abs(wrap(b.h-a.h))/10;maxCurve=Math.max(maxCurve,k);
  const corner=Math.sqrt(9/Math.max(k,.0001));
  target=Math.min(target,Math.sqrt(corner*corner+2*9*Math.max(0,d-18)));
 }
 target=Math.min(target,Math.max(18,63-Math.abs(error)*65));
 const u=route?c.routeDistance(s,route):local,gaps=route?.gaps||c.data.gaps||[];
 const approaching=gaps.find(g=>u>g.from-19&&u<g.to+12);
 const lift=!!approaching||car.airborne;
 const boost=!lift&&maxCurve<.0035&&speed>18&&speed<target-3&&car.fuel>40;
 return {throttle:speed>target+1?-1:1,spin,lift,boost,ebrake:false};
}
