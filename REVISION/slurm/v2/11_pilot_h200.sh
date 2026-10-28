#!/bin/bash
#SBATCH -J pw2_pilot_h200
#SBATCH -o pw2_pilot_h200_%A_%a.out
#SBATCH -e pw2_pilot_h200_%A_%a.err
#SBATCH -p gpu-H200
#SBATCH -A h200_hbku
#SBATCH -q h200_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=120000MB
#SBATCH -t 08:00:00
#SBATCH --array=0-3
# Step 4 pilot, H200 models (large or memory-heavy). Same 12-clip pilot as the
# A100 job. cosmos2_2b runs in the separate physweep2-cosmos env.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
MODELS=(wan22_i2v_a14b hunyuan15_i2v ltx2 cosmos2_2b)
MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$(env_for_model "$MODEL")"
cd "$CODE"
echo "model=$MODEL host=$(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python experiments/v2_run.py --model "$MODEL" --pilot
