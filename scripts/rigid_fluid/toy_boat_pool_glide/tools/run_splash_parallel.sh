#!/bin/bash
# Water surfaces of one run over several processes, as bowling_ball_pool_drop's pipeline does: one process
# keeps the frame-by-frame spray/mist/foam history (and meshes nothing), the others each mesh every
# K-th frame independently.  Frames already meshed are skipped.
# Usage: run_splash_parallel.sh <run dir> [processes, default 6]
set -u
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=$ROOT/.venv-genesis-mpm-sph/bin/python
run=$(cd "$1" && pwd)
K=${2:-6}
mkdir -p "$run/logs"
pids=()
"$PY" -u "$HERE/physics/splash_toy_boat_pool_glide.py" --run "$run" --frames 1-96 --surfaces 1 --skip-existing \
  --part secondaries > "$run/logs/splash_secondaries.log" 2>&1 < /dev/null &
pids+=($!)
for k in $(seq 0 $((K - 1))); do
  "$PY" -u "$HERE/physics/splash_toy_boat_pool_glide.py" --run "$run" --surfaces "$(seq -s, $((1 + k)) $K 96)" \
    --no-secondaries --skip-existing --part $k > "$run/logs/splash_mesh_$k.log" 2>&1 < /dev/null &
  pids+=($!)
done
status=0
for pid in "${pids[@]}"; do wait $pid || status=1; done
test "$(ls "$run"/surface/water_*.npz | wc -l)" -eq 96 || status=1
exit $status
