import re

with open("__init__.py", "r") as f:
    content = f.read()

with open("patch_pushpull.py", "r") as f:
    patch = f.read()

# Insert patch before classes = (
idx = content.find("classes = (")
content = content[:idx] + patch + "\n" + content[idx:]

# Add to classes
content = content.replace(
    "classes = (",
    "classes = (\n    SKETCHUP_OT_push_pull_tool,"
)

# Add to register
content = content.replace(
    'bpy.utils.register_tool(SketchUpRectangleTool, after={"sketchup.draw_tool_v2"})',
    'bpy.utils.register_tool(SketchUpRectangleTool, after={"sketchup.draw_tool_v2"})\n    bpy.utils.register_tool(SketchUpPushPullTool, after={"sketchup.rectangle_tool"})'
)
content = content.replace(
    'bpy._sketchup_rect_tool_class = SketchUpRectangleTool',
    'bpy._sketchup_rect_tool_class = SketchUpRectangleTool\n    bpy._sketchup_pushpull_tool_class = SketchUpPushPullTool'
)

# Add to unregister
content = content.replace(
    'old_rect_tool = getattr(bpy, "_sketchup_rect_tool_class", None)',
    'old_pushpull_tool = getattr(bpy, "_sketchup_pushpull_tool_class", None)\n    try:\n        if old_pushpull_tool: bpy.utils.unregister_tool(old_pushpull_tool)\n        else: bpy.utils.unregister_tool(SketchUpPushPullTool)\n    except Exception: pass\n    old_rect_tool = getattr(bpy, "_sketchup_rect_tool_class", None)'
)

with open("__init__.py", "w") as f:
    f.write(content)
