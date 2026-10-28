#!/bin/bash
#SBATCH -J pw2_analyze
#SBATCH -o logs/pw2_analyze_%j.out
#SBATCH -e logs/pw2_analyze_%j.err
#SBATCH -p cpu-all
#SBATCH -c 4
#SBATCH --mem=32000MB
#SBATCH -t 08:00:00
# After the sweep: re-score every clip with the current rules (CPU), then
# analyze the main run and compare it with the API-mode run.
# Writes REVISION/results_v2/main_text_analysis.{json,md}.
set -euo pipefail
source "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/REVISION/slurm/v2/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate "$ENV_MAIN"
cd "$CODE"
python experiments/v2_rescore.py --run main_text
python experiments/v2_rescore.py --run api_text
python experiments/v2_pilot_summary.py --run main_text
python experiments/v2_analyze.py --run main_text --compare api_text
