#!/bin/bash -l
#SBATCH -J physweep_e3_score
#SBATCH -o e3_score_%j.out
#SBATCH -e e3_score_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 06:00:00

# E3: score every clip saved by 07/08/09_e3e5_*.sh with the Qwen2.5-VL-7B-Instruct
# plausibility rater, then pair (mean plausibility, PRE) per model-system.
# PREREQUISITE: 07_e3e5_ltx.sh, 08_e3e5_cogvideox.sh, 09_e3e5_dynamicrafter.sh
# must have already run with --save-video (they do by default) -- this job
# reads results/e3e5_default_{system}_{model}.json and the .mp4 files it
# points to; it does not generate anything itself.
#
# Qwen2.5-VL-7B is much lighter than the video generators (7B params,
# inference-only, no generation sampling loop) -- scoring ~210 clips x 3
# models = ~630 clips should take well under 6h even with per-clip video
# decode overhead; sized with margin, not a tight estimate.
#
# Uses --models/--systems (batch mode) so the 7B rater loads ONCE for the
# whole job, not once per (model, system) pair -- e3_plausibility_gap.py's
# score_one() internally skips any pair whose e3e5_default_*.json doesn't
# exist yet, so it's safe to request all 18 pairs even if some of
# 07/08/09_e3e5_*.sh haven't finished.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
# see 07_e3e5_ltx.sh for the full explanation: a stray user-site
# huggingface_hub in ~/.local can shadow the conda env's correctly-pinned
# copy -- this job loads transformers/qwen-vl-utils, same risk class.
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

python3 experiments/e3_plausibility_gap.py \
    --models ltx cogvideox dynamicrafter \
    --systems projectile pendulum_omega pendulum_zeta bouncing_ball spring_mass inclined_slide \
    --variant default

echo "All available E3 scoring done. Result files: results/e3_plausibility_default_{system}_{model}.json"
