import bpy
import bmesh
from mathutils import Vector, geometry

def point_on_line_segment(p, a, b, tol=1e-4):
    # Check if point p is on line segment a-b
    intersect, _ = geometry.intersect_point_line(p, a, b)
    if (intersect - p).length > tol:
        return False
    # Check if it's within the segment bounds
    dot = (p - a).dot(b - a)
    if dot < -tol or dot > (b - a).length_squared + tol:
        return False
    return True

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v_first = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new((0, 1.5, 0))
bm.edges.new((v_first, v2))

bmesh.update_edit_mesh(obj.data)
bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

v_prev = bm.verts.new((1.5, 0, 0))
bm.edges.new((v2_new, v_prev))

bmesh.update_edit_mesh(obj.data)
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
v_prev_new = next(v for v in bm.verts if (v.co - Vector((1.5, 0, 0))).length < 0.01)
v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

# newly added edge
e = bm.edges.new((v_prev_new, v_first_new))

# line segments drawn by user (in local space for simplicity here)
segments = [
    (Vector((-1.5, 0, 0)), Vector((0, 1.5, 0))),
    (Vector((0, 1.5, 0)), Vector((1.5, 0, 0))),
    (Vector((1.5, 0, 0)), Vector((-1.5, 0, 0)))
]

for bv in bm.verts: bv.select = False
for be in bm.edges: be.select = False
for bf in bm.faces: bf.select = False

# Select all edges that lie on any of the segments
selected_edges = 0
for be in bm.edges:
    p1 = be.verts[0].co
    p2 = be.verts[1].co
    for seg_a, seg_b in segments:
        if point_on_line_segment(p1, seg_a, seg_b) and point_on_line_segment(p2, seg_a, seg_b):
            be.select = True
            selected_edges += 1
            break

bmesh.update_edit_mesh(obj.data)
print("Selected edges:", selected_edges)
bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Edges after face add:", len(bm.edges))

