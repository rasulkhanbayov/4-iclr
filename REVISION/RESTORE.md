# Restoring PhysWeep after the pause

The project is split in two: **code and documents** in git (you push and pull them), and **data** in the
private Hugging Face dataset `rasulkhanbayov/physweep-revision-archive`. Model weights and environments
are not archived. They are re-downloaded and rebuilt at the exact versions recorded in `REVISION/env/`.
Nothing here needs a GPU. Run on a shared server (10.4.64.27 or .28), not on panther-login.

## 0. Get the code

Clone or pull your repository so that `4-ICLR/REVISION/` exists at
`/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR` (the paths in `slurm/v2/cluster.env`). Put your
HF token in `4-ICLR/.env` as one line, `HF_TOKEN=...` (not in git).

## 1. Data (5,574 files, 9.5 GB)

```bash
cd "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"
bash REVISION/restore.sh data --sample      # quick: every small file + LTX-2's main-run videos
bash REVISION/restore.sh data               # everything
bash REVISION/restore.sh data --parts runs  # one part: runs, results_v1, results_v2, provenance, env, logs_v1, logs_v1_root, logs_v2
```

Files land at their original paths (`runs/` under `/export/hbku-research/rakh90100/physweep_revision/`,
the rest under `4-ICLR/`). Every file is checked against `MANIFEST.sha256`. A file that already exists is
never overwritten: it is skipped if its hash matches, and reported as a conflict otherwise.
`--target-root DIR` restores under `DIR` instead, which is how the archive is verified before deleting.
`--snapshot` also unpacks a tarball of every small project file, as a fallback if something never
reached git.

## 2. Numbers check (CPU, ~15 s; ~2 min with --recompute)

Without `physweep2`, the first run builds a small helper conda env (`envs/restore_helper`: Python 3.10,
huggingface_hub, numpy, pyyaml, pillow). The system `python3` on the shared servers cannot make venvs.

```bash
bash REVISION/restore.sh check                 # recompute all 622 numbers; expect the counts in PROVENANCE.md
bash REVISION/restore.sh check --recompute     # also re-run v2_analyze.py and diff its output byte for byte
bash REVISION/restore.sh check --find 0.033    # where does a number come from
```

## 3. Environments (only for new runs)

```bash
bash REVISION/restore.sh envs
```

This rebuilds `physweep2` and `physweep2-cosmos` (conda, Python 3.10.22) and `external/dynamicrafter_venv`
from the `pip freeze` lock files in `REVISION/env/`. The DynamiCrafter env becomes a self-contained conda
env with Python 3.10.20; the original was a venv on the v1 env's Python and broke with it. torch 2.11.0+cu128 comes from the PyTorch cu128 index.
Each environment is then diffed against its lock file, and `v2_check_env.py` runs. The v1 environment
(`~/miniconda3/envs/physweep`) is locked in `env/physweep_v1.*`, but no remaining step needs it.

## 4. Weights (only for new runs)

```bash
bash REVISION/restore.sh weights step6        # frame channel: DynamiCrafter, Wan2.2-A14B, LTX-2, Cosmos (~319 GB)
bash REVISION/restore.sh weights text_sweep   # everything the text sweep used (~489 GB)
bash REVISION/restore.sh weights ltx2 cosmos2_2b
python REVISION/archive/restore_weights.py --list    # sizes and which step needs what
```

Each HF repo is downloaded at the commit in `generators.REVISIONS` and restricted to the file list in
`env/hf_snapshots.json`. `refs/main` is set to that commit, then sizes are checked (`--deep` also checks
every sha256). DynamiCrafter comes from GitHub's tarball of commit `859021927d8e`, plus our patched
`inference.py` (3 lines: `imageio` instead of the removed `torchvision.io.write_video`). Its two
`model.ckpt` files come from `Doubiiu/DynamiCrafter_512@9eb8744` and `_Interp@5163d01`. Both checkpoints
are sha256-checked; these hashes equal both the files the runs used and HF's own LFS hashes.
**Run jobs with `HF_HUB_OFFLINE=1`** afterwards, so nothing resolves to a newer commit.

| model | GB | needed by |
|---|---|---|
| ltx | 28.4 | text sweep |
| cogvideox | 21.6 | text sweep |
| dynamicrafter | 24.8 (2 checkpoints + CLIP) | step 6, text sweep |
| wan22_ti2v_5b | 34.2 | text sweep |
| cogvideox15_i2v | 31.1 | text sweep |
| wan22_i2v_a14b | 126.2 | step 6, text sweep |
| hunyuan15_i2v (480p) | 54.2 | text sweep |
| hunyuan15_i2v_720p | 54.2 | first pilot only, not needed |
| ltx2 | 144.7 | step 6, text sweep |
| cosmos2_2b (+ guardrail, Qwen3Guard) | 23.4 | step 6, text sweep |
| Qwen3-VL-30B-A3B (plan step 7) | ~60 | not downloaded yet: pin its commit on first download |

The shaded-style ablation has no model list yet; choose one and restore those models. CoTracker3 (the
second tracker) is in `$TORCH_HOME` (156 MB), which stays on disk during the pause. Its code came from
GitHub `main` unpinned. `env/weights_sha256.txt` records the checkpoint (`scaled_online.pth`) and the
code files, so a re-download can be checked.

## What is not restored

- `4-ICLR/results/` was a byte-identical copy of `REVISION/results_v1/`. Only the v1 E3 rows refer to
  it, through absolute `video_path` values. Copy `results_v1` back to `results` only if you re-run the
  v1 VLM rater.
- Weights and runtime caches (`hf_home/xet`, `hf_home/cosmos_guardrail` NLTK data) are re-created on
  first use.
- Failed or partial job attempts from before the final results. They were never part of any number.
