import * as THREE from 'three';
import { GLTFLoader } from 'three/addons/loaders/GLTFLoader.js';
import { DRACOLoader } from 'three/addons/loaders/DRACOLoader.js';

// Drop your own car at assets/car.glb (or .gltf) and adjust these to fit it.
// The physics body is about 4.5 m long and 1.9 m wide, with wheels 2.76 m apart.
// In game space the car faces +x, up is +y, and the origin sits 0.6 m above the road.
export const CAR_MODEL = {
  url: 'assets/car.glb',
  length: 4.736,         // the model is scaled so its longest horizontal side matches this, in m
  rotationY: 0,          // rotate so the nose points to +x (try Math.PI / 2 or -Math.PI / 2)
  groundOffset: -0.6,    // where the bottom of the model sits relative to the car centre
  wheelPattern: /wheel|tire|tyre|rim/i, // node names that should spin
  wheelAxis: 'z',        // local axis the wheel nodes spin around
  wheelRadius: 0.36,
};

const DRACO_PATH = 'https://cdn.jsdelivr.net/npm/three@0.160.0/examples/jsm/libs/draco/gltf/';

export async function loadCarModel(rover) {
  const head = await fetch(CAR_MODEL.url, { method: 'HEAD' }).catch(() => null);
  if (!head || !head.ok) return false;

  const loader = new GLTFLoader();
  const draco = new DRACOLoader();
  draco.setDecoderPath(DRACO_PATH);
  loader.setDRACOLoader(draco);
  const gltf = await loader.loadAsync(CAR_MODEL.url);
  draco.dispose();

  const model = gltf.scene;
  model.rotation.y = CAR_MODEL.rotationY;
  model.updateMatrixWorld(true);
  const box = new THREE.Box3().setFromObject(model);
  const size = box.getSize(new THREE.Vector3());
  const scale = CAR_MODEL.length / Math.max(size.x, size.z);
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
  rover.useModel(holder, wheels, CAR_MODEL);
  return true;
}

function isAncestor(a, b) {
  for (let p = b.parent; p; p = p.parent) if (p === a) return true;
  return false;
}
