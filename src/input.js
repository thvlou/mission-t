const KEYS = {
  ArrowUp: 'up', KeyW: 'up',
  ArrowDown: 'down', KeyS: 'down',
  ArrowLeft: 'left', KeyA: 'left',
  ArrowRight: 'right', KeyD: 'right',
  Space: 'lift',
  ShiftLeft: 'shift', ShiftRight: 'shift',
  KeyE: 'boost',
};

// Keyboard and on-screen buttons share one held-state table.
export function createInput(onCommand) {
  const held = { up: false, down: false, left: false, right: false, lift: false, shift: false, boost: false };

  window.addEventListener('keydown', (e) => {
    if (e.target instanceof HTMLInputElement) return;
    const k = KEYS[e.code];
    if (k) {
      held[k] = true;
      e.preventDefault();
      onCommand('any');
      return;
    }
    if (e.repeat) return;
    if (e.code === 'KeyR' || e.code === 'Enter') onCommand('restart');
    else if (e.code === 'KeyC') onCommand('camera');
    else if (e.code === 'KeyM') onCommand('mode');
    else if (e.code === 'KeyG') onCommand('cars');
    else if (e.code === 'KeyP' || e.code === 'Escape') onCommand('pause');
  });
  window.addEventListener('keyup', (e) => {
    const k = KEYS[e.code];
    if (k) held[k] = false;
  });
  window.addEventListener('blur', () => {
    for (const k in held) held[k] = false;
  });

  for (const btn of document.querySelectorAll('[data-hold]')) {
    const k = btn.dataset.hold;
    const on = (e) => {
      e.preventDefault();
      btn.setPointerCapture?.(e.pointerId);
      held[k] = true;
      btn.classList.add('on');
      onCommand('any');
    };
    const off = () => {
      held[k] = false;
      btn.classList.remove('on');
    };
    btn.addEventListener('pointerdown', on);
    btn.addEventListener('pointerup', off);
    btn.addEventListener('pointercancel', off);
    btn.addEventListener('lostpointercapture', off);
  }

  return {
    held,
    read() {
      return {
        throttle: (held.up ? 1 : 0) - (held.down ? 1 : 0),
        spin: (held.left ? 1 : 0) - (held.right ? 1 : 0),
        lift: held.lift,
        boost: held.boost,
        // Shift is the e-brake on the highway; the stunt modes ignore it.
        shift: held.shift,
      };
    },
  };
}
