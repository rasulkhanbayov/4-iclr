#!/bin/bash
# Submit the whole step 5 sweep: main (304 clips x 9 models) and API mode
# (152 clips x 7 models). Run from anywhere on panther-login:
#   bash ".../REVISION/slurm/v2/submit_sweep.sh"            # everything
#   bash ".../REVISION/slurm/v2/submit_sweep.sh" main       # main sweep only
#   bash ".../REVISION/slurm/v2/submit_sweep.sh" api        # API mode only
set -euo pipefail
D="$(dirname "$(readlink -f "$0")")"
cd "$D"; mkdir -p logs
WHAT="${1:-all}"
n() { grep -v '^#' "$1" | grep -cv '^\s*$'; }
sub() {  # $1 queue, $2 tasks file
    local N; N=$(n "$2")
    echo "submitting $2 ($N tasks) to $1"
    sbatch --array=0-$((N - 1)) "20_sweep_$1.sh" "$D/$2"
}
if [ "$WHAT" = all ] || [ "$WHAT" = main ]; then sub a100 main_a100.tasks; sub h200 main_h200.tasks; fi
if [ "$WHAT" = all ] || [ "$WHAT" = api ];  then sub a100 api_a100.tasks;  sub h200 api_h200.tasks;  fi
