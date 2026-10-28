#!/bin/bash
#SBATCH -J pw2_repilot_cosmos
#SBATCH -o pw2_repilot_cosmos_%j.out
#SBATCH -e pw2_repilot_cosmos_%j.err
#SBATCH -p gpu-H200
#SBATCH -A h200_hbku
#SBATCH -q h200_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=120000MB
#SBATCH -t 04:00:00
# Cosmos re-pilot after the cosmos-guardrail device fix (generators.py,
# _fix_cosmos_guardrail_device). Resumes run pilot_b: the 12 errored clips are retried.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_COSMOS"
cd "$CODE"
echo "host=$(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python experiments/v2_run.py --model cosmos2_2b --pilot --run pilot_b
