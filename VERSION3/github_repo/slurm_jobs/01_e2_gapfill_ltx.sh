#!/bin/bash -l
#SBATCH -J physweep_e2_ltx
#SBATCH -o e2_ltx_%j.out
#SBATCH -e e2_ltx_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=40000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 08:00:00

# E2 gap-fill: LTX-Video, add MORE OUT-OF-RANGE seeds to close the
# >=4-gated-out-of-range-points gap experiments/e2_extrapolation.py reported
# (run `python3 experiments/e2_extrapolation.py` after 00_setup_env.sh to
# reproduce this table -- it will drift if E4/E0 are re-run before this job,
# so re-check rather than trusting this comment blindly):
#
#   projectile       n_out=3  (need 1 more)              -> e0_pilot.py, seeds 5-9
#   inclined_slide   n_out=4  ALREADY ADJUDICATED         -> not re-run here
#   bouncing_ball    n_out=1  (94% historical drop rate)  -> seeds 5-14 (10 more)
#   pendulum_omega   n_out=0  (100% historical drop rate) -> seeds 5-14 (10 more)
#   pendulum_zeta    n_out=0  (100% historical drop rate) -> seeds 5-14 (10 more)
#   spring_mass      n_out=0  (100% historical drop rate) -> seeds 5-14 (10 more)
#
# pendulum_omega/zeta and spring_mass historically failed the fit-quality
# gate on EVERY seed tested (n_out=0 despite 15-30 out-of-range clips
# already generated) -- 10 more seeds may still not clear the >=4 bar. This
# is a real possibility, not a script bug: report whatever the new dropped
# rate is (per the project notes's flag-back trigger for "fit R^2 low on many
# generations"), do not force more seeds indefinitely chasing a gate that
# may reflect a genuine model limitation (see the project notes Section 5's account
# of LTX-Video's near-total-inertia failure mode).

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

echo "=== projectile: +5 out-of-range seeds (5-9) ==="
python3 experiments/e0_pilot.py --seeds-in 0 --seeds-out 5 --start-seed 5 --merge

echo "=== bouncing_ball: +10 out-of-range seeds (5-14) ==="
python3 experiments/e4_generality.py --model ltx --systems bouncing_ball \
    --seeds-in 0 --seeds-out 10 --start-seed 5 --merge

echo "=== pendulum_omega: +10 out-of-range seeds (5-14) ==="
python3 experiments/e4_generality.py --model ltx --systems pendulum_omega \
    --seeds-in 0 --seeds-out 10 --start-seed 5 --merge

echo "=== pendulum_zeta: +10 out-of-range seeds (5-14) ==="
python3 experiments/e4_generality.py --model ltx --systems pendulum_zeta \
    --seeds-in 0 --seeds-out 10 --start-seed 5 --merge

echo "=== spring_mass: +10 out-of-range seeds (5-14) ==="
python3 experiments/e4_generality.py --model ltx --systems spring_mass \
    --seeds-in 0 --seeds-out 10 --start-seed 5 --merge

echo "=== re-running E2 analysis to see what cleared the gate ==="
python3 experiments/e2_extrapolation.py
