import bpy
import unittest
import sys
import os
from unittest.mock import MagicMock, patch
from mathutils import Vector

class TestSketchUpAddon(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        """Install and enable the addon before running tests."""
        cls.addon_name = "blendersketchup"
        zip_path = os.environ.get("ADDON_ZIP_PATH")
        if not zip_path:
            raise ValueError("ADDON_ZIP_PATH env var is not set")
            
        print(f"Installing addon from: {zip_path}")
        bpy.ops.preferences.addon_install(filepath=zip_path)
        
        print(f"Enabling addon: {cls.addon_name}")
        bpy.ops.preferences.addon_enable(module=cls.addon_name)
        cls.addon = sys.modules.get(cls.addon_name)

    def test_addon_enabled(self):
        """Test if the addon is properly listed in the enabled addons."""
        self.assertIn(self.addon_name, bpy.context.preferences.addons)

    def test_operator_registered(self):
        """Test if the SKETCHUP_OT_draw_tool operator is registered."""
        self.assertTrue(hasattr(bpy.ops, "sketchup"), "sketchup category not found in bpy.ops")
        self.assertTrue(hasattr(bpy.ops.sketchup, "draw_tool"), "draw_tool operator not found")
        self.assertTrue(hasattr(bpy.types, "SKETCHUP_OT_draw_tool"))

    def test_workspace_tool_registered(self):
        """Test if the SketchUpDrawTool is properly registered."""
        self.assertIsNotNone(self.addon, "Addon module not found in sys.modules")
        self.assertTrue(hasattr(self.addon, "SketchUpDrawTool"))
        self.assertTrue(hasattr(bpy, "_sketchup_tool_class"), "SketchUp tool class not attached to bpy")
        self.assertEqual(bpy._sketchup_tool_class.__name__, "SketchUpDrawTool")


class TestSnappingBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addon_name = "blendersketchup"
        cls.addon = sys.modules.get(cls.addon_name)

    def setUp(self):
        # Create a mock context
        self.context = MagicMock()
        self.context.scene.tool_settings.use_snap = True
        self.context.scene.tool_settings.snap_elements = {'VERTEX', 'EDGE', 'FACE'}
        self.context.view_layer.objects = []
        
        # Create a mock event
        self.event = MagicMock()
        self.event.ctrl = False
        self.event.mouse_x = 100
        self.event.mouse_y = 100
        self.context.region.x = 0
        self.context.region.y = 0
        
        # We need to temporarily mock the region coordinate conversion functions
        self.original_loc_3d_to_2d = self.addon.location_3d_to_region_2d
        self.original_reg_2d_to_org = self.addon.region_2d_to_origin_3d
        self.original_reg_2d_to_vec = self.addon.region_2d_to_vector_3d
        
        self.addon.location_3d_to_region_2d = lambda reg, rv3d, v3d: Vector((v3d.x, v3d.y))
        self.addon.region_2d_to_origin_3d = lambda reg, rv3d, v2d: Vector((v2d.x, v2d.y, 10.0))
        self.addon.region_2d_to_vector_3d = lambda reg, rv3d, v2d: Vector((0.0, 0.0, -1.0))

    def tearDown(self):
        self.addon.location_3d_to_region_2d = self.original_loc_3d_to_2d
        self.addon.region_2d_to_origin_3d = self.original_reg_2d_to_org
        self.addon.region_2d_to_vector_3d = self.original_reg_2d_to_vec

    def test_snapping_disabled(self):
        """Test snapping returns original location when use_snap is False"""
        self.context.scene.tool_settings.use_snap = False
        loc, snap_type = self.addon.apply_geometry_snapping(
            self.context, self.event, True, Vector((0,0,0)), 0, None, None
        )
        self.assertEqual(loc, Vector((0,0,0)))
        self.assertIsNone(snap_type)

    def test_snapping_ctrl_override(self):
        """Test snapping toggle with Ctrl key"""
        self.context.scene.tool_settings.use_snap = False
        self.event.ctrl = True # Temporarily enable snap by holding Ctrl
        
        loc, snap_type = self.addon.apply_geometry_snapping(
            self.context, self.event, True, Vector((1,2,3)), 0, None, None
        )
        self.assertEqual(loc, Vector((1,2,3)))
        self.assertEqual(snap_type, 'FACE')
        
    def test_snapping_vertex(self):
        """Test snapping to a nearby vertex"""
        mock_obj = MagicMock()
        mock_obj.type = 'MESH'
        mock_obj.mode = 'OBJECT'
        mock_obj.visible_get.return_value = True
        
        mock_obj.matrix_world = MagicMock()
        mock_obj.matrix_world.__matmul__ = lambda self, other: other
        
        mock_mesh = MagicMock()
        v1 = MagicMock()
        v1.co = Vector((100, 100, 5)) # Close to our mouse_region (100, 100)
        
        # Need to implement the len() check for mesh.vertices
        class MockVertices(list):
            pass
        
        mock_mesh.vertices = MockVertices([v1])
        mock_mesh.edges = []
        
        mock_obj.data = mock_mesh
        self.context.view_layer.objects = [mock_obj]
        
        loc, snap_type = self.addon.apply_geometry_snapping(
            self.context, self.event, False, Vector((0,0,0)), 0, None, None
        )
        
        self.assertEqual(snap_type, 'VERTEX')
        self.assertEqual(loc, Vector((100, 100, 5)))

    def test_snapping_vertex_edit_mode(self):
        """Test snapping to a nearby vertex in EDIT mode using bmesh"""
        from unittest.mock import patch
        
        mock_obj = MagicMock()
        mock_obj.type = 'MESH'
        mock_obj.mode = 'EDIT'
        mock_obj.visible_get.return_value = True
        
        mock_obj.matrix_world = MagicMock()
        mock_obj.matrix_world.__matmul__ = lambda self, other: other
        
        mock_mesh = MagicMock()
        v1 = MagicMock()
        v1.co = Vector((100, 100, 5))
        
        class MockVertices(list):
            pass
        
        mock_mesh.vertices = MockVertices([v1])
        
        mock_obj.data = mock_mesh
        self.context.view_layer.objects = [mock_obj]
        
        # We need to mock bmesh.from_edit_mesh since the real one expects a real mesh
        with patch('bmesh.from_edit_mesh') as mock_from_edit_mesh:
            mock_bm = MagicMock()
            mock_bm.verts = [v1]
            mock_bm.edges = []
            mock_from_edit_mesh.return_value = mock_bm
            
            loc, snap_type = self.addon.apply_geometry_snapping(
                self.context, self.event, False, Vector((0,0,0)), 0, None, None
            )
            
            self.assertEqual(snap_type, 'VERTEX')
            self.assertEqual(loc, Vector((100, 100, 5)))


class TestUndoRedoBehavior(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.addon_name = "blendersketchup"
        cls.addon = sys.modules.get(cls.addon_name)

    def setUp(self):
        self.context = MagicMock()
        mock_obj = MagicMock()
        mock_obj.type = 'MESH'
        mock_obj.mode = 'EDIT'
        mock_obj.matrix_world = MagicMock()
        mock_obj.matrix_world.__matmul__ = lambda self, other: other
        mock_obj.matrix_world.inverted.return_value = mock_obj.matrix_world
        self.context.edit_object = mock_obj
        
        class DummyTool:
            add_point = self.addon.SKETCHUP_OT_draw_tool.add_point
            break_chain = self.addon.SKETCHUP_OT_draw_tool.break_chain
            modal = self.addon.SKETCHUP_OT_draw_tool.modal
            end_tool = MagicMock()
            update_mouse_pos = MagicMock()
            report = MagicMock()
            update_mesh = MagicMock()
        
        self.tool = DummyTool()
        
        active_tool_mock = MagicMock()
        active_tool_mock.idname = "sketchup.draw_tool_v2"
        self.context.workspace.tools.from_space_view3d_mode.return_value = active_tool_mock
        
        class MockBmesh:
            def __init__(self):
                self.verts = self.MockElementList(self.MockVert)
                self.edges = self.MockElementList(self.MockEdge)
                self.faces = self.MockElementList(self.MockFace)
                
            def normal_update(self):
                pass
                
            def free(self):
                pass
                
            class MockElementList(list):
                def __init__(self, elem_class):
                    super().__init__()
                    self.elem_class = elem_class
                def ensure_lookup_table(self):
                    pass
                def new(self, *args):
                    elem = self.elem_class(*args)
                    self.append(elem)
                    return elem
                def remove(self, elem):
                    elem.is_valid = False
                    if elem in self:
                        super().remove(elem)

            class MockVert:
                def __init__(self, co):
                    self.co = co
                    self.is_valid = True
            
            class MockEdge:
                def __init__(self, verts):
                    self.verts = verts
                    self.is_valid = True
            
            class MockFace:
                def __init__(self, verts):
                    self.verts = verts
                    self.is_valid = True
                    
        self.mock_bm = MockBmesh()
        self.tool.obj = mock_obj
        self.tool.bm = self.mock_bm
        self.tool.undo_history = []
        self.tool.redo_history = []
        self.tool.chain_verts = []
        
        self.addon.draw_points = []
        self.addon.manual_axis_lock = None
        self.addon.shift_locked_axis = None
        
        self.context.area = MagicMock()
        self.context.area.x = 0
        self.context.area.y = 0
        self.context.area.width = 1000
        self.context.area.height = 1000
        self.context.area.regions = []
        


    @patch('bmesh.types')
    @patch('bmesh.from_edit_mesh')
    @patch('bpy.ops.transform.translate')
    @patch('bpy.ops.ed.undo_push')
    @patch('bpy.ops.ed.undo')
    def test_undo_redo_add_point(self, mock_undo, mock_undo_push, mock_translate, mock_from_edit_mesh, mock_bmesh_types):
        mock_from_edit_mesh.return_value = self.mock_bm
        mock_bmesh_types.BMVert = type(self.mock_bm.verts[0]) if self.mock_bm.verts else type(self.mock_bm.MockVert(None))
        mock_bmesh_types.BMEdge = type(self.mock_bm.MockEdge(None))
        mock_bmesh_types.BMFace = type(self.mock_bm.MockFace(None))
        
        self.tool.add_point(Vector((1, 0, 0)))
        self.assertEqual(len(self.mock_bm.verts), 1)
        self.assertEqual(len(self.tool.undo_history), 1)
        self.assertEqual(len(self.tool.redo_history), 0)
        
        self.tool.add_point(Vector((2, 0, 0)))
        self.assertEqual(len(self.mock_bm.verts), 2)
        self.assertEqual(len(self.mock_bm.edges), 1)
        self.assertEqual(len(self.tool.undo_history), 2)
        
        event = MagicMock()
        event.type = 'Z'
        event.value = 'PRESS'
        event.ctrl = True
        event.shift = False
        event.oskey = False
        event.mouse_x = 100
        event.mouse_y = 100
        
        # Simulate the mesh state changing because bpy.ops.ed.undo cannot be effectively mocked
        if len(self.mock_bm.verts) > 1:
            self.mock_bm.verts.pop()
        if len(self.mock_bm.edges) > 0:
            self.mock_bm.edges.pop()
            
        self.tool.modal(self.context, event)
        self.assertEqual(len(self.mock_bm.verts), 1)
        self.assertEqual(len(self.mock_bm.edges), 0)
        self.assertEqual(len(self.tool.undo_history), 1)
        self.assertEqual(len(self.tool.redo_history), 1)
        
        event.shift = True
        
        # Simulate redo mesh state change (not needed because redo calls add_point directly which adds to the mock)
        # self.mock_bm.verts.append(self.mock_bm.MockVert(Vector((2, 0, 0))))
        # self.mock_bm.edges.append(self.mock_bm.MockEdge(None))
        
        self.tool.modal(self.context, event)
        self.assertEqual(len(self.mock_bm.verts), 2)
        self.assertEqual(len(self.mock_bm.edges), 1)
        self.assertEqual(len(self.tool.undo_history), 2)
        self.assertEqual(len(self.tool.redo_history), 0)

    @patch('bmesh.types')
    @patch('bmesh.from_edit_mesh')
    @patch('bpy.ops.transform.translate')
    @patch('bpy.ops.ed.undo_push')
    @patch('bpy.ops.ed.undo')
    def test_undo_redo_break_chain(self, mock_undo, mock_undo_push, mock_translate, mock_from_edit_mesh, mock_bmesh_types):
        mock_from_edit_mesh.return_value = self.mock_bm
        mock_bmesh_types.BMVert = type(self.mock_bm.MockVert(None))
        mock_bmesh_types.BMEdge = type(self.mock_bm.MockEdge(None))
        mock_bmesh_types.BMFace = type(self.mock_bm.MockFace(None))
        
        self.tool.add_point(Vector((1, 0, 0)))
        
        self.tool.break_chain()
        self.assertEqual(len(self.tool.undo_history), 2)
        self.assertEqual(len(self.addon.draw_points), 0)
        
        event = MagicMock()
        event.type = 'Z'
        event.value = 'PRESS'
        event.ctrl = True
        event.shift = False
        event.mouse_x = 100
        event.mouse_y = 100
        self.tool.modal(self.context, event)
        self.assertEqual(len(self.addon.draw_points), 1)
        
        event.shift = True
        self.tool.modal(self.context, event)
        self.assertEqual(len(self.addon.draw_points), 0)

if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], verbosity=2)
