#!/bin/bash -l
#SBATCH -J physweep_e5_ablations
#SBATCH -o e5_ablations_%j.out
#SBATCH -e e5_ablations_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=48000MB
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH -t 1-00:00:00

# E5(b)/(d)/(e)/(f): parameter-variant ablations, scoped to the PROJECTILE
# system only across all 3 models (the runbook does not specify a
# system/model scope for these; projectile is the paper's primary,
# best-characterized system and the natural choice). No --save-video or
# --dual-track here -- these ablations test whether the FAITHFULNESS METRIC
# itself is robust to measurement/hyperparameter choices, not plausibility
# or tracker-artifact questions (those are E3 and E5a, run separately in
# 07/08/09_e3e5_*.sh).
#
# E5(d) NOTE: the runbook's E5(d) also covers "conditioning length (#frames
# in C1)" -- NOT run here, since C1 (frame-implied conditioning) is broken/
# unusable for every model in this study (LTXConditionPipeline bug,
# documented in the paper's own Limitations section) -- only the
# RESOLUTION half of E5(d) is covered via --cond-resolution.
#
# Sized to ~1 day: LTX-Video's variants are trivial (~2s/clip); CogVideoX's
# are the bottleneck (~2.3min/clip x 40 clips x 4 variant settings below
# = several hours, well within the 1-day limit given projectile's small
# 40-clip grid, unlike the full-6-system E3/E5a jobs).
#
# RESILIENCE (real bug found 2026-08-23, job 380561): this script originally
# relied on `set -euo pipefail` alone, so ONE python3 call returning nonzero
# (CogVideoX's E5(d) resolution sweep: THUDM/CogVideoX-5b-I2V's checkpoint
# uses learned, non-interpolatable positional embeddings baked to 480x720 --
# diffusers raises ValueError for ANY other resolution, a hard model
# limitation, not a bug in this project's code) killed the ENTIRE script
# immediately, losing every remaining variant including all of
# DynamiCrafter's ablations that would have run after it in the loop.
# Every python3 call below is now wrapped with `|| echo "... FAILED,
# continuing"` so one variant's failure is logged and skipped, not fatal to
# the rest of the sweep -- this file has NOT re-enabled `set -e` for that
# reason (still on, but only governs setup lines above the loop).

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
# see 07_e3e5_ltx.sh for the full explanation: a stray user-site
# huggingface_hub in ~/.local shadows the conda env's correctly-pinned
# copy and breaks every diffusers import (this job hits ltx/cogvideox).
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

for MODEL in ltx cogvideox dynamicrafter; do
    # E5(e) guidance-scale sweep: SKIPPED for dynamicrafter -- run_dynamicrafter()
    # hardcodes --unconditional_guidance_scale=7.5 in its own subprocess call
    # (experiments/e0_pilot_dynamicrafter.py); make_dynamicrafter_generate_fn()
    # takes no args at all, so --guidance-scale would be silently ignored by
    # the actual generation while still tagging the output filename as if it
    # took effect (e3e5_cfg1.0_projectile_dynamicrafter.json) -- a real
    # mislabeling risk, not just wasted compute. Do not add this back without
    # first threading guidance_scale through run_dynamicrafter() itself.
    if [ "$MODEL" != "dynamicrafter" ]; then
        echo "======================================================================"
        echo "E5(e) guidance-scale sweep: $MODEL, projectile"
        echo "======================================================================"
        for GS in 1.0 1.5 4.5 9.0; do
            echo "--- guidance_scale=$GS ---"
            python3 experiments/e3e5_extended.py --model "$MODEL" --systems projectile \
                --guidance-scale "$GS" || echo "!! $MODEL guidance_scale=$GS FAILED, continuing to next variant"
        done
    else
        echo "Skipping E5(e) for dynamicrafter: guidance_scale is hardcoded in run_dynamicrafter(), not pass-through -- see comment above."
    fi

    echo "======================================================================"
    echo "E5(f) prompt-phrasing variants: $MODEL, projectile"
    echo "======================================================================"
    for VARIANT in terse verbose; do
        echo "--- prompt-variant=$VARIANT ---"
        python3 experiments/e3e5_extended.py --model "$MODEL" --systems projectile \
            --prompt-variant "$VARIANT" || echo "!! $MODEL prompt-variant=$VARIANT FAILED, continuing to next variant"
    done

    echo "======================================================================"
    echo "E5(b) scale-invariance: $MODEL, projectile"
    echo "======================================================================"
    for SCALE in 0.5 1.5 2.0; do
        echo "--- disk_scale=$SCALE ---"
        python3 experiments/e3e5_extended.py --model "$MODEL" --systems projectile \
            --disk-scale "$SCALE" || echo "!! $MODEL disk_scale=$SCALE FAILED, continuing to next variant"
    done
    for FPS in 0.5 2.0; do
        echo "--- fps_scale=$FPS ---"
        python3 experiments/e3e5_extended.py --model "$MODEL" --systems projectile \
            --fps-scale "$FPS" || echo "!! $MODEL fps_scale=$FPS FAILED, continuing to next variant"
    done

    # E5(d) conditioning resolution: SKIPPED for dynamicrafter (same reason as
    # guidance-scale above -- make_dynamicrafter_generate_fn() takes no args,
    # cond_resolution would be silently ignored while still mislabeling
    # output) AND skipped for cogvideox (a HARD model limitation, not a
    # tunable/no-op like dynamicrafter's: THUDM/CogVideoX-5b-I2V's transformer
    # uses learned, non-interpolatable positional embeddings baked to its
    # training resolution 480x720 -- diffusers raises ValueError for ANY
    # other height/width, confirmed via diffusers' own source
    # (CogVideoXPatchEmbed.forward) during this project's investigation of
    # job 380561's crash. Only the CogVideoX1.5 series supports variable
    # resolution, a DIFFERENT checkpoint this project has not validated.
    if [ "$MODEL" == "ltx" ]; then
        echo "======================================================================"
        echo "E5(d) conditioning resolution: $MODEL, projectile"
        echo "======================================================================"
        for RES in 256 384; do
            echo "--- cond_resolution=$RES ---"
            python3 experiments/e3e5_extended.py --model "$MODEL" --systems projectile \
                --cond-resolution "$RES" || echo "!! $MODEL cond_resolution=$RES FAILED, continuing to next variant"
        done
    elif [ "$MODEL" == "cogvideox" ]; then
        echo "Skipping E5(d) for cogvideox: THUDM/CogVideoX-5b-I2V's checkpoint hard-rejects any non-480x720 resolution -- see comment above."
    else
        echo "Skipping E5(d) for dynamicrafter: resolution is hardcoded in run_dynamicrafter(), not pass-through -- see comment above."
    fi
done

echo "All E5(b)/(d)/(e)/(f) variants done. Result files: results/e3e5_*_projectile_{model}.json"
