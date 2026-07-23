from unittest.mock import MagicMock, patch

def test():
    with patch('bpy.ops.ed.undo') as mock_undo:
        def fake_undo(*args, **kwargs):
            print("Fake undo called!")
        mock_undo.side_effect = fake_undo
        import bpy
        bpy.ops.ed.undo()

test()
