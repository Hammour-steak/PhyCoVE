#!/bin/bash
# The render and video steps of pipeline_apple_drop_kitchen_basin.sh on the CPU, for when no GPU is free: the frames
# are split over several Blender processes with a fixed thread count each (half the machine by default).
# Frames before [first frame] keep their existing images (e.g. when only the splash outputs of later
# frames changed).
# Usage: render_cpu_apple_drop_kitchen_basin.sh <run dir> <video.mp4> [processes=4] [threads per process=32] [first frame=1]
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
BLENDER=${BLENDER:-$HOME/.local/opt/blender-4.3.2-linux-x64/blender}
run=$(cd "$1" && pwd)
video=$2
parts=${3:-4}
threads=${4:-32}
first=${5:-1}
logs=$run/logs
mkdir -p "$logs" "$run/render"
for frame in $(seq "$first" 96); do rm -f "$run/render/$(printf %04d "$frame").png"; done
echo "cpu render start $(date +%H:%M), $parts x $threads threads, frames $first-96"
pids=()
for k in $(seq 0 $((parts - 1))); do
  "$BLENDER" --factory-startup -b --python-exit-code 1 --python "$HERE/render_apple_drop_kitchen_basin.py" -- --run "$run" \
    --out "$run/render" --frame-list "$(seq -s, $((first + k)) "$parts" 96)" --cpu-threads "$threads" --part "_$k" \
    > "$logs/render_cpu_$k.log" 2>&1 < /dev/null &
  pids+=($!)
done
for pid in "${pids[@]}"; do wait $pid || { echo "render failed"; exit 1; }; done
[ "$(ls "$run/render"/*.png | wc -l)" = 96 ] || { echo "render incomplete"; exit 1; }
ffmpeg -nostdin -v error -y -framerate 24 -i "$run/render/%04d.png" -c:v libx264 -crf 16 -pix_fmt yuv420p \
  -movflags +faststart "$video" && echo "video $video $(date +%H:%M)"
