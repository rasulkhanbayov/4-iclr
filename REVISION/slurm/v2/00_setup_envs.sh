#!/bin/bash
# Run ONCE, interactively, on a shared server (ssh <user>@10.4.64.27 or .28),
# not on panther-login (it kills long-running installs). Safe to re-run.
# Creates two conda envs under /export/hbku-research (home is 89% full):
#   physweep2         all models except Cosmos (transformers 4.57.6)
#   physweep2-cosmos  Cosmos only (cosmos-guardrail needs transformers>=5)
set -euo pipefail
source "$(dirname "$(readlink -f "$0")")/cluster.env"
source "$HOME/miniconda3/etc/profile.d/conda.sh"
mkdir -p "$BASE/envs" "$HF_HOME" "$TORCH_HOME" "$PHYSWEEP_OUT"

make_env () {   # $1 = prefix, $2 = requirements file, $3 = check name
    if [ ! -x "$1/bin/python" ]; then
        echo "== creating $1 =="
        conda create -y -p "$1" python=3.10
    fi
    conda activate "$1"
    pip install --upgrade pip
    pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
    pip install -r "$2"
    pip freeze > "$1.freeze.txt"
    echo "== verifying $1 =="
    ( cd "$CODE" && python experiments/v2_check_env.py --env "$3" )
    conda deactivate
}

make_env "$ENV_MAIN"   "$CODE/requirements_v2.txt"        main
make_env "$ENV_COSMOS" "$CODE/requirements_v2_cosmos.txt" cosmos

echo "== DynamiCrafter (reused from v1) =="
for f in "$DC_ROOT/checkpoints/dynamicrafter_512_v1/model.ckpt" \
         "$DC_ROOT/checkpoints/dynamicrafter_512_interp_v1/model.ckpt" "$DC_PYTHON"; do
    [ -e "$f" ] && echo "  found $f" || { echo "  MISSING $f -- re-run slurm/reference_v1/00_setup_env.sh"; exit 1; }
done
echo "== ALL SETUP DONE =="
