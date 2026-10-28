#!/bin/bash -l
#SBATCH -J physweep_e3e5_ltx
#SBATCH -o e3e5_ltx_%j.out
#SBATCH -e e3e5_ltx_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=40000MB
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH -t 08:00:00

# E3 (plausibility gap) + E5(a) (tracker swap) default generation pass,
# LTX-Video. Cheapest model per clip (~2s), so all 6 systems x 5 seeds
# in-range+out-of-range (210 clips) fits comfortably even with video-saving
# and CoTracker3 dual-tracking overhead added on top -- 8h is a large safety
# margin, not an expected runtime (LTX-Video's own E4/E2 runs finished in
# minutes-to-tens-of-minutes at similar clip counts, see CLAUDE.md).
#
# PREREQUISITE: run 06_cotracker_smoke_test.sh FIRST and confirm it passes
# before trusting this job's --dual-track output (E5a's data).
#
# Writes results/e3e5_default_{system}_ltx.json (rows with video_path +
# cotracker_cx/cy fields) and saves clips to results/e3e5_videos/.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
# real bug found 2026-08-22 (jobs 380474/380475/380477): ~/.local's user
# site-packages had a stray huggingface_hub==1.27.0 (installed 2026-08-18,
# outside any conda env) that SHADOWS the correctly-pinned
# huggingface_hub==0.36.2 inside the physweep env's own site-packages,
# since ~/.local/lib/python3.10/site-packages comes BEFORE the conda env's
# site-packages on sys.path regardless of which env is active. This broke
# every diffusers import (transformers==4.57.6 requires huggingface-hub<1.0).
# PYTHONNOUSERSITE=1 makes Python ignore ~/.local entirely so the conda
# env's own correctly-pinned packages are used, without deleting anything
# from ~/.local that some other project might depend on.
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

python3 experiments/e3e5_extended.py --model ltx \
    --systems projectile pendulum_omega pendulum_zeta bouncing_ball spring_mass inclined_slide \
    --save-video --dual-track
