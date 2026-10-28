#!/bin/bash -l
#SBATCH -J physweep_e2_cogvideox
#SBATCH -o e2_cogvideox_%j.out
#SBATCH -e e2_cogvideox_%j.err
#SBATCH -p gpu-A100
#SBATCH --gres=gpu:1
#SBATCH -c 8
#SBATCH --mem=48000MB
#SBATCH -A a100_hbku
#SBATCH -q a100_hbku_qos
#SBATCH -t 3-00:00:00

# E2 gap-fill: CogVideoX-5B-I2V, add MORE OUT-OF-RANGE seeds. CogVideoX is
# MUCH slower than LTX-Video per clip (measured 2026-07-04/05, CLAUDE.md
# Section 5: ~2.3 min/clip at 49 frames, ~5.9 min/clip at 97 frames) --
# hence the full 3-day time limit (gpu-A100's max per the Panther guide;
# email qcrisupport if this needs extending further).
#
# Gap per experiments/e2_extrapolation.py (re-check before trusting this --
# it will drift if E0/E4 are re-run first):
#   projectile       n_out=12  ALREADY ADJUDICATED -> not re-run here
#   pendulum_omega/zeta, bouncing_ball, spring_mass, inclined_slide: n_out=0
#   every one of these had a 97-100% fit-quality-dropped rate across the
#   ORIGINAL 5 out-of-range seeds x however-many-grid-points (CLAUDE.md
#   Section 5's E4 CogVideoX table) -- i.e. CogVideoX has so far produced
#   ZERO gated out-of-range clips on any of these 4 systems. Adding seeds
#   is the only lever available, but given a ~100% historical drop rate,
#   treat "still 0 after this job" as a REAL, reportable finding (the
#   runbook's flag-back trigger for high non-physical-generation rate), not
#   evidence to keep throwing more seeds at it. 8 extra seeds chosen as a
#   proportionate second attempt, not a guarantee of clearing the gate.

set -euo pipefail
source "$HOME/miniconda3/etc/profile.d/conda.sh"
conda activate physweep
module load cuda12.1/toolkit/12.1.1 2>/dev/null || true

REPO="/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
cd "$REPO"

for SYS in bouncing_ball inclined_slide; do
    echo "=== $SYS: +8 out-of-range seeds (5-12), N_FRAMES=24 system, faster ==="
    python3 experiments/e4_generality.py --model cogvideox --systems "$SYS" \
        --seeds-in 0 --seeds-out 8 --start-seed 5 --merge
done

for SYS in pendulum_omega pendulum_zeta spring_mass; do
    echo "=== $SYS: +8 out-of-range seeds (5-12), 97-frame-capped system, slow ==="
    python3 experiments/e4_generality.py --model cogvideox --systems "$SYS" \
        --seeds-in 0 --seeds-out 8 --start-seed 5 --merge
done

echo "=== re-running E2 analysis to see what cleared the gate ==="
python3 experiments/e2_extrapolation.py
