#!/bin/bash
# Run the edit_viscous_water preset: free glide with additional stationary-medium resistance.
# No visible velocity prescription; this is not a full horizontal two-way CFD model.
set -euo pipefail
HERE=$(cd "$(dirname "$0")/.." && pwd)
ROOT=$(cd "$HERE/../../.." && pwd)
PY=$ROOT/.venv-genesis-mpm-sph/bin/python
out=$1
mkdir -p "$out/logs"
out=$(cd "$out" && pwd)
cd "$ROOT"
if [ -f "$out/run/simulation_report.json" ]; then
  "$PY" - "$HERE" "$out/run" <<'PY'
import sys
from pathlib import Path
sys.path.insert(0, sys.argv[1])
import build_pcve_toy_boat_pool_glide as b
case=next(c for c in b.EDIT_CASES if c.case_id == 'edit_viscous_water')
b.check_run_matches(Path(sys.argv[2]), b.edit_info(case)['physics_override'])
PY
  exit 0
fi
if [ -d "$out/run" ]; then
  echo "Incomplete run exists; preserve it and choose a fresh output directory: $out/run" >&2
  exit 1
fi
if [ -z "${CUDA_VISIBLE_DEVICES:-}" ]; then
  gpu=$(nvidia-smi --query-gpu=index,memory.used,utilization.gpu --format=csv,noheader,nounits |
    awk -F, '$2 < 1500 && $3 < 10 {print $1}' | head -1)
  test -n "$gpu" || { echo 'No idle GPU; retry when resources are available' >&2; exit 1; }
  export CUDA_VISIBLE_DEVICES=$gpu
fi
export OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1
# the accepted settled start of this preset; without it the water is settled again from the source settle
accepted=$ROOT/renders/toy_boat_pool_glide/viscous_settle
if [ ! -f "$out/settle/water_state.npz" ]; then
  if [ -e "$out/settle" ]; then
    echo "Incomplete settle exists; preserve it and choose a fresh output directory" >&2
    exit 1
  fi
  if [ -f "$accepted/water_state.npz" ]; then
    cp -a "$accepted" "$out/settle"
  else
    "$PY" "$HERE/simulate_toy_boat_pool_glide.py" settle --out "$out/settle" \
      --water-state "$ROOT/renders/toy_boat_pool_glide/source/settle/water_state.npz" \
      --settle-frames 48 --fluid-damping 0.8 --initial-draft-ratio 1.0 \
      --single-force-integration --hull-viscous-shear --hull-pressure-mode hydrostatic \
      > "$out/logs/settle.log" 2>&1
  fi
fi
"$PY" - "$out/settle/settle_report.json" <<'PY'
import json, sys
r=json.load(open(sys.argv[1]))
assert r['single_force_integration'] and r['initial_draft_ratio'] == 1.0
assert r['hull_pressure_mode'] == 'hydrostatic'
PY
"$PY" "$HERE/simulate_toy_boat_pool_glide.py" run --out "$out/run" \
  --water-state "$out/settle/water_state.npz" --frames 96 \
  --water-viscosity 0.003514 --steps-per-frame 88 --substeps 4 \
  --hull-viscous-shear --single-force-integration --record-coupling-forces \
  --hull-pressure-mode hydrostatic --initial-draft-ratio 1.0 --quasistatic-planar-drag --pool-no-slip --fluid-drag-rate 6 \
  > "$out/logs/run.log" 2>&1
