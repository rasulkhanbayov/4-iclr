#!/bin/bash -l
#SBATCH -J physweep_e2_analysis
#SBATCH -o e2_analysis_%j.out
#SBATCH -e e2_analysis_%j.err
#SBATCH -p cpu-all
#SBATCH -c 2
#SBATCH --mem=4000MB
#SBATCH -t 00:10:00

# experiments/e2_extrapolation.py is pure numpy/yaml analysis over EXISTING
# results/*.json -- no GPU, no torch, no model loading. It re-runs
# automatically at the end of each 01/02/03_e2_gapfill_*.sh job, so this
# script is only useful standalone: to check current E2 status without
# waiting for a GPU allocation, e.g. right after cloning this repo or
# between gap-fill jobs. Per the Panther guide, GPU queues (gpu-A100 etc.)
# should not be used for CPU-only work -- this uses cpu-all instead.
#
# Can also just be run directly on the login node without sbatch at all
# (it finishes in well under a second) -- this script exists mainly so
# there's a record of it in squeue/sacct if you want one.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

python3 experiments/e2_extrapolation.py
