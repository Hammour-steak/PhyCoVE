"""Bounded job dispatch. Distinct name deliberately avoids Python's stdlib queue."""
from pathlib import Path
import os, subprocess, sys, time
HERE=Path(__file__).resolve().parent
ROOT=Path(os.environ['BOOK_PILLOW_ROOT'])
phase,case=sys.argv[1:3]
start=time.monotonic()
while time.monotonic()-start<14400:
    code=subprocess.run([sys.executable,str(HERE/'launch.py'),phase,case,*sys.argv[3:]]).returncode
    if code!=75:raise SystemExit(code)
    print('WAIT_IDLE_GPU',phase,case,'retry_seconds=60',flush=True)
    time.sleep(60)
raise SystemExit('Four-hour eligible-idle GPU wait limit reached')
