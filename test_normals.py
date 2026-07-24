import bpy
import bmesh
from mathutils import Vector

bpy.ops.mesh.primitive_grid_add(x_subdivisions=3, y_subdivisions=3, size=2, enter_editmode=True)
obj = bpy.context.active_object
bm = bmesh.from_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()

face = bm.faces[4] # Center face
res = bmesh.ops.extrude_face_region(bm, geom=[face])

new_faces = [e for e in res['geom'] if isinstance(e, bmesh.types.BMFace)]
cap = new_faces[0]
for v in cap.verts:
    v.co += Vector((0, 0, -1))  # Pushing DOWN

bm.normal_update()
bmesh.update_edit_mesh(obj.data)
bm.faces.ensure_lookup_table()

print("Normals when pushed DOWN:")
for i, f in enumerate(bm.faces[-4:]):
    print(f"Side Face normal: {f.normal}")

bpy.ops.object.mode_set(mode='OBJECT')
