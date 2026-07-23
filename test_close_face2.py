import bpy
import bmesh
from mathutils import Vector

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
bpy.ops.mesh.delete(type='ONLY_FACE')
obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v_first = bm.verts.new((-1, -1, 0))
v2 = bm.verts.new((1, -1, 0))
v_prev = bm.verts.new((1, 1, 0))

bm.edges.new((v_first, v2))
bm.edges.new((v2, v_prev))
bmesh.update_edit_mesh(obj.data)

chain_verts = [v_first, v2, v_prev]

# Simulate closing
e = bm.edges.new((v_prev, v_first))
for bv in bm.verts: bv.select = False
for be in bm.edges: be.select = False
for bf in bm.faces: bf.select = False

for cv in chain_verts:
    cv.select = True
e.select = True

bmesh.update_edit_mesh(obj.data)

bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))
bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Faces after close:", len(bm.faces))

