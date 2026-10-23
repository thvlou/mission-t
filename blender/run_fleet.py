# Headless driver for the Vertigo fleet, one car per Blender process:
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/run_fleet.py -- <car-id> <steps> <out-dir> [percent]
# steps: any of build,render,export,save joined with '+'. Renders go to <out-dir>, the GLB to
# assets/vehicles/<car-id>.glb.
import bpy, os, sys, traceback

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
argv = sys.argv[sys.argv.index('--') + 1:]
cid, steps, out = argv[0], argv[1].split('+'), argv[2]
pct = int(argv[3]) if len(argv) > 3 else 45
ns = {}
try:
    exec(open(os.path.join(REPO, 'blender', 'vertigo_fleet.py'), encoding='utf-8').read(), ns)
    if 'build' in steps:
        ns['build'](cid)
        print('STEP built', cid, flush=True)
    if 'render' in steps:
        print('STEP rendered', ns['render'](cid, out, ('front', 'side', 'rear'), pct=pct), flush=True)
    if 'thumb' in steps:
        print('STEP thumb', ns['render'](cid, out, ('front',), pct=pct), flush=True)
    if 'export' in steps:
        path = os.path.join(REPO, 'assets', 'vehicles', f'{cid}.glb')
        ns['export'](cid, path)
        print('STEP exported', path, os.path.getsize(path), flush=True)
    if 'save' in steps:
        bpy.ops.wm.save_mainfile()
        print('STEP saved', flush=True)
except Exception:
    traceback.print_exc()
    sys.exit(1)
