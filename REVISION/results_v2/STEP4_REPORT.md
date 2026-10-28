# Step 4 — Pilot jobs (2026-10-15): written and dry-run tested, not yet run on a GPU

## What was built

| file | purpose |
|---|---|
| `code/physweep/fits.py` | closed-form fits with an explicit frame interval `dt` (fixes F8) |
| `code/physweep/generators.py` | one adapter interface for 9 models plus a CPU `simulator` dry run; edge-padded canvas in, centre-crop back to 256 px out |
| `code/experiments/v2_run.py` | sweep runner: shards, resume, raw video saved, both trackers, validity labels, timing and peak VRAM per clip |
| `code/experiments/v2_pilot_summary.py` | pilot table and projected GPU-hours for the 304-clip sweep |
| `code/experiments/v2_check_env.py` | env verification (pins, from-this-env, pipeline classes) |
| `code/requirements_v2.txt`, `requirements_v2_cosmos.txt` | two envs (see below) |
| `slurm/v2/cluster.env` | paths on `/export/hbku-research/rakh90100/physweep_revision`, env per model |
| `slurm/v2/00_setup_envs.sh` | build both envs (interactive, shared server) |
| `slurm/v2/01_download_models.sh` | download all weights (CPU job, ~350–450 GB) |
| `slurm/v2/10_pilot_a100.sh` | pilot array: ltx, cogvideox, dynamicrafter, wan22_ti2v_5b, cogvideox15_i2v |
| `slurm/v2/11_pilot_h200.sh` | pilot array: wan22_i2v_a14b, hunyuan15_i2v, ltx2, cosmos2_2b |

Pilot per model: 12 clips (3 systems × lowest and highest in-range θ × scene
seeds 0–1 × one noise seed), structured scenes, text channel, both trackers.

## Model settings (from diffusers 0.39.0 signatures and each repo's model_index.json)

| model | pipeline | canvas | frames @ fps | steps | guidance | GPU | env |
|---|---|---|---|---|---|---|---|
| ltx (v1) | LTXImageToVideoPipeline | 768×512 | 25 @ 24 | 30 | 3.0 | A100 | main |
| cogvideox (v1) | CogVideoXImageToVideoPipeline | 720×480 | 49 @ 8 | 30 | 6.0 | A100 | main |
| dynamicrafter (v1) | subprocess (v1 call) | 512×320 | 16 @ 24 | 50 | 7.5 | A100 | DC venv |
| wan22_ti2v_5b | WanImageToVideoPipeline | 1280×704 | 49 @ 24 | 50 | 5.0 | A100 | main |
| cogvideox15_i2v | CogVideoXImageToVideoPipeline | 1360×768 | 81 @ 16 | 50 | 6.0 | A100 | main |
| wan22_i2v_a14b | WanImageToVideoPipeline | 832×480 | 49 @ 16 | 40 | 3.5/3.5 | H200 | main |
| hunyuan15_i2v | HunyuanVideo15ImageToVideoPipeline | 1280×720 | 61 @ 24 | 50 | (model guider) | H200 | main |
| ltx2 | LTX2ImageToVideoPipeline | 768×512 | 49 @ 24 | 40 | 4.0 | H200 | main |
| cosmos2_2b | Cosmos2VideoToWorldPipeline | 1280×704 | 93 @ 16 | 35 | 7.0 | H200 | cosmos |

MAGI-1 is dropped: diffusers 0.39 has no pipeline for it.

## Verified (CPU)

- `fits.fit_theta(dt = 1/24)` reproduces the v1 refit on 630/630 trajectories.
- Full dry run with the `simulator` model: 12/12 clips valid, θ recovered
  within 2% through the canvas round trip; resume skips finished clips; API mode
  gives unique noise seeds; videos saved at 768×512.
- `v2_check_env.py` correctly reports the old v1 env as unfit (missing `ftfy`).
- All four job scripts pass `bash -n`.

## Not verified: needs the GPU pilot

The diffusers adapters have not run on a GPU. Likely failure points, which is
what the pilot is for: output formats (`out.frames[0]` type), HunyuanVideo-1.5
sizing from the input image, VRAM on A100 for CogVideoX1.5 at 1360×768×81
(the runner has `--offload` as a fallback), and the Cosmos guardrail's own
model download.

## Two environments, and why

`cosmos-guardrail` 0.3.x requires transformers ≥ 5; 0.1.0 pins torch 2.6.0.
transformers 5.x broke LTX-Video's tokenizer in v1. So Cosmos runs in its own
env. The guardrail stays on, because the NVIDIA Open Model License forbids
bypassing it.

## New finding while building this: F8 (added to 01_review_analysis.md)

v1 fitted CogVideoX output with dt = 1/24 s although the model plays at 8 fps,
so its published ĝ values are 9× too large in the model's real time.
Scale-free conclusions stand; absolute PRE and Figure 1(a)'s axis comparison
do not. v2 records and uses each model's playback rate.

---

## Pilot results (2026-10-16; jobs 425643, 425708, 425709)

Download: 8/8 repos, 455 GB on `/export/hbku-research` (now 65% full). Both
envs built and verified. The H200 pilots started before the download job
finished and fetched weights themselves, hence load times of 2–4 h (one-off).

### Fixes made after the pilot (logged as post-pilot changes)

1. **Fit window (fits.py).** Generated clips run 2–6 s, so the ball often
   lands and rests. Fitting through the rest bent the parabola the wrong way
   (Wan2.2-A14B: ĝ = −0.92 for a ball that fell at a constant 3.8 px/frame).
   Projectile and slide are now fitted only on frames before floor contact
   (≥ 6 frames required).
2. **Amendment 2: camera stability (validity.py).** A HunyuanVideo clip moved
   its camera (floor line drifted 17–25 px). New label `invalid_camera`
   (floor line must stay within 3 px). The injection test now includes camera
   drift: it passes the fit gate on 60/65 clips and is rejected on 65/65.
3. **Runner:** errored clips are retried on resume; the DynamiCrafter timeout
   was raised to 1800 s (its first clip hit 900 s on a cold start; later clips
   took ~70 s); the shard index no longer comes from the array index.
4. **`v2_rescore.py`:** re-scores a saved run on CPU with the current rules.
   Pilot re-scored.

Regression after the fixes: positive control PASS for all 3 styles (0 false
rejections), injection results unchanged, dry run 12/12 valid.

### Pilot table (re-scored)

| model | done | s/clip | peak VRAM GB | valid | broken obj. | fit fail | camera | confirmed by CoTracker3 | projected sweep GPU-h |
|---|---|---|---|---|---|---|---|---|---|
| ltx | 12 | 4 | 15.4 | 3 | 2 | 7 | 0 | 3 | 0.3 |
| cogvideox | 12 | 144 | 25.4 | 1 | 3 | 8 | 0 | 1 | 12.1 |
| dynamicrafter | 11 (+1 timeout) | 69 | (subprocess) | 5 | 2 | 4 | 0 | 5 | 5.8 |
| wan22_ti2v_5b | 12 | 126 | 45.3 | 7 | 2 | 3 | 0 | 7 | 10.6 |
| cogvideox15_i2v | 12 | **1021** | 28.6 | 4 | 0 | 8 | 0 | 4 | **86.2** |
| wan22_i2v_a14b | 12 | 152 | 78.8 | 11 | 0 | 1 | 0 | 11 | 12.9 |
| hunyuan15_i2v | 12 | **1200** | 50.7 | 4 | 0 | 7 | 1 | 4 | **101.3** |
| ltx2 | 12 | 19 | 73.3 | 6 | 0 | 6 | 0 | 6 | 1.6 |
| cosmos2_2b | 0 | — | — | — | — | — | — | — | — |

Projected text-channel sweep: 231 GPU-h (without Cosmos).

**Cosmos failed to load:** its guardrail downloads from a second gated repo,
`nvidia/Cosmos-1.0-Guardrail` (HTTP 403 for the user's token). The user must
accept that license too (auto-approved). Its other component,
`Qwen/Qwen3Guard-Gen-0.6B`, is public.

### Preliminary pattern (12 clips per model, only 2 θ values: not a result yet)

Every valid clip fits the step 1 reading. Slide: μ̂ ≈ 1.6–1.7 for both
requested μ (0.1, 0.4), i.e. constant speed with almost no acceleration.
Projectile: |ĝ| ≤ 0.25 on all valid clips (still, or dropping at constant
speed). Bouncing ball (Wan models): ê ≈ 0.92–1.0 regardless of the requested
e. The step 5 sweep will test this properly.

### Open decision: the cost of the two slow models

CogVideoX1.5 (81 frames at 1360×768) and HunyuanVideo-1.5 (61 frames at 720p)
take 17–20 min per clip. Because the fit now stops at floor contact (~1–2 s),
most of those frames are unused. Options:
- **A:** keep the settings, ~231 GPU-h + Cosmos.
- **B (recommended):** CogVideoX1.5 at 49 frames; HunyuanVideo-1.5 via its
  official non-distilled 480p I2V checkpoint
  (`hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-480p_i2v`, confirmed on
  HF) at 33 frames. Needs a short re-pilot of those two models.

---

## Step 4 closed (2026-10-18): final settings and pilot outcome per model

All rules applied (pre-contact fit window, amendments 1–3, v2 tracker).
Results are from the pilot run at each model's FINAL settings (12 clips:
3 systems × 2 θ × 2 scene seeds).

| model | final settings | source run | s/clip | valid | 304-clip sweep GPU-h |
|---|---|---|---|---|---|
| ltx | 768×512, 25 fr @24 | pilot | 4 | 3/12 | 0.3 |
| cogvideox | 720×480, 49 fr @8 | pilot | 144 | 1/12 | 12.1 |
| dynamicrafter | 512×320, 16 fr | pilot | 69 | 5/11 | 5.8 |
| wan22_ti2v_5b | 1280×704, 49 fr @24 | pilot | 126 | 6/12 | 10.6 |
| cogvideox15_i2v | 1360×768, **81** fr @16 (native) | pilot | 1021 | 4/12 | 86.2 |
| wan22_i2v_a14b | 832×480, 49 fr @16 | pilot | 152 | 11/12 | 12.9 |
| hunyuan15_i2v | **480p** checkpoint, 848×480, 33 fr @24 | pilot_b | 116 | 8/12 | 9.8 |
| ltx2 | 768×512, 49 fr @24 | pilot | 19 | 6/12 | 1.6 |
| cosmos2_2b | 1280×704, 93 fr @16, guardrail on | pilot_b (job 426984) | ~290 | 0/12 | ~24.5 |
| **total** | | | | | **≈ 164** (+ model-load overhead per shard) |

**Cosmos**, after two fixes to device handling (guardrail `.device` bug, then
the pipeline's sorted-module device inference; both in `generators.py`):
11/11 retried clips generated without error, the guardrail blocked nothing,
and camera shift was 0 px. All 12 clips are invalid on genuine output
problems, confirmed by frame inspection: the ball teleports and swells
(bouncing ball), slides then vanishes and reappears at the top (slide), or
drifts with dark specks appearing (projectile).

**Seen in 12-clip pilots; preliminary only, to be tested in step 5:**
HunyuanVideo-1.5's projectile ĝ rises with the requested g within each scene
(5.7 → 10.2, 8.4 → 10.2), the only model so far to show this. Most other
valid clips show little or no acceleration.
