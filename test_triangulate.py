import bpy
import bmesh

bpy.ops.mesh.primitive_circle_add(vertices=8, fill_type='NGON', enter_editmode=True)
obj = bpy.context.active_object
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()

triangles = bm.calc_loop_triangles()
print(triangles)
if triangles:
    print(triangles[0])

