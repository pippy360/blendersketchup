import bpy
import json

out = []
for k in dir(bpy.context.window_manager):
    if 'gizmo' in k.lower():
        out.append(k)

print(json.dumps(out))
