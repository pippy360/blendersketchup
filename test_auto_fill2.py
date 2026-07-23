import bpy
import bmesh

bpy.ops.mesh.primitive_circle_add(vertices=4, fill_type='NOTHING', enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')

obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v1 = bm.verts.new((-1, 0, 0))
v2 = bm.verts.new((1, 0, 0))
bm.edges.new((v1, v2))
bmesh.update_edit_mesh(obj.data)

bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True
bpy.ops.transform.translate(value=(0, 0, 0))

bpy.ops.mesh.select_all(action='SELECT')
bpy.ops.mesh.edge_face_add()

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print(f"End: Faces = {len(bm.faces)}")
