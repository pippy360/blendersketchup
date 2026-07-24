import bpy

class TEST_OT_dummy(bpy.types.Operator):
    bl_idname = "test.dummy"
    bl_label = "Dummy"
    
    def invoke(self, context, event):
        print("hasattr:", hasattr(self, "bl_idname"))
        print("getattr:", getattr(self, "bl_idname", "NOT FOUND"))
        print("type(self).bl_idname:", type(self).bl_idname)
        return {'FINISHED'}

bpy.utils.register_class(TEST_OT_dummy)

def test_func():
    for window in bpy.context.window_manager.windows:
        for area in window.screen.areas:
            if area.type == 'VIEW_3D':
                override = {'window': window, 'screen': window.screen, 'area': area}
                bpy.ops.test.dummy(override, 'INVOKE_DEFAULT')
                return
    print("No 3D view found")

bpy.app.timers.register(test_func, first_interval=0.1)
