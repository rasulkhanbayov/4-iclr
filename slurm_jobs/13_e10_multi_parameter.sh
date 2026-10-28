#!/bin/bash -l
#SBATCH -J physweep_e10_multi_param
#SBATCH -o e10_multi_param_%j.out
#SBATCH -e e10_multi_param_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=40000MB
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH -t 06:00:00

# The multi-parameter experiment (E10, optional) -- joint omega x zeta sweep
# on the damped pendulum system, both models. See
# experiments/e10_multi_parameter.py's own docstring for the full design
# rationale (why this system, why this grid, why DynamiCrafter is excluded).
#
# 9 grid cells (omega in {3,5,8} x zeta in {0.05,0.3,0.6}) x 5 seeds = 45
# clips per model. Per-clip cost measured from the existing pendulum_omega
# experiment at the same n_frames=180: LTX-Video ~5.7s/clip (~260s total,
# a few minutes), CogVideoX ~142s/clip (~6400s, ~1.8h total) -- this job
# runs BOTH models sequentially in one job (LTX first, since it is cheap
# enough that failing fast on a real bug costs almost nothing) rather than
# two separate jobs, since combined runtime comfortably fits one modest
# time budget. 6h gives real margin over the ~2h estimate.
#
# Writes results/e10_multi_parameter_ltx.json and
# results/e10_multi_parameter_cogvideox.json.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
export PYTHONNOUSERSITE=1
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

echo "=== E10, LTX-Video ==="
python3 experiments/e10_multi_parameter.py --model ltx

echo
echo "=== E10, CogVideoX ==="
python3 experiments/e10_multi_parameter.py --model cogvideox

echo
echo "== E10 done. Cross-axis degradation summary for both models =="
python3 - <<'PYEOF'
import json, os
RESULTS_DIR = "results"
for model in ["ltx", "cogvideox"]:
    path = os.path.join(RESULTS_DIR, f"e10_multi_parameter_{model}.json")
    if not os.path.exists(path):
        print(f"{model}: missing result file")
        continue
    s = json.load(open(path))["summary"]
    print(f"\n{model}:")
    for key in ["omega_faithfulness_when_zeta_other_in_range",
                "omega_faithfulness_when_zeta_other_out_of_range",
                "zeta_faithfulness_when_omega_other_in_range",
                "zeta_faithfulness_when_omega_other_out_of_range"]:
        print(f"  {key}: {s.get(key)}")
    print(f"  overall_dropped_rate: {s.get('overall_dropped_rate')}")
PYEOF
