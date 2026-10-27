import * as THREE from 'three';

// Every jump deck here is drawn from the exact samples used by Circuit.surfaceAt().
export function buildStuntScenery(c, palette) {
  const group = new THREE.Group(), accent = palette.accent || '#d23437';
  const material = (color, roughness = .8) => new THREE.MeshStandardMaterial({ color, roughness });
  const asphalt = material(palette.asphalt), paint = material(accent), white = material('#fbfaf8');
  asphalt.color.multiplyScalar(.45);
  const concrete = material(palette.concrete || '#e4e1db'), dark = material('#525a5d');
  function box(pos, size, mat, h = 0) {
    const mesh = new THREE.Mesh(new THREE.BoxGeometry(...size), mat);
    mesh.position.set(...pos); mesh.rotation.y = h; mesh.receiveShadow = mesh.castShadow = true; group.add(mesh); return mesh;
  }
  function strip(points, widths, mat, gaps = [], lift = .025) {
    const v = [], uv = [], idx = [], cum = [0];
    for (let i = 1; i < points.length; i++) cum.push(cum[i-1] + Math.hypot(points[i].x-points[i-1].x,points[i].z-points[i-1].z));
    points.forEach((p,i) => widths(p,i).forEach(([d,up],k) => { v.push(p.x+p.rx*d,p.y+up+lift,p.z+p.rz*d);uv.push(k,cum[i]/20); }));
    const cols = widths(points[0],0).length;
    for(let i=0;i<points.length-1;i++) {
      if(gaps.some(g=>(cum[i]+cum[i+1])*.5>=g.from&&(cum[i]+cum[i+1])*.5<g.to))continue;
      for(let k=0;k<cols-1;k++){const a=i*cols+k;idx.push(a,a+1,a+cols,a+1,a+cols+1,a+cols);}
    }
    const geo=new THREE.BufferGeometry();geo.setAttribute('position',new THREE.Float32BufferAttribute(v,3));geo.setAttribute('uv',new THREE.Float32BufferAttribute(uv,2));geo.setIndex(idx);geo.computeVertexNormals();
    const mesh=new THREE.Mesh(geo,mat);mesh.receiveShadow=true;group.add(mesh);return mesh;
  }
  function sign(s, text, routeId = null, side = -1) {
    const p=c.drivingFrame(s,routeId), offset=side*10, x=p.x+p.rx*offset,z=p.z+p.rz*offset;
    box([x,p.y+2.2,z],[.18,4.4,.18],dark);
    const canvas=document.createElement('canvas');canvas.width=1024;canvas.height=256;
    const ctx=canvas.getContext('2d');ctx.fillStyle=accent;ctx.fillRect(0,0,1024,256);ctx.fillStyle='#fffdf8';ctx.font='bold 78px system-ui';ctx.textAlign='center';ctx.textBaseline='middle';ctx.fillText(text,512,128,960);
    const texture=new THREE.CanvasTexture(canvas);texture.colorSpace=THREE.SRGBColorSpace;
    const board=new THREE.Mesh(new THREE.BoxGeometry(.18,1.3,6),[new THREE.MeshStandardMaterial({map:texture}),new THREE.MeshStandardMaterial({map:texture}),dark,dark,dark,dark]);
    board.position.set(x,p.y+4.5,z);board.rotation.y=p.h;group.add(board);
  }
  function bars(s,width=12,routeId=null,count=4) {
    for(let i=0;i<count;i++){
      const p=c.drivingFrame(s-i*3,routeId);
      box([p.x,p.y+.045,p.z],[.6,.025,width],i%2?white:paint,p.h);
    }
  }
  function portal(s,routeId,label) {
    const p=c.drivingFrame(s,routeId);
    for(const side of [-1,1])box([p.x+p.rx*side*7.2,p.y+3.2,p.z+p.rz*side*7.2],[.45,6.4,.45],paint,p.h);
    box([p.x,p.y+6.5,p.z],[.45,.45,14.8],paint,p.h);
    sign(s-30,label,routeId);
  }
  for(const route of c.routes){
    const p=route.path,pts=p.x.map((x,i)=>({x,y:p.y[i],z:p.z[i],rx:Math.sin(p.h[i]),rz:Math.cos(p.h[i])}));
    strip(pts,()=>[[-6,0],[6,0]],asphalt,route.gaps);
    strip(pts,()=>[[-6,-.55],[-6,0]],concrete,route.gaps);
    strip(pts,()=>[[6,0],[6,-.55]],concrete,route.gaps);
    strip(pts,()=>[[6,-.55],[-6,-.55]],concrete,route.gaps);
    for(let u=40;u<p.length-40;u+=36){
      if(route.gaps.some(g=>u>g.from-10&&u<g.to+10))continue;
      const s=route.from+u/p.length*(route.to-route.from),top=c.drivingFrame(s,route.id),base=c.frame(s).y-2;
      // Bridge piers stand clear of the lower carriageway, including its run-off.
      if(c.x.some((x,i)=>i%3===0&&Math.hypot(x-top.x,c.z[i]-top.z)<18))continue;
      const height=Math.max(1,top.y-base-.55);
      box([top.x,top.y-.55-height/2,top.z],[1.5,height,3.5],concrete,top.h);
    }
    // Colour-coded edge stripes. Rail gaps stay open at both fork merges.
    for(const side of [-1,1]){
      strip(pts,()=>[[side*5.7,.015],[side*5.95,.015]],paint,route.gaps);
      const middle=pts.filter((_,i)=>p.cum[i]>35&&p.cum[i]<p.length-35);
      // Rail distance must use the original branch arc length, even after trimming endpoints.
      const startU=p.cum[pts.indexOf(middle[0])];
      strip(middle,()=>[[side*7,-.30],[side*7,.85]],concrete,route.gaps.map(g=>({...g,from:g.from-startU,to:g.to-startU})));
    }
    const g=route.gaps[0], map=u=>route.from+u/p.length*(route.to-route.from);
    portal(map(g.from-9),route.id,route.name.toUpperCase());bars(map(g.from-4),12,route.id);
    portal(map(g.to+25),route.id,'LANDING');bars(map(g.to+18),12,route.id,3);
    const entry=c.frame(route.from+70),fork=c.drivingFrame(route.from+70,route.id);
    const side=Math.sign((fork.x-entry.x)*entry.rx+(fork.z-entry.z)*entry.rz);
    sign(route.from-45,side<0?'← OPTIONAL CUT':'OPTIONAL CUT →');sign(route.to+25,'MERGE');
  }
  for(const gap of c.data.gaps||[]){portal(gap.from-10,null,'SPACE · JUMP');bars(gap.from-4);bars(gap.to+18,12,null,3);}
  for(const z of c.data.zones||[]){
    if(z.type==='boost'){sign(z.from+15,'E · BOOST');bars(z.from+30,7,null,5);}
    if(z.type==='drift')sign(z.from,'SHIFT · DRIFT');
  }
  // Three theme silhouettes, kept away from every drivable route and landing zone.
  const clear = (x,z,radius) => {
    for(const p of [c,...c.routes.map(r=>r.path)])for(let i=0;i<p.n;i+=3)if(Math.hypot(p.x[i]-x,p.z[i]-z)<radius)return false;
    return true;
  };
  let seed=c.data.seed||7;const rand=()=>((seed=(Math.imul(seed,1664525)+1013904223)>>>0)/4294967296);
  const minX=Math.min(...c.x),maxX=Math.max(...c.x),minZ=Math.min(...c.z),maxZ=Math.max(...c.z);
  if(c.data.theme==='harbor'){
    box([(minX+maxX)/2,-19,(minZ+maxZ)/2],[maxX-minX+1500,.2,maxZ-minZ+1500],material(palette.water,.22));
    const colors=['#bd6054','#b4c9c5','#c8b888','#688c98'].map(v=>material(v));
    for(let i=0;i<48;i++){
      const x=minX+rand()*(maxX-minX),z=minZ+rand()*(maxZ-minZ);
      if(!clear(x,z,32))continue;
      box([x,1.3,z],[12,2.6,2.6],colors[i%4]);if(i%3===0)box([x,3.9,z],[12,2.6,2.6],colors[(i+1)%4]);
    }
    for(const t of [.22,.66]){const p=c.frame(c.length*t),x=p.x+p.rx*48,z=p.z+p.rz*48;
      if(clear(x,z,25)){box([x,p.y+13,z],[1.2,26,1.2],paint);box([x+9,p.y+25,z],[27,1.2,1.2],paint);box([x+19,p.y+18,z],[.15,14,.15],dark);}}
  }else if(c.data.theme==='canyon'){
    const rock=material('#c79c7d');
    for(let i=0;i<40;i++){
      const x=minX-80+rand()*(maxX-minX+160),z=minZ-80+rand()*(maxZ-minZ+160),r=18+rand()*25;
      if(!clear(x,z,r+35))continue;
      const geo=new THREE.CylinderGeometry(r*.65,r,22+rand()*30,7,1);const mesh=new THREE.Mesh(geo,rock);mesh.position.set(x,3,z);mesh.castShadow=mesh.receiveShadow=true;group.add(mesh);
    }
  }else{
    const snow=material('#f1f0e9');
    for(let i=0;i<32;i++){
      const x=minX-100+rand()*(maxX-minX+200),z=minZ-100+rand()*(maxZ-minZ+200),r=12+rand()*20;
      if(!clear(x,z,r+28))continue;
      const mesh=new THREE.Mesh(new THREE.IcosahedronGeometry(r,0),i%3?snow:concrete);mesh.position.set(x,0,z);mesh.scale.y=.5;mesh.castShadow=true;group.add(mesh);
    }
  }
  return group;
}
