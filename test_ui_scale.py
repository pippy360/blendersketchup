import bpy
import json

try:
    scale1 = getattr(bpy.context.preferences.view, 'ui_scale', None)
    scale2 = getattr(bpy.context.preferences.system, 'ui_scale', None)
    print(json.dumps({"view.ui_scale": scale1, "system.ui_scale": scale2}))
except Exception as e:
    print(f"Error: {e}")
