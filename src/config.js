// Tunable physics. Every value here is exposed in the settings panel.
export const DEFAULTS = {
  gravity: 9.81,   // m/s²
  cruise: 22,      // target speed on flat ground, m/s
  climb: 6,        // target speed while gripping the ramp, m/s
  lift: 2.4,       // lift thrust, in g
  boost: 2.2,      // boost thrust, in g
  spin: 5,         // angular acceleration from attitude jets, rad/s²
  steady: 1.6,     // how hard the jets hold the current angle, 1/s
  fuel: 600,       // tank size, L
  burn: 180,       // lift burn rate, L/s (boost uses half, attitude jets 18%)
  landAngle: 28,   // max tilt for a clean touchdown, deg
  landSpeed: 7,    // max sink rate for a clean touchdown, m/s
  timeScale: 1,
};

export const SETTINGS = [
  { key: 'gravity', label: 'Gravity', unit: 'm/s²', min: 1, max: 20, step: 0.01 },
  { key: 'cruise', label: 'Cruise speed', unit: 'm/s', min: 10, max: 40, step: 1 },
  { key: 'climb', label: 'Climb speed', unit: 'm/s', min: 3, max: 14, step: 0.5 },
  { key: 'lift', label: 'Lift thrust', unit: 'g', min: 1, max: 4, step: 0.1 },
  { key: 'boost', label: 'Boost thrust', unit: 'g', min: 0.5, max: 4, step: 0.1 },
  { key: 'spin', label: 'Spin torque', unit: '', min: 1, max: 12, step: 0.5 },
  { key: 'steady', label: 'Stability', unit: '', min: 0, max: 4, step: 0.05 },
  { key: 'fuel', label: 'Fuel tank', unit: 'L', min: 100, max: 1500, step: 50 },
  { key: 'burn', label: 'Fuel burn', unit: 'L/s', min: 40, max: 300, step: 10 },
  { key: 'landAngle', label: 'Landing angle', unit: '°', min: 10, max: 60, step: 1 },
  { key: 'landSpeed', label: 'Landing speed', unit: 'm/s', min: 2, max: 15, step: 0.5 },
  { key: 'timeScale', label: 'Time scale', unit: '×', min: 0.1, max: 1, step: 0.05 },
];

export const PRESETS = {
  Default: {},
  Arcade: { lift: 3.2, boost: 2.8, spin: 7, steady: 2.8, landAngle: 38, landSpeed: 10, fuel: 1000 },
  Hard: { landAngle: 16, landSpeed: 5, steady: 0.4, fuel: 420 },
  'Low-G': { gravity: 2.5, lift: 1.7, boost: 1.3, burn: 90, spin: 3, landSpeed: 3.5 },
};

// Fraction of the lift burn rate used by the other jets.
export const BURN_SHARE = { lift: 1, boost: 0.5, spin: 0.18 };

export const DECK = 0.45;      // ramp deck thickness, m
export const DECK_WIDTH = 4.6; // ramp width, m

// One quarter-pipe with an overhang. Pieces: { line } or { arc: radius, turn: degrees, + = counter-clockwise }.
export const RUN_IN = 190;
export const TRACK = {
  origin: [-RUN_IN, 0],
  pieces: [{ line: RUN_IN }, { arc: 7, turn: 90 }, { line: 9 }, { arc: 5, turn: 90 }, { line: 3 }],
};

// A row of parked vehicles on the run-in. Sizes are ordinary road-vehicle dimensions.
const VEHICLES = [
  { label: 'compact', length: 4.2, width: 1.9, height: 1.45, color: '#c9b48a', kind: 'car' },
  { label: 'pickup', length: 5.7, width: 2.15, height: 1.95, color: '#5c6f7e', kind: 'pickup' },
  { label: 'box truck', length: 7.2, width: 2.45, height: 3.9, color: '#e6e3dc', kind: 'truck' },
  { label: 'SUV', length: 4.8, width: 2.0, height: 1.65, color: '#30363d', kind: 'car' },
  { label: 'sedan', length: 4.7, width: 1.9, height: 1.45, color: '#8e2f2f', kind: 'car' },
];

export const OBSTACLES = (() => {
  let x = -124;
  return VEHICLES.map((v) => {
    const o = { ...v, x0: x, x1: x + v.length, h: v.height };
    x += v.length + 1.6;
    return o;
  });
})();

// Both challenges share one course; they differ in where you start and where you should land.
export const CHALLENGES = {
  ramp: { key: 'ramp', name: 'Ramp', startS: RUN_IN - 7, zone: { x: -24, half: 5 } },
  jump: { key: 'jump', name: 'Jump', startS: 12, zone: { x: -76, half: 6 } },
};
