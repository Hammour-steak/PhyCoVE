#!/usr/bin/env bash
# Reuse the accepted Genesis reservoir and bulk meshes,
# simulate the rope + puddle, mesh, render on several GPUs, encode, validate.
# Usage: pipeline_viscous_rope.sh RUN_NAME "GPU_IDS"   e.g.  viscous_rope "1 2 4 7"
# Outputs go to renders/honey_spoon_toast/RUN_NAME and RUN_NAME_renders; $BLENDER overrides the Blender binary.
set -euo pipefail
SCENE=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
P=$(cd "$SCENE/../../.." && pwd)
W=$P/renders/honey_spoon_toast
PY=$P/.venv-genesis-mpm-sph/bin/python
ASSETS="import sys; sys.path.insert(0, sys.argv[1]); import pcve_assets"
BLENDER=$("$PY" -c "$ASSETS; print(pcve_assets.blender())" "$P/scripts")
TEMPLATE=$("$PY" -c "$ASSETS; print(pcve_assets.asset('scenes/honey_spoon_toast/scene_template.blend'))" "$P/scripts")
INPUTS=$P/renders/pcve_suites/pcve_honey_spoon_toast_suite/inputs/04_realtime_runs
SOURCE=$INPUTS/reservoir_ts1
BULK_MESHES=$INPUTS/rope_source
RUN=$W/${1:?run name}
FRAMES=${RUN}_renders
if [[ ! -f "$TEMPLATE" ]]; then
  echo "Missing prepared scene: $TEMPLATE; see the scene README" >&2
  exit 1
fi
GPUS=(${2:?gpu ids})
cd "$SCENE"
OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 "$PY" simulate_viscous_rope.py --source "$SOURCE" --out "$RUN"
# The reservoir removal rule is unchanged, so the accepted bulk surface is reused.
"$PY" - "$RUN" "$BULK_MESHES" <<'PYEOF'
import sys, numpy as np
run, old = sys.argv[1:]
for f in range(1, 97):
    a = np.load(f"{run}/particles/frame_{f:04d}.npz")["honey_pos"]
    b = np.load(f"{old}/particles/frame_{f:04d}.npz")["honey_pos"]
    assert np.array_equal(a, b), f"bulk differs at frame {f}"
PYEOF
cp -al "$BULK_MESHES/meshes_smooth" "$RUN/meshes_smooth"
cp "$BULK_MESHES/meshing_report_meshes_smooth.json" "$RUN/"
"$PY" mesh_viscous_rope.py --run "$RUN" --workers 16
mkdir -p "$FRAMES"
n=${#GPUS[@]}
for k in "${!GPUS[@]}"; do
  frames=$(seq $((k+1)) $n 96 | tr '\n' ' ')
  CUDA_VISIBLE_DEVICES=${GPUS[$k]} "$BLENDER" --background --threads 8 --python render_honey_spoon_toast.py -- \
    --input-blend "$TEMPLATE" --run "$RUN" --out-dir "$FRAMES" --samples 32 \
    --mesh-subdir meshes_smooth --extra-mesh-subdir filament_meshes --frames $frames > "$FRAMES/render_gpu${GPUS[$k]}.log" 2>&1 &
done
wait
ffmpeg -y -v error -framerate 24 -i "$FRAMES/frame_%04d.png" -c:v libx264 -pix_fmt yuv420p -crf 18 "$FRAMES/honey_spoon_toast.mp4"
"$PY" physics/validate_viscous_rope.py --run "$RUN" --source "$SOURCE" --video "$FRAMES/honey_spoon_toast.mp4" \
  --out "$RUN/technical_acceptance.json"
echo PIPELINE_DONE
