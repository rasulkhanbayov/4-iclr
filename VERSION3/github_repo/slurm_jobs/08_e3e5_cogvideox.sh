#!/bin/bash -l
#SBATCH -J physweep_e3e5_cogvideox
#SBATCH -o e3e5_cogvideox_%j.out
#SBATCH -e e3e5_cogvideox_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=48000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 3-00:00:00

# E3 (plausibility gap) + E5(a) (tracker swap) default generation pass,
# CogVideoX-5B-I2V. This is the SLOW one: ~2.3min/clip at 49 frames,
# ~5.9min/clip at the 97-frame cap (pendulum_omega, pendulum_zeta,
# spring_mass). Rough estimate across all 6 systems x 5 seeds in+out
# (210 clips total, 100 of them frame-capped): ~14h of pure generation,
# plus video-encoding + CoTracker3 inference overhead on top -- hence the
# full 3-day gpu-A100 limit (same margin the E2 CogVideoX gap-fill job
# used). Split into two sub-loops below (fast systems first) so partial
# progress is checkpointed to disk system-by-system even if the job is
# killed before the slow systems finish.
#
# PREREQUISITE: run 06_cotracker_smoke_test.sh FIRST and confirm it passes
# before trusting this job's --dual-track output (E5a's data).
#
# Writes results/e3e5_default_{system}_cogvideox.json and saves clips to
# results/e3e5_videos/.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
# see 07_e3e5_ltx.sh for the full explanation: a stray user-site
# huggingface_hub==1.27.0 in ~/.local shadows the conda env's correctly-
# pinned 0.36.2 and breaks every diffusers import. Force the env's own
# site-packages to take priority.
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

echo "=== fast systems (24-frame, ~2.3min/clip): projectile, bouncing_ball, inclined_slide ==="
python3 experiments/e3e5_extended.py --model cogvideox \
    --systems projectile bouncing_ball inclined_slide \
    --save-video --dual-track

echo "=== slow, frame-capped systems (97-frame, ~5.9min/clip): pendulum_omega, pendulum_zeta, spring_mass ==="
python3 experiments/e3e5_extended.py --model cogvideox \
    --systems pendulum_omega pendulum_zeta spring_mass \
    --save-video --dual-track
