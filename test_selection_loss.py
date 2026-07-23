import bpy
import bmesh
from mathutils import Vector

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v_first = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new((0, 1.5, 0))
v_prev = bm.verts.new((1.5, 0, 0))

bm.edges.new((v_first, v2))
bm.edges.new((v2, v_prev))
e = bm.edges.new((v_prev, v_first))

bm.verts.ensure_lookup_table()
bm.edges.ensure_lookup_table()

for bv in bm.verts: bv.select = False
for be in bm.edges: be.select = False
for bf in bm.faces: bf.select = False

for v in [v_first, v2, v_prev]:
    v.select = True
e.select = True
bmesh.update_edit_mesh(obj.data)

bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
selected_verts = [v for v in bm.verts if v.select]
print("Selected verts after translate:", len(selected_verts))

bpy.ops.mesh.edge_face_add()
bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Faces after edge_face_add:", len(bm.faces))
