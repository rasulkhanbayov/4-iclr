#!/bin/bash
# Run this ONCE, interactively, on one of the SHARED PHYSICAL SERVERS
# (<SHARED_SERVER_1> or <SHARED_SERVER_2>), NOT on the cluster-login -- the login node kills
# stray long-running user processes (python, conda/pip installers included),
# per the the cluster End Users Guide ("Anaconda Installation" section). SSH
# there first:
#   ssh <username>@<SHARED_SERVER_1>
# then run this script from the same path (home directory is shared/
# symlinked across the cluster-login, the shared servers, and compute nodes, so
# no copying is needed): this repo lives at
#   <PATH_TO_REPO>
#
# Sets up TWO separate environments, matching the project notes Section 6 exactly:
#   1. "physweep" (conda) -- LTX-Video + CogVideoX, diffusers in-process.
#   2. external/dynamicrafter_venv (plain venv, NOT conda) -- DynamiCrafter,
#      a standalone non-diffusers research codebase with its own dependency
#      constraints that conflict with (1). Also clones the DynamiCrafter
#      repo itself and downloads its checkpoint.
#
# Safe to re-run: every step is skipped if already done.
#
# PYTHONNOUSERSITE=1 (real bug found 2026-08-22): a stray package installed
# to ~/.local/lib/python3.10/site-packages OUTSIDE any conda env (e.g. from
# a `pip install` run without an activated env) silently SHADOWS this env's
# own correctly-pinned packages, since ~/.local's site-packages comes before
# the active conda env's site-packages on sys.path regardless of which env
# is active. Concretely: a stray huggingface_hub==1.27.0 in ~/.local broke
# every diffusers import here despite this env's own huggingface_hub==0.36.2
# being correctly installed and untouched -- `pip show huggingface_hub`
# still reported 0.36.2 in the env, but Python actually loaded the ~/.local
# copy at runtime. Exporting this for the whole setup (not just downstream
# jobs) so any verification step below sees the same resolution the actual
# experiment jobs will.
export PYTHONNOUSERSITE=1
set -euo pipefail

REPO="<PATH_TO_REPO>"
CONDA_DIR="$HOME/miniconda3"

# ---------------------------------------------------------------------------
# 1. physweep conda env (LTX-Video, CogVideoX)
# ---------------------------------------------------------------------------
if [ ! -x "$CONDA_DIR/bin/conda" ]; then
    echo "== conda not found at $CONDA_DIR -- installing Miniconda =="
    TMP_INSTALLER="$HOME/miniconda_installer.sh"
    curl -fsSL -o "$TMP_INSTALLER" \
        https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh
    bash "$TMP_INSTALLER" -b -p "$CONDA_DIR"
    rm -f "$TMP_INSTALLER"
else
    echo "== conda already installed at $CONDA_DIR =="
fi

source "$CONDA_DIR/etc/profile.d/conda.sh"

# Newer Anaconda default channels require Terms of Service acceptance before
# any env can be created or solved against them -- accept once,
# non-interactively (see 3-ACL/generator_build/slurm_jobs/00_setup_env.sh for
# the same pattern used elsewhere in this workspace).
echo "== accepting Anaconda channel Terms of Service (one-time) =="
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r

echo "== creating conda env physweep (python 3.10) if missing =="
if ! conda env list | grep -q "^physweep "; then
    conda create -y -n physweep python=3.10
fi
conda activate physweep

echo "== installing physweep packages from requirements.txt =="
# REAL BUG found 2026-08-22: without PYTHONNOUSERSITE=1 during pip install
# itself (not just at runtime), pip's dependency resolver treats a package
# already present in ~/.local's user site-packages as "already satisfied"
# and SKIPS installing its own copy into this conda env's site-packages --
# discovered when numpy/scipy/pillow/tqdm/filelock/typing-extensions/fsspec
# turned out to have NEVER actually been installed inside the physweep env
# itself, despite `pip show`/`pip list` reporting them at the correct
# pinned versions (pip was reporting the ~/.local shadow copy, not the
# env's own state). This worked by silent accident for the whole project
# until an unrelated ~/.local package (huggingface_hub, bumped to 1.27.0 on
# 2026-08-18 by some process outside this project) broke the shadow.
# PYTHONNOUSERSITE=1 during the INSTALL forces pip to see the true state of
# THIS env and actually install everything into it, making the env
# genuinely self-contained rather than accidentally dependent on whatever
# happens to be in the shared user site-packages at runtime.
export PYTHONNOUSERSITE=1
pip install --upgrade pip
# torch (+ torchvision, its officially paired release) is installed
# separately from the cu128 index (per requirements.txt's header comment) to
# match this cluster's A100/H200 nodes' CUDA 12.x. Do NOT split torch and any
# package that depends on it (e.g. a bare `pip install torchvision` with no
# pin, or in a SEPARATE pip call) -- resolving an unpinned dependency, or
# letting a later `pip install -r requirements.txt` resolve torchvision on
# its own, can silently upgrade torch itself or pull a CPU-only/mismatched
# build (see 3-ACL/generator_build/slurm_jobs/00_setup_env.sh's note on
# exactly this bug). torchvision==0.26.0 is the officially paired release
# for torch==2.11.0; added 2026-08-2x after job 380915 found it missing
# entirely -- transformers' AutoVideoProcessor (Qwen2.5-VL's video-input
# path, used by E3's plausibility rater) needs it, even though LTX-Video/
# CogVideoX's own diffusers pipelines never did, which is why this went
# unnoticed until the E3 script actually ran.
pip install torch==2.11.0 torchvision==0.26.0 --index-url https://download.pytorch.org/whl/cu128
pip install -r "$REPO/requirements.txt"

echo "== verifying the ACTUAL runtime-resolved versions (not just pip show), =="
echo "== and that every import actually resolves from THIS env, not ~/.local =="
CONDA_ENV_SITE="$CONDA_DIR/envs/physweep/lib/python3.10/site-packages"
python3 - "$CONDA_ENV_SITE" <<'PYEOF'
import sys, importlib
env_site = sys.argv[1]
checks = [
    ("numpy", "2.2.6"), ("scipy", "1.15.3"), ("yaml", "6.0.3"),
    ("PIL", "12.3.0"), ("imageio", "2.37.3"),
    ("diffusers", "0.39.0"), ("transformers", "4.57.6"),
    ("tiktoken", None), ("accelerate", "1.14.0"), ("safetensors", "0.8.0"),
    ("sentencepiece", "0.2.1"), ("huggingface_hub", "0.36.2"),
    ("torchvision", "0.26.0+cu128"),  # added 2026-08-2x after job 380915's
    # ImportError (transformers' AutoVideoProcessor, needed by E3's Qwen2.5-VL
    # rater, was never in requirements.txt at all -- see that file's comment).
    ("qwen_vl_utils", None),
]
ok = True
for mod_name, expected in checks:
    try:
        mod = importlib.import_module(mod_name)
    except ImportError as e:
        print(f"  {mod_name}: FAILED TO IMPORT ({e})")
        ok = False
        continue
    actual = getattr(mod, "__version__", "?")
    from_env = mod.__file__.startswith(env_site) if mod.__file__ else False
    version_ok = (expected is None or actual == expected)
    status = "OK" if (version_ok and from_env) else "PROBLEM"
    print(f"  {mod_name}: version={actual} from_this_env={from_env} [{status}] ({mod.__file__})")
    if not (version_ok and from_env):
        ok = False
if not ok:
    print("!! At least one package failed to import, resolved to the wrong version,")
    print("!! or is being loaded from OUTSIDE this conda env's own site-packages")
    print(f"!! ({env_site}). Do not trust any experiment run until every line above")
    print("!! says OK -- re-run 'pip install --force-reinstall --no-deps <pkg>==<pin>'")
    print("!! for whichever package(s) failed, with PYTHONNOUSERSITE=1 still set.")
    sys.exit(1)
print("  All checked packages import correctly from THIS env at their pinned versions.")
PYEOF

echo
echo "== physweep env ready. =="
echo

# ---------------------------------------------------------------------------
# 2. DynamiCrafter: clone repo + isolated venv + checkpoint download
# ---------------------------------------------------------------------------
DC_ROOT="$REPO/external/DynamiCrafter"
DC_VENV="$REPO/external/dynamicrafter_venv"

mkdir -p "$REPO/external"

if [ ! -d "$DC_ROOT" ]; then
    echo "== cloning DynamiCrafter =="
    git clone https://github.com/Doubiiu/DynamiCrafter.git "$DC_ROOT"
else
    echo "== DynamiCrafter already cloned at $DC_ROOT =="
fi

# Real bug #2 from the project notes Section 5: torchvision.io.write_video was
# removed in torchvision>=0.20, but scripts/evaluation/inference.py calls it
# at 2 sites. Patch to use imageio instead -- safe to re-apply (idempotent
# via the grep check) since this is a local clone, not upstream.
INFER_SCRIPT="$DC_ROOT/scripts/evaluation/inference.py"
# Match an ACTUAL call (torchvision.io.write_video followed by an open
# paren), not just any mention of the string -- a bare grep for the string
# also matches the explanatory comments this same patch leaves behind on a
# previous run ("## ... (torchvision.io.write_video removed in ...)"),
# which caused a false "still needs patching" positive on a second setup
# run against an already-correctly-patched file (2026-08-22).
if [ -f "$INFER_SCRIPT" ] && grep -q "torchvision\.io\.write_video(" "$INFER_SCRIPT"; then
    echo "== patching $INFER_SCRIPT: torchvision.io.write_video -> imageio.mimwrite =="
    # REGEX replace (not an exact-string match) -- an earlier version of this
    # patch used a hand-guessed exact call signature that did NOT match the
    # real upstream source (wrong arg names), so it silently did nothing:
    # every DynamiCrafter generation call failed with "AttributeError: module
    # 'torchvision.io' has no attribute 'write_video'" (the cluster job 371751,
    # 2026-08-07) despite this script printing a success message. The regex
    # below matches the call by shape (any first positional arg, any second
    # positional arg, ignoring the exact variable names and the trailing
    # video_codec/options kwargs) so it is robust to minor upstream variation,
    # and the script now VERIFIES the match count afterward instead of just
    # asserting success.
    python3 - "$INFER_SCRIPT" <<'PYEOF'
import sys, re
path = sys.argv[1]
with open(path) as f:
    src = f.read()
pattern = re.compile(
    r"torchvision\.io\.write_video\(([^,]+),\s*([^,]+),\s*fps=fps,\s*video_codec='h264',\s*options=\{'crf':\s*'10'\}\)"
)
new_src, n = pattern.subn(r"imageio.mimwrite(\1, \2.numpy(), fps=fps)", src)
if "import imageio" not in new_src:
    new_src = new_src.replace("import torchvision", "import torchvision\nimport imageio", 1)
with open(path, "w") as f:
    f.write(new_src)
print(f"  replaced {n} call site(s)")
if n == 0:
    print("  WARNING: 0 replacements -- the regex did not match. DynamiCrafter's")
    print("  upstream source has likely changed again; inspect the file manually")
    print("  before trusting any DynamiCrafter generation from this setup.")
    sys.exit(1)
PYEOF
    # Verify: the ORIGINAL broken CALL must be gone (not just any mention of
    # the string -- the patch's own explanatory comments deliberately keep
    # saying "torchvision.io.write_video removed in torchvision>=0.20", so
    # checking for the bare string here would permanently false-positive on
    # this script's own output), or every DynamiCrafter inference call will
    # crash with AttributeError at generation time (exactly what happened in
    # job 371751) despite this script's own exit code being 0 up to now.
    if grep -q "torchvision\.io\.write_video(" "$INFER_SCRIPT"; then
        echo "!! PATCH VERIFICATION FAILED: a torchvision.io.write_video(...) call"
        echo "!! still present in $INFER_SCRIPT after patching. Every DynamiCrafter"
        echo "!! generation call will crash. Fix this file manually before running"
        echo "!! any DynamiCrafter job."
        exit 1
    fi
    echo "   Patch verified: no remaining torchvision.io.write_video call sites."
else
    echo "== $INFER_SCRIPT already patched (no torchvision.io.write_video found) =="
fi

if [ ! -x "$DC_VENV/bin/python" ]; then
    echo "== creating isolated venv for DynamiCrafter (NOT conda, NOT the physweep env) =="
    python3 -m venv "$DC_VENV"
    source "$DC_VENV/bin/activate"
    pip install --upgrade pip
    # Modern torch (matches the physweep env's CUDA wheel), NOT the old
    # torch==2.0.0 DynamiCrafter's own requirements.txt pins -- its actual
    # API usage is version-tolerant (verified 2026-07-05, the project notes Section 5).
    pip install torch==2.11.0 torchvision --index-url https://download.pytorch.org/whl/cu128
    pip install pytorch-lightning omegaconf einops decord kornia \
        "open_clip_torch==2.22.0" transformers imageio imageio-ffmpeg \
        opencv-python-headless pillow numpy moviepy av timm
    deactivate
else
    echo "== dynamicrafter_venv already exists at $DC_VENV =="
fi

CKPT="$DC_ROOT/checkpoints/dynamicrafter_512_v1/model.ckpt"
if [ ! -f "$CKPT" ]; then
    echo "== downloading DynamiCrafter_512 checkpoint (~2.6GB) from HF Hub =="
    mkdir -p "$(dirname "$CKPT")"
    "$DC_VENV/bin/python" -c "
from huggingface_hub import hf_hub_download
import shutil
p = hf_hub_download(repo_id='Doubiiu/DynamiCrafter_512', filename='model.ckpt')
shutil.copy(p, '$CKPT')
print('Saved to $CKPT')
" || {
        echo "!! huggingface_hub download failed -- pip install huggingface_hub in"
        echo "!! dynamicrafter_venv first, or download model.ckpt manually from"
        echo "!! https://huggingface.co/Doubiiu/DynamiCrafter_512/blob/main/model.ckpt"
        echo "!! and place it at: $CKPT"
    }
else
    echo "== DynamiCrafter checkpoint already present at $CKPT =="
fi

INTERP_CKPT="$DC_ROOT/checkpoints/dynamicrafter_512_interp_v1/model.ckpt"
if [ ! -f "$INTERP_CKPT" ]; then
    echo "== downloading DynamiCrafter_512_Interp checkpoint (~2.6GB) from HF Hub =="
    echo "== (E8 conditioning-channel ablation: official first+last-frame =="
    echo "== interpolation checkpoint, same inference.py, --interp flag) =="
    mkdir -p "$(dirname "$INTERP_CKPT")"
    "$DC_VENV/bin/python" -c "
from huggingface_hub import hf_hub_download
import shutil
p = hf_hub_download(repo_id='Doubiiu/DynamiCrafter_512_Interp', filename='model.ckpt')
shutil.copy(p, '$INTERP_CKPT')
print('Saved to $INTERP_CKPT')
" || {
        echo "!! huggingface_hub download failed for the interp checkpoint --"
        echo "!! download model.ckpt manually from"
        echo "!! https://huggingface.co/Doubiiu/DynamiCrafter_512_Interp/blob/main/model.ckpt"
        echo "!! and place it at: $INTERP_CKPT"
    }
else
    echo "== DynamiCrafter interp checkpoint already present at $INTERP_CKPT =="
fi

echo
echo "== ALL SETUP DONE. =="
echo "IMPORTANT: 'conda activate physweep' does not work in a fresh"
echo "non-interactive shell (e.g. inside an sbatch script) without first"
echo "sourcing conda.sh -- the job scripts in this directory already do this."
echo
echo "Quick GPU-visibility check from THIS shell (a shared server, may or"
echo "may not have a free GPU right now -- the check that matters is inside"
echo "an actual sbatch job on a the cluster compute node):"
echo "  conda activate physweep && python3 -c 'import torch; print(torch.cuda.is_available())'"
