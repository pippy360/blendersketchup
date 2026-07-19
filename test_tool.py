import bpy
tool = bpy.context.workspace.tools.from_space_view3d_mode(bpy.context.mode, create=False)
print("ACTIVE TOOL ID:", tool.idname if tool else None)
