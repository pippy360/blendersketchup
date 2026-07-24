import bpy

class TEST_OT_dummy(bpy.types.Operator):
    bl_idname = "test.dummy"
    bl_label = "Dummy"

print("instance:", getattr(TEST_OT_dummy(), "bl_idname", "NOT FOUND"))
