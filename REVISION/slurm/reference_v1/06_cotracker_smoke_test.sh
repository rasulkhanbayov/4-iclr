#!/bin/bash -l
#SBATCH -J physweep_cotracker_smoke
#SBATCH -o cotracker_smoke_%j.out
#SBATCH -e cotracker_smoke_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 4
#SBATCH --mem=16000MB
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH -t 00:30:00

# E5(a) prerequisite: validate CoTracker3 (physweep/track.py's
# cotracker_track()) against ground-truth projectile trajectories BEFORE
# trusting it on any generated-model clip. This is the SAME validation
# philosophy as E6 (measurement must be proven on known-truth data before
# touching a real generator) -- do not run 07/08/09_e3e5_*.sh with
# --dual-track until this job actually prints PASS-equivalent numbers
# (rel_err comparable to centroid_track()'s own smoke test, R2 reasonably
# high). First-run cost: torch.hub auto-downloads CoTracker3 weights from
# HF Hub, needs network access from the compute node (confirm this works;
# if the compute node has no internet egress, download the checkpoint on a
# node that does and set TORCH_HOME so torch.hub finds the cache).

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

python3 -m physweep.track
