#!/bin/bash
# The render chain of one complete simulated apple run: the kitchen ground map (once per run), splash
# stage (surfaces over six processes, the first also writes spray/mist/foam), a CPU dry run of the
# render, the render on an idle GPU, then the video.
# SKIP_SPLASH=1 re-renders from the existing splash outputs; SPLASH_ONLY=1 stops after the splash stage
# (to render on another host with render_gpus_apple_drop_kitchen_basin.sh).
# Usage: [RENDER_GPUS=n] [SKIP_SPLASH=1 | SPLASH_ONLY=1] pipeline_apple_drop_kitchen_basin.sh <run dir> <video.mp4>
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=${PCVE_GENESIS_PYTHON:-$ROOT/.venv-genesis-mpm-sph/bin/python}
BLENDER=${BLENDER:-$HOME/.local/opt/blender-4.3.2-linux-x64/blender}
IDLE_GPU=$ROOT/scripts/rigid_fluid/bowling_ball_pool_drop/tools/run_on_idle_gpu.sh
RENDER_GPUS=${RENDER_GPUS:-1}
CYCLES_BACKEND=${CYCLES_BACKEND:-OPTIX}
# OptiX crashes Blender 4.3.2 under NVIDIA driver 550: render with CUDA there.
driver=$(nvidia-smi --query-gpu=driver_version --format=csv,noheader 2>/dev/null | head -1)
[ "${driver%%.*}" = 550 ] && CYCLES_BACKEND=CUDA
run=$(cd "$1" && pwd)
video=$2
logs=$run/logs
mkdir -p "$logs"
status=$("$PY" -c "import json, sys; print(json.load(open(sys.argv[1]))['status'])" "$run/simulation_report.json")
[ "$status" = complete ] || { echo "simulation incomplete"; exit 1; }
if [ ! -f "$run/ground.npz" ]; then
  "$BLENDER" --factory-startup -b --python-exit-code 1 --python "$HERE/appearance/ground_apple_drop_kitchen_basin.py" -- \
    --out "$run/ground.npz" > "$logs/ground.log" 2>&1 < /dev/null || { echo "ground map failed"; exit 1; }
fi
if [ -z "${SKIP_SPLASH:-}" ]; then
  echo "splash start $(date +%H:%M)"
  pids=()
  for k in 0 1 2 3 4 5; do
    extra=""; [ $k = 0 ] && extra=--write-particles
    "$PY" -u "$HERE/physics/splash_apple_drop_kitchen_basin.py" "$run" --frames 1-96 --surfaces "$(seq -s, $((1 + k)) 6 96)" \
      --part $k $extra > "$logs/splash_$k.log" 2>&1 < /dev/null &
    pids+=($!)
  done
  for pid in "${pids[@]}"; do wait $pid || { echo "splash failed"; exit 1; }; done
fi
[ -n "${SPLASH_ONLY:-}" ] && { echo "splash done $(date +%H:%M)"; exit 0; }
rm -rf "$run/render"
echo "render start $(date +%H:%M)"
render=("$BLENDER" --factory-startup -b --python-exit-code 1 --python "$HERE/render_apple_drop_kitchen_basin.py" --
        --run "$run" --out "$run/render" --gpu-backend "$CYCLES_BACKEND")
"${render[@]}" --frames 1-1 --native-dry-run > "$logs/dryrun.log" 2>&1 < /dev/null || { echo "dry run failed"; exit 1; }
# RENDER_GPUS idle GPUs each render every RENDER_GPUS-th frame.
pids=()
for k in $(seq 0 $((RENDER_GPUS - 1))); do
  bash "$IDLE_GPU" "${render[@]}" --frame-list "$(seq -s, $((1 + k)) "$RENDER_GPUS" 96)" --part "_$k" \
    > "$logs/render_$k.log" 2>&1 < /dev/null &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait $pid || { echo "render failed"; exit 1; }; done
ffmpeg -nostdin -v error -y -framerate 24 -i "$run/render/%04d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p \
  -movflags +faststart "$video" && echo "video $video $(date +%H:%M)"
