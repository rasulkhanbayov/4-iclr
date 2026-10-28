#!/bin/bash
#SBATCH -J pw2_sweep_h200
#SBATCH -o logs/pw2_sweep_h200_%A_%a.out
#SBATCH -e logs/pw2_sweep_h200_%A_%a.err
#SBATCH -p gpu-H200
#SBATCH -A h200_hbku
#SBATCH -q h200_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=120000MB
#SBATCH -t 12:00:00
# Step 5 sweep worker for the h200 queue. Usage (normally via submit_sweep.sh):
#   sbatch --array=0-<N-1> 20_sweep_h200.sh <tasks file>
# Array index i runs the i-th non-comment line of the tasks file:
#   run model mode n_noise shard count [extra v2_run.py arguments, e.g. --channel frame --pilot]
# Resumable: resubmitting skips every clip already recorded by any shard.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
TASKS="$1"
read -r RUN MODEL MODE NNOISE SHARD COUNT EXTRA < <(grep -v '^#' "$TASKS" | grep -v '^\s*$' | sed -n "$((SLURM_ARRAY_TASK_ID + 1))p")
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$(env_for_model "$MODEL")"
cd "$CODE"
echo "task $SLURM_ARRAY_TASK_ID: run=$RUN model=$MODEL mode=$MODE n_noise=$NNOISE shard=$SHARD/$COUNT extra=${EXTRA:-none} host=$(hostname) $(nvidia-smi --query-gpu=name --format=csv,noheader)"
python experiments/v2_run.py --model "$MODEL" --run "$RUN" --mode "$MODE" --n-noise "$NNOISE" \
    --shard-index "$SHARD" --shard-count "$COUNT" ${EXTRA:-}
