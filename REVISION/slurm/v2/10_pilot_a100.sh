#!/bin/bash
#SBATCH -J pw2_pilot_a100
#SBATCH -o pw2_pilot_a100_%A_%a.out
#SBATCH -e pw2_pilot_a100_%A_%a.err
#SBATCH -p gpu-A100
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=64000MB
#SBATCH -t 06:00:00
#SBATCH --array=0-4
# Step 4 pilot, A100 models: 12 clips each (3 systems x 2 theta x 2 scene seeds,
# one noise seed), structured scenes, text channel, both trackers.
# Measures seconds/clip, peak VRAM and validity rate before the main sweep.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
MODELS=(ltx cogvideox dynamicrafter wan22_ti2v_5b cogvideox15_i2v)
MODEL=${MODELS[$SLURM_ARRAY_TASK_ID]}
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$(env_for_model "$MODEL")"
cd "$CODE"
echo "model=$MODEL host=$(hostname) $(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader)"
python experiments/v2_run.py --model "$MODEL" --pilot
