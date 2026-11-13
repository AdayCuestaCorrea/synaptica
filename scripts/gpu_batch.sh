#!/usr/bin/env bash
# Run a long local LLM batch with the GPU watched (plan, step 20).
#
#   scripts/gpu_batch.sh RUN_DIR COMMAND [ARGS...]
#
# - systemd-inhibit keeps the PC from sleeping mid-batch (paleo-atlas lost 227 genera to a
#   suspend on 2026-11-08, docs/fases/fase-3.md there).
# - nvidia-smi writes the GPU vitals to RUN_DIR/gpu-vitals.csv every 10 s.
# - A watchdog stops the batch (by its PID, never by name) when the GPU reaches
#   GPU_MAX_TEMP °C (default 85, as in paleo-atlas). The driver prints decimals
#   ("74.50"), so the integer part is compared: the integer-only parse of paleo-atlas never
#   fired (fixed there on 2026-11-10). Test it on purpose with a low GPU_MAX_TEMP.
# - The output of the command goes to RUN_DIR/run.log as well as to the terminal.
# The syn commands skip what is up to date, so a stopped batch resumes on the next run.
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "usage: $0 RUN_DIR COMMAND [ARGS...]" >&2
  exit 2
fi
run_dir=$1
shift
max_temp=${GPU_MAX_TEMP:-85}
mkdir -p "$run_dir"
log="$run_dir/run.log"

nvidia-smi --query-gpu=timestamp,temperature.gpu,power.draw,memory.used,utilization.gpu \
  --format=csv -l 10 >>"$run_dir/gpu-vitals.csv" &
vitals_pid=$!

systemd-inhibit --what=sleep:idle --who=synaptica --why="LLM batch" "$@" \
  > >(tee -a "$log") 2>&1 &
batch_pid=$!

stop_all() { kill "$vitals_pid" 2>/dev/null || true; }
trap stop_all EXIT

echo "$(date -u +%FT%TZ) batch PID $batch_pid, watchdog at ${max_temp} °C: $*" | tee -a "$log"
while kill -0 "$batch_pid" 2>/dev/null; do
  temp=$(nvidia-smi --query-gpu=temperature.gpu --format=csv,noheader,nounits | head -1)
  temp=${temp%%.*}
  if [[ -n "$temp" && "$temp" -ge "$max_temp" ]]; then
    echo "$(date -u +%FT%TZ) GPU at ${temp} °C >= ${max_temp} °C: stopping PID $batch_pid" \
      | tee -a "$log"
    kill "$batch_pid"
    wait "$batch_pid" || true
    exit 3
  fi
  sleep 10
done
status=0
wait "$batch_pid" || status=$?
echo "$(date -u +%FT%TZ) batch finished with exit $status" | tee -a "$log"
exit "$status"
