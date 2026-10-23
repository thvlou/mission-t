# Mission T — Porsche-inspired additional fleet

공식 포르쉐 페이지와 측면·전면·후면 사진을 브라우저 스냅샷으로 검토한 뒤 Blender MCP로 제작한 스타일화 차량 5종입니다. 공장 CAD가 아니며, 사진의 형태를 게임 에셋 스타일로 단순화했습니다. 페인트 값은 색상명의 시각적 해석입니다.

| 차량 | 색상 | 삼각형 | GLB 크기 | 파일 |
|---|---|---:|---:|---|
| Macan 4S Electric | Oak Green Metallic | 51,672 | 1.47 MB | `macan-4s.glb` |
| 911 Carrera | Guards Red | 59,796 | 1.72 MB | `911-carrera.glb` |
| 718 Cayman | Racing Yellow | 61,548 | 1.75 MB | `718-cayman.glb` |
| Taycan | Frozen Blue Metallic | 54,708 | 1.54 MB | `taycan.glb` |
| 911 GT3 RS | Ultraviolet / Satin Black | 69,140 | 1.97 MB | `911-gt3-rs.glb` |

## 사용

- 게임 상단 Garage → 차량 선택 → 이 차량으로 주행.
- `http://localhost:5173/garage.html`에서 360도 회전, 앞·뒤·측면, 휠 회전을 확인할 수 있습니다.
- 직접 실행: `http://localhost:5173/?car=718-cayman` (ID를 다른 차량으로 변경 가능).
- 기존 `assets/car.glb`와 `assets/vertigo-gt.blend`를 유지합니다.
- 모든 차는 동일한 게임 물리를 사용합니다. 네트워크 상대 차량 외형은 기존 레이스 방식 그대로이며, 새 차량 선택은 로컬 플레이어에 적용됩니다.

## 파일과 좌표

- 각 차량의 `.blend`: 편집 가능한 차체 메시 1개, 바퀴 메시 4개, 스튜디오와 카메라.
- `porsche-collection.blend`: 5종을 한 번에 볼 수 있는 별도 컬렉션 장면.
- `manifest.json`: 차량별 경로, 크기, 바퀴, 출처, 검증 결과.
- GLB는 +X 전방, +Y 위, 미터 단위, 바닥 Y=0. Blender 원본은 +Z 위입니다.
- 바퀴 이름은 `wheel_FL/FR/RL/RR`로 시작합니다. 반복 생성 시 Blender가 숫자 접미사를 붙일 수 있습니다. 게임은 Z축으로 바퀴를 회전합니다.
- PBR 색상/금속/거칠기/발광 재질을 사용하며 외부 텍스처가 없습니다. UV 텍스처 및 실내는 제작 범위에 포함하지 않았습니다.
- 조명·카메라·바닥은 GLB에 포함하지 않았습니다.
- `renders/vehicles/`의 앞·뒤·측면 렌더 15장과 `collection.png`로 검토할 수 있습니다.

## 재생성

설치된 Blender MCP 애드온이 localhost:9876에서 실행 중일 때:

```sh
python tools/blender_client.py tools/build_porsche_fleet.py
python tools/validate_vehicles.py
python tools/blender_client.py tools/finalize_fleet.py
python tools/package_fleet.py
```

차량 하나만 다시 만들려면 생성 명령 끝에 `--models 718-cayman`을 붙이세요. 자세한 출처와 차종별 반영 특징은 `references/porsche/sources.json`에 있습니다.
