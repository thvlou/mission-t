# Mission T 멀티플레이 트랙 3종

## 선택한 제작 방법

현재 게임은 `Circuit`이 JSON 도로 중심선·폭·높이를 읽어 Three.js 지형과 차량 물리 좌표를 생성합니다. 이미지나 배경 GLB만 교체하면 도로 폭, 착지, 지름길 진행률이 일치하지 않습니다. 따라서 **게임용 JSON을 원본으로 제작 → 같은 데이터로 웹 3D 렌더 → 실제 HighwayCar 물리와 멀티플레이 테스트 → 표시용 GLB 내보내기** 순서로 만들었습니다. 이미지 생성은 사용하지 않았습니다.

게임용 파일은 이미 현재 프로젝트의 멀티플레이 코스 목록과 서버에 연결되어 있습니다. 기존 Highway와 Ridgeline도 유지됩니다.

## 코스와 실측

| 코스 | 길이 | 기본 루트 | 지름길 루트 | 주요 구간 |
|---|---:|---:|---:|---|
| Harbor Run | 2.05 km | 61.96초 | 61.11초 | 항만 드리프트, 14m 필수 점프, Dock Hop 22m 점프 |
| Canyon Flight | 2.15 km | 70.76초 | 62.77초 | 긴 부스터 접근, 24m 필수 점프, Glide Cut 58m 활강 |
| Alpine Ring | 2.00 km | 67.80초 | 64.65초 | S자·헤어핀 드리프트, 16m 필수 점프, Ridge Leap 30m 점프 |

- 위 기록은 정지 출발, 120Hz 실제 차량 물리, 안전한 자동 조향을 사용한 기준입니다. 위치나 속도를 강제로 이동시키지 않았습니다. 운전 방식·부스터·드리프트에 따라 기록은 달라집니다.
- 일반 도로와 지름길 모두 **포장 폭 12m = 4m 기준 3열**입니다. 포장 밖 런오프는 이 폭에 포함하지 않으며, 잔디/자갈에서 감속합니다.
- 기본 레이스는 **2바퀴**이며, 목표 한 바퀴는 약 1분입니다. 전체 경기 시간은 약 2분입니다.
- 각 지름길은 기본 루트보다 물리적인 길이가 실제로 짧으며, 기존 원형 코스의 같은 진행률로 합류합니다. 점프 실패 시 램프 접근 구간으로 복귀하고 경기 타이머는 계속 갑니다.
- 지름길과 기본 도로가 교차하는 지점은 교량 높이로 분리했습니다. GLB에는 교량의 측면·바닥과 지지 기둥도 포함합니다.

## 지금 실행하기

```powershell
npm start
```

1. `http://localhost:5173/` → **Race** → 방 생성.
2. 방장이 Course에서 **Harbor Run / Canyon Flight / Alpine Ring** 선택.
3. 참가자는 같은 방 링크로 접속해 Ready. 방장이 Start.
4. 기존 서버가 켜져 있었다면 코드 반영을 위해 서버를 재시작하고 각 브라우저를 새로고침합니다.

현재 검수용 서버는 별도 포트 **5174**에서 실행했습니다. 바로 살펴보려면:

- `http://localhost:5174/tracks.html?track=harbor-run`
- `http://localhost:5174/tracks.html?track=canyon-flight`
- `http://localhost:5174/tracks.html?track=alpine-ring`

Track Lab은 실제 게임의 `HighwayMode`, `CircuitScenery`, 차량 GLB, 조향/점프 물리를 사용합니다. 드래그로 임의의 그림을 보여주는 미리보기가 아닙니다.

## 조작과 검토

- ↑/W 가속, ↓/S 제동, ←→/AD 조향.
- Shift + 조향: 드리프트. 슬라이드를 유지했다가 직진하면 기존 드리프트 부스트가 지급됩니다.
- Space: 점프. 누른 상태를 유지하면 연료를 소비하며 활강합니다.
- E: 부스터. 부스터 표지·노면 표시는 사용 구간 안내이며 자동 가속 패드는 아닙니다.
- Track Lab의 **자동 주행 / 지름길 사용**으로 기본 루트와 지름길을 비교할 수 있습니다.
- **점프 구간 / 지름길 입구**는 차량을 접근 지점으로 이동합니다. 자동 주행을 켜거나 직접 가속해서 점프합니다.
- **추적 시점 / 전체 시점**, **PNG 저장**, **GLB 내보내기**를 제공합니다.

## 전달 파일

### 게임용 원본

- `assets/tracks/harbor-run.json`
- `assets/tracks/canyon-flight.json`
- `assets/tracks/alpine-ring.json`

외부 지형/이미지/상용 에셋을 다운로드하지 않은 자체 제작 코스입니다. 파일은 수십 KB 크기이며, 텍스처와 소품은 런타임에서 생성됩니다.

### Blender·다른 툴에서 볼 표시용 3D 파일

- `assets/tracks/visual/harbor-run-visual.glb`
- `assets/tracks/visual/canyon-flight-visual.glb`
- `assets/tracks/visual/alpine-ring-visual.glb`

웹에서 실제 생성한 지형·분기 도로·표지·나무·소품을 GLB로 내보냈습니다. Blender의 **File → Import → glTF 2.0**으로 열 수 있습니다. GLB는 미터 단위, Y-up이며 Blender가 가져오면서 Z-up으로 변환합니다.

**게임에서 권장하는 실행 원본은 JSON입니다. GLB는 표시용이며 지름길 연결·주행 진행률·착지 판정 데이터는 JSON과 런타임 코드에 있습니다.** GLB에서 도로를 변형했다면 JSON 중심선·높이·점프 구간도 함께 바꿔야 합니다.

### 실제 렌더와 검증

- `renders/tracks/*-overview.png`: 실제 WebGL 전체 렌더.
- `renders/tracks/*-drive.png`: 접근 구간 주행 시점 렌더.
- `assets/tracks/stunt-manifest.json`: 길이·도로 폭·지름길·점프 사양.
- `assets/tracks/stunt-validation.json`: 실제 물리의 루트별 주행 결과.
- `assets/tracks/visual-validation.json`: GLB 구조와 유효성 검사.

## 다른 동일 버전 프로젝트 사본에 적용할 때

전달 ZIP의 상대 경로를 유지합니다. JSON 세 개만 추가하면 기존 엔진은 바닥 끊김과 분기를 모르므로 아래 런타임 변경도 함께 필요합니다.

- `src/highway/circuit-path.js`: 중심선·열린 분기·같은 랩 진행률·표면/틈 판정.
- `src/highway/circuit.js`, `stunt-scenery.js`: JSON과 일치하는 도로/지형/테마/분기 렌더.
- `src/highway/car.js`: 분기 기준 조향·벽·오프로드, 바닥 소실 시 비행, 윗면 착지, 실패 복귀.
- `src/race/courses.js`: 코스 등록과 바퀴 수.
- `server/room-core.js`: 같은 코스 레지스트리 공유. Node와 Cloudflare Worker 양쪽이 사용하는 코드입니다.
- `src/race/race.js`, `minimap.js`, `src/main.js`: 상대의 분기 ID·높이·주행 위치·미니맵 반영.
- `tracks.html`, `src/track-lab.js`, `src/highway/course-driver.js`, `track-export.js`: 검토 페이지와 내보내기.
- `.assetsignore`: 게임용 JSON과 Track Lab을 배포 대상으로 포함. 무거운 표시용 GLB와 제작 파일은 웹 배포에서 제외.

현재 폴더에는 위 변경이 이미 적용되어 있습니다. 공개 서비스 배포는 실행하지 않았습니다. 배포하려면 기존 프로젝트 배포 흐름을 사용하고 클라이언트와 서버를 함께 갱신합니다.

## 직접 수정·재생성

```powershell
node tools/build-stunt-tracks.mjs
node tools/test-stunt-tracks.mjs
# 로컬 서버를 켠 상태에서 실제 두 클라이언트 검증
node tools/test-stunt-websocket.mjs ws://127.0.0.1:5173
```

생성 스크립트의 `specs`에서 전체 길이, 제어점, 테마 색, 점프 길이와 지름길 진입/합류 비율을 바꿉니다. 원본 JSON을 수정한 뒤에는 웹을 새로고침하고 GLB/PNG도 다시 내보내세요.

JSON의 `points`는 `[x, y, z, widthRight, widthLeft]`이며 미터 단위입니다. `gaps`의 `from/to`는 기본 루트상의 거리, `shortcuts.from/to`는 기본 루트에 대응하는 진행 거리, 지름길의 `gaps.from/to`는 해당 지름길 자체를 따라간 거리입니다. 시작/결승선은 0이며 한 바퀴마다 진행 거리가 누적됩니다.

현재 멀티플레이는 기존 방식대로 각 클라이언트가 자기 차량을 시뮬레이션하고 서버가 상태를 전달합니다. 이번 검증은 일반적인 동기화와 주행을 대상으로 하며, 서버 권한 기반의 안티치트 구현은 포함하지 않습니다.
