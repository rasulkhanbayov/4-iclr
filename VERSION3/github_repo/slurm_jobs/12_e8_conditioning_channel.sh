#!/bin/bash -l
#SBATCH -J physweep_e8_conditioning
#SBATCH -o e8_conditioning_%j.out
#SBATCH -e e8_conditioning_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=32000MB
#SBATCH -A <YOUR_GPU_ACCOUNT>
#SBATCH -q <YOUR_GPU_QOS>
#SBATCH -t 12:00:00

# E8 -- conditioning-channel ablation, C1 (frame-implied) vs C2 (text-specified),
# DynamiCrafter only. See experiments/e8_conditioning_channel.py's own docstring
# for why: LTX-Video's multi-frame pipeline is genuinely broken in this project's
# diffusers version beyond the mu-parameter fix (physweep/ltx_patch.py); CogVideoX
# has no official multi-frame conditioning path at all; DynamiCrafter ships an
# OFFICIAL interpolation checkpoint (Doubiiu/DynamiCrafter_512_Interp) through the
# exact same inference.py already integrated in this project, just with --interp
# and a first+second conditioning-frame pair instead of one image -- the one
# bounded, same-codebase path to a real C1 test.
#
# Scope: projectile, bouncing_ball, inclined_slide -- the three systems where
# DynamiCrafter's C2 run already produces usable (non-frame-ceiling-blocked) data.
# pendulum_omega/pendulum_zeta/spring_mass need >=1-2 oscillation periods this
# model's fixed 16-frame output cannot deliver regardless of conditioning channel,
# so C1 vs C2 is not a meaningful comparison there -- deliberately not run.
#
# 40 clips per system x 3 systems = 120 clips, ~70-95s/clip subprocess cost
# (same order as the existing C2 DynamiCrafter runs) -> ~2.5-3.5h pure generation;
# 12h gives real margin.
#
# PREREQUISITE: 00_setup_env.sh must have downloaded
# checkpoints/dynamicrafter_512_interp_v1/model.ckpt (added to 00_setup_env.sh
# this session) -- if this job errors on a missing checkpoint, run
# 00_setup_env.sh again first.
#
# Writes results/e8_conditioning_channel_{system}_dynamicrafter.json.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="<PATH_TO_REPO>"
cd "$REPO"

if [ ! -f "external/DynamiCrafter/checkpoints/dynamicrafter_512_interp_v1/model.ckpt" ]; then
    echo "ERROR: DynamiCrafter interp checkpoint not found. Run slurm_jobs/00_setup_env.sh" >&2
    echo "on a shared server (<SHARED_SERVER_1>/28) first." >&2
    exit 1
fi

python3 experiments/e8_conditioning_channel.py --systems projectile bouncing_ball inclined_slide

echo
echo "== E8 generation done. Comparing against the existing C2 (text-specified) =="
echo "== baseline for the same systems/model =="
python3 - <<'PYEOF'
import json, os
RESULTS_DIR = "results"
for system in ["projectile", "bouncing_ball", "inclined_slide"]:
    c1_path = os.path.join(RESULTS_DIR, f"e8_conditioning_channel_{system}_dynamicrafter.json")
    c2_path = os.path.join(RESULTS_DIR, f"e3e5_default_{system}_dynamicrafter.json")
    if not (os.path.exists(c1_path) and os.path.exists(c2_path)):
        print(f"{system}: missing a comparison file, skip")
        continue
    c1 = json.load(open(c1_path))["summary"]
    c2_rows = json.load(open(c2_path))["rows"]
    n_total_in = sum(1 for r in c2_rows if r["split"] == "in")
    gated = [r for r in c2_rows if r["r2"] >= 0.8 and r["theta_hat"] == r["theta_hat"]]
    c2_dropped = 1.0 - len(gated) / max(len(c2_rows), 1)
    print(f"{system}: C1 dropped={c1.get('dropped_rate'):.2%} slope_in={c1.get('slope_in')}  |  "
          f"C2 dropped={c2_dropped:.2%}")
PYEOF
