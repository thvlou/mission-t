"""Records every Vertigo engine in engine-sim (community build v0.1.14a): a 1000 rpm idle, then
dyno-held RPM steps at full throttle (on-load) and closed throttle (off-load).

Each engine gets a fresh engine-sim. The dyno spins the crank from the start, so engines that will
not idle on their own still record, and a take that comes back silent is retried in a new window."""
import os, sys, time, json
import esrig as e

# python record_all.py [takes dir] [car ids...]   then: node tools/build-engine-audio.mjs <takes dir>

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), sys.argv[1] if len(sys.argv) > 1 and not sys.argv[1].startswith('vertigo') else 'takes')
LOG = os.path.join(OUT, 'log.txt')
os.makedirs(OUT, exist_ok=True)

N9000 = dict(on=[1800, 2700, 4000, 5600, 7800], off=[2700, 5600])
CARS = [
    ('vertigo-gt', 'engines/vertigo/gt.mr', N9000),
    ('vertigo-arc', 'engines/vertigo/flat6.mr', N9000),
    ('vertigo-apex', 'engines/vertigo/v12.mr', dict(on=[1700, 2600, 3800, 5400, 7600], off=[2600, 5400])),
    ('vertigo-grand', 'engines/vertigo/grand.mr', dict(on=[1300, 2000, 3000, 4300, 6300], off=[2000, 4300])),
    ('vertigo-terra', 'engines/vertigo/terra.mr', dict(on=[1400, 2100, 3000, 4300, 6000], off=[2100, 4300])),
    ('vertigo-r', 'engines/vertigo/r.mr', N9000),
]
only = [a for a in sys.argv[1:] if a.startswith('vertigo')]
TAKE = 4.0
SILENT = 0.02   # anything quieter is the engine not running


def log(*a):
    line = time.strftime('%H:%M:%S ') + ' '.join(str(x) for x in a)
    print(line, flush=True)
    with open(LOG, 'a', encoding='utf8') as f: f.write(line + '\n')


def take(name, seconds=TAKE):
    path = os.path.join(OUT, name + '.wav')
    e.record(path, seconds)
    return path, e.rms(path)


def record_engine(car, path, steps):
    sim = e.PostedSim(path)
    sim.STEP = steps.get('step', e.PostedSim.STEP)   # heavier engines run fewer frames; space wheel steps wider
    try:
        # Small and always on top, without taking focus: Windows throttles a covered window, and a
        # throttled engine-sim drops input and falls behind real time.
        e.user32.SetWindowPos(sim.hwnd, -1, 0, 0, 640, 360, 0x0010)
        time.sleep(12)
        # Dyno on and holding 1000 rpm turns the engine over; then ignition and a crack of throttle.
        sim.tap('D'); sim.tap('H'); sim.tap('A')
        time.sleep(2.5)
        # A crack of throttle: Q (1%) by default; a car's steps can ask for W (10%) via idle='W'.
        idle_key = ord(steps.get('idle', 'Q'))
        sim.key(idle_key, True); time.sleep(1.5)
        f, level = take(f'{car}_idle')
        sim.key(idle_key, False)
        if level < SILENT: return False, f'idle silent ({level:.3f})'
        log(car, 'idle', round(level, 4))
        cur, takes = 1000, []
        for rpm in sorted(set(steps['on']) | set(steps['off'])):
            sim.wheel((rpm - cur) // 100, while_key='G'); cur = rpm
            time.sleep(2.0)
            if rpm in steps['off']:
                f, level = take(f'{car}_off_{rpm}')
                log(car, 'off', rpm, round(level, 4)); takes.append(('off', rpm, level))
            if rpm in steps['on']:
                sim.key(ord('R'), True); time.sleep(1.5)
                f, level = take(f'{car}_on_{rpm}')
                sim.key(ord('R'), False)
                log(car, 'on', rpm, round(level, 4)); takes.append(('on', rpm, level))
                time.sleep(1.0)
        silent = [t for t in takes if t[2] < SILENT]
        if silent: return False, f'silent takes {silent}'
        return True, takes
    finally:
        sim.close()
        time.sleep(3)   # let the audio device go before the next window opens


meta = {}
try:
    for car, path, steps in CARS:
        if only and car not in only: continue
        for attempt in range(1, 4):
            ok, info = record_engine(car, path, steps)
            if ok: meta[car] = {'engine': path, 'takes': info}; break
            log(car, 'attempt', attempt, 'failed:', info)
        else:
            log(car, 'GAVE UP')
    with open(os.path.join(OUT, 'takes.json'), 'w') as f: json.dump(meta, f, indent=1)
    log('done', sorted(meta))
except Exception as ex:
    log('FAILED', repr(ex))
    raise
