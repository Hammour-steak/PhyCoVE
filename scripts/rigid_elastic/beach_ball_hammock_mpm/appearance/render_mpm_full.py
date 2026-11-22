import os

import bpy


ROOT = os.environ.get("PCVE_SCENE_ROOT", os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORK_DIR = os.environ.get("PCVE_WORK_DIR", os.path.join(ROOT, "work"))
OUTPUT = os.path.join(WORK_DIR, os.environ.get("MPM_FRAME_DIR", "mpm_flat_drop_720p"))
os.makedirs(OUTPUT, exist_ok=True)

scene = bpy.context.scene
start = int(os.environ.get("RENDER_START", "1"))
end = int(os.environ.get("RENDER_END", "96"))
skip_existing = os.environ.get("SKIP_EXISTING", "0") == "1"
for frame in range(start, end + 1):
    frame_path = os.path.join(OUTPUT, f"frame_{frame:04d}.png")
    if skip_existing and os.path.exists(frame_path):
        print("MPM_RENDER_SKIP", frame)
        continue
    scene.frame_set(frame)
    scene.render.filepath = frame_path
    bpy.ops.render.render(write_still=True)
    print("MPM_RENDER_FRAME", frame)
