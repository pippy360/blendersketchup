import bpy

for ws in bpy.data.workspaces:
    for screen in ws.screens:
        for area in screen.areas:
            if area.type == 'VIEW_3D':
                tool = ws.tools.from_space_view3d_mode('OBJECT', create=False)
                print("Active tool in OBJECT mode:", tool.idname if tool else None)
