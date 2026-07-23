import bpy
import bmesh
from mathutils import Vector, geometry

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v_first = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new((0, 1.5, 0))
e1 = bm.edges.new((v_first, v2))
v_first.select = True
v2.select = True
e1.select = True

bmesh.update_edit_mesh(obj.data)
bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

v_prev = bm.verts.new((1.5, 0, 0))
e2 = bm.edges.new((v2_new, v_prev))
for v in bm.verts: v.select = False
for e in bm.edges: e.select = False
v2_new.select = True
v_prev.select = True
e2.select = True

bmesh.update_edit_mesh(obj.data)
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
v_prev_new = next(v for v in bm.verts if (v.co - Vector((1.5, 0, 0))).length < 0.01)
v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

# close it
e3 = bm.edges.new((v_prev_new, v_first_new))

for bv in bm.verts: bv.select = False
for be in bm.edges: be.select = False

segments = [
    (Vector((-1.5, 0, 0)), Vector((0, 1.5, 0))),
    (Vector((0, 1.5, 0)), Vector((1.5, 0, 0))),
    (Vector((1.5, 0, 0)), Vector((-1.5, 0, 0)))
]

sel_count = 0
for be in bm.edges:
    p1 = be.verts[0].co
    p2 = be.verts[1].co
    for seg_a, seg_b in segments:
        if (seg_a - seg_b).length < 1e-4: continue
        i1, pct1 = geometry.intersect_point_line(p1, seg_a, seg_b)
        on1 = (-1e-4 <= pct1 <= 1.0 + 1e-4) and (p1 - i1).length < 1e-4
        i2, pct2 = geometry.intersect_point_line(p2, seg_a, seg_b)
        on2 = (-1e-4 <= pct2 <= 1.0 + 1e-4) and (p2 - i2).length < 1e-4
        
        if on1 and on2:
            be.select = True
            be.verts[0].select = True
            be.verts[1].select = True
            sel_count += 1
            break

print("Selected edges by segment logic:", sel_count)
bmesh.update_edit_mesh(obj.data)

bpy.ops.transform.translate(value=(0, 0, 0))
bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Edges after face add:", len(bm.edges))
print("Faces after face add:", len(bm.faces))

