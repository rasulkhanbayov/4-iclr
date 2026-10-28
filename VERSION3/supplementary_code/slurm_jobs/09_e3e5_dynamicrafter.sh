#!/bin/bash -l
#SBATCH -J physweep_e3e5_dynamicrafter
#SBATCH -o e3e5_dynamicrafter_%j.out
#SBATCH -e e3e5_dynamicrafter_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 12:00:00

# E3 (plausibility gap) + E5(a) (tracker swap) default generation pass,
# DynamiCrafter_512. ~90-95s/clip (subprocess-driven, see the project notes
# Section 0f/0g's measured per-call timing) x 210 clips (6 systems x 5
# seeds in+out) is roughly ~5.5h of pure generation; 12h gives real margin
# for video-encoding + CoTracker3 overhead without being the unbounded
# 24h+ some earlier DynamiCrafter jobs needed.
#
# DynamiCrafter's fixed 16-frame ceiling means pendulum_omega, pendulum_zeta,
# and spring_mass will very likely reproduce the near-total dropped rate
# already documented in the project notes (100%/96.7%/100%) -- run them anyway for
# E3/E5a coverage parity with the other two models (a clip can still be
# scored for plausibility and dual-tracked even if its physics fit fails
# the R^2 gate), but do not expect usable PRE pairings from those three.
#
# PREREQUISITE: run 06_cotracker_smoke_test.sh FIRST and confirm it passes
# before trusting this job's --dual-track output (E5a's data).
#
# Writes results/e3e5_default_{system}_dynamicrafter.json and saves clips
# to results/e3e5_videos/.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep   # only used for numpy/yaml/imageio/CoTracker3 in this
                          # script; DynamiCrafter's own generation subprocess
                          # uses the isolated external/dynamicrafter_venv
# see 07_e3e5_ltx.sh for the full explanation: a stray user-site
# huggingface_hub in ~/.local can shadow the conda env's correctly-pinned
# copy. Not hit by THIS script (diffusers is only imported for ltx/
# cogvideox branches, never reached here), but set for consistency/safety.
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

if [ ! -f "external/DynamiCrafter/checkpoints/dynamicrafter_512_v1/model.ckpt" ]; then
    echo "ERROR: DynamiCrafter checkpoint not found. Run slurm_jobs/00_setup_env.sh" >&2
    echo "on a shared server (<SHARED_SERVER_1>/28) first." >&2
    exit 1
fi

python3 experiments/e3e5_extended.py --model dynamicrafter \
    --systems projectile pendulum_omega pendulum_zeta bouncing_ball spring_mass inclined_slide \
    --save-video --dual-track
