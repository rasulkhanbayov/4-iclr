#!/bin/bash
# Rebuild the PhysWeep project after the pause. Run from a clone of the code repository, on a shared
# server (10.4.64.27/.28), not on panther-login. Every part is optional; see REVISION/RESTORE.md.
#
#   bash REVISION/restore.sh data              # archived data from HF -> original paths, sha256-checked
#   bash REVISION/restore.sh data --sample     # small files + one model's videos (quick check)
#   bash REVISION/restore.sh envs              # physweep2, physweep2-cosmos, dynamicrafter_venv from lock files
#   bash REVISION/restore.sh weights step6     # weights for one step (step6 | text_sweep), pinned commits
#   bash REVISION/restore.sh weights ltx2 ...  # or for named models
#   bash REVISION/restore.sh check             # re-run the number check against the restored data
#
# HF token: exported HF_TOKEN, else ONLY the HF_TOKEN= line of 4-ICLR/.env (never source that file).
set -euo pipefail

HERE="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"          # .../4-ICLR/REVISION
source "$HERE/slurm/v2/cluster.env"                               # BASE, HF_HOME, ENV_MAIN, ENV_COSMOS, DC_ROOT, ...
export PYTHONNOUSERSITE=1
LOCK="$HERE/env"
CU128="https://download.pytorch.org/whl/cu128"

# A Python with huggingface_hub, numpy, pyyaml and pillow, for the restore scripts and the number check.
# Uses physweep2 if it exists, otherwise builds a small conda env once (the system python3 on the shared
# servers has no ensurepip, so `python3 -m venv` fails there).
helper_python () {
    if [ -x "$ENV_MAIN/bin/python" ]; then echo "$ENV_MAIN/bin/python"; return; fi
    local v="$BASE/envs/restore_helper"
    if [ ! -x "$v/bin/python" ]; then
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
        conda create -y -q -p "$v" python=3.10 >&2
        PIP_CACHE_DIR="$BASE/.pip_cache_restore" "$v/bin/pip" install -q huggingface_hub==0.36.2 numpy pyyaml pillow >&2
    fi
    echo "$v/bin/python"
}

lock_reqs () {   # lock file without pip/setuptools/wheel and local-file lines
    grep -v -E '^(pip|setuptools|wheel)( |==|@)|@ file://' "$1"
}

restore_conda_env () {   # $1 = prefix, $2 = lock name
    local prefix="$1" name="$2"
    if [ -x "$prefix/bin/python" ]; then echo "== $prefix exists, verifying only"; else
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
        conda create -y -p "$prefix" "python=$(awk '{print $2}' "$LOCK/$name.python-version.txt")"
        PIP_CACHE_DIR="$BASE/.pip_cache_restore" "$prefix/bin/pip" install --extra-index-url "$CU128" \
            -r <(lock_reqs "$LOCK/$name.pip-freeze.txt")
    fi
    diff <(lock_reqs "$LOCK/$name.pip-freeze.txt" | sort) <("$prefix/bin/pip" freeze --all | grep -v -E '^(pip|setuptools|wheel)( |==|@)|@ file://' | sort) \
        && echo "== $name matches its lock file" || { echo "!! $name differs from its lock file (diff above)"; return 1; }
}

case "${1:-}" in
  data)
    shift; PY="$(helper_python)"
    "$PY" "$HERE/archive/restore_data.py" --source hf "$@"
    # 4-ICLR/results/ was a byte-identical copy of REVISION/results_v1/; only the v1 E3 rows point into it
    # (absolute video_path). Recreate it only if you need to re-run the v1 VLM rater.
    ;;
  envs)
    restore_conda_env "$ENV_MAIN" physweep2
    restore_conda_env "$ENV_COSMOS" physweep2-cosmos
    if [ ! -x "$DC_PYTHON" ]; then
        # The original was a venv on top of the v1 conda env's Python 3.10.20 (~/miniconda3/envs/physweep),
        # so it died with that env. Rebuild it as a self-contained conda env at the same path and version.
        source "$HOME/miniconda3/etc/profile.d/conda.sh"
        conda create -y -p "$(dirname "$(dirname "$DC_PYTHON")")" "python=$(awk '{print $2}' "$LOCK/dynamicrafter_venv.python-version.txt")"
        PIP_CACHE_DIR="$BASE/.pip_cache_restore" "$DC_PYTHON" -m pip install --extra-index-url "$CU128" \
            -r <(lock_reqs "$LOCK/dynamicrafter_venv.pip-freeze.txt")
    fi
    diff <(lock_reqs "$LOCK/dynamicrafter_venv.pip-freeze.txt" | sort) <("$DC_PYTHON" -m pip freeze --all | grep -v -E '^(pip|setuptools|wheel)( |==|@)|@ file://' | sort) \
        && echo "== dynamicrafter_venv matches its lock file" || echo "!! dynamicrafter_venv differs (diff above)"
    ( cd "$CODE" && "$ENV_MAIN/bin/python" experiments/v2_check_env.py --env main && "$ENV_COSMOS/bin/python" experiments/v2_check_env.py --env cosmos )
    rm -rf "$BASE/.pip_cache_restore"
    ;;
  weights)
    shift; PY="$(helper_python)"
    if [ "${1:-}" = "step6" ] || [ "${1:-}" = "text_sweep" ]; then
        "$PY" "$HERE/archive/restore_weights.py" --step "$1" "${@:2}"
    else
        "$PY" "$HERE/archive/restore_weights.py" --models "$@"
    fi
    echo "Run jobs with HF_HUB_OFFLINE=1 so no model resolves to a newer commit."
    ;;
  check)
    PY="$(helper_python)"
    ( cd "$CODE" && "$PY" -W ignore experiments/reproduce_numbers.py "${@:2}" )
    ;;
  *)
    sed -n '2,13p' "$0"; exit 1 ;;
esac
