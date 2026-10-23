import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import { RoomEnvironment } from 'three/addons/environments/RoomEnvironment.js';
import { VEHICLES } from './vehicles.js';
import { buildVehicleModel, preloadVehicle } from './car-model.js';

// The Cars viewer: a studio turntable with its own renderer. Drag to orbit 360°, scroll or pinch
// (or the − / + control) to zoom, ◀ ▶ or the arrow keys to switch, Enter to drive the car shown.
const GAUGE_NAMES = { classic: 'Classic', ring: 'Ring', segments: 'Segment', minimal: 'Chrono', rugged: 'Rugged', track: 'Track' };
const EASE = 'cubic-bezier(0.32, 0.72, 0, 1)';
const DIST = { min: 5.2, max: 13.5, start: 8.4 };
const FLOOR = -0.6; // car-model.js puts the bottom of every car 0.6 m below its origin
const easeOut = (t) => 1 - (1 - t) ** 4;
const pad2 = (n) => String(n).padStart(2, '0');
const esc = (s) => String(s ?? '').replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

const ICON = {
  close: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18"/></svg>',
  prev: '<svg viewBox="0 0 24 24"><path d="M15 4.5 7.5 12l7.5 7.5"/></svg>',
  next: '<svg viewBox="0 0 24 24"><path d="M9 4.5 16.5 12 9 19.5"/></svg>',
  go: '<svg viewBox="0 0 24 24"><path d="M7 17 17 7M9 7h8v8"/></svg>',
  check: '<svg viewBox="0 0 24 24"><path d="M5 12.5l4.5 4.5L19 7.5"/></svg>',
  orbit: '<svg viewBox="0 0 24 24"><ellipse cx="12" cy="12" rx="9.5" ry="4"/><path d="M17.5 5.5 19.6 8l-3 .9"/></svg>',
};

export class CarsModal {
  // actions: { current() → car id, onPick(id), onOpen(), onClose() }
  constructor(actions) {
    this.actions = actions;
    this.index = 0;
    this.token = 0;
    this.moves = [];
    this.car = null;
    this.el = buildDom();
    document.body.append(this.el);
    this.q = (sel) => this.el.querySelector(sel);
    this.el.addEventListener('click', (e) => {
      const act = e.target.closest('[data-act]')?.dataset.act;
      if (!act) return;
      if (act === 'close') this.close();
      else if (act === 'prev') this.step(-1);
      else if (act === 'next') this.step(1);
      else if (act === 'pick') this.pick();
      else if (act === 'zoom-in') this.zoom(0.8);
      else if (act === 'zoom-out') this.zoom(1.25);
      else if (act === 'dot') this.show(Number(e.target.closest('[data-i]').dataset.i));
    });
    // Capture phase: while the viewer is open the game never sees a key.
    window.addEventListener('keydown', (e) => {
      if (!this.isOpen || e.target instanceof HTMLInputElement) return;
      const k = e.key;
      if (k === 'Tab') return this.trapFocus(e);
      e.stopPropagation();
      if (e.repeat && !k.startsWith('Arrow')) return;
      if (k === 'Escape') this.close();
      else if (k === 'ArrowLeft' || k === 'a' || k === 'A') this.step(-1);
      else if (k === 'ArrowRight' || k === 'd' || k === 'D') this.step(1);
      else if (k === 'Enter') { e.preventDefault(); this.pick(); }
      else if (k === '+' || k === '=') this.zoom(0.8);
      else if (k === '-' || k === '_') this.zoom(1.25);
      else return;
      e.preventDefault();
    }, { capture: true });
  }

  get isOpen() {
    return !this.el.hidden;
  }

  open() {
    if (this.isOpen) return;
    this.actions.onOpen?.();
    this.el.hidden = false;
    this.el.classList.remove('closing');
    this.el.getBoundingClientRect(); // start the entrance from its first frame
    this.el.classList.add('open');
    this.initGl();
    this.fit();
    const id = this.actions.current();
    this.show(Math.max(0, VEHICLES.findIndex((v) => v.id === id)), 0, true);
    this.camera.position.copy(this.home());
    this.zoomGoal = null;
    this.controls.update();
    this.resumeSpin(0);
    this.last = performance.now();
    cancelAnimationFrame(this.raf);
    this.raf = requestAnimationFrame(() => this.frame());
    setTimeout(() => this.q('.cars-cta').focus({ preventScroll: true }), 60);
  }

  close() {
    if (!this.isOpen || this.el.classList.contains('closing')) return;
    this.el.classList.remove('open');
    this.el.classList.add('closing');
    clearTimeout(this.closeTimer);
    this.closeTimer = setTimeout(() => {
      this.el.hidden = true;
      this.el.classList.remove('closing');
      cancelAnimationFrame(this.raf);
      document.activeElement?.blur?.();
      this.actions.onClose?.();
    }, 320);
  }

  step(dir) {
    this.show(this.index + dir, dir);
  }

  pick() {
    const v = VEHICLES[this.index];
    if (v.id !== this.actions.current()) this.actions.onPick(v.id);
    this.paintCta();
    this.close();
  }

  // ---------- text ----------
  async show(i, dir = 0, instant = false) {
    const n = VEHICLES.length;
    this.index = ((i % n) + n) % n;
    const v = VEHICLES[this.index];
    this.paintText(v, dir, instant);
    const token = ++this.token;
    if (this.car) this.leave(this.car, dir);
    this.car = null;
    this.el.classList.add('loading');
    let built;
    try {
      built = await buildVehicleModel(v.id);
    } catch (err) {
      console.warn('Car model failed to load', err);
      if (token === this.token) this.el.classList.remove('loading');
      return;
    }
    if (token !== this.token || !this.isOpen) return;
    this.el.classList.remove('loading');
    this.enter(built.holder, dir);
    // Warm the neighbours so the next arrow press is instant.
    for (const d of [1, -1]) preloadVehicle(VEHICLES[(this.index + d + n) % n].id);
  }

  paintText(v, dir, instant) {
    const t = v.theme;
    this.el.style.setProperty('--car-tint', v.hex);
    this.el.style.setProperty('--car-accent', t.accent);
    this.q('.cars-count').textContent = `${pad2(this.index + 1)} / ${pad2(VEHICLES.length)}`;
    this.q('.cars-specs').innerHTML = `
      <div><dt>Paint</dt><dd><i style="background:${esc(v.hex)}"></i>${esc(v.color)}</dd></div>
      <div><dt>Boost · Jump</dt><dd><i style="background:${esc(t.flame)}"></i><i style="background:${esc(t.lift)}"></i>${esc(t.trail)}</dd></div>
      <div><dt>Speedometer</dt><dd>${esc(GAUGE_NAMES[t.gauge] || t.gauge)}</dd></div>`;
    for (const d of this.el.querySelectorAll('.cars-dots button')) {
      const on = Number(d.dataset.i) === this.index;
      d.classList.toggle('on', on);
      d.setAttribute('aria-current', on ? 'true' : 'false');
    }
    this.paintCta();
    const swap = (sel, html) => {
      const node = this.q(sel);
      node.innerHTML = html;
      if (instant) return;
      node.animate(
        [{ opacity: 0, transform: `translate3d(${dir * 36}px, ${dir ? 0 : 14}px, 0)` }, { opacity: 1, transform: 'none' }],
        { duration: 720, easing: EASE },
      );
    };
    swap('.cars-name', `<span class="cars-type">${esc(v.type)}</span><h2 id="carsTitle">${esc(v.name)}</h2>`);
    swap('.cars-mark', esc(v.name));
    if (!instant) {
      this.q('.cars-specs').animate([{ opacity: 0, transform: 'translateY(8px)' }, { opacity: 1, transform: 'none' }], { duration: 600, easing: EASE, delay: 60, fill: 'backwards' });
    }
  }

  paintCta() {
    const btn = this.q('.cars-cta');
    const mine = VEHICLES[this.index].id === this.actions.current();
    btn.classList.toggle('current', mine);
    btn.innerHTML = mine
      ? `<span>Driving this car</span><i>${ICON.check}</i>`
      : `<span>Drive this car</span><i>${ICON.go}</i>`;
  }

  trapFocus(e) {
    const items = [...this.el.querySelectorAll('button')].filter((b) => b.offsetParent);
    const first = items[0], last = items[items.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  }

  // ---------- 3D ----------
  initGl() {
    if (this.renderer) return;
    const canvas = this.q('canvas');
    const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    renderer.setPixelRatio(Math.min(2, window.devicePixelRatio));
    renderer.toneMapping = THREE.ACESFilmicToneMapping;
    renderer.toneMappingExposure = 1.02;
    renderer.shadowMap.enabled = true;
    renderer.shadowMap.type = THREE.PCFSoftShadowMap;
    this.renderer = renderer;

    const scene = new THREE.Scene();
    const pmrem = new THREE.PMREMGenerator(renderer);
    scene.environment = pmrem.fromScene(new RoomEnvironment(), 0.04).texture;
    scene.add(new THREE.HemisphereLight('#ffffff', '#d8d4ce', 0.55));
    const key = new THREE.DirectionalLight('#ffffff', 1.9);
    key.position.set(3.5, 9, 4.5);
    key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -5, right: 5, top: 5, bottom: -5, near: 1, far: 30 });
    key.shadow.bias = -0.0004;
    key.shadow.radius = 4;
    scene.add(key);
    const fill = new THREE.DirectionalLight('#ffffff', 0.45);
    fill.position.set(-6, 4, -5);
    scene.add(fill);

    // Floor: a catch-only shadow plus a soft contact blob, so the car sits on the card itself.
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(40, 40), new THREE.ShadowMaterial({ opacity: 0.16 }));
    floor.rotation.x = -Math.PI / 2;
    floor.position.y = FLOOR;
    floor.receiveShadow = true;
    scene.add(floor);
    const blob = new THREE.Mesh(
      new THREE.PlaneGeometry(6.4, 3.2),
      new THREE.MeshBasicMaterial({ map: blobTexture(), transparent: true, depthWrite: false, toneMapped: false }),
    );
    blob.rotation.x = -Math.PI / 2;
    blob.position.y = FLOOR + 0.002;
    scene.add(blob);
    this.blob = blob;

    const camera = new THREE.PerspectiveCamera(26, 2, 0.1, 100);
    const controls = new OrbitControls(camera, canvas);
    controls.enablePan = false;
    controls.enableDamping = true;
    controls.dampingFactor = 0.075;
    controls.rotateSpeed = 0.65;
    controls.zoomSpeed = 0.7;
    controls.minDistance = DIST.min;
    controls.maxDistance = DIST.max;
    controls.minPolarAngle = Math.PI * 0.16;
    controls.maxPolarAngle = Math.PI * 0.485;
    controls.target.set(0, -0.08, 0);
    controls.autoRotateSpeed = 0.55;
    controls.addEventListener('start', () => {
      controls.autoRotate = false;
      clearTimeout(this.spinTimer);
      this.zoomGoal = null;
      this.el.classList.add('touched');
    });
    controls.addEventListener('end', () => this.resumeSpin(3500));
    Object.assign(this, { scene, camera, controls });
    new ResizeObserver(() => this.fit()).observe(this.q('.cars-stage'));
  }

  // Front three-quarter view: the cars face +x. Tall stages (phones) need the camera further back.
  frameDist() {
    return DIST.start * THREE.MathUtils.clamp(1.7 / this.camera.aspect, 1, 1.75);
  }

  home() {
    const az = THREE.MathUtils.degToRad(38), polar = THREE.MathUtils.degToRad(74);
    return new THREE.Vector3().setFromSphericalCoords(this.frameDist(), polar, az + Math.PI / 2).add(this.controls.target);
  }

  resumeSpin(ms) {
    clearTimeout(this.spinTimer);
    this.spinTimer = setTimeout(() => { this.controls.autoRotate = true; }, ms);
  }

  fit() {
    if (!this.renderer) return;
    const stage = this.q('.cars-stage');
    const w = stage.clientWidth, h = stage.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    // Narrow screens pull the camera back so the whole car stays in frame.
    this.camera.fov = w / h < 1.2 ? 34 : 26;
    this.camera.updateProjectionMatrix();
    this.controls.maxDistance = Math.max(DIST.max, this.frameDist() * 1.2);
  }

  zoom(f) {
    const d = this.camera.position.distanceTo(this.controls.target);
    this.zoomGoal = THREE.MathUtils.clamp((this.zoomGoal ?? d) * f, DIST.min, this.controls.maxDistance);
    this.controls.autoRotate = false;
    this.resumeSpin(3500);
  }

  // Slide direction follows the screen: "next" leaves to the left and arrives from the right.
  screenRight() {
    const r = new THREE.Vector3().setFromMatrixColumn(this.camera.matrixWorld, 0);
    r.y = 0;
    return r.lengthSq() ? r.normalize() : r.set(1, 0, 0);
  }

  enter(holder, dir) {
    const g = new THREE.Group();
    g.add(holder);
    this.scene.add(g);
    this.car = g;
    const from = this.screenRight().multiplyScalar(dir * 7.5);
    if (!dir) from.set(0, 0.25, 0);
    g.position.copy(from);
    g.rotation.y = dir * 0.5;
    this.blob.scale.setScalar(dir ? 0.6 : 0.9);
    this.moves.push({ obj: g, from, to: new THREE.Vector3(), rot: [dir * 0.5, 0], t: 0, dur: dir ? 0.9 : 0.8, blob: true });
  }

  leave(g, dir) {
    const to = this.screenRight().multiplyScalar(-(dir || 1) * 7.5);
    this.moves = this.moves.filter((m) => m.obj !== g);
    this.moves.push({ obj: g, from: g.position.clone(), to, rot: [g.rotation.y, -(dir || 1) * 0.4], t: 0, dur: 0.5, done: () => this.scene.remove(g) });
  }

  frame() {
    if (!this.isOpen) return;
    this.raf = requestAnimationFrame(() => this.frame());
    const now = performance.now();
    const dt = Math.min(0.05, (now - this.last) / 1000);
    this.last = now;
    for (const m of [...this.moves]) {
      m.t += dt / m.dur;
      const k = easeOut(Math.min(1, m.t));
      m.obj.position.lerpVectors(m.from, m.to, k);
      m.obj.rotation.y = m.rot[0] + (m.rot[1] - m.rot[0]) * k;
      if (m.blob) this.blob.scale.setScalar(0.6 + 0.4 * k);
      if (m.t >= 1) {
        this.moves.splice(this.moves.indexOf(m), 1);
        m.done?.();
      }
    }
    if (!this.moves.some((m) => m.blob) && this.car) this.blob.scale.setScalar(1);
    const target = this.controls.target;
    if (this.zoomGoal != null) {
      const off = this.camera.position.clone().sub(target);
      const d = off.length();
      const nd = d + (this.zoomGoal - d) * (1 - Math.exp(-dt * 9));
      this.camera.position.copy(target).add(off.setLength(nd));
      if (Math.abs(nd - this.zoomGoal) < 0.005) this.zoomGoal = null;
    }
    this.controls.update();
    const far = this.controls.maxDistance;
    const level = (far - this.camera.position.distanceTo(target)) / (far - DIST.min);
    this.q('.cars-zoom i b').style.transform = `scaleX(${Math.max(0.04, level).toFixed(3)})`;
    this.renderer.render(this.scene, this.camera);
  }
}

function blobTexture() {
  const c = document.createElement('canvas');
  c.width = 256;
  c.height = 128;
  const g = c.getContext('2d');
  const grad = g.createRadialGradient(128, 64, 4, 128, 64, 124);
  grad.addColorStop(0, 'rgba(18,19,22,0.42)');
  grad.addColorStop(0.45, 'rgba(18,19,22,0.16)');
  grad.addColorStop(1, 'rgba(18,19,22,0)');
  g.setTransform(1, 0, 0, 0.5, 0, 32);
  g.fillStyle = grad;
  g.fillRect(0, -64, 256, 256);
  const tex = new THREE.CanvasTexture(c);
  tex.colorSpace = THREE.SRGBColorSpace;
  return tex;
}

function buildDom() {
  const el = document.createElement('div');
  el.className = 'cars';
  el.hidden = true;
  el.setAttribute('role', 'dialog');
  el.setAttribute('aria-modal', 'true');
  el.setAttribute('aria-labelledby', 'carsTitle');
  el.innerHTML = `
    <div class="cars-scrim" data-act="close"></div>
    <div class="cars-shell">
      <div class="cars-core">
        <header class="cars-top">
          <span class="cars-tag"><i></i>Cars<em class="cars-count">01 / 06</em></span>
          <button type="button" class="cars-close" data-act="close" aria-label="Close">${ICON.close}</button>
        </header>
        <div class="cars-stage">
          <div class="cars-mark" aria-hidden="true"></div>
          <canvas aria-label="Car preview. Drag to look around, scroll to zoom."></canvas>
          <button type="button" class="cars-arrow prev" data-act="prev" aria-label="Previous car"><span>${ICON.prev}</span></button>
          <button type="button" class="cars-arrow next" data-act="next" aria-label="Next car"><span>${ICON.next}</span></button>
          <p class="cars-help">${ICON.orbit}<span>Drag to look around · Scroll to zoom</span></p>
          <nav class="cars-dots" aria-label="Cars">${VEHICLES.map((v, i) => `<button type="button" data-act="dot" data-i="${i}" aria-label="${esc(v.name)}"><b></b></button>`).join('')}</nav>
          <div class="cars-zoom" role="group" aria-label="Zoom">
            <button type="button" data-act="zoom-out" aria-label="Zoom out"><svg viewBox="0 0 24 24"><path d="M6 12h12"/></svg></button>
            <i><b></b></i>
            <button type="button" data-act="zoom-in" aria-label="Zoom in"><svg viewBox="0 0 24 24"><path d="M6 12h12M12 6v12"/></svg></button>
          </div>
          <span class="cars-wait" aria-hidden="true"></span>
        </div>
        <footer class="cars-info">
          <dl class="cars-specs"></dl>
          <div class="cars-name"></div>
          <div class="cars-act"><button type="button" class="cars-cta" data-act="pick"></button></div>
        </footer>
      </div>
    </div>`;
  return el;
}
