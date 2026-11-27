#!/bin/bash
#SBATCH -J pw2_rate
#SBATCH -o logs/pw2_rate_%A_%a.out
#SBATCH -e logs/pw2_rate_%A_%a.err
#SBATCH -p gpu-A100
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=96000MB
#SBATCH -t 12:00:00
# Step 7 (plan E-D): plausibility rating of a run's saved clips. Usage, from this folder:
#   sbatch --array=0-1 21_rate_a100.sh [run]     # 0 = Qwen3-VL-30B-A3B (62 GB, fits an 80 GB A100), 1 = Qwen2.5-VL-7B
# Default run: main_text. Resumable: resubmitting skips clips already rated. Weights: restore.sh weights step7.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
RATERS=(qwen3vl_30b_a3b qwen25vl_7b)
RATER="${RATERS[$SLURM_ARRAY_TASK_ID]}"
RUN="${1:-main_text}"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_MAIN"
export HF_HUB_OFFLINE=1          # weights are pinned and on disk; never resolve a newer commit
cd "$CODE"
echo "rater=$RATER run=$RUN host=$(hostname) $(nvidia-smi --query-gpu=name --format=csv,noheader)"
python experiments/v2_rate_plausibility.py --rater "$RATER" --run "$RUN"
