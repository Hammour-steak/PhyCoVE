#!/bin/bash
# The render chain of one complete simulated run: splash stage (surfaces over six processes, the first
# also writes spray/mist/foam) beside the sun visibility at the run's settled level, traced caustics
# over three processes, a CPU dry run of the render, the render on an idle GPU, then the video.
# Usage: pipeline_bowling_ball_pool_drop.sh <run dir> <video.mp4>
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=$ROOT/.venv-genesis-mpm-sph/bin/python
BLENDER=${BLENDER:-$HOME/.local/opt/blender-4.3.2-linux-x64/blender}
run=$(cd "$1" && pwd)
video=$2
logs=$run/logs
mkdir -p "$logs"
info() { "$PY" -c "import json, sys; print(json.load(open(sys.argv[1]))$1)" "$run/simulation_report.json"; }
[ "$(info "['status']")" = complete ] || { echo "simulation incomplete"; exit 1; }
[ "$(info "['frames'].__len__()")" = 96 ] || { echo "final render requires all 96 simulation states"; exit 1; }
level=$(info "['info']['settled_surface_m']")
echo "splash start $(date +%H:%M), still level $level"
pids=()
for k in 0 1 2 3 4 5; do
  extra=""; [ $k = 0 ] && extra=--write-particles
  "$PY" -u "$HERE/physics/splash_bowling_ball_pool_drop.py" "$run" --frames 1-96 --surfaces "$(seq -s, $((1 + k)) 6 96)" \
    --part $k $extra > "$logs/splash_$k.log" 2>&1 < /dev/null &
  pids+=($!)
done
"$BLENDER" --factory-startup -b -t "${PCVE_THREADS:-8}" --python-exit-code 1 --python "$HERE/appearance/sun_visibility_bowling_ball_pool_drop.py" -- \
  --level "$level" --out "$run/visibility_sun.npz" > "$logs/visibility.log" 2>&1 < /dev/null || { echo "visibility failed"; exit 1; }
for pid in "${pids[@]}"; do wait $pid || { echo "splash failed"; exit 1; }; done
echo "caustics start $(date +%H:%M)"
pids=()
for part in 1-32 33-64 65-96; do
  "$PY" -u "$HERE/physics/caustics_bowling_ball_pool_drop.py" "$run" --visibility "$run/visibility_sun.npz" --frames $part \
    --part _$part > "$logs/caustics_$part.log" 2>&1 < /dev/null &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait $pid || { echo "caustics failed"; exit 1; }; done
echo "render start $(date +%H:%M)"
render=("$BLENDER" --factory-startup -b -t "${PCVE_THREADS:-8}" --python-exit-code 1 --python "$HERE/render_bowling_ball_pool_drop.py" --
        --run "$run" --out "$run/render")
"${render[@]}" --frames 1-1 --native-dry-run > "$logs/dryrun.log" 2>&1 < /dev/null || { echo "dry run failed"; exit 1; }
bash "$HERE/tools/run_on_idle_gpu.sh" "${render[@]}" --frames 1-96 > "$logs/render.log" 2>&1 < /dev/null || { echo "render failed"; exit 1; }
ffmpeg -nostdin -v error -y -framerate 24 -i "$run/render/%04d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p \
  -movflags +faststart "$video" && echo "video $video $(date +%H:%M)"
