"""Validate and package exactly the three new courses, with a reproducible source snapshot."""
import json, struct, hashlib, math, zipfile
from pathlib import Path
from PIL import Image
ROOT=Path(__file__).resolve().parents[1]
IDS=['harbor-run','canyon-flight','alpine-ring']
report=[]
for ident in IDS:
 p=ROOT/'assets/tracks/visual'/f'{ident}-visual.glb';raw=p.read_bytes()
 magic,version,size=struct.unpack_from('<III',raw);assert (magic,version,size)==(0x46546c67,2,len(raw))
 n,kind=struct.unpack_from('<II',raw,12);assert kind==0x4e4f534a;doc=json.loads(raw[20:20+n])
 assert all('uri' not in b for b in doc['buffers'])
 assert all('bufferView' in im for im in doc.get('images',[]))
 triangles=0
 for mesh in doc['meshes']:
  for prim in mesh['primitives']:
   pos=doc['accessors'][prim['attributes']['POSITION']];assert all(math.isfinite(v) for v in pos['min']+pos['max'])
   assert prim.get('mode',4)==4
   triangles+=doc['accessors'][prim['indices']]['count']//3 if 'indices'in prim else pos['count']//3
 assert triangles>50000 and len(doc['meshes'])>10
 source=ROOT/'assets/tracks'/f'{ident}.json'
 report.append({'id':ident,'file':str(p.relative_to(ROOT)).replace('\\','/'),'bytes':size,'meshes':len(doc['meshes']),'triangles':triangles,'embeddedImages':len(doc.get('images',[])),'sourceSha256':hashlib.sha256(source.read_bytes()).hexdigest(),'glbSha256':hashlib.sha256(raw).hexdigest()})
 for view in ['overview','drive']:
  image=Image.open(ROOT/'renders/tracks'/f'{ident}-{view}.png');image.verify()
(ROOT/'assets/tracks/visual-validation.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
runtime=['tracks.html','.assetsignore','src/track-lab.js','src/main.js','src/highway/car.js','src/highway/circuit.js','src/highway/circuit-path.js','src/highway/course-driver.js','src/highway/stunt-scenery.js','src/highway/track-export.js','src/race/courses.js','src/race/race.js','src/race/minimap.js','server/room-core.js']
tools=['tools/build-stunt-tracks.mjs','tools/test-stunt-tracks.mjs','tools/test-stunt-websocket.mjs','tools/package-stunt-tracks.py']
files=[ROOT/f for f in runtime+tools]
files += [ROOT/'assets/tracks'/f for f in ['STUNT_TRACKS_GUIDE.md','stunt-manifest.json','stunt-validation.json','visual-validation.json']]
for ident in IDS:
 files += [ROOT/'assets/tracks'/f'{ident}.json',ROOT/'assets/tracks/visual'/f'{ident}-visual.glb']
 files += [ROOT/'renders/tracks'/f'{ident}-{view}.png' for view in ['overview','drive']]
out=ROOT/'deliveries';out.mkdir(exist_ok=True)
dest=out/'mission-t-stunt-tracks-2026-10-27.zip'
with zipfile.ZipFile(dest,'w',zipfile.ZIP_DEFLATED) as z:
 for p in files:z.write(p,str(p.relative_to(ROOT)))
 z.write(ROOT/'assets/tracks/STUNT_TRACKS_GUIDE.md','START-HERE.md')
print(json.dumps({'bundle':str(dest),'files':len(files)+1,'bytes':dest.stat().st_size,'tracks':report},indent=2))
