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
    const p = loader.loadAsync(url).then((gltf) => gltf.scene);
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
  return { holder, wheels, vehicle, opts: { ...CAR_MODEL, wheelRadius: vehicle.wheelRadius } };
}

// Put a registry car on the shared rover (our own car). Calling it again swaps the car.
let request = 0;
export async function loadCarModel(rover, id = linkedCarId) {
  const mine = ++request;
  const built = await buildVehicleModel(id);
  if (mine !== request) return false; // a newer choice arrived while this one loaded
  rover.useModel(built.holder, built.wheels, built.opts);
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
