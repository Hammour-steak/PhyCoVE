"""Launch one delivered-look Cycles job (appearance/scene.py) on an inspected, exclusively leased GPU.

appearance/scene.py keeps the pool-host check of the delivered look, so the job only completes on those workers.
The launch record goes to <out>/../logs/."""

import argparse
import csv
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import socket
import shutil
import subprocess
import sys

HERE = Path(__file__).resolve().parent
CASE = HERE.parent
ROOT = HERE.parents[3]
CASE_ID = "silicone_block_chain"
sys.path[:0] = [str(ROOT/"scripts"), str(CASE), str(HERE)]
from scene_paths import CASES, OUTPUT, TEMPLATE, blender_runtime, cache, output_path
from pcve_gpu_policy import rank_uuids, require_gpu
from pcve_gpu_reservations import reservations


def gpu_snapshot():
    fields = ["index", "uuid", "name", "memory.total", "memory.free", "memory.used", "utilization.gpu"]
    raw = subprocess.check_output(["nvidia-smi", "--query-gpu="+",".join(fields),
                                   "--format=csv,noheader,nounits"], text=True, timeout=15)
    processes = subprocess.check_output(["nvidia-smi", "--query-compute-apps=gpu_uuid,pid,used_memory",
                                         "--format=csv,noheader,nounits"], text=True, timeout=15)
    rows = [dict(zip(fields, row, strict=True)) for row in csv.reader(raw.splitlines(), skipinitialspace=True)]
    bound = reservations([(row["index"], row["uuid"]) for row in rows], exclude=(os.getpid(), os.getppid()))
    busy = {row[0].strip() for row in csv.reader(processes.splitlines()) if row} | {r["gpu_uuid"] for r in bound}
    idle = [row["uuid"] for row in rows if row["uuid"] not in busy and int(row["memory.free"]) >= 8192
            and int(row["memory.used"]) < 100 and int(row["utilization.gpu"]) <= 3]
    return idle, {"inventory": rows, "compute_processes": processes.splitlines(), "bindings": bound}


def main():
    host = socket.gethostname().split(".")[0]
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--case", required=True)
    p.add_argument("--preview", type=int, nargs="+")
    p.add_argument("--threads", type=int, default=6)
    p.add_argument("--samples", type=int, default=64)
    p.add_argument("--gpu-uuid")
    p.add_argument("--cache", type=Path, help="native cache; default: the delivered one for this case")
    p.add_argument("--out", type=Path, help="default: renders/silicone_block_chain/rebuild/delivered/<case>")
    a = p.parse_args()
    if a.case not in CASES:
        p.error("Unknown case")
    output = output_path(a.out or OUTPUT/("delivered_previews" if a.preview else "delivered")/a.case)
    if output.exists():
        raise FileExistsError(output)
    blender = blender_runtime(None)
    ffmpeg = Path(shutil.which("ffmpeg") or "")
    template = TEMPLATE   # workshop model, sha pinned in appearance/scene.py
    for path in (blender, ffmpeg):
        if not os.access(path, os.X_OK):
            raise FileNotFoundError(path)
    args = [str(blender), "-b", "--factory-startup", "--disable-autoexec", "--python-exit-code", "1",
            "-t", str(a.threads), "--python", str(CASE/"appearance/scene.py"), "--", "--case", a.case,
            "--cache", str(a.cache or cache(a.case)),
            "--template", str(template), "--out", str(output),
            "--ffmpeg", str(ffmpeg), "--samples", str(a.samples), "--threads", str(a.threads)]
    if a.preview:
        args += ["--preview", *map(str, a.preview)]
    candidates, _ = gpu_snapshot()
    lease_dir = ROOT/"tools/pcve_gpu_leases"
    lease_dir.mkdir(exist_ok=True)
    for uuid in rank_uuids(candidates, case_id=CASE_ID):
        if a.gpu_uuid and uuid != a.gpu_uuid:
            continue
        with (lease_dir/(uuid+".lock")).open("a+") as lease:
            try:
                fcntl.flock(lease, fcntl.LOCK_EX|fcntl.LOCK_NB)
            except BlockingIOError:
                continue
            policy = require_gpu(uuid, case_id=CASE_ID)
            idle, info = gpu_snapshot()
            if uuid not in idle:
                continue
            logs = output.parent/"logs"
            logs.mkdir(exist_ok=True)
            launch = {"worker": host, "gpu_uuid": uuid,
                      "policy": policy, "prelaunch": info, "command": args,
                      "started_utc": datetime.now(timezone.utc).isoformat()}
            dest = logs/(output.parent.name+"_"+a.case+"_launch.json")
            dest.write_text(json.dumps(launch, indent=2)+"\n", encoding="utf-8")
            print("LEASED", host, uuid, a.case, flush=True)
            env = dict(os.environ, CUDA_VISIBLE_DEVICES=uuid, OMP_NUM_THREADS=str(a.threads),
                       OPENBLAS_NUM_THREADS="1", PYTHONDONTWRITEBYTECODE="1")
            subprocess.run(args, env=env, pass_fds=(lease.fileno(),), check=True)
            return
    raise RuntimeError("No eligible idle GPU lease. Retry without disturbing existing jobs.")


if __name__ == "__main__":
    main()
