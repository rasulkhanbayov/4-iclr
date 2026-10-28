#!/bin/bash
#SBATCH -J pw2_repilot_a100
#SBATCH -o pw2_repilot_a100_%j.out
#SBATCH -e pw2_repilot_a100_%j.err
#SBATCH -p gpu-A100
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=64000MB
#SBATCH -t 06:00:00
# Option B re-pilot: CogVideoX1.5 at 49 frames. Same 12-clip pilot, written to
# run "pilot_b" so the original pilot stays untouched.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_MAIN"
cd "$CODE"
echo "host=$(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python experiments/v2_run.py --model cogvideox15_i2v --pilot --run pilot_b
