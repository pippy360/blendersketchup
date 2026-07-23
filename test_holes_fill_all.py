import bpy
import bmesh

bpy.ops.mesh.primitive_circle_add(vertices=4, fill_type='NOTHING', enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')
obj = bpy.context.edit_object

bm = bmesh.from_edit_mesh(obj.data)

v1 = bm.verts.new((-5, 0, 0))
v2 = bm.verts.new((-4, 0, 0))
bm.edges.new((v1, v2))
bmesh.update_edit_mesh(obj.data)

bmesh.ops.holes_fill(bm, edges=bm.edges, sides=0)
bmesh.update_edit_mesh(obj.data)

bm.free()
bm = bmesh.from_edit_mesh(obj.data)
print("Faces after holes_fill all:", len(bm.faces))
