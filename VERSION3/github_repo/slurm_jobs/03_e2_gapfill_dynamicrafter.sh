#!/bin/bash -l
#SBATCH -J physweep_e2_dynamicrafter
#SBATCH -o e2_dynamicrafter_%j.out
#SBATCH -e e2_dynamicrafter_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 06:00:00

# E2 gap-fill: DynamiCrafter_512. Per experiments/e2_extrapolation.py
# (re-check before trusting this -- drifts if E0/E4 are re-run first):
#
#   projectile       n_out=9  ALREADY ADJUDICATED
#   bouncing_ball    n_out=4  ALREADY ADJUDICATED (borderline -- exactly at
#                    the >=4 minimum; a few more seeds tighten the CI)
#   inclined_slide   n_out=5  ALREADY ADJUDICATED
#   pendulum_omega   n_out=0  NOT ADJUDICABLE, AND WILL NOT BECOME SO
#   pendulum_zeta    n_out=1  NOT ADJUDICABLE, AND WILL NOT BECOME SO
#   spring_mass      n_out=0  NOT ADJUDICABLE, AND WILL NOT BECOME SO
#
# DynamiCrafter emits a HARD FIXED 16 frames (not a tunable cap like the
# other two models) -- pendulum_omega/zeta and spring_mass need >=1-2
# oscillation periods to be identifiable AT ALL, confirmed empirically at
# 96.7-100% dropped across the original seeds (the project notes Section 5). Adding
# seeds cannot fix an architectural frame-count ceiling. Do NOT spend GPU
# time on those 3 systems here -- this job only tightens the 3 ALREADY-
# adjudicated systems (mainly bouncing_ball, sitting right at the n>=4 line)
# with a few more seeds for a more robust CI, per the runbook's general
# preference for m>=5 seeds per grid point wherever practical.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep   # only used for numpy/yaml/imageio in the wrapper script;
                          # actual generation subprocess uses dynamicrafter_venv
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

if [ ! -f "external/DynamiCrafter/checkpoints/dynamicrafter_512_v1/model.ckpt" ]; then
    echo "ERROR: DynamiCrafter checkpoint not found. Run slurm_jobs/00_setup_env.sh" >&2
    echo "on a shared server (<SHARED_SERVER_1>/28) first." >&2
    exit 1
fi

echo "=== projectile: +5 out-of-range seeds (5-9) ==="
python3 experiments/e0_pilot_dynamicrafter.py --seeds-in 0 --seeds-out 5 --start-seed 5 --merge

echo "=== bouncing_ball: +5 out-of-range seeds (5-9), tightens the borderline n=4 case ==="
python3 experiments/e4_generality.py --model dynamicrafter --systems bouncing_ball \
    --seeds-in 0 --seeds-out 5 --start-seed 5 --merge

echo "=== inclined_slide: +5 out-of-range seeds (5-9) ==="
python3 experiments/e4_generality.py --model dynamicrafter --systems inclined_slide \
    --seeds-in 0 --seeds-out 5 --start-seed 5 --merge

echo "=== re-running E2 analysis ==="
python3 experiments/e2_extrapolation.py
