# PhysWeep

**Does a video generator realize the physics you ask for?**

PhysWeep is a label-free audit of *parameter faithfulness* in image-to-video
generators. Most video-physics benchmarks ask whether a generated clip
*looks* physically plausible — but a clip can look perfectly smooth while
encoding the wrong value of the physical parameter it was conditioned on
(e.g. the wrong gravity, the wrong restitution). PhysWeep instead treats a
frozen generator as a black box, recovers the *realized* parameter from
generated pixels with a tracker and a closed-form physics fit, and measures
how far that recovered value sits from the one actually requested — in
range and out of range.

Applied to three open generators (LTX-Video, CogVideoX-5B-I2V,
DynamiCrafter) across six sweep axes, PhysWeep finds that none of them
detectably honor a requested physical parameter, and that two of the three
converge to a small number of fixed, wrong values selected by the
*sampling seed* rather than by the request — a signature that reproduces
across model families, physical systems, and an independent tracker.

📄 Paper: **[arXiv:⟨ARXIV_ID⟩](https://arxiv.org/abs/⟨ARXIV_ID⟩)** *(link
to be added once the arXiv listing is live)*

This repository contains the full pipeline — the deterministic physics
suite, the tracker, the metrics and mechanism-adjudication code, the
experiment drivers, and every per-clip raw result — needed to reproduce
every number in the paper.

## Contents

```
requirements.txt          Pinned Python environment
physweep_metrics.py        Metrics, fitters, bootstrap CIs, mechanism
                            selection (PRE, EG, PRI, CBI, SDI/FDI), plus a
                            self-contained smoke test (see below)
physweep/
  render.py                 Deterministic 2D renderer for all 6 sweep axes
  track.py                  Trackers: blob-centroid (default) and a
                              CoTracker3 wrapper (independent-tracker check)
  configs/systems.yaml       Exact sweep grids used for every result
  ltx_patch.py               A documented, reproducible upstream diffusers
                              bug workaround (LTXConditionPipeline), kept
                              for the record though not used by any
                              reported result (see the paper's Results
                              section, "protocol deviations")
experiments/                One script per experiment (E0–E10), plus the
                              consolidated plausibility-and-robustness
                              harness (e3e5_extended.py) and standalone
                              re-analysis scripts for the sub-ablations
slurm_jobs/*.sh              The exact batch-job scripts used to run every
                              experiment on a SLURM cluster (see "Adapting
                              for your own cluster" below)
results/*.json               Every per-clip raw result file referenced in
                              the paper: model, system, seed, requested
                              theta, recovered theta_hat, fit R^2,
                              in/out-of-range split, and (for the
                              plausibility pass) the VLM score
```

Not included: the ~630 generated video clips themselves (large binary
files, not needed to verify any reported number, and reproducible by
re-running the pipeline against the released renderer/config).

## Setup

```bash
git clone <this-repo-url>
cd physweep
python3 -m venv .venv
source .venv/bin/activate
pip install torch==2.11.0+cu128 torchvision==0.26.0+cu128 \
    --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```

Requires an NVIDIA GPU with CUDA 12.8 support (results were produced on an
A100-SXM4-40GB) for any script that loads a video generator. The metrics,
fitters, smoke test, and every `results/*.json` re-analysis script
(`e2_extrapolation.py`, `e5a_cotracker_analysis.py`,
`e5bdef_ablation_analysis.py`, `e5c_fit_gate_sensitivity.py`,
`e7_mechanism_adjudication.py`) need only CPU and numpy/scipy — no GPU,
no model download.

DynamiCrafter is not a `diffusers`-compatible pipeline and is invoked via
subprocess against a separately cloned copy of
[`Doubiiu/DynamiCrafter`](https://github.com/Doubiiu/DynamiCrafter) in an
isolated virtual environment; see the comments at the top of
`experiments/e0_pilot_dynamicrafter.py` and `slurm_jobs/00_setup_env.sh`
for the exact clone/patch/checkpoint-download steps.

## Verifying the metrics and fitters (no GPU needed)

```bash
python3 physweep_metrics.py
```

Runs a self-contained smoke test against closed-form synthetic
trajectories: every physics fitter (gravity, angular frequency,
restitution, friction), the metrics (PRE, EG, faithfulness slope,
Spearman rho), and the mechanism-selection rule (PRI/CBI, AIC,
leave-one-theta-out R^2, the margin requirement). All checks should print
PASS.

## Reproducing a paper number from the raw data (no GPU needed)

Every reported statistic can be recomputed directly from `results/*.json`
without regenerating any video. For example, the paper's simulator-video
positive control (PRE(in) = 0.0031, slope = 1.0001, mean fit R^2 = 0.986,
pooled over 203 measurements):

```bash
python3 -c "
import json
with open('results/e6_negative_control.json') as f:
    d = json.load(f)
print(d['overall'])
"
```

The paper's Tier-0 statistical checks (SDI/FDI on all adjudicated pairs,
the label-permutation null, the TOST equivalence test) are pure
re-analysis of these same JSON files using the functions in
`physweep_metrics.py` (`seed_determination_index`,
`variance_decomposition`, `select_mechanism`) — no new generation
required.

## Running a full experiment end to end (GPU required)

```bash
# 1. One-time environment + DynamiCrafter checkpoint setup
sbatch slurm_jobs/00_setup_env.sh
# (or run the same steps interactively if not using SLURM — see the
#  comments at the top of that script for the manual equivalent)

# 2. Any experiment, e.g. the main faithfulness sweep for LTX-Video:
sbatch slurm_jobs/07_e3e5_ltx.sh
```

Every `slurm_jobs/*.sh` script begins with a `REPO=<PATH_TO_REPO>` line —
replace this with the absolute path to wherever you place this repository
on your own machine or cluster before submitting.

## Adapting for your own cluster

The provided `slurm_jobs/*.sh` scripts were written for a SLURM cluster
with two GPU partitions (a general one and a higher-priority one) and a
shared home directory across the login node and compute nodes. Every
cluster-specific value is a placeholder:

- `<PATH_TO_REPO>` — replace with the absolute path to this repository.
- `<YOUR_GPU_ACCOUNT>` / `<YOUR_GPU_QOS>` — the `#SBATCH -A` / `#SBATCH -q`
  values; replace with your own cluster's account/QoS names, or remove
  those two lines entirely if your scheduler doesn't use them.
- `<SHARED_SERVER_1>` / `<SHARED_SERVER_2>` — `00_setup_env.sh` was
  originally run interactively on a shared physical server rather than
  the SLURM login node (to avoid the login node killing long-running
  installs); if your cluster doesn't have this restriction, just run
  `00_setup_env.sh` directly wherever `sbatch` is available.

If you are not using SLURM at all, every `.sh` file's actual commands
(after the `#SBATCH` header block) are plain bash and can be run directly
in any shell with the right conda/venv environments active.

## Scope

This release covers the main results (the full faithfulness sweep, the
negative/positive controls, the mechanism adjudication, the SDI/FDI
theory-validation checks) and the large majority of the minor experiments
and ablations (tracker swap, scale/resolution/guidance/prompt-phrasing
robustness checks, the conditioning-channel ablation, the multi-parameter
sweep). It does not include the exact generated video files, since they
are large, not needed to verify any reported number, and reproducible
from the released renderer and config.

## License

The code in this repository (everything under `physweep/`, `experiments/`,
`physweep_metrics.py`, and `slurm_jobs/`) is released under the MIT
License — see [`LICENSE`](LICENSE).

This does **not** cover the third-party models the pipeline calls out to,
which retain their own licenses and are not redistributed here:
LTX-Video (custom Open Weights license), CogVideoX-5B-I2V (custom,
free for academic use), DynamiCrafter (weights: research/non-commercial;
companion code: Apache-2.0), Qwen2.5-VL-7B-Instruct (Apache-2.0), and
CoTracker3 (CC-BY-NC 4.0). See the paper's supplementary material for the
exact repository IDs and license terms of each.

## Citation

If you use PhysWeep, please cite:

```bibtex
@article{physweep2026,
  title   = {PhysWeep: Does a Video Generator Realize the Physics You Ask For?},
  author  = {Khanbayov, Rasul and Kurban, Hasan},
  journal = {arXiv preprint arXiv:⟨ARXIV_ID⟩},
  year    = {2026}
}
```

*(Replace `⟨ARXIV_ID⟩` above and in the paper link once the arXiv
submission is live.)*
