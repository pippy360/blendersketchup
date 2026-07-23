import bpy
import bmesh

bpy.context.preferences.edit.use_global_undo = True

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
obj = bpy.context.edit_object

bpy.ops.ed.undo_push(message="Before vertex")

bm = bmesh.from_edit_mesh(obj.data)
v1 = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new((1.5, 0, 0))
bm.edges.new((v1, v2))
bmesh.update_edit_mesh(obj.data)
print(f"After add: Verts = {len(bm.verts)}")

bpy.ops.ed.undo_push(message="After vertex")

bpy.ops.ed.undo()
bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print(f"After undo: Verts = {len(bm.verts)}")
