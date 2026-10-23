import * as THREE from 'three';

export function getWheelNodes(model) {
  const wheels = [];
  model.traverse(o => {
    if (!/^wheel_[FR][LR]/i.test(o.name)) return;
    for (let p = o.parent; p; p = p.parent) if (/^wheel_[FR][LR]/i.test(p.name)) return;
    wheels.push(o);
  });
  return wheels;
}

// Bind once per GLB instance. Materials are cloned so a remote car cannot light ours.
export function bindVehicleEffects(model) {
  const lamps = [], steering = [], calipers = [];
  const copies = new Map();
  model.traverse(o => {
    if (/^steering_wheel/.test(o.name)) {
      o.userData.steeringRest ||= o.quaternion.toArray();
      steering.push({ node: o, rest: new THREE.Quaternion().fromArray(o.userData.steeringRest) });
    }
    if (/^caliper_/.test(o.name)) calipers.push(o);
    if (!o.material) return;
    const replace = material => {
      const kind = /^CenterBrakeLamp/.test(material.name) ? 'center'
        : /^BrakeLamp|^TailLamp/.test(material.name) ? 'brake'
        : /^ReverseLamp/.test(material.name) ? 'reverse' : null;
      if (!kind) return material;
      if (!copies.has(material)) {
        const copy = material.clone(); copies.set(material, copy);
        lamps.push({ material: copy, kind });
      }
      return copies.get(material);
    };
    o.material = Array.isArray(o.material) ? o.material.map(replace) : replace(o.material);
  });
  const axis = new THREE.Vector3(1, 0, 0), turn = new THREE.Quaternion();
  const result = {
    calipers,
    update(steer = 0, state = {}) {
      turn.setFromAxisAngle(axis, -steer * 14);
      for (const s of steering) s.node.quaternion.copy(s.rest).multiply(turn);
      for (const lamp of lamps) {
        lamp.material.emissiveIntensity = lamp.kind === 'center' ? (state.brake ? 7 : 0)
          : lamp.kind === 'reverse' ? (state.reverse ? 3 : 0)
          : state.brake ? 6 : 0.25;
        lamp.material.emissive.set(lamp.kind === 'reverse' ? '#e6f2ff' : '#ff0714');
      }
    },
  };
  result.update();
  return result;
}

export function attachCaliper(pivot, wheel, calipers) {
  const match = wheel.name.match(/^wheel_([FR][LR])/i);
  if (!match) return;
  const caliper = calipers.find(c => c.name.startsWith(`caliper_${match[1]}`));
  if (caliper) { pivot.updateWorldMatrix(true, false); pivot.attach(caliper); }
}
