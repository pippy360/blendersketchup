rect_code = """
# --- Rectangle Tool State ---
rect_start_pos = None
rect_plane_axis = None # The normal axis of the plane (X, Y, or Z)

def get_mouse_3d_pos_rect(context, event):
    # Determine intersection with a plane
    region = context.region
    rv3d = context.region_data
    mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
    
    ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_coord)
    view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
    
    depsgraph = context.evaluated_depsgraph_get()
    
    # 1. Check for geometry snapping (face)
    has_geo_snap = False
    geo_snap_pos = None
    geo_snap_normal = None
    
    use_snap = getattr(context.scene.tool_settings, "use_snap", False)
    if event.ctrl: use_snap = not use_snap
    
    if use_snap:
        snap_obj, snap_loc, snap_normal, snap_idx = context.scene.ray_cast(depsgraph, ray_origin, view_vector)
        if snap_obj and snap_loc:
            has_geo_snap = True
            geo_snap_pos = snap_loc
            geo_snap_normal = snap_normal

    # If we have a start pos, we MUST stay on the same plane
    if rect_start_pos is not None and rect_plane_axis is not None:
        # Intersect with the plane defined by rect_start_pos and rect_plane_axis
        hit = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, rect_start_pos, rect_plane_axis)
        if hit:
            if has_geo_snap:
                # Snap to geometry but project onto our plane
                proj_dist = (geo_snap_pos - rect_start_pos).dot(rect_plane_axis)
                return geo_snap_pos - rect_plane_axis * proj_dist, 'GEOMETRY'
            
            # Grid snapping
            if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements):
                grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
                target_x = round(hit.x / grid_scale) * grid_scale
                target_y = round(hit.y / grid_scale) * grid_scale
                target_z = round(hit.z / grid_scale) * grid_scale
                if rect_plane_axis.z > 0.9: hit = Vector((target_x, target_y, hit.z))
                elif rect_plane_axis.y > 0.9: hit = Vector((target_x, hit.y, target_z))
                elif rect_plane_axis.x > 0.9: hit = Vector((hit.x, target_y, target_z))
                return hit, 'GRID'
                
            return hit, None
            
    # We don't have a start pos, or we don't have an axis yet
    if has_geo_snap:
        return geo_snap_pos, 'GEOMETRY'
        
    # Default to XY plane (ground) if no snap
    hit = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, Vector((0,0,0)), Vector((0,0,1)))
    if hit:
        if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements):
            grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
            target_x = round(hit.x / grid_scale) * grid_scale
            target_y = round(hit.y / grid_scale) * grid_scale
            hit = Vector((target_x, target_y, 0))
            return hit, 'GRID'
        return hit, None
        
    return ray_origin + view_vector * 10, None

class SKETCHUP_OT_rectangle_tool(bpy.types.Operator):
    bl_idname = "sketchup.rectangle_tool"
    bl_label = "SketchUp Rectangle Tool"
    bl_options = {'REGISTER', 'UNDO'}
    
    def setup_bmesh(self, context):
        if context.active_object and context.active_object.type == 'MESH':
            self.obj = context.active_object
        else:
            bpy.ops.mesh.primitive_plane_add(size=0, enter_editmode=False)
            self.obj = context.active_object
            
        if self.obj.mode != 'EDIT':
            bpy.ops.object.mode_set(mode='EDIT')
            
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.verts.ensure_lookup_table()
        
    def update_mesh(self):
        if hasattr(self, 'bm') and self.obj:
            bmesh.update_edit_mesh(self.obj.data)
            
    def add_draw_handler(self, context):
        global draw_handler_3d
        if draw_handler_3d is None:
            draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW')
            
    def remove_draw_handler(self, context):
        global draw_handler_3d
        if draw_handler_3d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler_3d, 'WINDOW')
            draw_handler_3d = None
            
    def end_tool(self, context):
        global is_tool_running, active_draw_tool, rect_start_pos
        self.remove_draw_handler(context)
        is_tool_running = False
        active_draw_tool = None
        rect_start_pos = None
        if hasattr(self, 'bm'):
            self.bm.free()
        context.area.tag_redraw()
        
    def add_rectangle(self, pos2):
        global rect_start_pos, rect_plane_axis
        
        pos1 = rect_start_pos
        if rect_plane_axis is None: return
        
        # Calculate the 4 corners
        if abs(rect_plane_axis.z) > 0.9:
            p2 = Vector((pos1.x, pos2.y, pos1.z))
            p4 = Vector((pos2.x, pos1.y, pos1.z))
        elif abs(rect_plane_axis.y) > 0.9:
            p2 = Vector((pos1.x, pos1.y, pos2.z))
            p4 = Vector((pos2.x, pos1.y, pos1.z))
        else:
            p2 = Vector((pos1.x, pos2.y, pos1.z))
            p4 = Vector((pos1.x, pos1.y, pos2.z))
            
        local_p1 = self.obj.matrix_world.inverted() @ pos1
        local_p2 = self.obj.matrix_world.inverted() @ p2
        local_p3 = self.obj.matrix_world.inverted() @ pos2
        local_p4 = self.obj.matrix_world.inverted() @ p4
        
        # Add to mesh
        self.bm.verts.ensure_lookup_table()
        
        v1 = self.bm.verts.new(local_p1)
        v2 = self.bm.verts.new(local_p2)
        v3 = self.bm.verts.new(local_p3)
        v4 = self.bm.verts.new(local_p4)
        
        # Deselect everything
        for bv in self.bm.verts: bv.select = False
        for be in self.bm.edges: be.select = False
        for bf in self.bm.faces: bf.select = False
        
        e1 = self.bm.edges.new((v1, v2))
        e2 = self.bm.edges.new((v2, v3))
        e3 = self.bm.edges.new((v3, v4))
        e4 = self.bm.edges.new((v4, v1))
        
        v1.select = v2.select = v3.select = v4.select = True
        e1.select = e2.select = e3.select = e4.select = True
        
        self.update_mesh()
        
        # Perform Auto Merge & Split + Fill
        ts = bpy.context.scene.tool_settings
        orig_am = ts.use_mesh_automerge
        orig_ams = ts.use_mesh_automerge_and_split
        ts.use_mesh_automerge = True
        ts.use_mesh_automerge_and_split = True
        
        bpy.ops.transform.translate(value=(0, 0, 0))
        bpy.ops.mesh.edge_face_add()
        
        ts.use_mesh_automerge = orig_am
        ts.use_mesh_automerge_and_split = orig_ams
        
        bpy.ops.ed.undo_push(message="SketchUp Add Rectangle")
        
        if hasattr(self, 'bm'):
            self.bm.free()
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.verts.ensure_lookup_table()
        
        # Deselect everything
        for bv in self.bm.verts: bv.select = False
        for be in self.bm.edges: be.select = False
        for bf in self.bm.faces: bf.select = False
        self.update_mesh()
        
        rect_start_pos = None

    def update_mouse_pos(self, context, event):
        global mouse_pos, draw_points, rect_start_pos, rect_plane_axis
        res = get_mouse_3d_pos_rect(context, event)
        if res:
            m_pos, _ = res
            mouse_pos = m_pos
            if rect_start_pos:
                # Calculate the 4 corners for draw_points
                if rect_plane_axis is not None:
                    if abs(rect_plane_axis.z) > 0.9:
                        p2 = Vector((rect_start_pos.x, mouse_pos.y, rect_start_pos.z))
                        p4 = Vector((mouse_pos.x, rect_start_pos.y, rect_start_pos.z))
                    elif abs(rect_plane_axis.y) > 0.9:
                        p2 = Vector((rect_start_pos.x, rect_start_pos.y, mouse_pos.z))
                        p4 = Vector((mouse_pos.x, rect_start_pos.y, rect_start_pos.z))
                    else:
                        p2 = Vector((rect_start_pos.x, mouse_pos.y, rect_start_pos.z))
                        p4 = Vector((rect_start_pos.x, rect_start_pos.y, mouse_pos.z))
                    
                    draw_points = [rect_start_pos, p2, mouse_pos, p4, rect_start_pos]

    def modal(self, context, event):
        global mouse_pos, draw_points, rect_start_pos, rect_plane_axis
        
        active_tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if active_tool and active_tool.idname != "sketchup.rectangle_tool":
            self.end_tool(context)
            return {'FINISHED'}

        if event.type == 'MOUSEMOVE':
            self.update_mouse_pos(context, event)
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if mouse_pos:
                if not hasattr(self, 'bm'):
                    self.setup_bmesh(context)
                    
                if rect_start_pos is None:
                    # First click
                    rect_start_pos = mouse_pos.copy()
                    
                    # Determine plane axis
                    region = context.region
                    rv3d = context.region_data
                    mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
                    view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
                    
                    # Snap normal to closest axis
                    best_axis = Vector((0,0,1))
                    best_dot = 0
                    for axis in [Vector((1,0,0)), Vector((0,1,0)), Vector((0,0,1))]:
                        dot = abs(view_vector.dot(axis))
                        if dot > best_dot:
                            best_dot = dot
                            best_axis = axis
                    rect_plane_axis = best_axis
                    draw_points = [rect_start_pos]
                else:
                    # Second click
                    if hasattr(self, 'bm'):
                        self.add_rectangle(mouse_pos)
                        draw_points = []
            return {'RUNNING_MODAL'}
            
        elif event.type == 'ESC' and event.value == 'PRESS':
            rect_start_pos = None
            draw_points = []
            context.area.tag_redraw()
            return {'RUNNING_MODAL'}
            
        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            global draw_points, mouse_pos, is_tool_running, active_draw_tool, rect_start_pos
            if is_tool_running:
                return {'PASS_THROUGH'}
            is_tool_running = True
            active_draw_tool = self
            
            draw_points = []
            mouse_pos = None
            rect_start_pos = None
            
            self.update_mouse_pos(context, event)
            self.add_draw_handler(context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set("Click to start rectangle. Click again to complete. ESC to cancel.")
            return {'RUNNING_MODAL'}
        else:
            return {'CANCELLED'}

class SketchUpRectangleTool(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = "sketchup.rectangle_tool"
    bl_label = "SketchUp Rectangle Tool"
    bl_description = "Draw rectangles in a SketchUp-like manner"
    bl_icon = "ops.mesh.primitive_plane_add"
    bl_cursor = 'PAINT_BRUSH'
    bl_widget = None
    bl_keymap = (
        ("sketchup.rectangle_tool", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None),
        ("sketchup.rectangle_tool", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
    )
"""

with open("__init__.py", "r") as f:
    content = f.read()

# Insert before registration
lines = content.split('\n')
idx = 0
for i, line in enumerate(lines):
    if "# --- Registration ---" in line:
        idx = i
        break

new_content = '\n'.join(lines[:idx]) + '\n' + rect_code + '\n' + '\n'.join(lines[idx:])

# Now update the classes tuple in registration to include the new classes
classes_idx = 0
for i, line in enumerate(new_content.split('\n')):
    if "classes = (" in line:
        classes_idx = i
        break

lines = new_content.split('\n')
lines.insert(classes_idx + 1, "    SKETCHUP_OT_rectangle_tool,")

new_content = '\n'.join(lines)

# Also add the workspace tool registration
register_idx = 0
for i, line in enumerate(new_content.split('\n')):
    if "bpy.utils.register_tool(SketchUpDrawTool" in line:
        register_idx = i
        break

lines = new_content.split('\n')
lines.insert(register_idx + 1, "    bpy.utils.register_tool(SketchUpRectangleTool, after={\"sketchup.draw_tool_v2\"})")
lines.insert(register_idx + 2, "    bpy._sketchup_rect_tool_class = SketchUpRectangleTool")

new_content = '\n'.join(lines)

# Also unregister tool
unregister_idx = 0
for i, line in enumerate(new_content.split('\n')):
    if "old_tool = getattr(bpy, \"_sketchup_tool_class\", None)" in line:
        unregister_idx = i
        break

lines = new_content.split('\n')
lines.insert(unregister_idx + 5, "    old_rect_tool = getattr(bpy, \"_sketchup_rect_tool_class\", None)")
lines.insert(unregister_idx + 6, "    try:")
lines.insert(unregister_idx + 7, "        if old_rect_tool: bpy.utils.unregister_tool(old_rect_tool)")
lines.insert(unregister_idx + 8, "        else: bpy.utils.unregister_tool(SketchUpRectangleTool)")
lines.insert(unregister_idx + 9, "    except Exception: pass")

new_content = '\n'.join(lines)


with open("__init__.py", "w") as f:
    f.write(new_content)
