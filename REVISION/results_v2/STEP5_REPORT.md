# Step 5 — Main sweep (2026-10-18): jobs written and dry-run tested, not yet submitted

## What runs

| run | design | models | clips |
|---|---|---|---|
| `main_text` | crossed: θ × 4 scene seeds × 4 noise seeds; projectile 7 θ, bouncing ball 6, slide 6; structured scenes; text channel | all 9 | 9 × 304 = 2736 |
| `api_text` | "API mode": θ × 4 scene seeds × 2 samples, a fresh noise seed per clip | 7 (not CogVideoX1.5, Cosmos) | 7 × 152 = 1064 |

Every clip saves its raw video; both trackers run; validity labels are
applied at generation time and again by the rescore job.

## Jobs

| file | purpose |
|---|---|
| `slurm/v2/main_a100.tasks`, `main_h200.tasks`, `api_a100.tasks`, `api_h200.tasks` | one line per job: run, model, mode, noise samples, shard |
| `slurm/v2/20_sweep_a100.sh`, `20_sweep_h200.sh` | array workers (A100: 16 h limit; H200: 12 h) |
| `slurm/v2/submit_sweep.sh` | submits everything (or `main` / `api` only) with the right array sizes |
| `slurm/v2/30_analyze.sh` | CPU: rescore both runs, summary, analysis + seeded-vs-API comparison |

Shards (each sized to ≤ ~11 h at pilot speed): A100: ltx 1, cogvideox 2,
dynamicrafter 2, wan22_ti2v_5b 2, cogvideox15_i2v 8 (≈ 10.8 h each); H200:
wan22_i2v_a14b 2, hunyuan15_i2v 2, ltx2 1, cosmos2_2b 4.

Estimated GPU time: main ≈ 164 h + API mode ≈ 27 h ≈ **190 GPU-h**, plus
~5 min model load per shard. Disk: < 15 GB of videos (Cosmos ≈ 21 MB/clip,
others < 3 MB).

## Code changes for the sweep

- `physweep/runio.py` (new): each shard writes `clips_shard<i>of<n>.jsonl`;
  readers merge all of a model's files, and a successful record is never
  overwritten by a later error. Reason: several shards of one model running at
  once must not append to the same file on NFS.
- `v2_run.py`, `v2_rescore.py`, `v2_pilot_summary.py` switched to it (old
  pilot `clips.jsonl` files are still read).
- `experiments/v2_analyze.py` (new): per model × system, label counts; on
  valid clips β (in-range) with a NaN-safe bootstrap CI, Spearman ρ, PRE
  in/out, EG; the request/scene/noise decomposition with chance correction
  and permutation p-values; a seeded-vs-API table for the seed-free tier.

## Verified (CPU dry run with the simulator model)

- 3 concurrent shards wrote 304 records with no collision; resubmitting a
  shard skips everything (304 already done).
- Every task line parses as intended, and each model's shards cover its
  design exactly once (3800 clips in total).
- Analysis of the simulator (perfectly faithful by construction): β =
  1.00–1.03, request share 1.00 (p = 0.002), scene and noise shares 0.00. API
  mode matches the seeded run (same valid rate, overlapping β CIs, same ρ).
  Bouncing ball valid 80/96 is the known e = 0.2 floor (too few bounces).

---

## Results (2026-10-21): sweep complete, rescored, analyzed

**Completion:** `main_text` 9 × 304/304 clips, `api_text` 7 × 152/152; 0
errors, no resubmits. Measured compute: **192.5 GPU-h** (generation + model
load) against the 190 estimate. Rescoring (16 parallel CPU processes)
changed only 1–11 labels per model (in-memory frames vs saved mp4).
Full tables: `results_v2/main_text_analysis.md`; confirmed-only check:
`results_v2/main_text_confirmed_analysis.md`.

**Validity (main run):** 1007 / 2736 clips valid (37%), 973 of them confirmed
by CoTracker3. By model: LTX-2 179, Wan2.2-A14B 170, HunyuanVideo-1.5 161,
Wan2.2-5B 119, DynamiCrafter 103, LTX-Video 86, CogVideoX 69, Cosmos 67,
CogVideoX1.5 53.

**Main findings (valid clips; all also hold on confirmed-only clips):**
1. **No model follows the requested value in-range.** The β 95% CI includes 0
   in 24/24 estimable model × system pairs (22/22 confirmed-only) and
   excludes 1 (faithful) in 19/24.
2. **What drives the realized value, with scene and noise separated:**
   noise share significant (p < 0.01) in 14/22 pairs (16/21 confirmed-only);
   scene share in 6/22 (5/21), mostly the older models (LTX-Video,
   DynamiCrafter, CogVideoX); request share in only 4/22 (the same 4 in both
   analyses): HunyuanVideo-1.5 projectile and slide, CogVideoX1.5 projectile,
   Wan2.2-A14B bouncing ball. **The v1 "seed" claim survives in a corrected
   form: it is the sampling noise, not the scene, for most models.**
3. **HunyuanVideo-1.5 partly responds to the request:** median ĝ 1.1 for the
   "Moon" request (1.6), rising from ~6–7 at g = 5–9.8 to ~9.4 at 12–15, then
   3.7 at g = 25; Spearman ρ 0.47; in-range β 0.08 [−0.30, 0.37] (noisy).
   Wan2.2-A14B's request share comes only from the low out-of-range e = 0.2
   (ê 0.82 vs 0.96–0.99 elsewhere).
4. **Physically impossible but real behaviours appear among valid clips**
   (frame-checked): decelerating "ease-out" falls (Wan2.2-A14B, ĝ = −14,
   both trackers agree) and energy-gaining bounces (HunyuanVideo, ê ≈ 3.5–4.8,
   trackers disagree on the size).

**Seed-free tier (seeded vs API mode, 7 models):** β CIs overlap in 16/16
pairs, so the faithfulness conclusion does not depend on seed control. Valid
rates differ at p < 0.01 in 5/21 pairs. This is expected if the noise seed
drives the output: 4 noise seeds give a noisy validity estimate, while API
mode samples ~50 seeds. Lesson for the protocol: estimate validity rates
from many fresh seeds.

**Caveats to state in the paper:** bootstrap is over clips (not clustered by
seed); shares are relative to each pair's own total variance, which is
small where the ball barely moves (e.g. slides at μ̂ ≈ tan 60°); with 4
levels per factor the scene/noise split has the ±0.05–0.14 accuracy found in
step 3.
