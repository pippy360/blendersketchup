import bpy
import bmesh
import gpu
from gpu_extras.batch import batch_for_shader
from mathutils import Vector, geometry
from bpy_extras.view3d_utils import region_2d_to_origin_3d, region_2d_to_vector_3d, location_3d_to_region_2d

# Globals for Push/Pull tool
push_pull_hover_face_index = None
push_pull_active_face_index = None
push_pull_start_3d_pt = None
push_pull_face_normal = None
push_pull_start_co = []
push_pull_extruded_verts = []
push_pull_start_mouse_pos = None
push_pull_drag_state = 0 # 0=none, 1=click-drag, 2=click-release-move
push_pull_typed_length = ""

def draw_callback_3d_push_pull(self, context):
    global push_pull_hover_face_index, push_pull_active_face_index
    face_idx = push_pull_active_face_index if push_pull_active_face_index is not None else push_pull_hover_face_index
    if face_idx is None:
        return
    if not hasattr(self, 'bm') or not self.obj:
        return
        
    try:
        shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
    except ValueError:
        shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        
    try:
        self.bm.faces.ensure_lookup_table()
        if face_idx < len(self.bm.faces):
            f = self.bm.faces[face_idx]
            coords = [self.obj.matrix_world @ v.co for v in f.verts]
            if len(coords) < 3: return
            
            # Subdivide polygons into triangles for TRI_FAN
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('LESS_EQUAL')
            
            from gpu_extras.batch import batch_for_shader
            batch = batch_for_shader(shader, 'TRI_FAN', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", (0.0, 0.5, 1.0, 0.3))
            batch.draw(shader)
            
            # outline
            gpu.state.line_width_set(2.0)
            batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": coords})
            shader.uniform_float("color", (0.0, 0.5, 1.0, 1.0))
            batch_outline.draw(shader)
            gpu.state.line_width_set(1.0)
            
            gpu.state.depth_test_set('NONE')
            gpu.state.blend_set('NONE')
    except Exception as e:
        print(f"Error drawing push/pull highlight: {e}")

class SKETCHUP_OT_push_pull_tool(bpy.types.Operator):
    bl_idname = "sketchup.push_pull_tool"
    bl_label = "SketchUp Push/Pull Tool"
    bl_options = {'REGISTER', 'UNDO'}
    
    def setup_bmesh(self, context):
        if context.active_object and context.active_object.type == 'MESH':
            self.obj = context.active_object
        else:
            return False
            
        if self.obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.verts.ensure_lookup_table()
        self.bm.faces.ensure_lookup_table()
        return True
        
    def add_draw_handler(self, context):
        if not hasattr(self, 'draw_handler_3d') or self.draw_handler_3d is None:
            self.draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d_push_pull, (self, context), 'WINDOW', 'POST_VIEW')
            
    def remove_draw_handler(self, context):
        if hasattr(self, 'draw_handler_3d') and self.draw_handler_3d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(self.draw_handler_3d, 'WINDOW')
            self.draw_handler_3d = None
            
    def end_tool(self, context):
        global push_pull_hover_face_index, push_pull_active_face_index
        self.remove_draw_handler(context)
        push_pull_hover_face_index = None
        push_pull_active_face_index = None
        if hasattr(self, 'bm'):
            self.bm.free()
        if getattr(context, 'area', None):
            context.area.tag_redraw()
            
    def update_hover(self, context, event):
        global push_pull_hover_face_index
        region = context.region
        rv3d = context.region_data
        mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
        ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_coord)
        view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
        
        depsgraph = context.evaluated_depsgraph_get()
        hit, location, normal, index, obj, matrix = context.scene.ray_cast(depsgraph, ray_origin, view_vector)
        
        if hit and obj == self.obj:
            push_pull_hover_face_index = index
        else:
            push_pull_hover_face_index = None

    def modal(self, context, event):
        global push_pull_hover_face_index, push_pull_active_face_index, push_pull_start_3d_pt
        global push_pull_face_normal, push_pull_start_co, push_pull_extruded_verts
        global push_pull_start_mouse_pos, push_pull_drag_state, push_pull_typed_length
        
        active_tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if active_tool and active_tool.idname != "sketchup.push_pull_tool":
            self.end_tool(context)
            return {'FINISHED'}

        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            if push_pull_active_face_index is None:
                self.update_hover(context, event)
            else:
                # We are dragging
                region = context.region
                rv3d = context.region_data
                mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
                ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_coord)
                view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
                
                # Intersect ray with a plane parallel to the view plane, passing through start point
                view_plane_normal = -rv3d.view_matrix.inverted().to_3x3().col[2]
                hit_pt = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, push_pull_start_3d_pt, view_plane_normal)
                
                if hit_pt:
                    delta_3d = hit_pt - push_pull_start_3d_pt
                    # Project delta onto the face normal to get distance
                    dist = delta_3d.dot(push_pull_face_normal)
                    
                    if push_pull_typed_length:
                        try:
                            dist = float(push_pull_typed_length)
                        except ValueError:
                            pass
                            
                    # Update verts
                    for i, v in enumerate(push_pull_extruded_verts):
                        v.co = push_pull_start_co[i] + push_pull_face_normal * dist
                        
                    bmesh.update_edit_mesh(self.obj.data)

            return {'RUNNING_MODAL'}
            
        elif event.type == 'LEFTMOUSE':
            if event.value == 'PRESS':
                if push_pull_active_face_index is None:
                    if push_pull_hover_face_index is not None:
                        bpy.ops.ed.undo_push(message="SketchUp Push/Pull Start")
                        
                        push_pull_active_face_index = push_pull_hover_face_index
                        self.bm.faces.ensure_lookup_table()
                        face = self.bm.faces[push_pull_active_face_index]
                        
                        push_pull_face_normal = self.obj.matrix_world.to_3x3() @ face.normal.copy()
                        push_pull_face_normal.normalize()
                        
                        push_pull_start_3d_pt = self.obj.matrix_world @ face.calc_center_median()
                        
                        # Extrude
                        res = bmesh.ops.extrude_discrete_faces(self.bm, faces=[face])
                        extruded_face = res['faces'][0]
                        
                        # The newly extruded face becomes the active face for movement
                        push_pull_extruded_verts = extruded_face.verts[:]
                        push_pull_start_co = [v.co.copy() for v in push_pull_extruded_verts]
                        
                        bmesh.update_edit_mesh(self.obj.data)
                        
                        push_pull_start_mouse_pos = Vector((event.mouse_x, event.mouse_y))
                        push_pull_drag_state = 1 # click-drag
                        push_pull_typed_length = ""
                else:
                    # Second click to finish
                    push_pull_active_face_index = None
                    push_pull_drag_state = 0
                    push_pull_typed_length = ""
                    bpy.ops.ed.undo_push(message="SketchUp Push/Pull End")
                    self.update_hover(context, event)
                    
            elif event.value == 'RELEASE':
                if push_pull_active_face_index is not None and push_pull_drag_state == 1:
                    current_mouse = Vector((event.mouse_x, event.mouse_y))
                    if (current_mouse - push_pull_start_mouse_pos).length > 5:
                        # They dragged and released, finish!
                        push_pull_active_face_index = None
                        push_pull_drag_state = 0
                        push_pull_typed_length = ""
                        bpy.ops.ed.undo_push(message="SketchUp Push/Pull End")
                        self.update_hover(context, event)
                    else:
                        # Click-release, switch to move mode
                        push_pull_drag_state = 2
                        
            return {'RUNNING_MODAL'}
            
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if push_pull_active_face_index is not None:
                push_pull_active_face_index = None
                push_pull_drag_state = 0
                push_pull_typed_length = ""
                bpy.ops.ed.undo_push(message="SketchUp Push/Pull End")
                self.update_hover(context, event)
            return {'RUNNING_MODAL'}
            
        elif event.type == 'BACK_SPACE' and event.value == 'PRESS':
            push_pull_typed_length = push_pull_typed_length[:-1]
            return {'RUNNING_MODAL'}
            
        elif event.unicode and event.unicode in "0123456789.-" and event.value == 'PRESS':
            push_pull_typed_length += event.unicode
            return {'RUNNING_MODAL'}
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            if push_pull_active_face_index is not None:
                bpy.ops.ed.undo()
                if hasattr(self, 'bm'):
                    self.bm.free()
                self.bm = bmesh.from_edit_mesh(self.obj.data)
                self.bm.verts.ensure_lookup_table()
                self.bm.faces.ensure_lookup_table()
                push_pull_active_face_index = None
                push_pull_drag_state = 0
                push_pull_typed_length = ""
            else:
                self.end_tool(context)
                return {'FINISHED'}
            return {'RUNNING_MODAL'}
            
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            if not self.setup_bmesh(context):
                self.report({'WARNING'}, "No active mesh object")
                return {'CANCELLED'}
                
            global push_pull_hover_face_index, push_pull_active_face_index, push_pull_typed_length
            push_pull_hover_face_index = None
            push_pull_active_face_index = None
            push_pull_typed_length = ""
            
            self.update_hover(context, event)
            self.add_draw_handler(context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set("Hover to select face. Click and drag to push/pull.")
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

class SketchUpPushPullTool(bpy.types.WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = "sketchup.push_pull_tool"
    bl_label = "SketchUp Push/Pull"
    bl_description = "Extrude faces like SketchUp Push/Pull"
    bl_icon = "ops.mesh.extrude_region_move"
    bl_cursor = 'CROSSHAIR'
    bl_widget = None
    bl_keymap = (
        ("sketchup.push_pull_tool", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None),
        ("sketchup.push_pull_tool", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
    )
