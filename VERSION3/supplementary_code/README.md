# PhysWeep — supplementary code and data

This is the anonymized code and data release accompanying the paper
"PhysWeep: Does a Video Generator Realize the Physics You Ask For?"
(WACV 2027, Evaluations & Datasets track). It covers the metrics, the
synthetic suite, the measurement pipeline, and per-clip raw results behind
every number reported in the paper and its supplementary material.

No author names, institution names, internal cluster names, IP addresses,
or filesystem paths tied to a specific person or machine appear anywhere
in this folder. Job IDs (e.g. "job 380915") that appear in a few comments
are internal batch-scheduler identifiers with no identifying information
attached to them and are kept only as debugging context.

## What's included

```
requirements.txt         Pinned Python environment
physweep_metrics.py       Metrics, fitters, bootstrap CIs, mechanism
                           selection (PRE, EG, PRI, CBI, SDI/FDI), plus a
                           self-contained smoke test (see below)
physweep/
  render.py                Deterministic 2D renderer for all 6 sweep axes
  track.py                 Trackers: blob-centroid (default) and a
                             CoTracker3 wrapper (independent-tracker check)
  configs/systems.yaml      Exact sweep grids used for every result
  ltx_patch.py              A documented, reproducible upstream diffusers
                             bug workaround (LTXConditionPipeline), kept
                             for the record though not used by any
                             reported result (see Results, "protocol
                             deviations")
experiments/               One script per experiment (E0-E10), plus the
                             consolidated E3/E5 plausibility-and-robustness
                             harness (e3e5_extended.py) and standalone
                             re-analysis scripts for E5's sub-ablations
slurm_jobs/*.sh             The exact batch-job scripts used to run every
                             experiment on a SLURM cluster (paths and
                             account names replaced with placeholders,
                             see "Adapting for your own cluster" below)
results/*.json              Every per-clip raw result file referenced in
                             the paper: model, system, seed, requested
                             theta, recovered theta_hat, fit R^2,
                             in/out-of-range split, and (for the
                             plausibility pass) the VLM score. Every
                             number in the paper was recomputed directly
                             from these files during finalization, not
                             carried forward from memory or an
                             intermediate summary.
```

Not included: the ~630 generated video clips themselves (large binary
files, not needed to verify any reported number, and reproducible by
re-running the pipeline against the released renderer/config) and two
debug PNG frame-comparison images used only during development.

## Setup

```bash
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

The Tier-0 statistical checks referenced in the appendix (SDI/FDI on all
adjudicated pairs, the label-permutation null, the TOST equivalence test)
are pure re-analysis of these same JSON files using the functions in
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
replace this with the absolute path to wherever you place this folder on
your own machine or cluster before submitting.

## Adapting for your own cluster

The provided `slurm_jobs/*.sh` scripts were written for a SLURM cluster
with two GPU partitions (a general one and a higher-priority one) and a
shared home directory across the login node and compute nodes. Every
cluster-specific value has been replaced with a placeholder:

- `<PATH_TO_REPO>` — replace with the absolute path to this folder.
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

Per the venue's reproducibility guidance, this release covers the main
results (the full faithfulness sweep, the negative/positive controls, the
mechanism adjudication, the SDI/FDI theory-validation checks) and the
large majority of the minor experiments and ablations (tracker swap,
scale/resolution/guidance/prompt-phrasing robustness checks, the
conditioning-channel ablation, the multi-parameter sweep). It does not
include the exact generated video files themselves, since they are large,
not needed to verify any reported number, and reproducible from the
released renderer and config.
