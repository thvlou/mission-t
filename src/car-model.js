import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';
import { getVehicle } from './vehicles.js';

// Cars come from the registry in src/vehicles.js. Every car uses the same physics body (about
// 4.5 m long and 1.9 m wide, wheels 2.76 m apart); models are scaled to their listed length.
// In game space the car faces +x, up is +y, and the origin sits 0.6 m above the road.
export const CAR_MODEL = {
  rotationY: 0,          // rotate so the nose points to +x (try Math.PI / 2 or -Math.PI / 2)
  groundOffset: -0.6,    // where the bottom of the model sits relative to the car centre
  wheelPattern: /^wheel_[FR][LR]/i, // exclude the steering wheel and stationary brake calipers
  wheelAxis: 'z',        // local axis the wheel nodes spin around
};

// A ?car=<id> link picks the starting car; otherwise the saved driver profile does.
export const linkedCarId = new URLSearchParams(location.search).get('car');

const DRACO_PATH = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/';
const loader = new GLTFLoader();
const draco = new DRACOLoader();
draco.setDecoderPath(DRACO_PATH);
loader.setDRACOLoader(draco);
const scenes = new Map(); // url → Promise<scene>, so five players on one car download it once

function sceneFor(url) {
  if (!scenes.has(url)) {
    const p = loader.loadAsync(url).then((gltf) => finishMaterials(gltf.scene));
    p.catch(() => scenes.delete(url));
    scenes.set(url, p);
  }
  return scenes.get(url);
}

// Start downloading a car without building it (the Cars viewer warms its neighbours).
export function preloadVehicle(id) {
  sceneFor(getVehicle(id).url).catch(() => {});
}

// A fresh, scaled copy of a registry car: { holder, wheels, opts }. Materials are shared between
// copies; vehicle-rig clones the lamp materials it animates.
export async function buildVehicleModel(id) {
  const vehicle = getVehicle(id);
  const model = (await sceneFor(vehicle.url)).clone(true);
  model.rotation.y = CAR_MODEL.rotationY;
  model.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const scale = vehicle.length / Math.max(size.x, size.z);
  const holder = new THREE.Group();
  holder.add(model);
  holder.scale.setScalar(scale);
  const center = box.getCenter(new THREE.Vector3());
  model.position.set(-center.x, -box.min.y + CAR_MODEL.groundOffset / scale, -center.z);

  const wheels = [];
  model.traverse((o) => {
    if (o.isMesh) {
      o.castShadow = true;
      o.receiveShadow = true;
    }
    if (CAR_MODEL.wheelPattern.test(o.name) && !wheels.some((w) => isAncestor(w, o))) wheels.push(o);
  });
  const exhausts = fitExhausts(holder, vehicle);
  return { holder, wheels, vehicle, exhausts, opts: { ...CAR_MODEL, wheelRadius: vehicle.wheelRadius } };
}

// ---------- materials ----------
// Each downloaded car is tuned once for the game's look (a clean, glossy animated-film finish):
// deep clear-coated paint with a fine metallic flake, rubber that reads as rubber, bright metal,
// glass that mirrors the sky, and lamps strong enough to bloom.
let flakeMap = null;
function flakes() {
  if (flakeMap) return flakeMap;
  const c = document.createElement('canvas');
  c.width = c.height = 256;
  const g = c.getContext('2d');
  const img = g.createImageData(256, 256);
  for (let i = 0; i < img.data.length; i += 4) {
    img.data[i] = 128 + (Math.random() - 0.5) * 90;
    img.data[i + 1] = 128 + (Math.random() - 0.5) * 90;
    img.data[i + 2] = 255;
    img.data[i + 3] = 255;
  }
  g.putImageData(img, 0, 0);
  flakeMap = new THREE.CanvasTexture(c);
  flakeMap.wrapS = flakeMap.wrapT = THREE.RepeatWrapping;
  flakeMap.repeat.set(24, 24);
  return flakeMap;
}

function finishMaterials(scene) {
  const done = new Set();
  scene.traverse((o) => {
    if (!o.isMesh) return;
    const hasUv = !!o.geometry.attributes.uv;
    for (const m of [].concat(o.material)) {
      if (done.has(m)) continue;
      done.add(m);
      tune(m, hasUv);
    }
  });
  return scene;
}

function tune(m, hasUv) {
  const n = m.name || '';
  const physical = m.isMeshPhysicalMaterial;
  if (/paint/i.test(n)) {
    m.roughness = Math.max(0.3, m.roughness + 0.12);
    m.metalness = Math.min(0.55, m.metalness + 0.08);
    if (physical) { m.clearcoat = 1; m.clearcoatRoughness = 0.045; }
    if (hasUv) { m.normalMap = flakes(); m.normalScale.set(0.1, 0.1); }
    m.envMapIntensity = 1.1;
  } else if (/glass/i.test(n)) {
    m.roughness = 0.04;
    m.envMapIntensity = 1.7;
    if (physical) { m.clearcoat = 1; m.clearcoatRoughness = 0.02; }
  } else if (/tirewall/i.test(n)) {
    m.color.set('#2c2d30');
    m.roughness = 0.6;
  } else if (/tire/i.test(n)) {
    m.color.set('#252629');
    m.roughness = 0.88;
  } else if (/rimlip|lug/i.test(n)) {
    m.metalness = 1;
    m.roughness = Math.max(m.roughness, 0.2);
    m.envMapIntensity = 1.15;
  } else if (/rim|barrel/i.test(n)) {
    m.envMapIntensity = 1.4;
    if (!/dark|black/i.test(n)) m.roughness = Math.min(m.roughness, 0.2);
  } else if (/disc/i.test(n)) {
    m.metalness = 1;
    m.roughness = 0.32;
  } else if (/headlamp/i.test(n)) {
    m.emissiveIntensity = (m.emissiveIntensity || 1) * 1.8;
  }
  m.needsUpdate = true;
}

// ---------- tail pipes ----------
// Find the car's rear surface behind each tip (registry: across, height) and fit a chrome pipe
// there. Returns the tip mouths in holder space, for the boost flames.
const ray = new THREE.Raycaster();
const chrome = new THREE.MeshStandardMaterial({ color: '#dcdde1', metalness: 1, roughness: 0.16, envMapIntensity: 1.6 });
const soot = new THREE.MeshStandardMaterial({ color: '#0d0d0f', metalness: 0.4, roughness: 0.7 });
function fitExhausts(holder, vehicle) {
  const spec = vehicle.exhaust;
  if (!spec) return [];
  holder.updateMatrixWorld(true);
  // Models built with their own tail pipes (exhaust_N lip rings) keep them; the flames go at
  // each lip's centre.
  const lips = [];
  holder.traverse((o) => { if (o.isMesh && /exhaust_\d+$/.test(o.name)) lips.push(o); });
  if (lips.length) {
    const k = 1 / holder.scale.x;
    return lips
      .sort((a, b) => +a.name.match(/\d+$/)[0] - +b.name.match(/\d+$/)[0])
      .map((o) => ({ pos: holder.worldToLocal(new THREE.Box3().setFromObject(o).getCenter(new THREE.Vector3())), r: spec.r * k }));
  }
  const box = new THREE.Box3().setFromObject(holder);
  const body = [];
  holder.traverse((o) => { if (o.isMesh && !/wheel|tire|caliper/i.test(`${o.name} ${o.parent?.name || ''}`)) body.push(o); });
  const k = 1 / holder.scale.x;
  return spec.tips.map(([z, h]) => {
    const y = box.min.y + h;
    ray.set(new THREE.Vector3(box.min.x - 1, y, z), new THREE.Vector3(1, 0, 0));
    const hit = ray.intersectObjects(body, false)[0];
    const x = hit ? Math.min(hit.point.x, box.min.x + 0.45) : box.min.x + 0.08;
    const mouth = holder.worldToLocal(new THREE.Vector3(x - 0.035, y, z));
    const r = spec.r * k;
    const pipe = new THREE.Group();
    const tube = new THREE.Mesh(new THREE.CylinderGeometry(r, r * 0.94, 0.2 * k, 28, 1, true), chrome);
    tube.rotation.z = Math.PI / 2;
    tube.position.x = 0.1 * k;
    const lip = new THREE.Mesh(new THREE.TorusGeometry(r, r * 0.12, 10, 28), chrome);
    lip.rotation.y = Math.PI / 2;
    const inner = new THREE.Mesh(new THREE.CircleGeometry(r * 0.92, 24), soot);
    inner.rotation.y = -Math.PI / 2;
    inner.position.x = 0.03 * k;
    pipe.add(tube, lip, inner);
    pipe.position.copy(mouth);
    pipe.traverse((o) => { if (o.isMesh) o.castShadow = true; });
    holder.add(pipe);
    return { pos: mouth, r };
  });
}

// Put a registry car on the shared rover (our own car). Calling it again swaps the car.
let request = 0;
export async function loadCarModel(rover, id = linkedCarId) {
  const mine = ++request;
  const built = await buildVehicleModel(id);
  if (mine !== request) return false; // a newer choice arrived while this one loaded
  rover.useModel(built.holder, built.wheels, { ...built.opts, exhausts: built.exhausts, theme: built.vehicle.theme });
  return true;
}

// Wheels that stay on the road while the body rolls and pitches on its springs: each wheel gets a
// hub at its centre, which is moved (keeping its world pose) onto `chassis`, a sibling of the car
// body that only follows the road. Call it while the body has no roll or pitch of its own. Steer
// a front hub with hub.quaternion = (turn about up) × rest. onHub(hub, node) runs before the move
// (calipers ride on the hub so they turn with the wheel but don't spin).
export function plantWheels(chassis, wheels, onHub) {
  const p = new THREE.Vector3();
  chassis.updateWorldMatrix(true, false);
  return wheels.map((node) => {
    node.updateWorldMatrix(true, false);
    const front = chassis.worldToLocal(node.getWorldPosition(p)).x > 0;
    const hub = new THREE.Group();
    hub.position.copy(node.position);
    node.parent.add(hub);
    node.position.set(0, 0, 0);
    hub.add(node);
    onHub?.(hub, node);
    chassis.attach(hub);
    return { node, hub, front, rest: hub.quaternion.clone() };
  });
}

// A soft contact shadow under a car: grounds it on the road whatever the sun's angle. The plane
// lies flat in its parent's frame; scale it to the car's footprint.
let shadowTex = null;
export function contactShadow(length = 4.7, width = 1.95) {
  if (!shadowTex) {
    const c = document.createElement('canvas');
    c.width = c.height = 128;
    const g = c.getContext('2d');
    const grad = g.createRadialGradient(64, 64, 0, 64, 64, 64);
    grad.addColorStop(0, 'rgba(18,19,22,0.62)');
    grad.addColorStop(0.55, 'rgba(18,19,22,0.42)');
    grad.addColorStop(0.8, 'rgba(18,19,22,0.14)');
    grad.addColorStop(1, 'rgba(18,19,22,0)');
    g.fillStyle = grad;
    g.fillRect(0, 0, 128, 128);
    shadowTex = new THREE.CanvasTexture(c);
    shadowTex.colorSpace = THREE.SRGBColorSpace;
  }
  const mesh = new THREE.Mesh(
    new THREE.PlaneGeometry(1, 1),
    new THREE.MeshBasicMaterial({ map: shadowTex, transparent: true, depthWrite: false, toneMapped: false, polygonOffset: true, polygonOffsetFactor: -4 }),
  );
  mesh.geometry.rotateX(-Math.PI / 2);
  mesh.scale.set(length + 0.5, 1, width + 0.55);
  mesh.renderOrder = 1;
  return mesh;
}

function isAncestor(a, b) {
  for (let p = b.parent; p; p = p.parent) if (p === a) return true;
  return false;
}
