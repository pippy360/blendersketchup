import unittest
from unittest.mock import patch
import bpy

class TestPatch(unittest.TestCase):
    @patch('bpy.ops.ed.undo')
    def test_patch(self, mock_undo):
        def fake_undo(*args, **kwargs):
            print("Fake undo called from test!")
        mock_undo.side_effect = fake_undo
        try:
            bpy.ops.ed.undo()
            print("Successfully called mock!")
        except Exception as e:
            print("Exception:", e)

if __name__ == '__main__':
    unittest.main()
