// Writes the six engines record_all.py records into engine-sim's assets/engines/vertigo/ (and a copy in
// engines/ here): the stock F136, LS and LFA scripts, a flat-six the stock set lacks (reusing the F136
// script's head, fuel and vehicle nodes), and two road V12s from the 412 T2 script.
// A W16 (w16.mr) is generated too but not recorded: sixteen cylinders cannot run in real time here.
// Every engine gets a simulation rate this PC can run in real time: when engine-sim falls behind
// (RT/DT under 100%) its audio buffer runs dry and the recording stutters or repeats.
// Ignition/cam timing follows the F136 convention: a cylinder on journal j in a bank at angle b
// reaches TDC at crank angle j + tdc - 90 - b, so j = fire - tdc + 90 + b.
import { readFileSync, writeFileSync, mkdirSync } from 'node:fs';
import { pathToFileURL } from 'node:url';

const ES = process.env.ENGINE_SIM_DIR
  ? pathToFileURL(process.env.ENGINE_SIM_DIR.replace(/[\/]?$/, '/assets/engines/'))
  : new URL('engine-sim-v0.1.14a/assets/engines/', import.meta.url);
const f136 = readFileSync(new URL('atg-video-2/08_ferrari_f136_v8.mr', ES), 'utf8').replace(/\r\n/g, '\n');
const cut = (from, to) => { const a = f136.indexOf(from), b = f136.indexOf(to, a); if (a < 0 || b < 0) throw new Error(from); return f136.slice(a, b); };
const HEAD = cut('private node f136_head', 'private node f136_camshaft');
const FUEL = cut('private node turbulence_to_flame_speed_ratio', 'public node f136_v8');
const VEHICLE = cut('private node mustang_vehicle', 'public node main');
const mod = (x) => ((x % 360) + 360) % 360;

function engineScript(spec) {
  const { id, name, bore, stroke, rodLength, redline, revLimit, crankMass, flywheelMass, tdc, banks, firing, exhaustVolume, exhaustLength, primaryLength, plenum, intakeFlow, lobe, idlePlate, simFreq } = spec;
  // firing: [{ bank, index }] in firing order, evenly spaced over 720 degrees.
  const n = firing.length, gap = 720 / n;
  const cyl = banks.map(() => []);
  firing.forEach(({ bank, index }, k) => { cyl[bank][index] = { fire: k * gap, wire: k + 1 }; });
  for (const c of cyl.flat()) if (!c) throw new Error(id + ': firing order misses a cylinder');
  cyl.forEach((list, b) => list.forEach((c) => { c.journal = mod(c.fire - tdc + 90 + banks[b]); }));

  const wires = `private node wires {\n${Array.from({ length: n }, (_, i) => `    output wire${i + 1}: ignition_wire();`).join('\n')}\n}\n\n`;
  const cams = banks.map((_, b) => `    output intake_cam_${b}: _intake_cam_${b};\n    output exhaust_cam_${b}: _exhaust_cam_${b};`).join('\n');
  const camDefs = banks.map((_, b) => `    camshaft _intake_cam_${b}(params, lobe_profile: intake_lobe_profile)\n    camshaft _exhaust_cam_${b}(params, lobe_profile: exhaust_lobe_profile)`).join('\n');
  const lobes = cyl.map((list, b) =>
    `    _exhaust_cam_${b}\n${list.map((c) => `        .add_lobe(rot360 - exhaust_lobe_center + ${c.fire} * units.deg)`).join('\n')}\n` +
    `    _intake_cam_${b}\n${list.map((c) => `        .add_lobe(rot360 + intake_lobe_center + ${c.fire} * units.deg)`).join('\n')}`).join('\n');
  const camshaft = `private node ${id}_camshaft {
    input lobe_profile;
    input intake_lobe_profile: lobe_profile;
    input exhaust_lobe_profile: lobe_profile;
    input lobe_separation: 114 * units.deg;
    input intake_lobe_center: lobe_separation;
    input exhaust_lobe_center: lobe_separation;
    input advance: 0 * units.deg;
    input base_radius: 0.5 * units.inch;

${cams}

    camshaft_parameters params (
        advance: advance,
        base_radius: base_radius
    )

${camDefs}

    label rot360(360 * units.deg)

${lobes}
}

`;
  const journals = cyl.flatMap((list, b) => list.map((c, i) => `    rod_journal rj_${b}_${i}(angle: ${c.journal} * units.deg)`)).join('\n');
  const addJournals = cyl.flatMap((list, b) => list.map((_, i) => `        .add_rod_journal(rj_${b}_${i})`)).join('\n');
  const exhausts = banks.map((_, b) => `    exhaust_system exhaust${b}(
        es_params,
        audio_volume: ${exhaustVolume} * ${(1 - b * 0.04).toFixed(2)},
        length: ${exhaustLength + b * 4} * units.inch,
        impulse_response: ir_lib.mild_exhaust_0_reverb
    )`).join('\n');
  const bankDefs = banks.map((a, b) => `    cylinder_bank b${b}(bank_params, angle: ${a} * units.deg)`).join('\n');
  const atten = [0.9, 0.8, 1.1, 1.0, 0.85, 0.95];
  const bankCyls = cyl.map((list, b) => `    b${b}
${list.map((c, i) => `        .add_cylinder(
            piston: piston(piston_params, blowby: k_28inH2O(0.0)),
            connecting_rod: connecting_rod(cr_params),
            rod_journal: rj_${b}_${i},
            intake: intake,
            exhaust_system: exhaust${b},
            ignition_wire: wires.wire${c.wire},
            sound_attenuation: ${atten[(i + b) % atten.length]},
            primary_length: ${primaryLength[(i + b) % primaryLength.length]} * units.cm
        )`).join('\n')}
        .set_cylinder_head(
            f136_head(
                intake_camshaft: camshaft.intake_cam_${b},
                exhaust_camshaft: camshaft.exhaust_cam_${b},
                flip_display: ${banks[b] > 0 ? 'true' : 'false'},
                flow_attenuation: 1.0)
        )`).join('\n');
  const wiresOrder = firing.map((_, k) => `            .connect_wire(wires.wire${k + 1}, ${k * gap} * units.deg)`).join('\n');

  return `import "engine_sim.mr"

units units()
constants constants()
impulse_response_library ir_lib()
label cycle(2 * 360 * units.deg)

${wires}${HEAD}${camshaft}${FUEL}public node ${id} {
    alias output __out: engine;

    engine engine(
        name: "${name}",
        starter_torque: 200 * units.lb_ft,
        starter_speed: 200 * units.rpm,
        redline: ${redline} * units.rpm,
        throttle_gamma: 2.0,
        fuel: fuel(
            max_burning_efficiency: 1.0,
            turbulence_to_flame_speed_ratio: turbulence_to_flame_speed_ratio()
        ),
        hf_gain: 0.01,
        noise: 1.0,
        jitter: 0.15,
        simulation_frequency: ${simFreq}
    )

    wires wires()

    label stroke(${stroke} * units.mm)
    label bore(${bore} * units.mm)
    label rod_length(${rodLength} * units.mm)
    label rod_mass(50 * units.g)
    label compression_height(1.0 * units.inch)
    label crank_mass(${crankMass} * units.lb)
    label flywheel_mass(${flywheelMass} * units.lb)
    label flywheel_radius(8 * units.inch)

    label crank_moment(
        1.5 * disk_moment_of_inertia(mass: crank_mass, radius: stroke)
    )
    label flywheel_moment(
        disk_moment_of_inertia(mass: flywheel_mass, radius: flywheel_radius)
    )
    label other_moment(
        disk_moment_of_inertia(mass: 1 * units.kg, radius: 1.0 * units.cm)
    )

    crankshaft c0(
        throw: stroke / 2,
        flywheel_mass: flywheel_mass,
        mass: crank_mass,
        friction_torque: 20.0 * units.lb_ft,
        moment_of_inertia:
            crank_moment + flywheel_moment + other_moment,
        position_x: 0.0,
        position_y: 0.0,
        tdc: ${tdc} * units.deg
    )

${journals}
    c0
${addJournals}

    piston_parameters piston_params(
        mass: (100) * units.g,
        compression_height: compression_height,
        wrist_pin_position: 0.0,
        displacement: 0.0
    )

    connecting_rod_parameters cr_params(
        mass: rod_mass,
        moment_of_inertia: rod_moment_of_inertia(
            mass: rod_mass,
            length: rod_length
        ),
        center_of_mass: 0.0,
        length: rod_length
    )

    intake intake(
        plenum_volume: ${plenum} * units.L,
        plenum_cross_section_area: 20.0 * units.cm2,
        intake_flow_rate: k_carb(${intakeFlow}),
        runner_flow_rate: k_carb(100.0),
        runner_length: 12.0 * units.inch,
        idle_flow_rate: k_carb(0.0),
        idle_throttle_plate_position: ${idlePlate},
        velocity_decay: 0.5
    )

    exhaust_system_parameters es_params(
        outlet_flow_rate: k_carb(1000.0),
        primary_tube_length: 29.0 * units.inch,
        primary_flow_rate: k_carb(600.0),
        velocity_decay: 0.5
    )

${exhausts}

    cylinder_bank_parameters bank_params(
        bore: bore,
        deck_height: stroke / 2 + rod_length + compression_height
    )

${bankDefs}
${bankCyls}

    engine
${banks.map((_, b) => `        .add_cylinder_bank(b${b})`).join('\n')}

    engine.add_crankshaft(c0)

    harmonic_cam_lobe intake_lobe(
        duration_at_50_thou: ${lobe} * units.deg,
        gamma: 0.9,
        lift: 551 * units.thou,
        steps: 256
    )

    harmonic_cam_lobe exhaust_lobe(
        duration_at_50_thou: ${lobe} * units.deg,
        gamma: 0.9,
        lift: 551 * units.thou,
        steps: 256
    )

    ${id}_camshaft camshaft(
        lobe_profile: "N/A",

        intake_lobe_profile: intake_lobe,
        exhaust_lobe_profile: exhaust_lobe,
        intake_lobe_center: 116 * units.deg,
        exhaust_lobe_center: 116 * units.deg,
        base_radius: 1.0 * units.inch
    )

    function timing_curve(1000 * units.rpm)
    timing_curve
        .add_sample(0000 * units.rpm, 12 * units.deg)
        .add_sample(1000 * units.rpm, 12 * units.deg)
        .add_sample(2000 * units.rpm, 20 * units.deg)
        .add_sample(3000 * units.rpm, 30 * units.deg)
        .add_sample(4000 * units.rpm, 38 * units.deg)
        .add_sample(5000 * units.rpm, 40 * units.deg)
        .add_sample(6000 * units.rpm, 40 * units.deg)
        .add_sample(7000 * units.rpm, 40 * units.deg)
        .add_sample(8000 * units.rpm, 40 * units.deg)
        .add_sample(9000 * units.rpm, 40 * units.deg)

    ignition_module ignition_module(
        timing_curve: timing_curve,
        rev_limit: ${revLimit} * units.rpm,
        limiter_duration: 0.1)
    ignition_module
${wiresOrder}

    engine.add_ignition_module(ignition_module)
}

${VEHICLE}public node main {
    run(
        engine: ${id}(),
        vehicle: mustang_vehicle(),
        transmission: mustang_transmission()
    )
}

main()
`;
}

// Porsche-style 4.0 flat-six: banks opposed, firing 1-6-2-4-3-5 (left 1-3, right 4-6).
const flat6 = engineScript({
  id: 'vertigo_flat6', name: 'Vertigo Arc [Flat-6]',
  bore: 102, stroke: 81.5, rodLength: 135, redline: 9000, revLimit: 9300,
  crankMass: 45, flywheelMass: 18, tdc: 90, banks: [90, -90],
  firing: [{ bank: 0, index: 0 }, { bank: 1, index: 2 }, { bank: 0, index: 1 }, { bank: 1, index: 0 }, { bank: 0, index: 2 }, { bank: 1, index: 1 }],
  exhaustVolume: 0.25, exhaustLength: 70, primaryLength: [2, 4, 3], plenum: 1.4, intakeFlow: 650, lobe: 236, idlePlate: 0.995, simFreq: 6000,
});

// Bugatti-style 8.0 W16, simulated as its two 8-cylinder halves in a 45-degree V: the real engine's
// 15-degree inner banks make engine-sim misfire, and the firing (16 events, every 45 degrees,
// alternating halves) is what the ear hears.
const w16Order = [];
for (let k = 0; k < 16; k++) w16Order.push({ bank: k % 2, index: Math.floor(k / 2) });
const w16 = engineScript({
  id: 'vertigo_w16', name: 'Vertigo Grand [W16]',
  bore: 86, stroke: 86, rodLength: 150, redline: 6700, revLimit: 6900,
  crankMass: 90, flywheelMass: 40, tdc: 112.5, banks: [22.5, -22.5],
  firing: w16Order,
  exhaustVolume: 0.12, exhaustLength: 120, primaryLength: [3, 5, 2, 4], plenum: 3.0, intakeFlow: 1100, lobe: 228, idlePlate: 0.996, simFreq: 3000,
});


// A stock script with its simulation rate changed (and any other text swaps).
function tuned(file, simFreq, swaps = []) {
  let text = readFileSync(new URL(file, ES), 'utf8').replace(/\r\n/g, '\n');
  for (const [a, b] of [[/simulation_frequency: \d+/, `simulation_frequency: ${simFreq}`], ...swaps]) {
    if (!(typeof a === 'string' ? text.includes(a) : a.test(text))) throw new Error(`${file}: ${a}`);
    text = text.replace(a, b);
  }
  return text;
}

// Road V12 from the 412 T2 script: Aventador bore/stroke, a road-car rev range and flywheel, and a
// throttle plate that lets it idle.
const v12 = tuned('atg-video-2/12_ferrari_412_t2.mr', 5000, [
  ['name: "Ferrari 412 T2 [V12]"', 'name: "Vertigo Apex [V12]"'],
  ['redline: 18000 * units.rpm', 'redline: 8500 * units.rpm'],
  ['rev_limit: 18500 * units.rpm', 'rev_limit: 8700 * units.rpm'],
  ['label stroke(43 * units.mm)', 'label stroke(76.4 * units.mm)'],
  ['label bore(86 * units.mm)', 'label bore(95 * units.mm)'],
  ['label crank_mass(20 * units.lb)', 'label crank_mass(50 * units.lb)'],
  ['label flywheel_mass(10 * units.lb)', 'label flywheel_mass(22 * units.lb)'],
  ['starter_speed: 500 * units.rpm', 'starter_speed: 250 * units.rpm'],
  ['idle_throttle_plate_position: 0.992', 'idle_throttle_plate_position: 0.975'],
]);

// Grand's luxury V12: 6.0 litres, heavy crank and flywheel and a low redline, so it swells rather than
// screams (the game layers twin-turbo whoosh on top).
const grand = tuned('atg-video-2/12_ferrari_412_t2.mr', 5000, [
  ['name: "Ferrari 412 T2 [V12]"', 'name: "Vertigo Grand [V12]"'],
  ['redline: 18000 * units.rpm', 'redline: 7000 * units.rpm'],
  ['rev_limit: 18500 * units.rpm', 'rev_limit: 7200 * units.rpm'],
  ['label stroke(43 * units.mm)', 'label stroke(80 * units.mm)'],
  ['label bore(86 * units.mm)', 'label bore(89 * units.mm)'],
  ['label crank_mass(20 * units.lb)', 'label crank_mass(75 * units.lb)'],
  ['label flywheel_mass(10 * units.lb)', 'label flywheel_mass(38 * units.lb)'],
  ['starter_speed: 500 * units.rpm', 'starter_speed: 250 * units.rpm'],
  ['idle_throttle_plate_position: 0.992', 'idle_throttle_plate_position: 0.975'],
]);

const ENGINES = [
  ['gt.mr', tuned('atg-video-2/08_ferrari_f136_v8.mr', 6000)],
  ['terra.mr', tuned('atg-video-2/07_gm_ls.mr', 6000)],
  ['r.mr', tuned('atg-video-2/10_lfa_v10.mr', 6000)],
  ['flat6.mr', flat6], ['w16.mr', w16], ['v12.mr', v12], ['grand.mr', grand],
];
for (const out of [new URL('engines/', import.meta.url), new URL('vertigo/', ES)]) {
  mkdirSync(out, { recursive: true });
  for (const [name, text] of ENGINES) writeFileSync(new URL(name, out), text);
}
console.log('wrote', ENGINES.map(([n]) => n).join(', '));
