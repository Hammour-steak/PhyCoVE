"""Case lists, data locations and the GPU launcher used by the simulate and render entries."""
import os
import subprocess
import sys
import time
from pathlib import Path

CASE_DIR=Path(__file__).resolve().parent
ROOT=CASE_DIR.parents[2]
# Accepted native delivery (accepted_delivery/, accepted_renders/; not in assets.json).
DATA=ROOT/"renders/cotton_tshirt_sofa"
SUITE=DATA/"accepted_delivery/benchmark_increment/scenes/cotton_tshirt_sofa"
# New solves, renders and launch records.
WORK=ROOT/"renders/cotton_tshirt_sofa"
# The published suite; it carries the merged native cache of each timed edit in inputs/native_timed/<case>/.
PUBLISHED=ROOT/"renders/pcve_suites/pcve_cotton_tshirt_sofa_suite"
NATIVE=CASE_DIR/"tools/native"
CASES=("source","stiff_shirt","heavy_shirt","low_friction","remove_seat")
# Timed edit: continues the accepted source solve from frame 10 (tools/native/simulate.py --source-cache).
TIMED_CASES=("low_friction_at_frame_10",)

def require_linux():
    if os.name=="nt" or sys.platform!="linux":
        raise SystemExit("The native solver and renderer run on Linux.")

def output(path):
    path=path.expanduser().resolve()
    if WORK.resolve() not in path.parents or path.exists():
        raise ValueError(f"Choose a fresh output folder beneath {WORK}")
    return path

def worker(tool,script,args,gpu,threads,scan,blender=None):
    require_linux()
    flags=["--blender-bin",blender] if blender else []
    audit=["--pool-audit",scan] if scan else []
    subprocess.run([sys.executable,"-B",*map(str,[NATIVE/"pool_job.py","--name",f"repro_{time.time_ns()}",
        "--tool",tool,"--gpu",gpu,"--threads",threads,*audit,*flags,"--",script,*args])],check=True)
