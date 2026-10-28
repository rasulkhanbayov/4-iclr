# Storage plan for the CVPR pause (2026-10-28)

**Nothing has been deleted.** Every command below waits for your approval, one group at a time.
Sizes are `du` on 2026-10-28. G = GiB, the unit `du` and `df` print.

## Filesystems

| filesystem | size | used | free | use |
|---|---|---|---|---|
| `/export/home` (shared NFS) | 110T | 97T | 14T | 88% |
| `/export/hbku-research` | 10T | 9.6T | 476G | **96%** |

## Inventory and classification

Categories: **A** irreplaceable (archived to HF), **B** exactly re-creatable from public sources (version
recorded in `REVISION/env/`), **C** re-creatable by our own code, **D** junk.

### `/export/hbku-research/rakh90100/physweep_revision` (568G)

| item | size | created by | cat. | needed by | action | frees |
|---|---|---|---|---|---|---|
| `hf_home/hub/` (12 model repos) | 546G | `01_download_models.sh` (job 425643), `02_download_extra.sh` (426446), pilot jobs | B | step 6 (319 GB of it), any re-run | delete in stage 2; restore per step with `restore.sh weights` | 546G |
| …of which HunyuanVideo-1.5 **720p** | 57G | first pilot (job 425709) | B | nothing (replaced by 480p) | not restored by default | (incl.) |
| …of which LTX-2 | 153G | download + H200 pilot | B | step 6 | | (incl.) |
| `hf_home/xet/` | 68M | huggingface_hub cache | D | nothing | delete in stage 1 | 0.07G |
| `hf_home/cosmos_guardrail/` | 35M | NLTK data the guardrail downloads at load time | B | Cosmos runs (re-created on load) | delete with stage 2 | 0.03G |
| `envs/physweep2` | 11G | `00_setup_envs.sh` | B | any new run, rescoring | delete in stage 2; `restore.sh envs` | 11G |
| `envs/physweep2-cosmos` | 11G | `00_setup_envs.sh` | B | Cosmos runs | delete in stage 2 | 11G |
| `envs/*.freeze.txt` | 3K | setup | A (tiny) | lock files | keep (copied to `env/`) | – |
| `torch_home/` (CoTracker3 code + checkpoint) | 156M | torch.hub, first run | B* | every new run (second tracker) | **keep**: tiny, and its code came from GitHub `main` unpinned | – |
| `runs/main_text/` | 9.1G | sweep jobs 427770/427772 + rescore | A | every v2 number | upload; delete in stage 3 | 9.1G |
| `runs/api_text/` | 1.1G | sweep jobs | A | seed-free tier numbers | upload; delete in stage 3 | 1.1G |
| `runs/pilot_b/` | 312M | re-pilot jobs 426446–426984 | A | step 4 numbers | upload; delete in stage 3 | 0.3G |
| `runs/pilot/` | 122M | pilot jobs 425643–425709 | A | step 4 numbers | upload; delete in stage 3 | 0.1G |
| `runs/*/clips_rescored.jsonl` | (in runs) | `v2_rescore.py` | C, archived anyway (small) | analysis | with runs | – |

### `/export/home/.../4-ICLR` (33G)

| item | size | created by | cat. | needed by | action | frees |
|---|---|---|---|---|---|---|
| `external/DynamiCrafter/` (code + 2 × 10.4 GB `model.ckpt`) | 23G | `slurm/reference_v1/00_setup_env.sh` (Aug 7; interp ckpt Aug 23) | B | step 6, DynamiCrafter re-runs | delete in stage 2; `restore.sh weights step6` | 23G |
| `external/dynamicrafter_venv/` | 11G | same script | B | DynamiCrafter runs | delete in stage 2; `restore.sh envs` | 11G |
| `.hf_home/` | 0.6M | v1 runs (lock files and an xet log, no token) | D | nothing | delete in stage 1 | – |
| `__pycache__/` folders (outside `external/`) | 2.5M | Python | D | nothing | delete in stage 1 | – |
| `results/` | 38M | v1 experiments | duplicate of `REVISION/results_v1/` (byte-identical) | v1 E3 rows' absolute `video_path` | **keep**: an original folder, too small to matter | – |
| `REVISION/` | ~200M | this revision | A | everything | keep; code/docs to git, data also on HF | – |
| `VERSION3/`, `submitted/`, paper, PDFs | ~10M | | A | | keep (originals) | – |
| `slurm_jobs/` | 8.5M | v1 jobs | A | GPU-hour and VLM-time numbers | keep; also on HF | – |

### Elsewhere in your home directory (project-related)

| item | size | cat. | action | frees |
|---|---|---|---|---|
| `~/miniconda3/envs/physweep` (v1 env) | 11G | B (locked in `env/physweep_v1.*`) | delete in stage 2; no remaining step needs it | 11G |
| `~/.cache/pip` | 39G | shared by all your projects | your call: `pip cache purge` frees it, costs re-downloads | (39G) |
| `~/miniconda3/pkgs` | 4.4G | shared conda cache | your call: `conda clean --all` | (4.4G) |
| `~/.cache/huggingface` | 23G | other projects only (no PhysWeep model) | leave | – |
| `~/.cache/torch/hub` | 0.9G | shared (CoTracker3 from v1, other projects' ResNet/VGG) | leave | – |

### Your other projects in `/export/hbku-research/rakh90100` (not touched)

`fwf_data` 590G, `somw` 288G, `fwf_ckpts` 127G; `.pip_cache` 6.1G (shared; created by another project
today). The other folders there (`Projects`, `TTT`, `baselines`, `huggingface_cache`, `multiphase_flow_*`,
`rsvel_cvpr27`, `swaprl_cvpr27`, `vlmthink_method_cvpr27`) were not measured or opened.

## Space freed by stage

| stage | condition | hbku-research | home |
|---|---|---|---|
| 1. now | junk only | 0.07G | ~0G |
| 2. after the HF upload is verified **and** you have pushed `REVISION/env/` and the code to git | B: weights (546G), envs (22G); DynamiCrafter (34G) and the v1 env (11G) on home | **568G** | **45G** |
| 3. after the full restore test from HF passes | A: `runs/` | 10.6G | – |
| **total** | | **~579G** (476G free → ~1.05T free) | **45G** |

Stage 2 does not depend on the data upload itself, since weights and envs come from public sources.
It waits for the upload because their version records live in `REVISION/env/`, and those records must
be off this disk (in git and on HF) before the things they describe are deleted.

## Deletion commands (approve one group at a time)

Each group lists what must be true first. Run from any directory.

**Group 1: junk (now)**
```bash
rm -rf "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/.hf_home"
find "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR" -path "*/external" -prune -o -type d -name __pycache__ -prune -print -exec rm -rf {} +
rm -rf /export/hbku-research/rakh90100/physweep_revision/hf_home/xet
rm -rf /export/hbku-research/rakh90100/physweep_revision/verify_restore.dl   # partial download from the 429'd test (226M)
```

**Group 2a: model weights (546G)** — first: HF upload verified; `REVISION/env/` pushed to git.
```bash
rm -rf /export/hbku-research/rakh90100/physweep_revision/hf_home/hub \
       /export/hbku-research/rakh90100/physweep_revision/hf_home/cosmos_guardrail
```

**Group 2b: v2 environments (22G)** — first: same as 2a.
```bash
rm -rf /export/hbku-research/rakh90100/physweep_revision/envs/physweep2 \
       /export/hbku-research/rakh90100/physweep_revision/envs/physweep2-cosmos
```

**Group 2c: DynamiCrafter code, checkpoints and venv (34G, home)** — first: same as 2a.
```bash
rm -rf "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/external/DynamiCrafter" \
       "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR/external/dynamicrafter_venv"
```

**Group 2d: v1 conda env (11G, home)** — first: same as 2a, and group 2c done or done together: the
old `dynamicrafter_venv` is a venv built on this env's Python and stops working without it (the restore
rebuilds it as a self-contained conda env, so this only matters if 2c is skipped).
```bash
source ~/miniconda3/etc/profile.d/conda.sh && conda env remove -y -n physweep
```

**Group 3: generated runs (10.6G)** — first: `python REVISION/archive/check_hf.py` printed `RESULT: OK`,
`python REVISION/archive/restore_data.py --source hf --target-root /tmp/pw_verify` finished with 0
mismatches and 0 missing files, and `reproduce_numbers.py` run against `/tmp/pw_verify` gave the same
counts as `PROVENANCE.md` (see `RESTORE.md`, section 2). `slurm/v2/40_archive_upload.sh` does all three.
```bash
rm -rf /export/hbku-research/rakh90100/physweep_revision/runs/{main_text,api_text,pilot,pilot_b}
rm -rf /tmp/pw_verify /export/hbku-research/rakh90100/physweep_revision/hf_archive_download
rm -rf /export/hbku-research/rakh90100/physweep_revision/hf_archive_staging   # symlinks + upload cache (426M); rm does not follow symlinks
```

## Risks

- **Re-download time:** about 3–5 h for step 6's 319 GB (the original download ran at 20–40 MB/s per
  repo), done before any new GPU work. Gated repos (Cosmos, its guardrail) need your token's accepted
  licenses, which are already accepted.
- **Upstream removal:** a model repo could be deleted or made private on HF. `env/hf_snapshots.json`
  would still say exactly what was used, but the weights would have to be found elsewhere. Community
  ports (the HunyuanVideo-1.5 diffusers repos) and the 2024 DynamiCrafter repos are the likeliest to
  change. We do not copy third-party weights to HF ourselves.
- **CoTracker3** was loaded from GitHub `main` without a pin, so `torch_home/` stays on disk (156M).
- **pip index drift:** the lock files pin every version, and the dry run resolved all of them today
  (see LOG.md). A wheel yanked later would need a manual substitute.
