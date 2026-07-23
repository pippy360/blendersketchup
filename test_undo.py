import bpy

class ModalUndoTest(bpy.types.Operator):
    bl_idname = "test.modal_undo"
    bl_label = "Modal Undo Test"
    bl_options = {'REGISTER', 'UNDO'}

    def invoke(self, context, event):
        self.points = 0
        context.window_manager.modal_handler_add(self)
        return {'RUNNING_MODAL'}

    def modal(self, context, event):
        if event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            bpy.ops.mesh.primitive_cube_add(size=1, location=(self.points, 0, 0))
            self.points += 2
            bpy.ops.ed.undo_push(message="Added Cube")
            print("Added cube and pushed undo")
            return {'RUNNING_MODAL'}
            
        elif event.type == 'Z' and event.value == 'PRESS' and (event.ctrl or event.oskey):
            print("Undoing inside modal...")
            bpy.ops.ed.undo()
            self.points -= 2
            return {'RUNNING_MODAL'}
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            return {'FINISHED'}
            
        return {'PASS_THROUGH'}

bpy.utils.register_class(ModalUndoTest)
