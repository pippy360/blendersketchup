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

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
bm.edges.ensure_lookup_table()

# Now find the newly added edge (on the X axis)
target_edge = None
for e in bm.edges:
    if abs(e.verts[0].co.y) < 0.001 and abs(e.verts[1].co.y) < 0.001:
        target_edge = e
        break

print("Faces before holes_fill:", len(bm.faces))
# try bmesh.ops.contextual_create? No, holes_fill
bmesh.ops.holes_fill(bm, edges=[target_edge], sides=0)
bmesh.update_edit_mesh(obj.data)

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Faces after holes_fill:", len(bm.faces))
