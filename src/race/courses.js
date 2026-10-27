// Courses a race room can run. The highway is the endless procedural road (a fresh one every
// race); a circuit is a real closed track from assets/tracks, raced over a number of laps.
// server/room-core.js keeps the same list of ids.
export const COURSES = {
  highway: { id: 'highway', name: 'Highway', note: '5 km sprint', length: 5000 },
  ridgeline: { id: 'ridgeline', name: 'Ridgeline', note: '2 laps · 7.0 km', track: 'ridgeline', laps: 2 },
  'harbor-run': { id: 'harbor-run', name: 'Harbor Run', note: '2 laps · ~1 min/lap · Dock Hop', track: 'harbor-run', laps: 2 },
  'canyon-flight': { id: 'canyon-flight', name: 'Canyon Flight', note: '2 laps · ~1 min/lap · Glide Cut', track: 'canyon-flight', laps: 2 },
  'alpine-ring': { id: 'alpine-ring', name: 'Alpine Ring', note: '2 laps · ~1 min/lap · Ridge Leap', track: 'alpine-ring', laps: 2 },
};

export const courseOf = (id) => COURSES[id] || COURSES.highway;
