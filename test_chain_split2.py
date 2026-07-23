import bpy
import bmesh
from mathutils import Vector

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
bm.verts.ensure_lookup_table()

v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

v_prev = bm.verts.new((1.5, 0, 0))
bm.edges.new((v2_new, v_prev))

bmesh.update_edit_mesh(obj.data)
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
bm.verts.ensure_lookup_table()

v_prev_new = next(v for v in bm.verts if (v.co - Vector((1.5, 0, 0))).length < 0.01)
v_first_new = next(v for v in bm.verts if (v.co - Vector((-1.5, 0, 0))).length < 0.01)
v2_new = next(v for v in bm.verts if (v.co - Vector((0, 1.5, 0))).length < 0.01)

e = bm.edges.new((v_prev_new, v_first_new))

for bv in bm.verts: bv.select = False
for be in bm.edges: be.select = False
for bf in bm.faces: bf.select = False

for v in [v_first_new, v2_new, v_prev_new]: v.select = True
e.select = True

bmesh.update_edit_mesh(obj.data)
bpy.ops.transform.translate(value=(0, 0, 0))
bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Edges:", len(bm.edges))

