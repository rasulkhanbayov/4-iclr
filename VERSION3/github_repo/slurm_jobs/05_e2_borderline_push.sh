#!/bin/bash -l
#SBATCH -J physweep_e2_borderline
#SBATCH -o e2_borderline_%j.out
#SBATCH -e e2_borderline_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=48000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 1-00:00:00

# E2 targeted push: the TWO closest-to-adjudicable pairs after the full
# 01/02/03_e2_gapfill_*.sh round (see the project notes Section 0i), rather than
# spending equal effort on systems that have shown a flat 0 gated-out rate
# across many more attempts already (those are treated as a likely-
# permanent negative finding, not a target for further seeds).
#
# Historical yield rate BEFORE this job (computed directly from the actual
# result JSONs, not assumed):
#   LTX-Video / pendulum_omega:   1 gated / 30 out-of-range attempts (~3.3%)
#     -- seeds 0-14 already used; need 3 MORE gated points to reach n>=4.
#     At ~3.3% yield, getting 3 more needs ~90 attempts in expectation --
#     genuinely a long shot, but pendulum_omega is CHEAP on LTX-Video (no
#     subprocess overhead, ~2s/clip in-process), so a large seed batch here
#     is still only a few hours, not the day-plus it would take on the
#     other two models. If this batch still doesn't clear the gate, that
#     is itself a strong signal to stop trying on this specific pair.
#   CogVideoX / bouncing_ball:    2 gated / 39 out-of-range attempts (~5.1%)
#     -- seeds 0-12 already used; need 2 MORE gated points to reach n>=4.
#     CogVideoX is much slower per clip (~2-6min) -- 40 more seeds here is
#     a substantial time cost (est. 3-8h for this one system alone), so the
#     batch size below is smaller than pure yield-rate math would suggest,
#     trading some probability of success for a bounded runtime.
#
# Seed counts below are sized to roughly 2-3x the expected attempts needed
# at the observed yield rate, not an exact guarantee -- more seeds always
# helps but this is already a proportionate, not indefinite, second push
# per the project notes's standing guidance not to chase a gate that may reflect a
# genuine model limitation.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

echo "=== LTX-Video / pendulum_omega: +40 out-of-range seeds (15-54) ==="
echo "    (cheap per-clip; sized generously since yield is only ~3.3%)"
python3 experiments/e4_generality.py --model ltx --systems pendulum_omega \
    --seeds-in 0 --seeds-out 40 --start-seed 15 --merge

echo "=== CogVideoX / bouncing_ball: +20 out-of-range seeds (13-32) ==="
echo "    (expensive per-clip; sized to bound runtime, not maximize odds)"
python3 experiments/e4_generality.py --model cogvideox --systems bouncing_ball \
    --seeds-in 0 --seeds-out 20 --start-seed 13 --merge

echo "=== re-running E2 analysis to see what cleared the gate ==="
python3 experiments/e2_extrapolation.py
