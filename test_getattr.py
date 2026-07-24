import bpy

class TEST_OT_dummy(bpy.types.Operator):
    bl_idname = "test.dummy"
    bl_label = "Dummy"
    
    def invoke(self, context, event):
        print("bl_idname:", getattr(self, "bl_idname", "NOT FOUND"))
        print("type(self).bl_idname:", getattr(type(self), "bl_idname", "NOT FOUND"))
        return {'FINISHED'}

bpy.utils.register_class(TEST_OT_dummy)
bpy.ops.test.dummy('INVOKE_DEFAULT')
