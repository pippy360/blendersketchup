import bpy
import bmesh
from mathutils import Vector

bpy.ops.mesh.primitive_plane_add(size=2, enter_editmode=True)
bpy.ops.mesh.select_all(action='DESELECT')

obj = bpy.context.edit_object
bm = bmesh.from_edit_mesh(obj.data)

target_pos = Vector((1.5, 0, 0))

v1 = bm.verts.new((-1.5, 0, 0))
v2 = bm.verts.new(target_pos)
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
bm.verts.ensure_lookup_table()

# Find the vertex at target_pos
found_v = None
best_dist = 9999
for v in bm.verts:
    dist = (v.co - target_pos).length
    if dist < best_dist:
        best_dist = dist
        found_v = v

print(f"Best dist: {best_dist}")
print(f"Found vertex at: {found_v.co}")

