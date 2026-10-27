# Headless driver for the v3 cars, one car per Blender process:
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/run_v3.py -- <car-id> <steps> <out-dir>
# steps: build, views (three studio renders into <out-dir>), quick-<view> (one view, fewer samples),
#        ortho (side view at sheet scale), export (assets/vehicles/<car-id>.glb)
import bpy, os, sys, traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index('--') + 1:]
cid, steps, out = argv[0], argv[1].split('+'), argv[2]
ns = {'__file__': os.path.join(REPO, 'blender', 'vertigo_v3.py')}
try:
    exec(open(ns['__file__'], encoding='utf-8').read(), ns)
    if 'build' in steps:
        ns['build'](cid)
        print('STEP built', cid, flush=True)
    if 'views' in steps:
        os.makedirs(out, exist_ok=True)
        print('STEP views', ns['render_views'](cid, out), flush=True)
    quick = [s[6:] for s in steps if s.startswith('quick-')]  # e.g. quick-front: one view at 64 samples
    if quick:
        os.makedirs(out, exist_ok=True)
        print('STEP quick', ns['render_views'](cid, out, only=quick, samples=64), flush=True)
    if 'match' in steps:  # 3/4 views through the fitted target cameras (blender/v3_fit)
        os.makedirs(out, exist_ok=True)
        print('STEP match', ns['render_match'](cid, out), flush=True)
    if 'ortho' in steps:
        os.makedirs(out, exist_ok=True)
        print('STEP ortho', ns['render_ortho'](cid, out), flush=True)
    if 'export' in steps:
        path = os.path.join(REPO, 'assets', 'vehicles', f'{cid}.glb')
        ns['export'](cid, path)
        print('STEP exported', path, os.path.getsize(path), flush=True)
except Exception:
    traceback.print_exc()
    sys.exit(1)
