#!/bin/bash
# Physical edit cases; use a fresh output root. Completed cases may be reused.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=$ROOT/.venv-genesis-mpm-sph/bin/python
out=$1
mkdir -p "$out"
out=$(cd "$out" && pwd)
echo '[{"frame":24,"params":{"boat_mass":2.153044702}}]' > "$out/heavy_at_24.json"
cases=(
  "edit_heavy_boat|--boat-mass 2.153044702"
  "edit_slow_push|--boat-speed 0.45"
  "edit_fast_push|--boat-speed 1.35"
  "edit_light_water|--water-density 249.5"
  "edit_viscous_water|--water-viscosity 0.003514 --hull-viscous-shear"
  "edit_remove_boat|--boat-presence 0"
  "edit_heavy_boat_mid_glide|--timed-edits-json $out/heavy_at_24.json"
)
cd "$ROOT"
for entry in "${cases[@]}"; do
  name=${entry%%|*}; args=${entry#*|}; directory=$out/$name
  mkdir -p "$directory"
  if [ "$name" = edit_viscous_water ]; then
    bash "$HERE/tools/run_viscous_glide.sh" "$directory"
    echo "DONE $name (reduced-order hybrid)"
    continue
  fi
  if [ -f "$directory/run/simulation_report.json" ]; then
    echo "REUSED $name"; continue
  fi
  if [ -d "$directory/run" ]; then
    echo "Incomplete run: $directory/run; preserve it and choose a fresh directory" >&2; exit 1
  fi
  gpu=$(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits |
    awk -F, '$2 < 1500 && $3 < 10 {print $1}' | head -1)
  test -n "$gpu" || { echo "No idle GPU" >&2; exit 1; }
  if [ ! -f "$directory/settle/water_state.npz" ]; then
    CUDA_VISIBLE_DEVICES=$gpu "$PY" "$HERE/simulate_toy_boat_pool_glide.py" settle \
      --out "$directory/settle" $args > "$directory/settle.log" 2>&1
  fi
  CUDA_VISIBLE_DEVICES=$gpu "$PY" "$HERE/simulate_toy_boat_pool_glide.py" run \
    --out "$directory/run" --water-state "$directory/settle/water_state.npz" $args > "$directory/run.log" 2>&1
  echo "DONE $name"
done
