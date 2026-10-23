"""Package revised assets and their rig contract."""
import json, html
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];OUT=ROOT/'assets/vehicles'
sources=json.loads((ROOT/'references/porsche/sources.json').read_text(encoding='utf-8'))['models']
checks={v['id']:v for v in json.loads((OUT/'validation.json').read_text(encoding='utf-8'))}
sources.append({'id':'mission-s','page':'','features':['기존 Vertigo GT 곡면 보존','보닛·리어 데크 패널선','제동등과 후진등','실내 핸들']})
fleet=[]
for source in sources:
    ident=source['id'];meta=json.loads((OUT/f'{ident}.json').read_text(encoding='utf-8'))
    meta.update(url='assets/car.glb' if ident=='mission-s' else f'assets/vehicles/{ident}.glb',blend=f'assets/vehicles/{ident}.blend',preview=f'renders/vehicles/{ident}_front.png',wheelAxis='z',steeringAxis='x',steeringRatio=14,wheelNodes=['wheel_FL','wheel_FR','wheel_RL','wheel_RR'],caliperNodes=['caliper_FL','caliper_FR','caliper_RL','caliper_RR'],lightMaterials=['BrakeLamp','CenterBrakeLamp','ReverseLamp'],source=source['page'],features=source['features'],validation=checks[ident])
    fleet.append(meta)
(OUT/'manifest.json').write_text(json.dumps({'version':2,'up':'Y','forward':'+X','units':'metres','vehicles':fleet},ensure_ascii=False,indent=2),encoding='utf-8')
rows='\n'.join(f"| {v['name']} | {v['color']} | {v['validation']['triangles']:,} | {v['validation']['bytes']/1048576:.2f} MB |" for v in fleet)
notes=f'''# Mission T — revised vehicle collection

공식 사진을 참고해 Blender MCP에서 제작한 차량 에셋입니다. 실차 스캔/CAD 또는 제조사 제공 모델은 아닙니다. 돌출 구체형 헤드램프 제거, 곡면에 맞춘 광학부, 범퍼 흡기구 깊이, 보닛 패널선, 윈도 프레임, 실내 핸들, 브레이크 작동을 포함합니다.

| 차량 | 색상 | 삼각형 | GLB |
|---|---|---:|---:|
{rows}

## 확인
- `http://localhost:5173/garage.html`: 전후측면, 휠 회전, ±30° 조향, 제동등, 후진등.
- `http://localhost:5173/tools/test-vehicle-rig.html`: 실제 GLB 6개로 앞바퀴/핸들/캘리퍼/조명/복귀 동작 검사.
- Highway와 Race에서 조향은 앞바퀴와 핸들(14:1)이 함께 반응합니다. 앞 캘리퍼는 조향만 따라가고 타이어 회전에는 따라가지 않습니다.
- 전진 중 후진 입력은 제동등, 후진 주행은 후진등, 핸드브레이크는 제동등을 켭니다. 미등은 낮은 밝기, 중앙 제동등은 제동 때만 켭니다.
- 레이스 상대에게 조향과 제동 상태를 전송합니다. 상대 차량 외형은 기존 로컬 모델 복제 방식입니다.
- 아케이드 물리와 차량별 성능 수치는 동일합니다. 실제 Ackermann 서스펜션이나 제조사 차량 동역학은 포함하지 않습니다.

## 파일
- 차량별 `.blend`, `.glb`, `.json`과 `porsche-collection.blend`.
- GLB: 차체 1, 휠 4, 캘리퍼 4, 핸들 1의 독립 노드 10개. 멀티 재질 노드는 Three.js 로더에서 하위 메시로 분리됩니다.
- Blender +Z 위 / GLB +Y 위, +X 전방, 미터 단위. 타이어 로컬 Z축, 핸들 로컬 X축 회전.
- `BrakeLamp`, `CenterBrakeLamp`, `ReverseLamp` 재질로 점등. 인스턴스마다 재질을 복제합니다.
- 원래 차량은 `vertigo-gt` ID와 `assets/car.glb` 경로를 유지하며 UI에는 Mission S로 표시합니다.
- 이전 파일은 `assets/vehicles/backup-v1/`에 보존했습니다. 백업은 Git/배포 대상에서 제외합니다.
- 사진 기반의 외관과 간략한 상부 실내입니다. 문 개폐, 전체 실내, UV 베이크 텍스처, LOD는 포함하지 않습니다.

## 재생성
```sh
python tools/blender_client.py tools/build_porsche_fleet.py
python tools/blender_client.py tools/refine_original_vehicle.py
python tools/validate_vehicles.py
python tools/blender_client.py tools/finalize_fleet.py
python tools/package_fleet.py
```
Blender MCP localhost:9876 연결이 필요합니다. 단일 차종은 `--models 911-carrera`처럼 선택합니다.
'''
(OUT/'README.md').write_text(notes,encoding='utf-8')
cards=''.join(f'<article><img src="{v["preview"]}" alt="{html.escape(v["name"])}"><h2>{html.escape(v["name"])}</h2><p>{html.escape(v["color"])} · {v["validation"]["triangles"]:,} triangles · {v["validation"]["bytes"]/1048576:.2f} MB</p><p>{" / ".join(html.escape(f) for f in v["features"])}</p>'+ (f'<a href="{v["source"]}" target="_blank" rel="noreferrer">공식 참고 페이지 ↗</a>' if v['source'] else '')+'</article>' for v in fleet)
(ROOT/'vehicle-notes.html').write_text(f'''<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Mission T — 차량 제작 정보</title><style>body{{max-width:1100px;margin:40px auto;padding:0 22px;background:#f4f3f0;color:#252a2d;font:15px system-ui;line-height:1.8}}a{{color:inherit}}h1{{font-weight:500}}.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:24px}}article{{background:#fff;padding:18px}}img{{width:100%}}h2{{font-weight:500}}p{{color:#697176}}</style><a href="garage.html">← Garage</a><h1>Revised Blender collection</h1><p>차체에 밀착된 헤드램프, 깊이 있는 범퍼 흡기구, 패널선과 실내 핸들. 조향·제동·후진 상태에 반응하는 여섯 차량입니다. 사진을 참고한 자체 제작 메시로 제조사 CAD 모델은 아닙니다.</p><p>차고의 조향 슬라이더와 제동등/후진등 버튼으로 동작을 살펴보세요. 기본 주행 물리는 동일한 아케이드 방식입니다.</p><div class="grid">{cards}</div></html>''',encoding='utf-8')
print(f'Packaged {len(fleet)} revised vehicles')
