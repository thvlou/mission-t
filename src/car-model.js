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

// Front wheels of a standalone car (an opponent) get a pivot so they can steer while spinning.
export function rigWheels(holder, wheels) {
  holder.updateMatrixWorld(true);
  const up = new THREE.Vector3(0, 1, 0);
  const p = new THREE.Vector3();
  return wheels.map((node) => {
    const front = holder.worldToLocal(node.getWorldPosition(p)).x > 0;
    const out = { node, front, base: node.rotation.z };
    if (front) {
      const parent = node.parent;
      const origin = parent.worldToLocal(holder.localToWorld(new THREE.Vector3()));
      out.axis = parent.worldToLocal(holder.localToWorld(up.clone())).sub(origin).normalize();
      out.pivot = new THREE.Group();
      out.pivot.position.copy(node.position);
      parent.add(out.pivot);
      node.position.set(0, 0, 0);
      out.pivot.add(node);
    }
    return out;
  });
}

function isAncestor(a, b) {
  for (let p = b.parent; p; p = p.parent) if (p === a) return true;
  return false;
}
