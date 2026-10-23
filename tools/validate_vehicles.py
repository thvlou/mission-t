"""Validate exported binary glTF structure, geometry, wheel pivots and bounds."""
import json, math, struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
IDS=['macan-4s','911-carrera','718-cayman','taycan','911-gt3-rs','mission-s']
report=[]
for vehicle in IDS:
    path=ROOT/'assets/vehicles'/f'{vehicle}.glb'
    raw=path.read_bytes();magic,version,size=struct.unpack_from('<III',raw)
    assert magic==0x46546c67 and version==2 and size==len(raw),path
    n,typ=struct.unpack_from('<II',raw,12);assert typ==0x4e4f534a
    doc=json.loads(raw[20:20+n]);offset=20+n
    bn,btyp=struct.unpack_from('<II',raw,offset);assert btyp==0x004e4942
    binary=raw[offset+8:offset+8+bn]
    nodes=doc['nodes'];scene=doc['scenes'][doc.get('scene',0)]
    wheels=[o for o in nodes if o.get('name','').startswith('wheel_')]
    assert len(wheels)==4,[(o.get('name'),o.get('mesh')) for o in nodes]
    assert len(nodes)==10 and len(scene['nodes'])==10,[o.get('name') for o in nodes]
    assert sum(o.get('name','').startswith('steering_wheel') for o in nodes)==1
    assert sum(o.get('name','').startswith('caliper_') for o in nodes)==4
    for label in ['BrakeLamp','CenterBrakeLamp','ReverseLamp']:
        assert any(m.get('name','').startswith(label) for m in doc['materials']),label
    assert 'cameras' not in doc
    assert 'images' not in doc,'Expected self-contained PBR materials with no external images'
    expected={'FL','FR','RL','RR'}
    assert {o['name'][6:8] for o in wheels}==expected
    for o in wheels:
        assert all(abs(a-b)<1e-5 for a,b in zip(o.get('rotation',[0,0,0,1]),[0,0,0,1])),o
        assert o.get('translation',[0,0,0])[1]>.2,o
    bounds=[ [float('inf')]*3, [float('-inf')]*3 ];triangles=0
    for o in nodes:
        assert 'mesh' in o
        t=o.get('translation',[0,0,0]);scale=o.get('scale',[1,1,1])
        assert all(abs(a-1)<1e-5 for a in scale)
        for prim in doc['meshes'][o['mesh']]['primitives']:
            positions=doc['accessors'][prim['attributes']['POSITION']]
            view=doc['bufferViews'][positions['bufferView']]
            start=view.get('byteOffset',0)+positions.get('byteOffset',0)
            stride=view.get('byteStride',12)
            for i in range(positions['count']):
                v=struct.unpack_from('<fff',binary,start+i*stride)
                assert all(math.isfinite(x) for x in v)
            for k in range(3):
                bounds[0][k]=min(bounds[0][k],positions['min'][k]+t[k]);bounds[1][k]=max(bounds[1][k],positions['max'][k]+t[k])
            idx=doc['accessors'][prim['indices']];assert idx['count']%3==0;triangles+=idx['count']//3
    dimensions=[round(bounds[1][i]-bounds[0][i],4) for i in range(3)]
    assert 4<dimensions[0]<5.4 and 1<dimensions[1]<1.9 and 1.7<dimensions[2]<2.4,dimensions
    assert abs(bounds[0][1])<.025,bounds
    assert triangles<280000,triangles
    report.append({'id':vehicle,'bytes':size,'triangles':triangles,'meshes':len(nodes),'wheels':4,'dimensions_xyz':dimensions,'ground_y':round(bounds[0][1],5)})
dest=ROOT/'assets/vehicles/validation.json';dest.write_text(json.dumps(report,indent=2),encoding='utf-8')
print(json.dumps(report,indent=2))
