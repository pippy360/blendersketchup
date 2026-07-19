import bpy
import unittest
import sys
import os
from unittest.mock import MagicMock
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
        self.event.mouse_region_x = 100
        self.event.mouse_region_y = 100
        
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


if __name__ == "__main__":
    unittest.main(argv=['first-arg-is-ignored'], verbosity=2)
