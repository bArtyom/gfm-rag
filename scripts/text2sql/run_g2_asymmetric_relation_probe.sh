#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 6 ]]; then
  printf 'usage: %s RUN_ID OUTPUT LOG TIMEOUT_SECONDS --checkpoint PATH [--device DEVICE]\n' "$0" >&2
  exit 64
fi

run_id=$1
output=$2
log=$3
timeout_seconds=$4
shift 4

if [[ "$timeout_seconds" -lt 1 ]]; then
  printf 'timeout must be a positive integer number of seconds\n' >&2
  exit 64
fi

runner_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
runner="$runner_dir/g2_asymmetric_relation_probe.py"
mkdir -p -- "$(dirname -- "$output")" "$(dirname -- "$log")"

set -o noclobber
if ! exec 3>"$log"; then
  set +o noclobber
  printf 'log already exists; refusing to truncate: %s\n' "$log" >&2
  exit 73
fi
lock="${output}.supervisor.lock"
if ! exec 4>"$lock"; then
  set +o noclobber
  printf 'run ID already reserved by another supervisor: %s\n' "$run_id" >&3
  exit 73
fi
printf 'run_id=%s supervisor_pid=%s\n' "$run_id" "$$" >&4
set +o noclobber
exec 1>&3 2>&1

status=0
timeout --signal=INT --kill-after=10s "${timeout_seconds}s" \
  python "$runner" --run-id "$run_id" --output "$output" "$@" || status=$?

reason='worker exited cleanly'
if [[ "$status" -ne 0 ]]; then
  reason='supervisor observed timeout or abnormal process exit; see run log'
fi
python "$runner" \
  --run-id "$run_id" \
  --output "$output" \
  --finalize-supervisor \
  --exit-code "$status" \
  --reason "$reason"

exit "$status"
