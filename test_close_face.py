import bpy
import bmesh

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
obj = bpy.context.edit_object

bm = bmesh.from_edit_mesh(obj.data)
v1 = bm.verts.new((-1, 0, 0))
v2 = bm.verts.new((1, 0, 0))
v3 = bm.verts.new((0, 1, 0))
bm.edges.new((v1, v2))
bm.edges.new((v2, v3))
bm.edges.new((v3, v1))

for v in [v1, v2, v3]:
    v.select = True
bmesh.update_edit_mesh(obj.data)

bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))

bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Faces after close:", len(bm.faces))
