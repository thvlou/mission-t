import * as THREE from 'three';

// An original low-poly rover, built from primitives. Forward is +x, up is +y.
export function buildRover() {
  const root = new THREE.Group();
  const body = new THREE.Group();
  root.add(body);
  // The drawn car. Swapped out when a custom model is loaded; jets stay on `body`.
  const shell = new THREE.Group();
  body.add(shell);

  const paint = new THREE.MeshStandardMaterial({ color: '#dfe3e8', roughness: 0.38, metalness: 0.35 });
  const under = new THREE.MeshStandardMaterial({ color: '#25282e', roughness: 0.8, metalness: 0.2 });
  const glass = new THREE.MeshStandardMaterial({ color: '#0b1218', roughness: 0.08, metalness: 0.9 });
  const accent = new THREE.MeshBasicMaterial({ color: '#d23437', toneMapped: false });
  const lamp = new THREE.MeshBasicMaterial({ color: '#fff6dd', toneMapped: false });
  const tail = new THREE.MeshBasicMaterial({ color: '#ff3b4e', toneMapped: false });

  const extrude = (pts, depth, mat, bevel = 0.05) => {
    const shape = new THREE.Shape(pts.map(([x, y]) => new THREE.Vector2(x, y)));
    const geo = new THREE.ExtrudeGeometry(shape, { depth, bevelEnabled: true, bevelSize: bevel, bevelThickness: bevel, bevelSegments: 2 });
    geo.translate(0, 0, -depth / 2);
    const mesh = new THREE.Mesh(geo, mat);
    mesh.castShadow = true;
    mesh.receiveShadow = true;
    return mesh;
  };

  shell.add(extrude([[-2.12, -0.32], [2.0, -0.32], [2.16, -0.12], [2.08, 0.04], [1.2, 0.2], [-1.55, 0.26], [-2.12, 0.16]], 1.78, paint));
  shell.add(extrude([[-2.0, -0.42], [1.95, -0.42], [1.95, -0.3], [-2.0, -0.3]], 1.6, under, 0.03));
  shell.add(extrude([[0.95, 0.19], [0.15, 0.6], [-0.95, 0.62], [-1.5, 0.27]], 1.36, glass, 0.04));

  const stripe = new THREE.Mesh(new THREE.BoxGeometry(3.6, 0.05, 1.86), accent);
  stripe.position.set(-0.1, -0.05, 0);
  shell.add(stripe);
  for (const z of [-0.62, 0.62]) {
    const l = new THREE.Mesh(new THREE.BoxGeometry(0.06, 0.08, 0.38), lamp);
    l.position.set(2.15, -0.06, z);
    shell.add(l);
  }
  const rear = new THREE.Mesh(new THREE.BoxGeometry(0.05, 0.07, 1.5), tail);
  rear.position.set(-2.14, 0.06, 0);
  shell.add(rear);

  // Wheels
  const tire = new THREE.MeshStandardMaterial({ color: '#141518', roughness: 0.95 });
  const hub = new THREE.MeshStandardMaterial({ color: '#9aa3ad', roughness: 0.35, metalness: 0.8 });
  const wheels = [];
  for (const x of [1.35, -1.35]) {
    for (const z of [0.98, -0.98]) {
      const w = new THREE.Group();
      const t = new THREE.Mesh(new THREE.CylinderGeometry(0.36, 0.36, 0.3, 24), tire);
      t.rotation.x = Math.PI / 2;
      t.castShadow = true;
      const h = new THREE.Mesh(new THREE.CylinderGeometry(0.2, 0.2, 0.32, 6), hub);
      h.rotation.x = Math.PI / 2;
      w.add(t, h);
      w.position.set(x, -0.24, z);
      shell.add(w);
      wheels.push(w);
    }
  }

  // Jets: four lift pods on the side skirts, one boost nozzle at the back, two attitude puffers.
  // Visible jet hardware; hidden when a custom car model brings its own bodywork.
  const fittings = [];
  const metal = new THREE.MeshStandardMaterial({ color: '#4a5059', roughness: 0.4, metalness: 0.8 });
  const flameMat = new THREE.MeshBasicMaterial({ color: '#e8484b', transparent: true, opacity: 0.8, depthWrite: false, toneMapped: false });
  const flame = (dir) => {
    const geo = new THREE.ConeGeometry(0.13, 1, 14, 1, true);
    geo.translate(0, -0.5, 0); // tip at -1 along local y
    const m = new THREE.Mesh(geo, flameMat);
    m.quaternion.setFromUnitVectors(new THREE.Vector3(0, -1, 0), dir.clone().normalize());
    m.scale.setScalar(0.001);
    return m;
  };

  const liftJets = [];
  for (const x of [1.7, -1.7]) {
    for (const z of [1.12, -1.12]) {
      const pod = new THREE.Mesh(new THREE.CylinderGeometry(0.11, 0.14, 0.26, 12), metal);
      pod.position.set(x, -0.2, z);
      body.add(pod);
      fittings.push(pod);
      const f = flame(new THREE.Vector3(0, -1, 0));
      f.position.set(x, -0.33, z);
      body.add(f);
      liftJets.push(f);
    }
  }
  const nozzle = new THREE.Mesh(new THREE.CylinderGeometry(0.16, 0.22, 0.3, 14), metal);
  nozzle.rotation.z = Math.PI / 2;
  nozzle.position.set(-2.2, -0.05, 0);
  body.add(nozzle);
  fittings.push(nozzle);
  const boostJet = flame(new THREE.Vector3(-1, 0, 0));
  boostJet.position.set(-2.36, -0.05, 0);
  body.add(boostJet);
  const noseDown = flame(new THREE.Vector3(0, -1, 0));
  noseDown.position.set(1.9, -0.34, 0);
  const noseUp = flame(new THREE.Vector3(0, 1, 0));
  noseUp.position.set(1.6, 0.25, 0);
  const tailDown = flame(new THREE.Vector3(0, -1, 0));
  tailDown.position.set(-1.9, -0.34, 0);
  const tailUp = flame(new THREE.Vector3(0, 1, 0));
  tailUp.position.set(-1.6, 0.3, 0);
  body.add(noseDown, noseUp, tailDown, tailUp);

  const glow = new THREE.PointLight('#ff5a4f', 0, 9, 2);
  glow.position.set(0, -0.8, 0);
  root.add(glow);

  const grip = new THREE.Mesh(
    new THREE.PlaneGeometry(4.2, 2.2),
    new THREE.MeshBasicMaterial({ color: '#d23437', transparent: true, opacity: 0, depthWrite: false, toneMapped: false }),
  );
  grip.rotation.x = -Math.PI / 2;
  grip.position.y = -0.6;
  root.add(grip);

  const set = (mesh, amount, len, t) => {
    const flicker = amount > 0 ? 0.85 + 0.3 * Math.sin(t * 61 + mesh.id) * Math.sin(t * 37) : 0;
    const k = Math.max(0.001, amount * flicker);
    mesh.scale.set(k, len * k, k);
  };

  // Front wheels sit in a pivot that turns about the car's up axis, so they can steer while spinning.
  const UP = new THREE.Vector3(0, 1, 0);
  const steerable = (node) => {
    const parent = node.parent;
    root.updateMatrixWorld(true);
    const origin = parent.worldToLocal(body.localToWorld(new THREE.Vector3()));
    const axis = parent.worldToLocal(body.localToWorld(UP.clone())).sub(origin).normalize();
    const pivot = new THREE.Group();
    pivot.position.copy(node.position);
    parent.add(pivot);
    node.position.set(0, 0, 0);
    pivot.add(node);
    return { pivot, steerAxis: axis };
  };
  const spinner = (node, axis, radius, base, rear) => ({ node, axis, radius, base, rear, ...(rear ? {} : steerable(node)) });
  let spinners = wheels.map((w) => spinner(w, 'z', 0.36, 0, w.position.x < 0));
  // The rear axle keeps its own roll so the e-brake can lock it while the fronts keep turning.
  let lastRoll = 0, rearRoll = 0;

  return {
    root,
    nozzles: { lift: liftJets, boost: boostJet },
    // Replace the drawn car with a loaded model (see src/car-model.js for the expected layout).
    useModel(model, wheelNodes, opts) {
      shell.visible = false;
      for (const f of fittings) f.visible = false;
      body.add(model);
      if (wheelNodes.length) {
        root.updateMatrixWorld(true);
        const p = new THREE.Vector3();
        spinners = wheelNodes.map((node) => spinner(
          node,
          opts.wheelAxis,
          opts.wheelRadius,
          node.rotation[opts.wheelAxis],
          body.worldToLocal(node.getWorldPosition(p)).x < 0,
        ));
      }
    },
    // Stunt modes: a side-plane pose (x, y, pitch).
    update(sim, t) {
      root.rotation.order = 'XYZ';
      root.position.set(sim.x, sim.y, 0);
      root.rotation.set(0, 0, sim.theta);
      drive(sim.roll, sim.jets, t, false, 0);
    },
    // Highway: a full 3D pose — yaw about up, then pitch, then body roll.
    // steer: front wheel angle in rad, positive turns left.
    pose3d(pos, yaw, pitch, lean, roll, jets, t, rearLock = false, steer = 0) {
      root.rotation.order = 'YZX';
      root.position.set(pos.x, pos.y, pos.z);
      root.rotation.set(lean, yaw, pitch);
      drive(roll, jets, t, rearLock, steer);
    },
  };

  function drive(roll, j, t, rearLock, steer) {
    if (!rearLock) rearRoll += roll - lastRoll;
    lastRoll = roll;
    for (const w of spinners) {
      w.node.rotation[w.axis] = w.base - (w.rear ? rearRoll : roll) / w.radius;
      if (w.pivot) w.pivot.quaternion.setFromAxisAngle(w.steerAxis, steer);
    }
    for (const f of liftJets) set(f, j.lift ? 1 : 0, 1.6, t);
    set(boostJet, j.boost ? 1.4 : 0, 2.2, t);
    set(noseDown, j.spin > 0 ? 0.8 : 0, 0.7, t);
    set(tailUp, j.spin > 0 ? 0.8 : 0, 0.7, t);
    set(noseUp, j.spin < 0 ? 0.8 : 0, 0.7, t);
    set(tailDown, j.spin < 0 ? 0.8 : 0, 0.7, t);
    glow.intensity = (j.lift ? 18 : 0) + (j.boost ? 8 : 0);
    grip.material.opacity += ((j.grip ? 0.22 : 0) - grip.material.opacity) * 0.2;
  }
}
