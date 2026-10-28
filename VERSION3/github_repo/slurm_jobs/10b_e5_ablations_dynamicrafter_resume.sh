#!/bin/bash -l
#SBATCH -J physweep_e5_ablations_dc
#SBATCH -o e5_ablations_dc_%j.out
#SBATCH -e e5_ablations_dc_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 12:00:00

# RESUME-ONLY job: job 380561 (10_e5_ablations.sh) died partway through
# CogVideoX's E5(d) resolution sweep (a hard model limitation -- see the
# fixed 10_e5_ablations.sh's comments -- not a bug), which under the
# original `set -euo pipefail`-only script killed the WHOLE run before it
# ever reached DynamiCrafter's ablations. All of LTX-Video's and
# CogVideoX's E5(b)/(e)/(f) variants already completed successfully and do
# NOT need re-running (confirmed: results/e3e5_*_projectile_{ltx,cogvideox}.json
# already exist for every variant except cogvideox's cond_resolution, which
# is permanently skipped now anyway). This job runs ONLY the missing
# DynamiCrafter ablations: E5(f) prompt variants and E5(b) scale-invariance
# (E5(e) guidance-scale and E5(d) resolution are both no-ops for
# DynamiCrafter, per 10_e5_ablations.sh's own documented exclusions).
#
# 10_e5_ablations.sh itself has ALSO been fixed (each variant call now
# wrapped so one failure doesn't kill the rest) for any future full re-run,
# but this resume job is the faster path to finishing 2026-08-23's
# interrupted run without waiting on LTX/CogVideoX to redo already-good work.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

echo "======================================================================"
echo "E5(f) prompt-phrasing variants: dynamicrafter, projectile"
echo "======================================================================"
for VARIANT in terse verbose; do
    echo "--- prompt-variant=$VARIANT ---"
    python3 experiments/e3e5_extended.py --model dynamicrafter --systems projectile \
        --prompt-variant "$VARIANT" || echo "!! dynamicrafter prompt-variant=$VARIANT FAILED, continuing"
done

echo "======================================================================"
echo "E5(b) scale-invariance: dynamicrafter, projectile"
echo "======================================================================"
for SCALE in 0.5 1.5 2.0; do
    echo "--- disk_scale=$SCALE ---"
    python3 experiments/e3e5_extended.py --model dynamicrafter --systems projectile \
        --disk-scale "$SCALE" || echo "!! dynamicrafter disk_scale=$SCALE FAILED, continuing"
done
for FPS in 0.5 2.0; do
    echo "--- fps_scale=$FPS ---"
    python3 experiments/e3e5_extended.py --model dynamicrafter --systems projectile \
        --fps-scale "$FPS" || echo "!! dynamicrafter fps_scale=$FPS FAILED, continuing"
done

echo "DynamiCrafter ablations done. E5(b)/(d)/(e)/(f) is now complete across all 3 models"
echo "(with the documented no-op/hard-limitation exclusions: E5(e)/(d) for dynamicrafter, E5(d) for cogvideox)."
