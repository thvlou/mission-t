import bpy
from pathlib import Path
from mathutils import Vector
p='C:/Users/user/Desktop/AIA/Tesla/assets/vertigo-gt.blend'
with bpy.data.libraries.load(p,link=False) as (a,b): b.scenes=a.scenes
s=b.scenes[0]
result={"objects":[{'name':o.name,'type':o.type,'loc':list(o.location),'dim':list(o.dimensions),'materials':[m.name for m in o.data.materials] if o.type=='MESH' else []} for o in s.objects]}
