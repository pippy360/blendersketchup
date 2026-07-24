import bpy
import bmesh

bpy.ops.mesh.primitive_cube_add(size=2, enter_editmode=True)
obj = bpy.context.active_object
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()

print("Faces before:", len(bm.faces))
face = bm.faces[0]
res = bmesh.ops.extrude_face_region(bm, geom=[face])

print("Faces after extrude_face_region with [face]:", len(bm.faces))

# Try geom=edges
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()
face = bm.faces[1]
res2 = bmesh.ops.extrude_face_region(bm, geom=[face] + list(face.edges) + list(face.verts))
print("Faces after extrude_face_region with geom=[face]+edges+verts:", len(bm.faces))

