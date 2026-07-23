import bpy
import bmesh

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')

obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

v1 = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new((1.5, 0, 0))
bm.edges.new((v1, v2))
bm.verts.ensure_lookup_table()
bm.edges.ensure_lookup_table()

for v in [v1, v2]:
    v.select = True
bm.edges[-1].select = True
bmesh.update_edit_mesh(obj.data)

bpy.context.scene.tool_settings.use_mesh_automerge = True
bpy.context.scene.tool_settings.use_mesh_automerge_and_split = True

bpy.ops.transform.translate(value=(0, 0, 0))

bm.free()
bm = bmesh.from_edit_mesh(obj.data)

print(f"Faces: {len(bm.faces)}")
for f in bm.faces:
    print(f"Face verts: {len(f.verts)}")

