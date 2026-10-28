#!/bin/bash
#SBATCH -J pw2_repilot_h200
#SBATCH -o pw2_repilot_h200_%A_%a.out
#SBATCH -e pw2_repilot_h200_%A_%a.err
#SBATCH -p gpu-H200
#SBATCH -A h200_hbku
#SBATCH -q h200_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=120000MB
#SBATCH -t 06:00:00
#SBATCH --array=0-1
# Option B re-pilot: HunyuanVideo-1.5 480p at 33 frames, and Cosmos (now that
# the guardrail license is accepted). Run "pilot_b". Submit after 02_download_extra.sh.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
MODELS=(hunyuan15_i2v cosmos2_2b)
MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$(env_for_model "$MODEL")"
cd "$CODE"
echo "model=$MODEL host=$(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python experiments/v2_run.py --model "$MODEL" --pilot --run pilot_b
