# Build all five Vertigo fleet cars, export the game GLBs, render the picker/review images and save
# the .blend, in one headless Blender run:
#   blender -b assets/vehicles/vertigo-fleet.blend -P blender/release_fleet.py
import bpy, os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ns = {}
exec(open(os.path.join(REPO, 'blender', 'vertigo_fleet.py'), encoding='utf-8').read(), ns)
renders = os.path.join(REPO, 'renders', 'vehicles')
os.makedirs(renders, exist_ok=True)
for cid in ns['SPECS']:
    ns['build'](cid)
    path = os.path.join(REPO, 'assets', 'vehicles', f'{cid}.glb')
    ns['export'](cid, path)
    deps = bpy.context.evaluated_depsgraph_get()
    tris = 0
    for o in bpy.data.collections[f'Fleet_{cid}'].objects:
        if o.type == 'MESH' and not o.hide_render:
            ev = o.evaluated_get(deps); me = ev.to_mesh()
            tris += sum(len(p.vertices) - 2 for p in me.polygons); ev.to_mesh_clear()
    ns['render'](cid, renders, ('front',), pct=40)               # picker thumbnail
    ns['render'](cid, renders, ('side', 'rear'), pct=55)         # review
    print('STEP', cid, 'tris', tris, 'glb', os.path.getsize(path), flush=True)
for c in bpy.data.collections:
    if c.name.startswith('Fleet_'):
        c.hide_render = False; c.hide_viewport = False
# Lay the cars out side by side in the saved file so they can be inspected together.
for k, cid in enumerate(ns['SPECS']):
    for o in bpy.data.collections[f'Fleet_{cid}'].objects:
        o.location.y += (k - 2) * 3.0
bpy.ops.wm.save_mainfile()
print('STEP saved', flush=True)
