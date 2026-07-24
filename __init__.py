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
shader = None

def get_shader():
    global shader
    if shader is None:
        try:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        except ValueError:
            shader = gpu.shader.from_builtin('3D_UNIFORM_COLOR')
        except Exception:
            pass # Fails in background mode
    return shader

draw_handler_3d = None
draw_handler_2d = None
draw_points = []
mouse_pos = None

manual_axis_lock = None  # None, 'X', 'Y', 'Z'
shift_locked_axis = None # Vector
shift_failed_lock = False
current_axis_color = (0.0, 0.0, 0.0, 1.0) # Black default
typed_length = ""
snap_type = None
constraint_snap_point = None
hover_start_time = 0.0
hover_last_pos = None
is_tool_running = False
active_draw_tool = None
debug_gizmo_rects = []
debug_hud_text = ""

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
    global constraint_snap_point, rect_plane_axis
    if not draw_points or not mouse_pos:
        return
        
    s = get_shader()
    if not s: return

    is_rect_tool = False
    if active_draw_tool is not None:
        if type(active_draw_tool).__name__ == "SKETCHUP_OT_rectangle_tool":
            is_rect_tool = True
            
    color = current_axis_color
    
    if is_rect_tool and len(draw_points) >= 4:
        coords = []
        for i in range(len(draw_points) - 1):
            coords.extend([draw_points[i], draw_points[i+1]])
            
        if rect_plane_axis is not None:
            if abs(rect_plane_axis.x) > 0.9: color = (1.0, 0.2, 0.2, 1.0) # Red
            elif abs(rect_plane_axis.y) > 0.9: color = (0.2, 1.0, 0.2, 1.0) # Green
            elif abs(rect_plane_axis.z) > 0.9: color = (0.2, 0.5, 1.0, 1.0) # Blue
            else: color = (1.0, 0.2, 0.8, 1.0) # Magenta
    else:
        coords = [draw_points[-1], mouse_pos]
        
    batch = batch_for_shader(s, 'LINES', {"pos": coords})
    
    s.bind()
    s.uniform_float("color", color)
    
    # SketchUp draws thicker lines for locked axes
    if manual_axis_lock or shift_locked_axis:
        gpu.state.line_width_set(3.0)
    else:
        gpu.state.line_width_set(2.0)
        
    batch.draw(s)
    gpu.state.line_width_set(1.0)
    
    if constraint_snap_point is not None:
        # Draw a dotted line from constraint_snap_point to mouse_pos
        dist = (constraint_snap_point - mouse_pos).length
        num_segments = max(2, int(dist / 0.05)) # Dotted every 5cm
        dot_coords = []
        for i in range(0, num_segments, 2):
            p1 = mouse_pos.lerp(constraint_snap_point, i / num_segments)
            p2 = mouse_pos.lerp(constraint_snap_point, (i + 1) / num_segments)
            dot_coords.extend([p1, p2])
            
        if dot_coords:
            dot_batch = batch_for_shader(s, 'LINES', {"pos": dot_coords})
            s.uniform_float("color", color)
            dot_batch.draw(s)

def draw_callback_2d(self, context):
    global mouse_pos, last_point, typed_length, snap_type, hover_start_time, hover_last_pos, debug_gizmo_rects, debug_hud_text
    
    if debug_gizmo_rects:
        try:
            shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
        except ValueError:
            shader = gpu.shader.from_builtin('UNIFORM_COLOR')
        
        gpu.state.blend_set('ALPHA')
        for rect in debug_gizmo_rects:
            if len(rect) == 5:
                x, y, w, h, color = rect
            else:
                x, y, w, h = rect
                color = (1.0, 0.0, 0.0, 0.3)
                
            coords = [(x, y), (x + w, y), (x + w, y + h), (x, y + h)]
            batch_bg = batch_for_shader(shader, 'TRI_FAN', {"pos": coords})
            shader.bind()
            shader.uniform_float("color", color)
            batch_bg.draw(shader)
            
            batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": coords})
            shader.uniform_float("color", (color[0], color[1], color[2], 1.0))
            batch_outline.draw(shader)
        gpu.state.blend_set('NONE')

    props = getattr(context.scene, "sketchup_debug", None)
    show_hud = props and props.show_hud_text

    if debug_hud_text and show_hud:
        font_id = 0
        blf.position(font_id, 20.0, 40.0, 0.0)
        blf.color(font_id, 1.0, 1.0, 0.0, 1.0)
        try: blf.size(font_id, 16, 72)
        except TypeError: blf.size(font_id, 16)
        blf.draw(font_id, debug_hud_text)

    if not mouse_pos:
        return
        
    import time
    if hover_last_pos is None or (hover_last_pos - mouse_pos).length > 0.05:
        hover_last_pos = mouse_pos.copy()
        hover_start_time = time.time()

    if draw_points:
        length = (mouse_pos - draw_points[-1]).length
        mid_point = (mouse_pos + draw_points[-1]) / 2.0
        
        pos_2d = location_3d_to_region_2d(context.region, context.region_data, mid_point)
        
        if pos_2d:
            font_id = 0
            blf.position(font_id, float(pos_2d[0] + 15), float(pos_2d[1] + 15), 0.0)
            try:
                blf.size(font_id, 40, 72)
            except TypeError:
                blf.size(font_id, 40)
            
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

    if snap_type:
        try:
            import math
            try:
                shader = gpu.shader.from_builtin('2D_UNIFORM_COLOR')
            except ValueError:
                shader = gpu.shader.from_builtin('UNIFORM_COLOR')
                
            if constraint_snap_point:
                pos_2d = location_3d_to_region_2d(context.region, context.region_data, constraint_snap_point)
                label_pos_2d = location_3d_to_region_2d(context.region, context.region_data, mouse_pos)
            else:
                pos_2d = location_3d_to_region_2d(context.region, context.region_data, mouse_pos)
                label_pos_2d = pos_2d
                
            if snap_type == 'VERTEX':
                color = (0.2, 0.8, 0.2, 1.0)
                shape = 'CIRCLE'
                label = "Constrained on Line from Point" if constraint_snap_point else "Endpoint"
            elif snap_type == 'MIDPOINT':
                color = (0.0, 0.8, 0.8, 1.0)
                shape = 'CIRCLE'
                label = "Constrained on Line from Midpoint" if constraint_snap_point else "Midpoint"
            elif snap_type == 'EDGE':
                color = (0.8, 0.2, 0.2, 1.0)
                shape = 'SQUARE'
                label = "Constrained on Line" if constraint_snap_point else "On Edge"
            elif snap_type == 'FACE':
                color = (0.2, 0.2, 0.8, 1.0)
                shape = 'SQUARE'
                label = "Constrained on Line from Face" if constraint_snap_point else "On Face"
            elif snap_type == 'GRID':
                color = (0.5, 0.5, 0.5, 1.0)
                shape = 'CIRCLE'
                label = "Grid"
            else:
                shape = None
                label = None
                
            if shape and pos_2d:
                gpu.state.blend_set('ALPHA')
                if shape == 'CIRCLE':
                    segments = 16
                    radius = 6.0
                    coords = []
                    for i in range(segments):
                        angle = i * 2.0 * math.pi / segments
                        coords.append((pos_2d[0] + math.cos(angle) * radius, pos_2d[1] + math.sin(angle) * radius))
                    batch_fill = batch_for_shader(shader, 'TRI_FAN', {"pos": coords})
                    shader.bind()
                    shader.uniform_float("color", color)
                    batch_fill.draw(shader)
                    batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": coords})
                    shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
                    batch_outline.draw(shader)
                elif shape == 'SQUARE':
                    radius = 5.0
                    coords = [
                        (pos_2d[0] - radius, pos_2d[1] - radius),
                        (pos_2d[0] + radius, pos_2d[1] - radius),
                        (pos_2d[0] + radius, pos_2d[1] + radius),
                        (pos_2d[0] - radius, pos_2d[1] + radius)
                    ]
                    batch_fill = batch_for_shader(shader, 'TRI_FAN', {"pos": coords})
                    shader.bind()
                    shader.uniform_float("color", color)
                    batch_fill.draw(shader)
                    batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": coords})
                    shader.uniform_float("color", (1.0, 1.0, 1.0, 1.0))
                    batch_outline.draw(shader)
                gpu.state.blend_set('NONE')

                if time.time() - hover_start_time > 10.0:
                    font_id = 0
                    try: blf.size(font_id, 14, 72)
                    except TypeError: blf.size(font_id, 14)
                    dims = blf.dimensions(font_id, label)
                    width = dims[0] + 8
                    height = dims[1] + 8
                    x = float(label_pos_2d[0] + 15) if label_pos_2d else float(pos_2d[0] + 15)
                    y = float(label_pos_2d[1] - 10) if label_pos_2d else float(pos_2d[1] - 10)
                    box_coords = [
                        (x, y), (x + width, y), (x + width, y + height), (x, y + height)
                    ]
                    gpu.state.blend_set('ALPHA')
                    batch_bg = batch_for_shader(shader, 'TRI_FAN', {"pos": box_coords})
                    shader.bind()
                    shader.uniform_float("color", (1.0, 1.0, 1.0, 0.9))
                    batch_bg.draw(shader)
                    batch_outline = batch_for_shader(shader, 'LINE_LOOP', {"pos": box_coords})
                    shader.uniform_float("color", (0.5, 0.5, 0.5, 1.0))
                    batch_outline.draw(shader)
                    gpu.state.blend_set('NONE')
                    blf.position(font_id, x + 4, y + 4, 0.0)
                    blf.color(font_id, 0.0, 0.0, 0.0, 1.0)
                    blf.draw(font_id, label)
        except Exception as e:
            font_id = 0
            blf.position(font_id, 50.0, 50.0, 0.0)
            blf.color(font_id, 1.0, 0.0, 0.0, 1.0)
            try: blf.size(font_id, 20, 72)
            except TypeError: blf.size(font_id, 20)
            blf.draw(font_id, str(e))

def apply_geometry_snapping(context, event, hit, location, index, obj, matrix):
    use_snap = context.scene.tool_settings.use_snap
    if event.ctrl:
        use_snap = not use_snap
        
    if not use_snap:
        return location, None
        
    region = context.region
    rv3d = context.region_data
    mouse_2d = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
    snap_elements = context.scene.tool_settings.snap_elements
    snap_radius_px = 30.0
    
    best_vertex = None
    best_vertex_dist = 20.0
    best_mid = None
    best_mid_dist = 20.0
    best_edge = None
    best_edge_dist = 15.0

    def check_vertex(v_world):
        nonlocal best_vertex, best_vertex_dist
        v_2d = location_3d_to_region_2d(region, rv3d, v_world)
        if v_2d:
            dist = (v_2d - mouse_2d).length
            if dist < best_vertex_dist:
                best_vertex_dist = dist
                best_vertex = v_world

    def check_edge(v1_world, v2_world):
        nonlocal best_mid, best_mid_dist, best_edge, best_edge_dist
        if 'EDGE_MIDPOINT' in snap_elements or 'EDGE_CENTER' in snap_elements:
            midpoint = (v1_world + v2_world) * 0.5
            p_2d = location_3d_to_region_2d(region, rv3d, midpoint)
            if p_2d:
                dist = (p_2d - mouse_2d).length
                if dist < best_mid_dist:
                    best_mid_dist = dist
                    best_mid = midpoint

        if 'EDGE' in snap_elements:
            ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_2d)
            view_vector = region_2d_to_vector_3d(region, rv3d, mouse_2d)
            line_pts = geometry.intersect_line_line(v1_world, v2_world, ray_origin, ray_origin + view_vector * 10000)
            if line_pts:
                pt = line_pts[0]
                vec1 = pt - v1_world
                vec2 = v2_world - v1_world
                if vec1.dot(vec2) < 0: pt = v1_world
                elif vec1.length > vec2.length: pt = v2_world
                    
                p_2d = location_3d_to_region_2d(region, rv3d, pt)
                if p_2d:
                    dist = (p_2d - mouse_2d).length
                    if dist < best_edge_dist:
                        best_edge_dist = dist
                        best_edge = pt

    # 1. Check all low-poly visible objects (catches all isolated lines and previous drawings)
    for o in context.view_layer.objects:
        if o.type == 'MESH' and o.visible_get():
            mesh = o.data
            if len(mesh.vertices) < 10000:
                mat = o.matrix_world
                if o.mode == 'EDIT':
                    import bmesh
                    bm = bmesh.from_edit_mesh(mesh)
                    if 'VERTEX' in snap_elements:
                        for v in bm.verts:
                            check_vertex(mat @ v.co)
                    if 'EDGE' in snap_elements or 'EDGE_MIDPOINT' in snap_elements or 'EDGE_CENTER' in snap_elements:
                        for edge in bm.edges:
                            v1 = mat @ edge.verts[0].co
                            v2 = mat @ edge.verts[1].co
                            check_edge(v1, v2)
                else:
                    if 'VERTEX' in snap_elements:
                        for v in mesh.vertices:
                            check_vertex(mat @ v.co)
                    if 'EDGE' in snap_elements or 'EDGE_MIDPOINT' in snap_elements or 'EDGE_CENTER' in snap_elements:
                        for edge in mesh.edges:
                            v1 = mat @ mesh.vertices[edge.vertices[0]].co
                            v2 = mat @ mesh.vertices[edge.vertices[1]].co
                            check_edge(v1, v2)

    # 2. Check the raycast hit polygon (crucial for high-poly meshes skipped above)
    if hit and obj and obj.type == 'MESH' and len(obj.data.vertices) >= 10000:
        poly = None
        try:
            depsgraph = context.view_layer.depsgraph
            eval_obj = obj.evaluated_get(depsgraph)
            mesh = eval_obj.data
            poly = mesh.polygons[index]
        except Exception:
            try:
                mesh = obj.data
                poly = mesh.polygons[index]
            except Exception:
                pass
                
        if poly is not None:
            mat = obj.matrix_world
            if 'VERTEX' in snap_elements:
                for v_idx in poly.vertices:
                    check_vertex(mat @ mesh.vertices[v_idx].co)
            if 'EDGE' in snap_elements or 'EDGE_MIDPOINT' in snap_elements or 'EDGE_CENTER' in snap_elements:
                for loop_idx in poly.loop_indices:
                    v1_idx = mesh.loops[loop_idx].vertex_index
                    next_loop_idx = poly.loop_start + (loop_idx - poly.loop_start + 1) % poly.loop_total
                    v2_idx = mesh.loops[next_loop_idx].vertex_index
                    v1 = mat @ mesh.vertices[v1_idx].co
                    v2 = mat @ mesh.vertices[v2_idx].co
                    check_edge(v1, v2)

    if best_vertex:
        return best_vertex, 'VERTEX'
    if best_mid:
        return best_mid, 'MIDPOINT'
    if best_edge:
        return best_edge, 'EDGE'
    if hit and 'FACE' in snap_elements:
        return location, 'FACE'
        
    return location, None

def get_mouse_3d_pos(context, event, last_point=None):
    global manual_axis_lock, shift_locked_axis, shift_failed_lock, current_axis_color, constraint_snap_point
    
    constraint_snap_point = None

    region = context.region
    rv3d = context.region_data
    coord = (event.mouse_x - region.x, event.mouse_y - region.y)
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
        final_pos, s_type = apply_geometry_snapping(context, event, hit, raw_pos, index, obj, matrix)
        
        use_snap = context.scene.tool_settings.use_snap
        if event.ctrl: use_snap = not use_snap
        if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements) and final_pos == raw_pos:
            grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
            
            s_type = 'GRID'
            final_pos = Vector((
                round(final_pos.x / grid_scale) * grid_scale,
                round(final_pos.y / grid_scale) * grid_scale,
                round(final_pos.z / grid_scale) * grid_scale
            ))
        return final_pos, s_type

    # 2. Check Geometry Snapping FIRST
    geo_snap_pos, geo_snap_type = apply_geometry_snapping(context, event, hit, raw_pos, index, obj, matrix)
    has_geo_snap = (geo_snap_pos != raw_pos)

    # 3. Determine Active Constraint Axis
    active_axis = None
    
    if manual_axis_lock == 'X':
        active_axis = Vector((1, 0, 0))
    elif manual_axis_lock == 'Y':
        active_axis = Vector((0, 1, 0))
    elif manual_axis_lock == 'Z':
        active_axis = Vector((0, 0, 1))
    else:
        if event.shift:
            if shift_locked_axis is None and not shift_failed_lock:
                # Lock to an axis only if we are currently hovering over it
                last_pt_2d = location_3d_to_region_2d(region, rv3d, last_point)
                mouse_2d = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
                
                if last_pt_2d and (mouse_2d - last_pt_2d).length > 5.0:
                    cam_pos = rv3d.view_matrix.inverted().translation
                    dist_to_cam = (last_point - cam_pos).length
                    
                    best_axis = None
                    best_dist = 20.0 # 20 pixels max perpendicular distance
                    
                    for axis in snap_dirs:
                        ax_pt_2d = location_3d_to_region_2d(region, rv3d, last_point + axis * (dist_to_cam * 0.5))
                        if ax_pt_2d:
                            ax_dir_2d = (ax_pt_2d - last_pt_2d)
                            if ax_dir_2d.length > 0.001:
                                ax_dir_2d.normalize()
                                
                                vec = mouse_2d - last_pt_2d
                                proj_len = vec.dot(ax_dir_2d)
                                if proj_len > 0:
                                    perp_vec = vec - ax_dir_2d * proj_len
                                    perp_dist = perp_vec.length
                                    if perp_dist < best_dist:
                                        best_dist = perp_dist
                                        best_axis = axis
                    if best_axis is not None:
                        shift_locked_axis = best_axis
                    else:
                        shift_failed_lock = True
        else:
            shift_locked_axis = None
            shift_failed_lock = False
            
        if shift_locked_axis is not None:
            active_axis = shift_locked_axis
        else:
            # ONLY auto-snap to axis if we didn't snap to geometry!
            if not has_geo_snap:
                last_pt_2d = location_3d_to_region_2d(region, rv3d, last_point)
                mouse_2d = Vector((event.mouse_x - region.x, event.mouse_y - region.y))
                
                if last_pt_2d and (mouse_2d - last_pt_2d).length > 5.0:
                    cam_pos = rv3d.view_matrix.inverted().translation
                    dist_to_cam = (last_point - cam_pos).length
                    
                    best_axis = None
                    best_dist = 20.0 # 20 pixels max perpendicular distance
                    
                    for axis in primary_axes:
                        ax_pt_2d = location_3d_to_region_2d(region, rv3d, last_point + axis * (dist_to_cam * 0.5))
                        if ax_pt_2d:
                            ax_dir_2d = (ax_pt_2d - last_pt_2d)
                            if ax_dir_2d.length > 0.001:
                                ax_dir_2d.normalize()
                                
                                vec = mouse_2d - last_pt_2d
                                proj_len = vec.dot(ax_dir_2d)
                                if proj_len > 0: # Only snap if pointing in the positive direction of this axis vector
                                    perp_vec = vec - ax_dir_2d * proj_len
                                    perp_dist = perp_vec.length
                                    if perp_dist < best_dist:
                                        best_dist = perp_dist
                                        best_axis = axis
                    
                    if best_axis is not None:
                        active_axis = best_axis

    # 4. Apply Constraint
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
            
        # SKETCHUP INFERENCE: Project geo_snap_pos onto the active axis
        if has_geo_snap:
            vec_to_snap = geo_snap_pos - last_point
            proj_dist = vec_to_snap.dot(active_axis)
            final_pos = last_point + active_axis * proj_dist
            constraint_snap_point = geo_snap_pos
            s_type = geo_snap_type
        else:
            final_pos = constrained_pos
            s_type = None
            constraint_snap_point = None
            
        # Grid Snapping along axis
        use_snap = context.scene.tool_settings.use_snap
        if event.ctrl: use_snap = not use_snap
        if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements) and not has_geo_snap:
            grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
            
            # Always use absolute grid snapping for drawing to align endpoints to the grid
            if abs(active_axis.x) > 0.5:
                target = round(final_pos.x / grid_scale) * grid_scale
                proj_dist = (target - last_point.x) / active_axis.x if active_axis.x != 0 else 0
            elif abs(active_axis.y) > 0.5:
                target = round(final_pos.y / grid_scale) * grid_scale
                proj_dist = (target - last_point.y) / active_axis.y if active_axis.y != 0 else 0
            else:
                target = round(final_pos.z / grid_scale) * grid_scale
                proj_dist = (target - last_point.z) / active_axis.z if active_axis.z != 0 else 0
            final_pos = last_point + active_axis * proj_dist
            s_type = 'GRID'

        return final_pos, s_type

    else:
        # No axis lock (either unconstrained or snapped to geometry)
        current_axis_color = (0.0, 0.0, 0.0, 1.0) # Black
        constraint_snap_point = None
        
        if has_geo_snap:
            final_pos = geo_snap_pos
            s_type = geo_snap_type
        else:
            final_pos = raw_pos
            s_type = None
            
        use_snap = context.scene.tool_settings.use_snap
        if event.ctrl: use_snap = not use_snap
        if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements) and not has_geo_snap:
            grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
            
            s_type = 'GRID'
            final_pos = Vector((
                round(final_pos.x / grid_scale) * grid_scale,
                round(final_pos.y / grid_scale) * grid_scale,
                round(final_pos.z / grid_scale) * grid_scale
            ))
            
        return final_pos, s_type

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

    def setup_bmesh(self, context):
        self.obj = context.edit_object
        if self.obj and self.obj.type == 'MESH':
            self.bm = bmesh.from_edit_mesh(self.obj.data)

    def update_mesh(self):
        if hasattr(self, 'bm') and hasattr(self, 'obj') and self.obj:
            self.bm.normal_update()
            bmesh.update_edit_mesh(self.obj.data)

    def end_tool(self, context):
        global draw_points, mouse_pos, manual_axis_lock, shift_locked_axis, shift_failed_lock, typed_length, snap_type, is_tool_running, active_draw_tool
        draw_points = []
        mouse_pos = None
        manual_axis_lock = None
        shift_locked_axis = None
        shift_failed_lock = False
        typed_length = ""
        snap_type = None
        is_tool_running = False
        active_draw_tool = None
        self.chain_verts = []
        context.workspace.status_text_set(None)
        self.remove_draw_handler()
        if getattr(self, 'cursor_set', False):
            context.window.cursor_modal_restore()
            self.cursor_set = False
        
        if hasattr(self, 'bm'):
            delattr(self, 'bm')
        if hasattr(self, 'obj'):
            delattr(self, 'obj')

    def break_chain(self, is_redo=False):
        global draw_points, manual_axis_lock, shift_locked_axis, shift_failed_lock, typed_length
        if not is_redo and hasattr(self, 'redo_history'):
            self.redo_history.clear()
            
        self.undo_history.append({
            'type': 'BREAK_CHAIN',
            'action_type': 'BREAK_CHAIN',
            'prev_chain_coords': [v.co.copy() for v in self.chain_verts],
            'prev_draw': list(draw_points)
        })
        draw_points.clear()
        self.chain_verts.clear()
        manual_axis_lock = None
        shift_locked_axis = None
        shift_failed_lock = False
        typed_length = ""
        bpy.ops.ed.undo_push(message="SketchUp Break Chain")

    def add_point(self, pos, is_redo=False):
        global draw_points, manual_axis_lock, shift_locked_axis, shift_failed_lock
        
        if not hasattr(self, 'bm') or not self.obj:
            return

        if not is_redo and hasattr(self, 'redo_history'):
            self.redo_history.clear()

        # Save state for undo BEFORE we change anything
        self.undo_history.append({
            'type': 'ADD_POINT',
            'action_type': 'ADD_POINT',
            'pos': pos.copy(),
            'prev_chain_coords': [v.co.copy() for v in self.chain_verts],
            'prev_draw': list(draw_points)
        })

        if len(draw_points) >= 2:
            world_first_co = draw_points[0]
            if (pos - world_first_co).length < 0.01:
                local_first_pos = self.obj.matrix_world.inverted() @ draw_points[0]
                local_last_pos = self.obj.matrix_world.inverted() @ draw_points[-1]
                
                self.bm.verts.ensure_lookup_table()
                v_first = None
                v_prev = None
                for bv in self.bm.verts:
                    if not v_first and (bv.co - local_first_pos).length < 0.001:
                        v_first = bv
                    if not v_prev and (bv.co - local_last_pos).length < 0.001:
                        v_prev = bv
                        
                if not v_first: v_first = self.bm.verts.new(local_first_pos)
                if not v_prev: v_prev = self.bm.verts.new(local_last_pos)
                
                e = None
                try:
                    e = self.bm.edges.new((v_prev, v_first))
                except ValueError:
                    pass
                
                for bv in self.bm.verts: bv.select = False
                for be in self.bm.edges: be.select = False
                for bf in self.bm.faces: bf.select = False
                
                for pt in draw_points:
                    local_pt = self.obj.matrix_world.inverted() @ pt
                    for bv in self.bm.verts:
                        if (bv.co - local_pt).length < 0.001:
                            bv.select = True
                            break
                            
                if e:
                    e.select = True
                
                self.update_mesh()
                
                ts = bpy.context.scene.tool_settings
                orig_am = ts.use_mesh_automerge
                orig_ams = ts.use_mesh_automerge_and_split
                ts.use_mesh_automerge = True
                ts.use_mesh_automerge_and_split = True
                
                bpy.ops.transform.translate(value=(0, 0, 0))
                bpy.ops.mesh.edge_face_add()
                
                ts.use_mesh_automerge = orig_am
                ts.use_mesh_automerge_and_split = orig_ams
                
                bpy.ops.ed.undo_push(message="SketchUp Close Face")
                
                self.chain_verts.clear()
                draw_points.clear()
                manual_axis_lock = None
                shift_locked_axis = None
                shift_failed_lock = False
                self.report({'INFO'}, "Face Closed")
                
                if hasattr(self, 'bm'):
                    self.bm.free()
                self.bm = bmesh.from_edit_mesh(self.obj.data)
                self.bm.verts.ensure_lookup_table()
                for bv in self.bm.verts: bv.select = False
                for be in self.bm.edges: be.select = False
                for bf in self.bm.faces: bf.select = False
                self.update_mesh()
                return

        local_pos = self.obj.matrix_world.inverted() @ pos
        v = self.bm.verts.new(local_pos)
        
        e = None
        if len(self.chain_verts) > 0:
            v_prev = self.chain_verts[-1]
            try:
                e = self.bm.edges.new((v_prev, v))
            except ValueError:
                pass
                
        draw_points.append(pos.copy())
        
        # Deselect everything
        for bv in self.bm.verts: bv.select = False
        for be in self.bm.edges: be.select = False
        for bf in self.bm.faces: bf.select = False
        
        # Select newly added geometry
        v.select = True
        if e: e.select = True
        if len(self.chain_verts) > 0:
            self.chain_verts[-1].select = True
            
        self.update_mesh()
        
        # Perform Auto Merge & Split
        ts = bpy.context.scene.tool_settings
        orig_am = ts.use_mesh_automerge
        orig_ams = ts.use_mesh_automerge_and_split
        ts.use_mesh_automerge = True
        ts.use_mesh_automerge_and_split = True
        
        bpy.ops.transform.translate(value=(0, 0, 0))
        
        ts.use_mesh_automerge = orig_am
        ts.use_mesh_automerge_and_split = orig_ams
        
        # Push to Blender undo stack
        bpy.ops.ed.undo_push(message="SketchUp Add Point")
        
        # Re-fetch the bmesh because topology might have changed completely
        if hasattr(self, 'bm'):
            self.bm.free()
        self.bm = bmesh.from_edit_mesh(self.obj.data)
        self.bm.verts.ensure_lookup_table()
        
        # Recover self.chain_verts (we only need the LAST vertex for the next segment)
        best_v = None
        best_d = 0.001
        for bv in self.bm.verts:
            d = (bv.co - local_pos).length
            if d < best_d:
                best_d = d
                best_v = bv
                
        self.chain_verts = [best_v] if best_v else []
        
        # Deselect everything so the last drawn line isn't highlighted in yellow
        for bv in self.bm.verts: bv.select = False
        for be in self.bm.edges: be.select = False
        for bf in self.bm.faces: bf.select = False
        self.update_mesh()
        
        manual_axis_lock = None
        shift_locked_axis = None
        shift_failed_lock = False

    def update_mouse_pos(self, context, event):
        global mouse_pos, draw_points, snap_type
        last_pt = draw_points[-1] if len(draw_points) > 0 else None
        res = get_mouse_3d_pos(context, event, last_pt)
        if res:
            mouse_pos, snap_type = res

    def modal(self, context, event):
        global mouse_pos, draw_points, manual_axis_lock, shift_locked_axis, shift_failed_lock, typed_length, debug_gizmo_rects, debug_hud_text
        
        # Check if the user selected a different tool
        active_tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if active_tool and active_tool.idname != "sketchup.draw_tool_v2":
            self.end_tool(context)
            self.report({'INFO'}, "SketchUp Draw Tool Deactivated")
            return {'FINISHED'}
            
        is_mouse_in_window = True
        props = getattr(context.scene, "sketchup_debug", None)
        disable_pass_through = props and props.disable_pass_through

        if event.mouse_x < context.area.x or event.mouse_x > context.area.x + context.area.width or \
           event.mouse_y < context.area.y or event.mouse_y > context.area.y + context.area.height:
            is_mouse_in_window = False
        elif not disable_pass_through:
            for region in context.area.regions:
                if region.type in {'UI', 'TOOLS', 'HEADER', 'FOOTER', 'TOOL_HEADER'}:
                    if region.x <= event.mouse_x <= region.x + region.width and \
                       region.y <= event.mouse_y <= region.y + region.height:
                        is_mouse_in_window = False
                        break
                        
        if is_mouse_in_window and getattr(context.space_data, 'show_gizmo_navigate', False):
            ui_scale = 1.0
            use_region_overlap = False
            if hasattr(context, 'preferences'):
                if hasattr(context.preferences, 'view') and hasattr(context.preferences.view, 'ui_scale'):
                    ui_scale = context.preferences.view.ui_scale
                if hasattr(context.preferences, 'system'):
                    use_region_overlap = getattr(context.preferences.system, 'use_region_overlap', False)
            
            # axis_gizmo_width = 210 * ui_scale
            # axis_gizmo_height = 210 * ui_scale
            
            # nav_buttons_width = 60 * ui_scale    # Narrower to free up drawing space
            # nav_buttons_height = 450 * ui_scale  # Taller to cover Camera and Grid
            # nav_buttons_top = 160 * ui_scale     # Starts below axis gizmo

            axis_gizmo_width = 250 * ui_scale
            axis_gizmo_height = 300 * ui_scale
            
            nav_buttons_width = 120 * ui_scale    # Narrower to free up drawing space
            nav_buttons_height = 450 * ui_scale  # Taller to cover Camera and Grid
            nav_buttons_top = 160 * ui_scale     # Starts below axis gizmo


            ui_region_width = 0
            if use_region_overlap:
                for r in context.area.regions:
                    if r.type == 'UI' and r.width > 1:
                        ui_region_width = r.width
                        break
                        
            debug_gizmo_rects.clear()
            window_region = None
            props = getattr(context.scene, "sketchup_debug", None)
            show_axis = props and props.show_axis_box if props else True
            show_nav = props and props.show_nav_box if props else True
            show_ui = props and props.show_ui_boxes if props else True
            
            for region in context.area.regions:
                if region.type == 'WINDOW':
                    window_region = region
                    right_edge = region.width - ui_region_width
                    mouse_x = event.mouse_x - region.x
                    mouse_y = event.mouse_y - region.y
                    
                    axis_x = right_edge - axis_gizmo_width
                    axis_y = region.height - axis_gizmo_height
                    if show_axis:
                        debug_gizmo_rects.append((axis_x, axis_y, axis_gizmo_width, axis_gizmo_height, (1.0, 0.0, 0.0, 0.3)))
                    
                    nav_top_y = region.height - nav_buttons_top
                    nav_bottom_y = nav_top_y - nav_buttons_height
                    nav_x = right_edge - nav_buttons_width
                    if show_nav:
                        debug_gizmo_rects.append((nav_x, nav_bottom_y, nav_buttons_width, nav_buttons_height, (1.0, 0.0, 0.0, 0.3)))
                    
                    debug_hud_text = f"Mouse: {mouse_x}, {mouse_y} | Scale: {ui_scale:.2f} | Overlap: {use_region_overlap} | UI_Width: {ui_region_width} | Window: {region.width}x{region.height}"
                    
                    is_over_axis = (mouse_x > axis_x) and (mouse_y > axis_y)
                                   
                    is_over_nav = (mouse_x > nav_x) and (nav_bottom_y < mouse_y < nav_top_y)
                                  
                    if not disable_pass_through and (is_over_axis or is_over_nav):
                        is_mouse_in_window = False
                    break
            
            if window_region and show_ui:
                for region in context.area.regions:
                    if region.type in {'UI', 'TOOLS', 'HEADER', 'FOOTER', 'TOOL_HEADER'}:
                        rx = region.x - window_region.x
                        ry = region.y - window_region.y
                        debug_gizmo_rects.append((rx, ry, region.width, region.height, (0.0, 0.0, 1.0, 0.3)))
                        
        if is_mouse_in_window:
            if not getattr(self, 'cursor_set', False):
                context.window.cursor_modal_set('PAINT_BRUSH')
                self.cursor_set = True
                self.report({'INFO'}, "Cursor changed to PEN")
        else:
            if getattr(self, 'cursor_set', False):
                context.window.cursor_modal_restore()
                self.cursor_set = False
                self.report({'INFO'}, "Cursor restored to DEFAULT")
                        
        context.area.tag_redraw()

        if event.type in {'LEFT_SHIFT', 'RIGHT_SHIFT'}:
            if event.value == 'RELEASE':
                shift_locked_axis = None
                shift_failed_lock = False
            self.update_mouse_pos(context, event)
            return {'PASS_THROUGH'}

        elif event.type == 'MOUSEMOVE':
            self.update_mouse_pos(context, event)
            if not is_mouse_in_window:
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}

        elif event.type == 'LEFTMOUSE':
            props = getattr(context.scene, "sketchup_debug", None)
            disable_pass_through = props and props.disable_pass_through
            
            if not disable_pass_through and not is_mouse_in_window:
                return {'PASS_THROUGH'}
                
            if event.value == 'PRESS':
                if mouse_pos:
                    if not hasattr(self, 'bm'):
                        self.setup_bmesh(context)
                    if hasattr(self, 'bm'):
                        self.add_point(mouse_pos)
                        typed_length = ""
                    self.update_mouse_pos(context, event)
            return {'RUNNING_MODAL'}
            
        elif event.type == 'RIGHTMOUSE' and event.value == 'PRESS':
            self.break_chain()
            self.report({'INFO'}, "Chain Broken")
            return {'RUNNING_MODAL'}

        elif event.type == 'ESC' and event.value == 'PRESS':
            self.end_tool(context)
            self.report({'INFO'}, "Finished SketchUp Draw Tool")
            return {'FINISHED'}
            
        elif event.type == 'Z' and event.value == 'PRESS' and (event.ctrl or event.oskey):
            if event.shift:
                if hasattr(self, 'redo_history') and len(self.redo_history) > 0:
                    action = self.redo_history.pop()
                    if action['type'] == 'ADD_POINT':
                        self.add_point(action['pos'], is_redo=True)
                        self.report({'INFO'}, "Redid Add Point")
                    elif action['type'] == 'BREAK_CHAIN':
                        self.break_chain(is_redo=True)
                        self.report({'INFO'}, "Redid Break Chain")
                else:
                    self.report({'WARNING'}, "Nothing to redo")
                return {'RUNNING_MODAL'}
                
            if len(self.undo_history) > 0:
                last_action = self.undo_history.pop()
                
                # Undo Blender mesh state
                bpy.ops.ed.undo()
                
                if hasattr(self, 'bm'):
                    self.bm.free()
                self.bm = bmesh.from_edit_mesh(self.obj.data)
                self.bm.verts.ensure_lookup_table()
                
                # Recover chain_verts
                self.chain_verts = []
                for co in last_action.get('prev_chain_coords', []):
                    best_v = None
                    best_d = 0.001
                    for bv in self.bm.verts:
                        d = (bv.co - co).length
                        if d < best_d:
                            best_d = d
                            best_v = bv
                    if best_v:
                        self.chain_verts.append(best_v)
                        
                draw_points.clear()
                draw_points.extend(last_action.get('prev_draw', []))
                manual_axis_lock = None
                shift_locked_axis = None
                shift_failed_lock = False
                typed_length = ""
                
                if not hasattr(self, 'redo_history'):
                    self.redo_history = []
                self.redo_history.append({
                    'type': last_action['action_type'],
                    'pos': last_action.get('pos')
                })
                
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
            global draw_points, mouse_pos, manual_axis_lock, shift_locked_axis, shift_failed_lock, typed_length, snap_type, is_tool_running, active_draw_tool
            if is_tool_running:
                return {'PASS_THROUGH'}
            is_tool_running = True
            active_draw_tool = self
            
            draw_points = []
            mouse_pos = None
            manual_axis_lock = None
            shift_locked_axis = None
            shift_failed_lock = False
            typed_length = ""
            snap_type = None
            self.chain_verts = []
            self.undo_history = []
            self.redo_history = []
            
            self.update_mouse_pos(context, event)
            
            self.add_draw_handler(context)

            context.window_manager.modal_handler_add(self)
            context.workspace.status_text_set("Click to draw. X/Y/Z to lock axis. Type numbers and press Enter for exact length. Right Click to break.")
            return {'RUNNING_MODAL'}
        else:
            self.report({'WARNING'}, "Active space must be a View3D")
            return {'CANCELLED'}


class SKETCHUP_OT_add_point(bpy.types.Operator):
    bl_idname = "sketchup.add_point"
    bl_label = "Add Point"
    bl_options = {'REGISTER', 'UNDO'}
    
    def invoke(self, context, event):
        global active_draw_tool, mouse_pos, typed_length
        if not active_draw_tool:
            bpy.ops.sketchup.draw_tool('INVOKE_DEFAULT')
            
        if active_draw_tool and mouse_pos:
            if not hasattr(active_draw_tool, 'bm'):
                active_draw_tool.setup_bmesh(context)
            if hasattr(active_draw_tool, 'bm'):
                active_draw_tool.add_point(mouse_pos)
                typed_length = ""
            active_draw_tool.update_mouse_pos(context, event)
        return {'FINISHED'}

# --- Workspace Tools ---

class SketchUpDrawTool(WorkSpaceTool):
    bl_space_type = 'VIEW_3D'
    bl_context_mode = 'EDIT_MESH'
    bl_idname = "sketchup.draw_tool_v2"
    bl_label = "SketchUp Draw Tool"
    bl_description = "Draw lines and outlines in a SketchUp-like manner"
    bl_icon = "ops.curve.draw"
    bl_cursor = 'PAINT_BRUSH'
    bl_widget = None
    bl_keymap = (
        ("sketchup.draw_tool", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None),
        ("sketchup.add_point", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
    )



# --- Rectangle Tool State ---
rect_start_pos = None
rect_plane_axis = None # The normal axis of the plane (X, Y, or Z)

def get_mouse_3d_pos_rect(context, event):
    global constraint_snap_point
    # Determine intersection with a plane
    region = context.region
    rv3d = context.region_data
    mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
    
    ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_coord)
    view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
    
    depsgraph = context.evaluated_depsgraph_get()
    
    hit, location, normal, index, obj, matrix = context.scene.ray_cast(depsgraph, ray_origin, view_vector)
    
    raw_pos = location
    if not hit:
        plane_normal = Vector((0, 0, 1))
        plane_point = Vector((0, 0, 0))
        raw_pos = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, plane_point, plane_normal)
        if raw_pos is None:
            raw_pos = ray_origin + view_vector * 10.0
            
    geo_snap_pos, snap_type = apply_geometry_snapping(context, event, hit, raw_pos, index, obj, matrix)
    has_geo_snap = (snap_type is not None)

    # If we have a start pos, we MUST stay on the same plane
    if rect_start_pos is not None and rect_plane_axis is not None:
        # Intersect with the plane defined by rect_start_pos and rect_plane_axis
        plane_hit = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, rect_start_pos, rect_plane_axis)
        if plane_hit:
            if has_geo_snap:
                # Snap to geometry but project onto our plane
                proj_dist = (geo_snap_pos - rect_start_pos).dot(rect_plane_axis)
                constraint_snap_point = geo_snap_pos
                return geo_snap_pos - rect_plane_axis * proj_dist, snap_type
            
            constraint_snap_point = None
            # Grid snapping
            use_snap = getattr(context.scene.tool_settings, "use_snap", False)
            if event.ctrl: use_snap = not use_snap
            if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements):
                grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
                target_x = round(plane_hit.x / grid_scale) * grid_scale
                target_y = round(plane_hit.y / grid_scale) * grid_scale
                target_z = round(plane_hit.z / grid_scale) * grid_scale
                if rect_plane_axis.z > 0.9: plane_hit = Vector((target_x, target_y, plane_hit.z))
                elif rect_plane_axis.y > 0.9: plane_hit = Vector((target_x, plane_hit.y, target_z))
                elif rect_plane_axis.x > 0.9: plane_hit = Vector((plane_hit.x, target_y, target_z))
                return plane_hit, 'GRID'
                
            return plane_hit, None
            
    # We don't have a start pos, or we don't have an axis yet
    if has_geo_snap:
        constraint_snap_point = geo_snap_pos
        return geo_snap_pos, snap_type
        
    constraint_snap_point = None
    # Default to XY plane (ground) if no snap
    fallback_normal = Vector((0,0,1))
    if manual_axis_lock == 'X':
        fallback_normal = Vector((1,0,0))
    elif manual_axis_lock == 'Y':
        fallback_normal = Vector((0,1,0))
    elif manual_axis_lock == 'Z':
        fallback_normal = Vector((0,0,1))
        
    plane_hit = geometry.intersect_line_plane(ray_origin, ray_origin + view_vector * 10000, Vector((0,0,0)), fallback_normal)
    if plane_hit:
        use_snap = getattr(context.scene.tool_settings, "use_snap", False)
        if event.ctrl: use_snap = not use_snap
        if use_snap and ('INCREMENT' in context.scene.tool_settings.snap_elements or 'GRID' in context.scene.tool_settings.snap_elements):
            grid_scale = getattr(context.space_data.overlay, "grid_scale", 1.0) if getattr(context, "space_data", None) and hasattr(context.space_data, "overlay") else 1.0
            target_x = round(plane_hit.x / grid_scale) * grid_scale
            target_y = round(plane_hit.y / grid_scale) * grid_scale
            plane_hit = Vector((target_x, target_y, 0))
            return plane_hit, 'GRID'
        return plane_hit, None
        
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
        global draw_handler_3d, draw_handler_2d
        if draw_handler_3d is None:
            draw_handler_3d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_3d, (self, context), 'WINDOW', 'POST_VIEW')
        if draw_handler_2d is None:
            draw_handler_2d = bpy.types.SpaceView3D.draw_handler_add(draw_callback_2d, (self, context), 'WINDOW', 'POST_PIXEL')
            
    def remove_draw_handler(self, context):
        global draw_handler_3d, draw_handler_2d
        if draw_handler_3d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler_3d, 'WINDOW')
            draw_handler_3d = None
        if draw_handler_2d is not None:
            bpy.types.SpaceView3D.draw_handler_remove(draw_handler_2d, 'WINDOW')
            draw_handler_2d = None
            
    def end_tool(self, context):
        global is_tool_running, active_draw_tool, rect_start_pos, manual_axis_lock
        self.remove_draw_handler(context)
        is_tool_running = False
        active_draw_tool = None
        rect_start_pos = None
        manual_axis_lock = None
        if hasattr(self, 'bm'):
            self.bm.free()
        if getattr(context, 'area', None):
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
        global mouse_pos, draw_points, rect_start_pos, rect_plane_axis, snap_type
        res = get_mouse_3d_pos_rect(context, event)
        if res:
            m_pos, s_type = res
            mouse_pos = m_pos
            snap_type = s_type
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
        global mouse_pos, draw_points, rect_start_pos, rect_plane_axis, manual_axis_lock
        
        active_tool = context.workspace.tools.from_space_view3d_mode(context.mode, create=False)
        if active_tool and active_tool.idname != "sketchup.rectangle_tool":
            self.end_tool(context)
            return {'FINISHED'}

        is_mouse_in_window = True
        props = getattr(context.scene, "sketchup_debug", None)
        disable_pass_through = props and props.disable_pass_through

        if event.mouse_x < context.area.x or event.mouse_x > context.area.x + context.area.width or \
           event.mouse_y < context.area.y or event.mouse_y > context.area.y + context.area.height:
            is_mouse_in_window = False
        elif not disable_pass_through:
            for region in context.area.regions:
                if region.type in {'UI', 'TOOLS', 'HEADER', 'FOOTER', 'TOOL_HEADER'}:
                    if region.x <= event.mouse_x <= region.x + region.width and \
                       region.y <= event.mouse_y <= region.y + region.height:
                        is_mouse_in_window = False
                        break
                        
        if is_mouse_in_window and getattr(context.space_data, 'show_gizmo_navigate', False):
            ui_scale = 1.0
            use_region_overlap = False
            if hasattr(context, 'preferences'):
                if hasattr(context.preferences, 'view') and hasattr(context.preferences.view, 'ui_scale'):
                    ui_scale = context.preferences.view.ui_scale
                if hasattr(context.preferences, 'system'):
                    use_region_overlap = getattr(context.preferences.system, 'use_region_overlap', False)
            
            axis_gizmo_width = 250 * ui_scale
            axis_gizmo_height = 300 * ui_scale
            
            nav_buttons_width = 120 * ui_scale
            nav_buttons_height = 450 * ui_scale
            nav_buttons_top = 160 * ui_scale

            ui_region_width = 0
            if use_region_overlap:
                for r in context.area.regions:
                    if r.type == 'UI' and r.width > 1:
                        ui_region_width = r.width
                        break
            
            for region in context.area.regions:
                if region.type == 'WINDOW':
                    right_edge = region.width - ui_region_width
                    mouse_x = event.mouse_x - region.x
                    mouse_y = event.mouse_y - region.y
                    
                    axis_x = right_edge - axis_gizmo_width
                    axis_y = region.height - axis_gizmo_height
                    
                    nav_top_y = region.height - nav_buttons_top
                    nav_bottom_y = nav_top_y - nav_buttons_height
                    nav_x = right_edge - nav_buttons_width
                    
                    is_over_axis = (mouse_x > axis_x) and (mouse_y > axis_y)
                    is_over_nav = (mouse_x > nav_x) and (nav_bottom_y < mouse_y < nav_top_y)
                    
                    if not disable_pass_through and (is_over_axis or is_over_nav):
                        is_mouse_in_window = False
                    break

        if is_mouse_in_window:
            if not getattr(self, 'cursor_set', False):
                context.window.cursor_modal_set('PAINT_BRUSH')
                self.cursor_set = True
        else:
            if getattr(self, 'cursor_set', False):
                context.window.cursor_modal_restore()
                self.cursor_set = False

        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            self.update_mouse_pos(context, event)
            if not is_mouse_in_window:
                return {'PASS_THROUGH'}
            return {'RUNNING_MODAL'}
            
        elif event.type == 'Z' and event.value == 'PRESS' and (event.ctrl or event.oskey):
            if event.shift:
                try:
                    bpy.ops.ed.redo()
                    self.report({'INFO'}, "Redo")
                except RuntimeError:
                    pass
            else:
                try:
                    bpy.ops.ed.undo()
                    self.report({'INFO'}, "Undo")
                except RuntimeError:
                    pass
            
            if hasattr(self, 'obj') and self.obj:
                if hasattr(self, 'bm'):
                    self.bm.free()
                self.bm = bmesh.from_edit_mesh(self.obj.data)
                self.bm.verts.ensure_lookup_table()
            
            rect_start_pos = None
            draw_points = []
            manual_axis_lock = None
            
            self.update_mouse_pos(context, event)
            return {'RUNNING_MODAL'}
            
        elif event.value == 'PRESS' and not (event.ctrl or event.oskey):
            if event.type == 'X':
                manual_axis_lock = 'X' if manual_axis_lock != 'X' else None
                if rect_start_pos is not None:
                    rect_plane_axis = Vector((1, 0, 0)) if manual_axis_lock else rect_plane_axis
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
            elif event.type == 'Y':
                manual_axis_lock = 'Y' if manual_axis_lock != 'Y' else None
                if rect_start_pos is not None:
                    rect_plane_axis = Vector((0, 1, 0)) if manual_axis_lock else rect_plane_axis
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
            elif event.type == 'Z':
                manual_axis_lock = 'Z' if manual_axis_lock != 'Z' else None
                if rect_start_pos is not None:
                    rect_plane_axis = Vector((0, 0, 1)) if manual_axis_lock else rect_plane_axis
                self.update_mouse_pos(context, event)
                return {'RUNNING_MODAL'}
            
        if event.type == 'LEFTMOUSE':
            if not disable_pass_through and not is_mouse_in_window:
                return {'PASS_THROUGH'}

            if event.value == 'PRESS':
                if mouse_pos:
                    if not hasattr(self, 'bm'):
                        self.setup_bmesh(context)
                        
                    if rect_start_pos is None:
                        # First click
                        rect_start_pos = mouse_pos.copy()
                        
                        # Determine plane axis
                        if manual_axis_lock == 'X':
                            rect_plane_axis = Vector((1, 0, 0))
                        elif manual_axis_lock == 'Y':
                            rect_plane_axis = Vector((0, 1, 0))
                        elif manual_axis_lock == 'Z':
                            rect_plane_axis = Vector((0, 0, 1))
                        else:
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
            global draw_points, mouse_pos, is_tool_running, active_draw_tool, rect_start_pos, manual_axis_lock
            if is_tool_running:
                return {'PASS_THROUGH'}
            is_tool_running = True
            active_draw_tool = self
            
            draw_points = []
            mouse_pos = None
            rect_start_pos = None
            manual_axis_lock = None
            
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
    bl_icon = "ops.gpencil.primitive_box"
    bl_cursor = 'PAINT_BRUSH'
    bl_widget = None
    bl_keymap = (
        ("sketchup.rectangle_tool", {"type": 'MOUSEMOVE', "value": 'ANY', "any": True}, None),
        ("sketchup.rectangle_tool", {"type": 'LEFTMOUSE', "value": 'PRESS', "any": True}, None),
    )

# --- Registration ---

class SketchUpDebugProperties(bpy.types.PropertyGroup):
    show_axis_box: bpy.props.BoolProperty(
        name="Show Axis Gizmo Box",
        description="Toggle the visibility of the red box over the top right axis gizmo",
        default=False
    )
    show_nav_box: bpy.props.BoolProperty(
        name="Show Navigation Buttons Box",
        description="Toggle the visibility of the red box over the navigation buttons",
        default=False
    )
    show_ui_boxes: bpy.props.BoolProperty(
        name="Show UI Region Boxes",
        description="Toggle the visibility of the blue boxes over standard UI regions",
        default=False
    )
    show_hud_text: bpy.props.BoolProperty(
        name="Show HUD Text",
        description="Toggle the visibility of the debug HUD text",
        default=False
    )
    disable_pass_through: bpy.props.BoolProperty(
        name="Disable UI Pass-Through",
        description="Disable passing clicks to the UI, allowing you to draw everywhere (UI buttons won't work)",
        default=False
    )

class SKETCHUP_PT_debug_panel(bpy.types.Panel):
    bl_label = "SketchUp Debug"
    bl_idname = "SKETCHUP_PT_debug_panel"
    bl_space_type = 'VIEW_3D'
    bl_region_type = 'UI'
    bl_category = 'SketchUp'
    
    def draw(self, context):
        layout = self.layout
        props = context.scene.sketchup_debug
        layout.prop(props, "show_axis_box")
        layout.prop(props, "show_nav_box")
        layout.prop(props, "show_ui_boxes")
        layout.prop(props, "show_hud_text")
        layout.prop(props, "disable_pass_through")

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
            
            # Offset slightly along normal to prevent Z-fighting
            face_normal_world = self.obj.matrix_world.to_3x3() @ f.normal
            face_normal_world.normalize()
            
            # Check if looking at the back of the face
            if context.region_data:
                view_vec = -context.region_data.view_matrix.inverted().to_3x3().col[2]
                if face_normal_world.dot(view_vec) > 0:
                    offset = face_normal_world * -0.002
                else:
                    offset = face_normal_world * 0.002
            else:
                offset = face_normal_world * 0.002
            
            # Get triangulated coordinates for rendering concave faces
            triangles = self.bm.calc_loop_triangles()
            face_tris = [tri for tri in triangles if tri[0].face.index == face_idx]
            
            tri_coords = []
            for tri in face_tris:
                for loop in tri:
                    tri_coords.append((self.obj.matrix_world @ loop.vert.co) + offset)
                    
            if not tri_coords: return
            
            # Subdivide polygons into triangles for correct rendering
            gpu.state.blend_set('ALPHA')
            gpu.state.depth_test_set('LESS_EQUAL')
            
            from gpu_extras.batch import batch_for_shader
            batch = batch_for_shader(shader, 'TRIS', {"pos": tri_coords})
            shader.bind()
            shader.uniform_float("color", (0.0, 0.5, 1.0, 0.3))
            batch.draw(shader)
            
            # outline
            coords = [(self.obj.matrix_world @ v.co) + offset for v in f.verts]
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
            
    def finish_push_pull(self, context, event):
        global push_pull_active_face_index, push_pull_drag_state, push_pull_typed_length
        push_pull_active_face_index = None
        push_pull_drag_state = 0
        push_pull_typed_length = ""
        
        if hasattr(self, 'bm') and self.bm:
            bmesh.ops.remove_doubles(self.bm, verts=self.bm.verts, dist=0.0001)
            bmesh.ops.dissolve_limit(self.bm, angle_limit=0.01, verts=self.bm.verts, edges=self.bm.edges)
            bmesh.update_edit_mesh(self.obj.data)
            
        bpy.ops.ed.undo_push(message="SketchUp Push/Pull End")
        self.update_hover(context, event)

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

        is_mouse_in_window = True
        props = getattr(context.scene, "sketchup_debug", None)
        disable_pass_through = props and props.disable_pass_through

        if event.mouse_x < context.area.x or event.mouse_x > context.area.x + context.area.width or \
           event.mouse_y < context.area.y or event.mouse_y > context.area.y + context.area.height:
            is_mouse_in_window = False
        elif not disable_pass_through:
            for region in context.area.regions:
                if region.type in {'UI', 'TOOLS', 'HEADER', 'FOOTER', 'TOOL_HEADER'}:
                    if region.x <= event.mouse_x <= region.x + region.width and \
                       region.y <= event.mouse_y <= region.y + region.height:
                        is_mouse_in_window = False
                        break
                        
        if is_mouse_in_window and getattr(context.space_data, 'show_gizmo_navigate', False):
            ui_scale = 1.0
            use_region_overlap = False
            if hasattr(context, 'preferences'):
                if hasattr(context.preferences, 'view') and hasattr(context.preferences.view, 'ui_scale'):
                    ui_scale = context.preferences.view.ui_scale
                if hasattr(context.preferences, 'system'):
                    use_region_overlap = getattr(context.preferences.system, 'use_region_overlap', False)
            
            axis_gizmo_width = 250 * ui_scale
            axis_gizmo_height = 300 * ui_scale
            
            nav_buttons_width = 120 * ui_scale
            nav_buttons_height = 450 * ui_scale
            nav_buttons_top = 160 * ui_scale

            ui_region_width = 0
            if use_region_overlap:
                for r in context.area.regions:
                    if r.type == 'UI' and r.width > 1:
                        ui_region_width = r.width
                        break
            
            for region in context.area.regions:
                if region.type == 'WINDOW':
                    right_edge = region.width - ui_region_width
                    mouse_x = event.mouse_x - region.x
                    mouse_y = event.mouse_y - region.y
                    
                    axis_x = right_edge - axis_gizmo_width
                    axis_y = region.height - axis_gizmo_height
                    
                    nav_top_y = region.height - nav_buttons_top
                    nav_bottom_y = nav_top_y - nav_buttons_height
                    nav_x = right_edge - nav_buttons_width
                    
                    is_over_axis = (mouse_x > axis_x) and (mouse_y > axis_y)
                    is_over_nav = (mouse_x > nav_x) and (nav_bottom_y < mouse_y < nav_top_y)
                    
                    if not disable_pass_through and (is_over_axis or is_over_nav):
                        is_mouse_in_window = False
                    break

        context.area.tag_redraw()

        if event.type == 'MOUSEMOVE':
            if push_pull_active_face_index is None:
                if is_mouse_in_window:
                    self.update_hover(context, event)
                else:
                    push_pull_hover_face_index = None
                
                if not is_mouse_in_window:
                    return {'PASS_THROUGH'}
            else:
                # We are dragging
                region = context.region
                rv3d = context.region_data
                mouse_coord = (event.mouse_x - region.x, event.mouse_y - region.y)
                ray_origin = region_2d_to_origin_3d(region, rv3d, mouse_coord)
                view_vector = region_2d_to_vector_3d(region, rv3d, mouse_coord)
                
                # Find the closest point between the extrusion axis and the mouse ray
                extrusion_p1 = push_pull_start_3d_pt
                extrusion_p2 = push_pull_start_3d_pt + push_pull_face_normal
                ray_p2 = ray_origin + view_vector
                
                intersect_pts = geometry.intersect_line_line(extrusion_p1, extrusion_p2, ray_origin, ray_p2)
                
                if intersect_pts:
                    pt_on_extrusion_line = intersect_pts[0]
                    delta_3d = pt_on_extrusion_line - push_pull_start_3d_pt
                    dist = delta_3d.dot(push_pull_face_normal)
                    
                    if push_pull_typed_length:
                        try:
                            dist = float(push_pull_typed_length)
                        except ValueError:
                            pass
                            
                    # Update verts
                    for i, v in enumerate(push_pull_extruded_verts):
                        v.co = push_pull_start_co[i] + push_pull_face_normal * dist
                        
                    self.bm.normal_update()
                    bmesh.update_edit_mesh(self.obj.data)

            return {'RUNNING_MODAL'}
            
        elif event.type == 'LEFTMOUSE':
            if not disable_pass_through and not is_mouse_in_window and push_pull_active_face_index is None:
                return {'PASS_THROUGH'}

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
                        
                        # Find edges to dissolve for seamless extrusion
                        local_normal = face.normal.copy()
                        edges_to_dissolve = []
                        is_full_face = True
                        for edge in face.edges:
                            if len(edge.link_faces) > 2:
                                is_full_face = False
                            
                            for adj_face in edge.link_faces:
                                if adj_face != face:
                                    if abs(adj_face.normal.dot(local_normal)) > 0.999:
                                        is_full_face = False
                                    elif abs(adj_face.normal.dot(local_normal)) < 0.001:
                                        if edge not in edges_to_dissolve:
                                            edges_to_dissolve.append(edge)
                        
                        if is_full_face:
                            extruded_face = face
                        else:
                            # Extrude
                            res = bmesh.ops.extrude_face_region(self.bm, geom=[face])
                            new_faces = [e for e in res['geom'] if isinstance(e, bmesh.types.BMFace)]
                            extruded_face = new_faces[0] if new_faces else None
                            
                            # Delete the original face to ensure edges are manifold
                            if face.is_valid:
                                bmesh.ops.delete(self.bm, geom=[face], context='FACES_ONLY')
                            
                            # Dissolve redundant edges
                            valid_edges = [e for e in edges_to_dissolve if e.is_valid]
                            if valid_edges:
                                bmesh.ops.dissolve_edges(self.bm, edges=valid_edges)
                        
                        # The newly extruded face becomes the active face for movement
                        if extruded_face:
                            push_pull_extruded_verts = extruded_face.verts[:]
                        else:
                            push_pull_extruded_verts = []
                        push_pull_start_co = [v.co.copy() for v in push_pull_extruded_verts]
                        
                        bmesh.update_edit_mesh(self.obj.data)
                        
                        push_pull_start_mouse_pos = Vector((event.mouse_x, event.mouse_y))
                        push_pull_drag_state = 1 # click-drag
                        push_pull_typed_length = ""
                else:
                    # Second click to finish
                    self.finish_push_pull(context, event)
                    
            elif event.value == 'RELEASE':
                if push_pull_active_face_index is not None and push_pull_drag_state == 1:
                    current_mouse = Vector((event.mouse_x, event.mouse_y))
                    if (current_mouse - push_pull_start_mouse_pos).length > 5:
                        # They dragged and released, finish!
                        self.finish_push_pull(context, event)
                    else:
                        # Click-release, switch to move mode
                        push_pull_drag_state = 2
                        
            return {'RUNNING_MODAL'}
            
        elif event.type in {'RET', 'NUMPAD_ENTER'} and event.value == 'PRESS':
            if push_pull_active_face_index is not None:
                self.finish_push_pull(context, event)
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
            
        elif event.type == 'Z' and event.value == 'PRESS' and (event.ctrl or event.oskey):
            if event.shift:
                try:
                    bpy.ops.ed.redo()
                    self.report({'INFO'}, "Redo")
                except RuntimeError:
                    pass
            else:
                try:
                    bpy.ops.ed.undo()
                    self.report({'INFO'}, "Undo")
                except RuntimeError:
                    pass
            
            if hasattr(self, 'bm'):
                self.bm.free()
            self.bm = bmesh.from_edit_mesh(self.obj.data)
            self.bm.verts.ensure_lookup_table()
            self.bm.faces.ensure_lookup_table()
            
            push_pull_active_face_index = None
            push_pull_drag_state = 0
            push_pull_typed_length = ""
            
            self.update_hover(context, event)
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

classes = (
    SKETCHUP_OT_push_pull_tool,
    SKETCHUP_OT_rectangle_tool,
    SKETCHUP_OT_draw_tool,
    SKETCHUP_OT_add_point,
    SketchUpDebugProperties,
    SKETCHUP_PT_debug_panel,
)

def register():
    for cls in classes:
        bpy.utils.register_class(cls)
    bpy.types.Scene.sketchup_debug = bpy.props.PointerProperty(type=SketchUpDebugProperties)
    bpy.utils.register_tool(SketchUpDrawTool, after={"builtin.measure"})
    bpy.utils.register_tool(SketchUpRectangleTool, after={"sketchup.draw_tool_v2"})
    bpy.utils.register_tool(SketchUpPushPullTool, after={"sketchup.rectangle_tool"})
    bpy._sketchup_rect_tool_class = SketchUpRectangleTool
    bpy._sketchup_pushpull_tool_class = SketchUpPushPullTool
    bpy._sketchup_tool_class = SketchUpDrawTool

def unregister():
    for cls in reversed(classes):
        old_cls = getattr(bpy.types, cls.__name__, None)
        try:
            if old_cls: bpy.utils.unregister_class(old_cls)
            else: bpy.utils.unregister_class(cls)
        except Exception: pass
            
    try: del bpy.types.Scene.sketchup_debug
    except Exception: pass
            
    old_tool = getattr(bpy, "_sketchup_tool_class", None)
    try:
        if old_tool: bpy.utils.unregister_tool(old_tool)
        else: bpy.utils.unregister_tool(SketchUpDrawTool)
    except Exception: pass
    old_pushpull_tool = getattr(bpy, "_sketchup_pushpull_tool_class", None)
    try:
        if old_pushpull_tool: bpy.utils.unregister_tool(old_pushpull_tool)
        else: bpy.utils.unregister_tool(SketchUpPushPullTool)
    except Exception: pass
    old_rect_tool = getattr(bpy, "_sketchup_rect_tool_class", None)
    try:
        if old_rect_tool: bpy.utils.unregister_tool(old_rect_tool)
        else: bpy.utils.unregister_tool(SketchUpRectangleTool)
    except Exception: pass

if __name__ == "__main__":
    try: unregister()
    except Exception: pass
    register()
