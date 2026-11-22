#!/bin/bash
# One case of the toy boat glide, end to end: settle the water around the held boat, push and release it,
# report how close it comes to the wall, mesh the surfaces in parallel, render camera F over four GPUs, encode.
# Extra arguments go to both simulation stages (e.g. --boat-mass 0.36, --water-presence 0 or
# --timed-edits-json <file> for an edit); the defaults are the accepted base. With --resume-from <run>
# --resume-frame k (a timed edit) there is no settle: the run continues that run's frame-k state.  Run it detached (setsid nohup ... &) on a remote machine.
# Usage: pipeline_toy_boat_pool_glide.sh <out dir> [simulate args...]
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=$ROOT/.venv-genesis-mpm-sph/bin/python
BLENDER=${BLENDER:-$HOME/.local/opt/blender-4.3.2-linux-x64/blender}
out=$1
shift
mkdir -p "$out"
out=$(cd "$out" && pwd)
mkdir -p "$out/logs"
cd "$ROOT"
started=$(date +%s)
stamp() { echo "$1 $(( $(date +%s) - started ))s"; }
# The box is shared: take the GPUs with the least memory in use.
idle_gpus() { nvidia-smi --query-gpu=index,memory.used --format=csv,noheader,nounits | sort -t, -k2 -n | head -"$1" | cut -d, -f1; }

if [ -f "$out/run/simulation_report.json" ]; then
  stamp SIM_REUSED  # a finished run placed here (the build script checks it matches the case)
elif printf '%s\n' "$@" | grep -qx -- --resume-from; then
  # A timed edit continues the accepted source run's state (--resume-from/--resume-frame): no settle.
  gpu=$(idle_gpus 1)
  CUDA_VISIBLE_DEVICES=$gpu "$PY" "$HERE/simulate_toy_boat_pool_glide.py" run --out "$out/run" "$@" > "$out/logs/run.log" 2>&1
  stamp SIM_DONE
else
  gpu=$(idle_gpus 1)
  CUDA_VISIBLE_DEVICES=$gpu "$PY" "$HERE/simulate_toy_boat_pool_glide.py" settle --out "$out/settle" "$@" > "$out/logs/settle.log" 2>&1
  CUDA_VISIBLE_DEVICES=$gpu "$PY" "$HERE/simulate_toy_boat_pool_glide.py" run --out "$out/run" \
    --water-state "$out/settle/water_state.npz" "$@" > "$out/logs/run.log" 2>&1
  stamp SIM_DONE
fi
# The base must glide free of the wall; an edit (a faster push) may reach it, so this only reports.
"$PY" "$HERE/physics/check_wall_toy_boat_pool_glide.py" "$out/run" || echo "WALL_CONTACT (reported, not an error)"
water=$("$PY" -c "import json, sys; print(json.load(open(sys.argv[1]))['physics']['water_presence'][0])" "$out/run/simulation_report.json")
if [ "$water" = 1 ]; then bash "$HERE/tools/run_splash_parallel.sh" "$out/run" 6; fi
stamp SURFACE_DONE

frames="$out/render/frames"
mkdir -p "$frames"
i=0
for g in $(idle_gpus 4); do
  CUDA_VISIBLE_DEVICES=$g "$BLENDER" -b --factory-startup --python-exit-code 1 \
    --python "$HERE/render_toy_boat_pool_glide.py" -- --run "$out/run" --out-dir "$out/render/chunk$i" \
    --camera kneeling_rim --frames $(seq -s " " $((i * 24 + 1)) $((i * 24 + 24))) --resolution 1280 720 --samples 64 \
    > "$out/logs/render_$i.log" 2>&1 &
  i=$((i + 1))
done
wait
for c in "$out"/render/chunk*/frames/*.png; do ln -sf "$c" "$frames/$(basename "$c")"; done
test "$(ls "$frames" | wc -l)" -eq 96
ffmpeg -nostdin -v error -y -framerate 24 -i "$frames/frame_%04d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p \
  -movflags +faststart "$out/video.mp4"
sha256sum "$out/video.mp4"
stamp PIPELINE_DONE
