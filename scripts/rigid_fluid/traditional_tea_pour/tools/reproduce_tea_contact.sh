#!/usr/bin/env bash
# Usage: bash reproduce_tea_contact.sh INPUT_FOLDER NEW_CASE ENVIRONMENT_BLEND
# ENVIRONMENT_BLEND may be the delivered scene_tea_fixed.blend in a separate
# folder: its embedded tea set, environment and camera are those of the environment scene.
# The input folder contains the supplied physical inputs and baseline cap JSON.
set -euo pipefail
if [[ $# -ne 3 ]]; then
    echo 'Usage: bash reproduce_tea_contact.sh INPUT_FOLDER NEW_CASE ENVIRONMENT_BLEND' >&2
    exit 2
fi
tea_inputs=$1
tea_case=$2
tea_environment=$3
tea_dir=$(cd -- "$(dirname -- "$0")/.." && pwd)
tea_repo=$(cd -- "$tea_dir/../../.." && pwd)
tea_python=${PCVE_GENESIS_PYTHON:-$tea_repo/.venv-genesis-mpm-sph/bin/python}
tea_blender=${PCVE_BLENDER:-$("$tea_python" -c 'import sys; sys.path.append(sys.argv[1]); from pcve_assets import blender; print(blender())' "$tea_repo/scripts")}
if [[ -e "$tea_case" ]]; then
    echo 'Use a new target case; never overwrite an existing solve.' >&2
    exit 2
fi
export OMP_NUM_THREADS=8 RAYON_NUM_THREADS=8
"$tea_python" "$tea_dir/physics/prepare_tea_dynamic_case.py" "$tea_inputs" "$tea_case" --coaster "$tea_inputs/coaster_world.obj"
mkdir "$tea_case/logs"
"$tea_python" "$tea_dir/physics/launch_tea_contact.py" "$tea_case" --skin 0.0005208333472364128 > "$tea_case/logs/simulation.log" 2>&1
"$tea_python" "$tea_dir/physics/surface_tea_dynamics.py" "$tea_case" > "$tea_case/logs/surface.log" 2>&1
"$tea_python" "$tea_dir/tools/audit_genesis_actual_cup.py" "$tea_case" > "$tea_case/logs/actual_cup.log" 2>&1
"$tea_python" "$tea_dir/tools/validate_genesis_tea.py" "$tea_case" --plan "$tea_case/acceptance_plan.json"
"$tea_python" "$tea_dir/physics/measure_tea_dynamics.py" "$tea_case" --all-frames > "$tea_case/logs/motion.log" 2>&1
"$tea_python" "$tea_dir/physics/measure_tea_table_caps.py" "$tea_case" "$tea_inputs/baseline_table_cap_geometry.json" "$tea_case" --all-frames > "$tea_case/logs/table_caps_all.log" 2>&1
"$tea_python" "$tea_dir/tools/accept_tea_contact.py" "$tea_case" --baseline-caps "$tea_inputs/baseline_table_cap_geometry.json"
"$tea_blender" -b "$tea_environment" --python-exit-code 1 --python "$tea_dir/appearance/prepare_tea_contact_native.py" -- "$tea_case" > "$tea_case/logs/native_prepare.log" 2>&1
"$tea_blender" -b "$tea_case/scene_tea_fixed.blend" --python-exit-code 1 --python "$tea_dir/appearance/verify_genesis_blend.py" -- "$tea_case" > "$tea_case/logs/native_all96.log" 2>&1
"$tea_python" "$tea_dir/appearance/launch_tea_render.py" -b "$tea_case/scene_tea_fixed.blend" --python-exit-code 1 --python "$tea_dir/appearance/render_tea_contact.py" -- "$tea_case" --samples 128 --save-quality > "$tea_case/logs/render_all.log" 2>&1
"$tea_blender" -b "$tea_case/scene_tea_fixed.blend" --python-exit-code 1 --python "$tea_dir/appearance/verify_tea_contact_scene.py" -- "$tea_case"
"$tea_python" "$tea_dir/tools/qa_tea_contact.py" "$tea_case"
echo "Rendered $tea_case/video_contact_fixed.mp4; inspect the full video and all-frame evidence."
