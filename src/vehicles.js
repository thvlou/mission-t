// The Mission T garage. Model dimensions are visual only; every car uses the same arcade physics.
// The fleet is original Mission T design (built by blender/vertigo_fleet.py).
//
// theme: the in-game look that follows the car. gauge picks the speedometer design (src/gauge.js);
// grad is its fill, boost the more saturated fill it switches to while boosting; flame and lift
// colour the boost and jump jets, trail names that pair in the Cars viewer.
// exhaust: the tail pipes (radius, and [across, height above the road] per tip, metres); the boost
// burns out of them. Tips are fitted onto each model's rear at load (src/car-model.js).
export const VEHICLES = [
  {
    id: 'vertigo-gt', name: 'GT', type: 'Mid-engine coupe', color: 'Pearl White', hex: '#e8e8e4',
    length: 4.736, wheelRadius: 0.36,
    theme: { gauge: 'classic', trail: 'Red / Gold', accent: '#d23437', grad: ['#ffe2a8', '#ff9a5c', '#f05a3a', '#d23437'], boost: ['#ff9e57', '#ff4d2e', '#ff1a3c', '#c8001e'], flame: '#ff2d3d', lift: '#ffb02e' },
    exhaust: { r: 0.05, tips: [[0.13, 0.38], [-0.13, 0.38]] },
  },
  {
    id: 'vertigo-arc', name: 'Arc', type: 'Open-top two-seater', color: 'Sky Blue', hex: '#64a8c9', length: 4.62, wheelRadius: 0.355,
    theme: { gauge: 'ring', trail: 'Sky / Aqua', accent: '#1f86c4', grad: ['#cdeefe', '#7ccbf2', '#3aa6e0', '#1f86c4'], boost: ['#5fd2ff', '#00a8ff', '#0080ff', '#0052e0'], flame: '#1aa3ff', lift: '#2ee0dc' },
    exhaust: { r: 0.042, tips: [[0.48, 0.3], [-0.48, 0.3]] },
  },
  {
    id: 'vertigo-apex', name: 'Apex', type: 'Mid-engine wedge', color: 'Lavender', hex: '#7d738d', length: 4.50, wheelRadius: 0.355,
    theme: { gauge: 'segments', trail: 'Violet / Pink', accent: '#6a4bd0', grad: ['#e6dcff', '#b9a2f7', '#8f6fe6', '#6a4bd0'], boost: ['#c084ff', '#9d4dff', '#7a1fff', '#5a00e6'], flame: '#8a4dff', lift: '#ff4fd8' },
    exhaust: { r: 0.038, tips: [[0.07, 0.4], [-0.07, 0.4], [0.2, 0.4], [-0.2, 0.4]] },
  },
  {
    id: 'vertigo-grand', name: 'Grand', type: 'Four-door fastback', color: 'Forest Green', hex: '#063722', length: 4.96, wheelRadius: 0.37,
    theme: { gauge: 'minimal', trail: 'Emerald / Lime', accent: '#16865a', grad: ['#cfeedd', '#86d3ab', '#3cb07f', '#16865a'], boost: ['#5cffb0', '#00e68a', '#00c06e', '#00894c'], flame: '#10d084', lift: '#a6ef4a' },
    exhaust: { r: 0.038, tips: [[0.4, 0.31], [0.53, 0.31], [-0.4, 0.31], [-0.53, 0.31]] },
  },
  {
    id: 'vertigo-terra', name: 'Terra', type: 'Coupe SUV', color: 'Crimson', hex: '#790113', length: 4.80, wheelRadius: 0.40,
    theme: { gauge: 'rugged', trail: 'Ember / Amber', accent: '#e0482a', grad: ['#ffe0b8', '#ffae6b', '#ff7a3d', '#e0482a'], boost: ['#ffb340', '#ff7a00', '#ff4d00', '#e62600'], flame: '#ff6a00', lift: '#ffc400' },
    exhaust: { r: 0.055, tips: [[0.56, 0.56], [-0.56, 0.56]] },
  },
  {
    id: 'vertigo-r', name: 'R', type: 'Track coupe', color: 'Cool Silver', hex: '#979fac', length: 4.68, wheelRadius: 0.355,
    theme: { gauge: 'track', trail: 'Yellow / Teal', accent: '#f0a500', grad: ['#fff2b8', '#ffe066', '#ffc83d', '#f0a500'], boost: ['#fff200', '#ffd000', '#ffaa00', '#ff7b00'], flame: '#ffc800', lift: '#00d9bf' },
    exhaust: { r: 0.07, tips: [[0, 0.43]] },
  },
].map(v => ({ ...v, url: v.url || `assets/vehicles/${v.id}.glb`, preview: v.preview || `renders/vehicles/${v.id}_front.png` }));

export function getVehicle(id) {
  return VEHICLES.find(v => v.id === id) || VEHICLES[0];
}
