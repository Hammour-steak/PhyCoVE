#!/bin/bash
# Only the render step of pipeline_apple_drop_kitchen_basin.sh, on n idle GPUs (each takes every n-th frame), for a
# host that has the run's splash outputs and Blender but not the simulation's Python or ffmpeg.
# Usage: render_gpus_apple_drop_kitchen_basin.sh <run dir> [GPUs=4] [Cycles backend=CUDA]
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
BLENDER=${BLENDER:-$HOME/.local/opt/blender-4.3.2-linux-x64/blender}
run=$(cd "$1" && pwd)
parts=${2:-4}
backend=${3:-CUDA}
mkdir -p "$run/logs"
rm -rf "$run/render"
echo "render start $(date +%H:%M)"
pids=()
for k in $(seq 0 $((parts - 1))); do
  bash "$ROOT/scripts/rigid_fluid/bowling_ball_pool_drop/tools/run_on_idle_gpu.sh" "$BLENDER" --factory-startup -b \
    --python-exit-code 1 --python "$HERE/render_apple_drop_kitchen_basin.py" -- --run "$run" --out "$run/render" \
    --gpu-backend "$backend" --frame-list "$(seq -s, $((1 + k)) "$parts" 96)" --part "_$k" \
    > "$run/logs/render_$k.log" 2>&1 < /dev/null &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait $pid || { echo "render failed"; exit 1; }; done
[ "$(ls "$run/render"/*.png | wc -l)" = 96 ] || { echo "render incomplete"; exit 1; }
echo "rendered $(date +%H:%M)"
