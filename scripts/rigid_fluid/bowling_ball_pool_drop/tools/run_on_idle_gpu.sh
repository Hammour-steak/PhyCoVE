#!/bin/bash
# Usage: run_on_idle_gpu.sh <command...>  -- wait for an idle GPU (no compute process, <256 MiB, 0% util),
# claim it, and run the command with CUDA_VISIBLE_DEVICES set to it. Claims live in $GPU_CLAIMS (default:
# renders/.gpu_claims in the repository) so concurrent jobs pick different GPUs.
if [ -n "${PCVE_GPU:-}" ] && [ "$PCVE_GPU" != available ]; then
  [[ "$PCVE_GPU" =~ ^[0-9]+$ ]] || { echo "invalid PCVE_GPU"; exit 2; }
  nvidia-smi -i "$PCVE_GPU" --query-gpu=index,memory.free,utilization.gpu --format=csv,noheader || exit 2
  echo "using explicitly inspected GPU $PCVE_GPU $(date +%H:%M)"
  CUDA_VISIBLE_DEVICES=$PCVE_GPU "$@"
  exit $?
fi
P=${GPU_CLAIMS:-$(cd "$(dirname "$0")/../../../.." && pwd)/renders/.gpu_claims}
mkdir -p "$P"
idle_gpu() {
  if [ "${PCVE_GPU:-}" = available ]; then
    # Explicit opt-in: use an idle shared GPU with ample free memory, chosen at each GPU stage.
    nvidia-smi --query-gpu=index,uuid,memory.free,utilization.gpu --format=csv,noheader,nounits |
    sort -t, -k3,3nr |
    while IFS=', ' read -r idx uuid free util; do
      if [ "$free" -gt 16384 ] && [ "$util" -le 2 ] && [ ! -e "$P/.claim_gpu$idx" ]; then
        echo "$idx"; break
      fi
    done
    return
  fi
  local busy
  busy=$(nvidia-smi --query-compute-apps=gpu_uuid --format=csv,noheader | sort -u)
  nvidia-smi --query-gpu=index,uuid,memory.used,utilization.gpu --format=csv,noheader,nounits |
  while IFS=', ' read -r idx uuid mem util; do
    if [ "$mem" -lt 256 ] && [ "$util" -eq 0 ] && ! grep -q "$uuid" <<<"$busy" && [ ! -e "$P/.claim_gpu$idx" ]; then
      echo "$idx"; break
    fi
  done
}
while true; do
  exec 9>"$P/.gpu_pick.lock"; flock 9
  gpu=$(idle_gpu)
  if [ -n "$gpu" ]; then echo $$ > "$P/.claim_gpu$gpu"; flock -u 9; break; fi
  flock -u 9; sleep 60
done
echo "start gpu$gpu $(date +%H:%M)"
trap 'rm -f "$P/.claim_gpu$gpu"' EXIT
CUDA_VISIBLE_DEVICES=$gpu "$@"
status=$?
rm -f "$P/.claim_gpu$gpu"
echo "end gpu$gpu exit $status $(date +%H:%M)"
exit $status
