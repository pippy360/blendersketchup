bl_info = {
    "name": "SketchUp Tools",
    "author": "Antigravity",
    "version": (0, 3),
    "blender": (3, 0, 0),
    "location": "View3D > Toolbar",
    "description": "SketchUp-like tools for building primitives and outlines",
    "category": "3D View",
}

import bpy
import bmesh
import gpu
import blf
from gpu_extras.batch import batch_for_shader
from bpy_extras.view3d_utils import region_2d_to_vector_3d, region_2d_to_origin_3d, location_3d_to_region_2d
from bpy.types import WorkSpaceTool
from mathutils import Vector, geometry

# --- Globals for Drawing ---
try:
    shader = gpu.shader.from_builtin('UNIFORM_COLOR')
except ValueError:
    shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')

draw_handler_3d = None
draw_handler_2d = None
draw_points = []
mouse_pos = None

manual_axis_lock = None  # None, 'X', 'Y', 'Z'
shift_locked_axis = None # Vector
current_axis_color = (0.0, 0.0, 0.0, 1.0) # Black default
typed_length = ""

primary_axes = [
    Vector((1,0,0)), Vector((-1,0,0)),
    Vector((0,1,0)), Vector((0,-1,0)),
    Vector((0,0,1)), Vector((0,0,-1))
]

snap_dirs = [v.normalized() for v in [
    Vector((1,0,0)), Vector((-1,0,0)), Vector((0,1,0)), Vector((0,-1,0)), Vector((0,0,1)), Vector((0,0,-1)),
    Vector((1,1,0)), Vector((1,-1,0)), Vector((-1,1,0)), Vector((-1,-1,0)),
    Vector((1,0,1)), Vector((1,0,-1)), Vector((-1,0,1)), Vector((-1,0,-1)),
    Vector((0,1,1)), Vector((0,1,-1)), Vector((0,-1,1)), Vector((0,-1,-1))
]]

def draw_callback_3d(self, context):
    if not draw_points or not mouse_pos:
        return
        
    coords = [draw_points[-1], mouse_pos]
    batch = batch_for_shader(shader, 'LINES', {"pos": coords})
    
    shader.bind()
    shader.uniform_float("color", current_axis_color)
    
    # SketchUp draws thicker lines for locked axes
    if manual_axis_lock or shift_locked_axis:
        gpu.state.line_width_set(3.0)
    else:
        gpu.state.line_width_set(2.0)
        
    batch.draw(shader)
    gpu.state.line_width_set(1.0)

def draw_callback_2d(self, context):
    if not draw_points or not mouse_pos:
        return

    length = (mouse_pos - draw_points[-1]).length
    mid_point = (mouse_pos + draw_points[-1]) / 2.0
    
    pos_2d = location_3d_to_region_2d(context.region, context.region_data, mid_point)
    
    if pos_2d:
        font_id = 0
        blf.position(font_id, float(pos_2d[0] + 15), float(pos_2d[1] + 15), 0.0)
        try:
            blf.size(font_id, 20, 72)
        except TypeError:
            blf.size(font_id, 20)
        
        blf.enable(font_id, blf.SHADOW)
        blf.shadow(font_id, 3, 0.0, 0.0, 0.0, 1.0)
        blf.shadow_offset(font_id, 1, -1)
        
        if typed_length:
            blf.color(font_id, 1.0, 0.8, 0.2, 1.0)
            text = f"Length: {typed_length}_"
        else:
            blf.color(font_id, 1.0, 1.0, 1.0, 1.0) 
            text = f"{length:.2f} m"
            
        blf.draw(font_id, text)
        blf.disable(font_id, blf.SHADOW)

def apply_native_snapping(context, event, hit, location, index, obj, matrix):
    if not hit:
        return location
        
    use_snap = context.scene.tool_settings.use_snap
    if event.ctrl:
        use_snap = not use_snap
        
    if use_snap and obj.type == 'MESH':
        region = context.region
        rv3d = context.region_data
        mouse_2d = Vector((event.mouse_region_x, event.mouse_region_y))
        
        snap_elements = context.scene.tool_settings.snap_elements
        mesh = obj.data
        poly = mesh.polygons[index]
        snap_radius_px = 30.0
        
        if 'VERTEX' in snap_elements:
            closest_dist = float('inf')
            closest_v = location
            for v_idx in poly.vertices:
                v_world = matrix @ mesh.vertices[v_idx].co
                dist = (v_world - location).length
                if dist < closest_dist:
                    closest_dist = dist
                    closest_v = v_world
            
            v_2d = location_3d_to_region_2d(region, rv3d, closest_v)
            if v_2d and (v_2d - mouse_2d).length < snap_radius_px:
                return closest_v

        if 'EDGE' in snap_elements:
            closest_dist = float('inf')
            closest_pt = location
            for loop_idx in poly.loop_indices:
                v1_idx = mesh.loops[loop_idx].vertex_index
                next_loop_idx = poly.loop_start + (loop_idx - poly.loop_start + 1) % poly.loop_total
                v2_idx = mesh.loops[next_loop_idx].vertex_index
                
                v1_world = matrix @ mesh.vertices[v1_idx].co
                v2_world = matrix @ mesh.vertices[v2_idx].co
                
                pt = geometry.intersect_point_line(location, v1_world, v2_world)[0]
                vec1 = pt - v1_world
                vec2 = v2_world - v1_world
                if vec1.dot(vec2) < 0: pt = v1_world
                elif vec1.length > vec2.length: pt = v2_world
                    
                dist = (pt - location).length
                if dist < closest_dist:
                    closest_dist = dist
                    closest_pt = pt
                    
            p_2d = location_3d_to_region_2d(region, rv3d, closest_pt)
            if p_2d and (p_2d - mouse_2d).length < snap_radius_px:
                return closest_pt
                
    return location

def get_mouse_3d_pos(context, event, last_point=None):
    global manual_axis_lock, shift_locked_axis, current_axis_color

    region = context.region
    rv3d = context.region_data
    coord = (event.mouse_region_x, event.mouse_region_y)
    view_vector = region_2d_to_vector_3d(region, rv3d, coord)
    ray_origin = region_2d_to_origin_3d(region, rv3d, coord)
    depsgraph = context.view_layer.depsgraph

    # 1. Raw Hit Position
    hit, location, normal, index, obj, matrix = context.scene.ray_cast(depsgraph, ray_origin, view_vector)
    
    raw_pos = location
    if not hit:
        plane_normal = Vector((0, 0, 1))
        plane_point = Vector((0, 0, 0))
        raw_pos = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, plane_point, plane_normal)
        if raw_pos is None:
            raw_pos = ray_origin + view_vector * 10.0

    if last_point is None:
        current_axis_color = (0.0, 0.0, 0.0, 1.0) # Black
        return apply_native_snapping(context, event, hit, raw_pos, index, obj, matrix)

    # 2. Determine Active Constraint Axis
    active_axis = None
    
    if manual_axis_lock == 'X':
        active_axis = Vector((1, 0, 0))
    elif manual_axis_lock == 'Y':
        active_axis = Vector((0, 1, 0))
    elif manual_axis_lock == 'Z':
        active_axis = Vector((0, 0, 1))
    elif event.shift:
        if shift_locked_axis is None:
            # Determine locked axis by 2D screen projection
            last_pt_2d = location_3d_to_region_2d(region, rv3d, last_point)
            mouse_2d = Vector((event.mouse_region_x, event.mouse_region_y))
            
            if last_pt_2d and (mouse_2d - last_pt_2d).length > 5.0:
                mouse_dir_2d = (mouse_2d - last_pt_2d).normalized()
                cam_pos = rv3d.view_matrix.inverted().translation
                dist_to_cam = (last_point - cam_pos).length
                
                best_axis = None
                best_dot = -1
                for axis in snap_dirs:
                    ax_pt_2d = location_3d_to_region_2d(region, rv3d, last_point + axis * (dist_to_cam * 0.5))
                    if ax_pt_2d:
                        ax_dir_2d = (ax_pt_2d - last_pt_2d)
                        if ax_dir_2d.length > 0.001:
                            ax_dir_2d.normalize()
                            d = mouse_dir_2d.dot(ax_dir_2d)
                            if d > best_dot:
                                best_dot = d
                                best_axis = axis
                if best_axis is not None:
                    shift_locked_axis = best_axis
                    
            if shift_locked_axis is None:
                # Fallback to 3D projection if 2D failed
                dir_vec = (raw_pos - last_point)
                if dir_vec.length > 0.001:
                    dir_vec.normalize()
                    shift_locked_axis = max(snap_dirs, key=lambda v: dir_vec.dot(v))
                    
        active_axis = shift_locked_axis
    else:
        shift_locked_axis = None
        # Auto-snapping using 2D screen projection of axes
        last_pt_2d = location_3d_to_region_2d(region, rv3d, last_point)
        mouse_2d = Vector((event.mouse_region_x, event.mouse_region_y))
        
        if last_pt_2d and (mouse_2d - last_pt_2d).length > 5.0:
            mouse_dir_2d = (mouse_2d - last_pt_2d).normalized()
            cam_pos = rv3d.view_matrix.inverted().translation
            dist_to_cam = (last_point - cam_pos).length
            
            best_axis = None
            best_dot = -1
            for axis in primary_axes:
                ax_pt_2d = location_3d_to_region_2d(region, rv3d, last_point + axis * (dist_to_cam * 0.5))
                if ax_pt_2d:
                    ax_dir_2d = (ax_pt_2d - last_pt_2d)
                    if ax_dir_2d.length > 0.001:
                        ax_dir_2d.normalize()
                        d = mouse_dir_2d.dot(ax_dir_2d)
                        if d > best_dot:
                            best_dot = d
                            best_axis = axis
            
            if best_dot > 0.985: # Roughly 10 degrees threshold in 2D space
                active_axis = best_axis

    # 3. Apply Constraint
    if active_axis is not None:
        abs_x = abs(active_axis.x)
        abs_y = abs(active_axis.y)
        abs_z = abs(active_axis.z)
        if abs_x > 0.99: current_axis_color = (1.0, 0.2, 0.2, 1.0) # Red
        elif abs_y > 0.99: current_axis_color = (0.2, 1.0, 0.2, 1.0) # Green
        elif abs_z > 0.99: current_axis_color = (0.2, 0.5, 1.0, 1.0) # Blue
        else: current_axis_color = (1.0, 0.2, 0.8, 1.0) # Magenta

        plane_normal = active_axis.cross(view_vector).cross(active_axis)
        if plane_normal.length < 0.0001:
            plane_normal = view_vector
            
        hit_plane = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, last_point, plane_normal)
        if hit_plane:
            proj = (hit_plane - last_point).dot(active_axis)
            constrained_pos = last_point + active_axis * proj
        else:
            constrained_pos = last_point + active_axis * (raw_pos - last_point).length
            
        # SKETCHUP INFERENCE: If we hover over a vertex while locked, project it onto our axis
        snap_pos = apply_native_snapping(context, event, hit, raw_pos, index, obj, matrix)
        if snap_pos != raw_pos:
            vec_to_snap = snap_pos - last_point
            proj_dist = vec_to_snap.dot(active_axis)
            return last_point + active_axis * proj_dist
            
        return constrained_pos

    current_axis_color = (0.0, 0.0, 0.0, 1.0) # Black

    # 4. Native Snapping (Unconstrained)
    return apply_native_snapping(context, event, hit, raw_pos, index, obj, matrix)

# --- Operators ---

class SKETCHUP_OT_draw_tool(bpy.types.Operator):
    """Interactive SketchUp-like Draw Tool"""
    bl_idname = "sketchup.draw_tool"
    bl_label = "SketchUp Draw"
    bl_options = {'REGISTER', 'UNDO'}

    def add_draw_handler(self, context):
        global draw_handler_3d, draw_handler_2d
        if draw_handler_3d is None:
            draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(
                draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW'
            )
        if draw_handler_2d is None:
            draw_handler_2d = bpy.types.SpaceView3D.draw_handler_add(
                draw_callback_2d, (self, context), 'WINDOW', 'POST_PIXEL'
            )

    def remove_draw_handler(self):
        global draw_handler_3d, draw_handler_2d
        if draw_handler_3d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler_3d, 'WINDOW')
            draw_handler_3d = None
        if draw_handler_2d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler_2d, 'WINDOW')
            draw_handler_2d = None

    def create_mesh_object(self, context):
        mesh = bpy.data.meshes.new("SketchUp_Mesh")
        self.obj = bpy.data.objects.new("SketchUp_Object", mesh)
        context.collection.objects.link(self.obj)
        
        bpy.ops.object.select_all(action='DESELECT')
        self.obj.select_set(True)
        context.view_layer.objects.active = self.obj
        
        self.bm = bmesh.new()

    def update_mesh(self):
        if hasattr(self, 'bm') and hasattr(self, 'obj'):
            self.bm.to_mesh(self.obj.data)
            self.obj.data.update()

    def end_tool(self, context):
        global draw_points, mouse_pos, manual_axis_lock, shift_locked_axis, typed_length
        draw_points = []
        mouse_pos = None
        manual_axis_lock = None
        shift_locked_axis = None
        typed_length = ""
        self.chain_verts = []
        context.workspace.status_text_set(None)
        self.remove_draw_handler()
        
        if hasattr(self, 'bm'):
            if len(self.bm.verts) == 0:
                bpy.data.objects.remove(self.obj)
            self.bm.free()

    def add_point(self, pos):
        global draw_points, manual_axis_lock, shift_locked_axis
        
        step_geom = []
        v = self.bm.verts.new(pos)
        step_geom.append(v)
        
        if len(self.chain_verts) > 0:
            v_prev = self.chain_verts[-1]
            try:
                e = self.bm.edges.new((v_prev, v))
                step_geom.append(e)
            except ValueError:
                pass
                
            if len(self.chain_verts) >= 2:
                dist = (pos - self.chain_verts[0].co).length
                if dist < 0.1:
                    self.bm.verts.remove(v)
                    step_geom.remove(v)
                    
                    v_first = self.chain_verts[0]
                    try:
                        e = self.bm.edges.new((v_prev, v_first))
                        step_geom.append(e)
                    except ValueError:
                        pass
                    try:
                        f = self.bm.faces.new(self.chain_verts)
                        step_geom.append(f)
                    except Exception:
                        pass
                        
                    self.undo_history.append({
                        'type': 'CLOSE_FACE',
                        'geom': step_geom,
                        'prev_chain': list(self.chain_verts),
                        'prev_draw': list(draw_points)
                    })
                    
                    self.chain_verts.clear()
                    draw_points.clear()
                    manual_axis_lock = None
                    shift_locked_axis = None
                    self.update_mesh()
                    self.report({'INFO'}, "Face Closed")
                    return
                    
        self.chain_verts.append(v)
        draw_points.append(pos.copy())
        
        self.undo_history.append({
            'type': 'ADD_POINT',
            'geom': step_geom,
            'prev_chain': list(self.chain_verts[:-1]),
            'prev_draw': list(draw_points[:-1])
        })
        
        manual_axis_lock = None
        shift_locked_axis = None
        self.update_mesh()

    def update_mouse_pos(self, context, event):
        global mouse_pos, draw_points
        last_pt = draw_points[-1] if len(draw_points) > 0 else None
        loc = get_mouse_3d_pos(context, event, last_pt)
        if loc:
            mouse_pos = loc

    def modal(self, context, event):
        global mouse_pos, draw_points, manual_axis_lock, shift_locked_axis, typed_length
        context.area.tag_redraw()

        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            if event.value == 'RELEASE':
                shift_locked_axis = None
            self.update_mouse_pos(context, event)
            return {'PASS_THROUGH'}

        elif event.type == 'MOUSEMOVE':
            self.update_mouse_pos(context, event)

        elif event.type == 'LEFTMOUSE' and event.value == 'PRESS':
            if mouse_pos:
                self.add_point(mouse_pos)
                typed_length = ""
                self.update_mouse_pos(context, event)
            return {'RUNNING_MODAL'}
            
        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self.undo_history.append({
                'type': 'BREAK_CHAIN',
                'geom': [],
                'prev_chain': list(self.chain_verts),
                'prev_draw': list(draw_points)
            })
            draw_points.clear()
            self.chain_verts.clear()
            manual_axis_lock = None
            shift_locked_axis = None
            typed_length = ""
            self.report({'INFO'}, "Chain Broken")
            return {'RUNNING_MODAL'}

        elif event.type == 'ESC' and event.value == 'PRESS':
            self.end_tool(context)
            self.report({'INFO'}, "Cancelled SketchUp Draw Tool")
            return {'CANCELLED'}
            
        elif event.type == 'Z' and event.value == 'PRESS' and (event.ctrl or event.oskey):
            if len(self.undo_history) > 0:
                last_action = self.undo_history.pop()
                
                geom = last_action['geom']
                for g in geom:
                    if isinstance(g, bmesh.types.BMFace) and g.is_valid: self.bm.faces.remove(g)
                for g in geom:
                    if isinstance(g, bmesh.types.BMEdge) and g.is_valid: self.bm.edges.remove(g)
                for g in geom:
                    if isinstance(g, bmesh.types.BMVert) and g.is_valid: self.bm.verts.remove(g)
                        
                self.chain_verts = last_action['prev_chain']
                draw_points.clear()
                draw_points.extend(last_action['prev_draw'])
                manual_axis_lock = None
                shift_locked_axis = None
                typed_length = ""
                
                self.update_mesh()
                self.update_mouse_pos(context, event)
                self.report({'INFO'}, "Undid Last Action")
                
            return {'RUNNING_MODAL'}
            
        elif event.value == 'PRESS':
            if event.type == 'X':
                manual_axis_lock = 'X' if manual_axis_lock != 'X' else None
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
            elif event.type == 'Y':
                manual_axis_lock = 'Y' if manual_axis_lock != 'Y' else None
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
            elif event.type == 'Z':
                manual_axis_lock = 'Z' if manual_axis_lock != 'Z' else None
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
                
            elif event.type == 'BACK_SPACE':
                typed_length = typed_length[:-1]
                return {'RUNNING_MODAL'}
            elif event.type in {'RET', 'NUMPAD_ENTER'}:
                if typed_length and len(draw_points) > 0:
                    try:
                        val = float(typed_length)
                        direction = (mouse_pos - draw_points[-1])
                        if direction.length > 0.0001:
                            direction.normalize()
                        else:
                            direction = Vector((1,0,0))
                            
                        exact_pos = draw_points[-1] + direction * val
                        self.add_point(exact_pos)
                        mouse_pos = exact_pos
                        
                    except ValueError:
                        self.report({'WARNING'}, "Invalid length entered")
                        
                    typed_length = ""
                    return {'RUNNING_MODAL'}
                else:
                    self.end_tool(context)
                    self.report({'INFO'}, "Finished SketchUp Draw Tool")
                    return {'FINISHED'}
                    
            elif event.unicode and event.unicode in "0123456789.-":
                typed_length += event.unicode
                return {'RUNNING_MODAL'}

        return {'PASS_THROUGH'}

    def invoke(self, context, event):
        if context.space_data.type == 'VIEW_3D':
            global draw_points, mouse_pos, manual_axis_lock, shift_locked_axis, typed_length
            draw_points = []
            mouse_pos = None
            manual_axis_lock = None
            shift_locked_axis = None
            typed_length = ""
            self.chain_verts = []
            self.undo_history = []
            
            self.update_mouse_pos(context, event)
            self.create_mesh_object(context)
            self.add_draw_handler(context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set("Click to draw. X/Y/Z to lock axis. Type numbers and press Enter for exact length. Right Click to break.")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}


# --- Workspace Tools ---

class SketchUpDrawTool(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'OBJECT'
    bl_idname = "sketchup.draw_tool_v2"
    bl_label = "SketchUp Draw Tool"
    bl_description = "Draw lines and outlines in a SketchUp-like manner"
    bl_icon = "ops.curve.draw"
    bl_widget = None
    bl_keymap = (
        ("sketchup.draw_tool", {"type": 'LEFTMOUSE', "value": 'PRESS'}, None),
    )


# --- Registration ---

classes = (
    SKETCHUP_OT_draw_tool,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.utils.register_tool(SketchUpDrawTool, after={"builtin.measure"})
    bpy._sketchup_tool_class = SketchUpDrawTool

def unregister():
    for cls in reversed(classes):
        old_cls = getattr(bpy.types, cls.__name__, None)
        try:
            if old_cls: bpy.utils.unregister_class(old_cls)
            else: bpy.utils.unregister_class(cls)
        except Exception: pass
            
    old_tool = getattr(bpy, "_sketchup_tool_class", None)
    try:
        if old_tool: bpy.utils.unregister_tool(old_tool)
        else: bpy.utils.unregister_tool(SketchUpDrawTool)
    except Exception: pass

if __name__ == "__main__":
    try: unregister()
    except Exception: pass
    register()
