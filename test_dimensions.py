import bpy
import json

out = {}
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        out['area_width'] = area.width
        out['area_height'] = area.height
        for region in area.regions:
            out[f'region_{region.type}_width'] = region.width
            out[f'region_{region.type}_height'] = region.height
            
try:
    out['system.ui_scale'] = getattr(bpy.context.preferences.system, 'ui_scale', 1.0)
    out['view.ui_scale'] = getattr(bpy.context.preferences.view, 'ui_scale', 1.0)
    out['system.pixel_size'] = getattr(bpy.context.preferences.system, 'pixel_size', 1.0)
except:
    pass

print(json.dumps(out))
