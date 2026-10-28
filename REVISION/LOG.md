# REVISION log

## 2026-10-15 — Phase 1: review analysis

**Done:** split the meta-review and three reviews into 14 weakness points and
7 strengths, and checked each against the paper source, code and data. Output:
`01_review_analysis.md`.

**Verified (how):**
- The submitted version is `VERSION3/main.tex`: the reviewers' quoted phrases
  are at lines 751 and 882, and SDI/FDI appear only there.
- Seed confound: one seed drives both the renderer (`render.py:103`) and the
  generator (e.g. `e0_pilot.py:139`). A scratch script showed frame 0 is
  identical across θ and differs across seeds for all six axes.
- Tracker disagreement: recomputed per seed from
  `results/e5a_cotracker_comparison.json`; jointly gated r = −0.975
  (DynamiCrafter projectile), −0.60 (slide).
- Inspected frames of 5 clips with ffmpeg: fragmentation (DC projectile seed 1),
  duplicated object (DC slide seed 0), ballooning/splitting (LTX projectile
  seed 4). Single clean objects: DC seed 3, CogVideoX g=25 stills.
- Figure 2 label read at full resolution: "untrusted/video", not "ideo".
- Literature check on seed→motion: Go-with-the-Flow, Open-Sora 2.0, LatSearch.

**Not modified:** `VERSION3/` and all other originals are untouched. No git
commands were run. Only `REVISION/01_review_analysis.md` and this log were
created.

**Open:** submitted PDF not on disk; venue, deadline and GPU budget are needed
before Phase 2.

## 2026-10-15 — Phase 2: workspace + plan

**Done:**
- Read the submitted PDF (`submitted/2935_PhysWeep_Does_a_Video_Gen.pdf`).
  Its line numbers match the reviewers' (L412-413, L510-511). Figure 2's
  embedded raster reads "untrusted/ideo", so T5 was changed to *accurate* in
  `01_review_analysis.md`. The PNG in VERSION3 was regenerated after
  submission.
- Created the workspace by copying (originals untouched): `submitted/`
  (PDF, reviews, VERSION3 source snapshot), `paper/` (working copy),
  `code/` (physweep, experiments, metrics; VERSION3's metrics module copied as
  `physweep/metrics_v3.py` to avoid the name clash), `results_v1/` (all 134
  JSON + 630 videos + debug frames), `slurm/reference_v1/` (old jobs). The
  DynamiCrafter checkout and venv were not copied (33 GB, re-creatable).
- Compared the three journals (aggregator impact factors disagree; Pattern
  Recognition length of 20–35 pages from its guide). Recommended Image and
  Vision Computing.
- Checked compute: `/export/hbku-research/rakh90100` is writable with 4.1 TB
  free; home is 89% full. Queues gpu-A100 (`a100_hbku`) and gpu-H200
  (`h200_hbku`) are taken from the user's 3-ACL jobs.
- Confirmed the new candidate models exist on HF (Wan2.2 I2V-A14B and TI2V-5B,
  HunyuanVideo-I2V, CogVideoX1.5-5B-I2V, LTX-2, Cosmos-Predict2 Video2World,
  which is gated).
- Wrote `02_revision_plan.md` and `figure2_paperbanana_prompt.md`.

**Not done (waiting for approval):** any Phase 3 work.

## 2026-10-15 — Plan approved

**Decisions:** journal = Image and Vision Computing; add LTX-2; the user will
accept the Cosmos license; GPU budget approved. API services are pending.

**Verified:** `Lightricks/LTX-2` is not gated and has bf16/fp8/fp4 weights.
`nvidia/Cosmos-Predict2-2B-Video2World` is gated "auto" and has a
`model_index.json` (diffusers). API prices: Veo 3.1 from Google's Gemini API
pricing page; Kling and Runway from aggregators (marked as such in the plan).

## 2026-10-15 — No API budget: open-source only

**Decision:** closed models dropped. T2/M6 is now answered by a two-tier
protocol: a seed-free tier, validated in "API mode" on open models with fresh
seeds, plus a seed-resolved tier. "Model-agnostic" is removed from the text.
HunyuanVideo-1.5 I2V replaces HunyuanVideo-I2V, MAGI-1 is added as optional,
and the plausibility rater is Qwen3-VL-30B-A3B.

**Verified on HF:** `hunyuanvideo-community/HunyuanVideo-1.5-Diffusers-720p_i2v`
(diffusers, not gated), `sand-ai/MAGI-1` (not gated),
`Qwen/Qwen3-VL-30B-A3B-Instruct` (not gated).

## 2026-10-15 — Phase 3, step 1: measurement validity layer (DONE)

**Done:** wrote `code/physweep/validity.py` (single object, stable size,
static flag, tracker agreement, plus amendment 1: static is invalid for
bounce/oscillation systems), `code/experiments/v2_validity_injection.py` and
`code/experiments/v2_validity_reanalysis.py`. Report:
`results_v2/STEP1_REPORT.md`.

**Verified:**
- Injection test: artifacts pass the fit gate at median R² ≈ 1.0 with 50–540%
  error; 0 pass the new checks; clean and still clips pass 100%.
- 630 saved clips: 95 pass the old gate, 38 are valid (33 confirmed by
  CoTracker3), 50 have broken objects and 7 are static/unidentifiable.
- 5 rejections checked visually (fragments, second ball, ballooning, camera
  zoom); all correct.
- Valid clips: in-range slope ≈ 0. All 19 valid projectile clips have
  |ĝ| < 0.5; 7/9 valid DC slide clips sit at the zero-acceleration value
  tan 60°.
- Saved clips are a replication run: not bit-identical to the paper's runs,
  but per-seed means reproduce closely.

**Amendment logged:** amendment 1 was added after the first pass (after seeing
sub-pixel "bounces"); both passes are recorded in the report.

**Open:** CogVideoX projectile (Figure 1a) can't be validated without
regeneration (step 5). The headline needs rewriting (see report §5).

## 2026-10-15 — Phase 3, step 2: scenes with visible physics (DONE)

**Done:** added `style` (minimal | structured | shaded) to all five simulators
in `code/physweep/render.py`: slope wedge, pendulum mount and rod, wall with
spring and table, plus a shaded variant. Wrote
`code/experiments/v2_positive_control.py`. Exported reference frames to
`figures/refs/`. Fixed the Table 1 pendulum-ω grid in `paper/main.tex` (F7).
Report: `results_v2/STEP2_REPORT.md`.

**Verified:**
- `minimal` is bit-identical to the original renderer (5/5 simulators,
  `np.array_equal`).
- Slope geometry: the ball stays 8.9–9.05 px from the surface (radius + 1)
  across frames.
- Positive control passes for all three styles (pooled PRE_in ≈ 0.0035–0.0039,
  slope 1.0002); 0 correct clips rejected by the validity checks.
- The bouncing ball measured through the tracker has slope 1.076
  [1.003, 1.181]; reported as is.

**Open:** none for this step.

## 2026-10-15 — Phase 3, step 3: scene seed / noise seed separated (DONE)

**Done:** new harness modules `code/physweep/{design,conditioning,prompts,decomposition}.py`
and `code/experiments/v2_design_selftest.py`. Report:
`results_v2/STEP3_REPORT.md`. The v1 scripts are left unchanged (a deviation
from the plan's wording, made for reproducibility).

**Verified:**
- Design: 304 clips per model; seed ranges disjoint; API-mode seeds unique.
- Conditioning depends on the scene seed only; the frame channel varies with θ.
- Decomposition: 119/120 synthetic runs within ±0.10 of the realized true
  shares; 0/40 false positives at p < 0.01; v1 coupled design flagged as
  confounded.

**Corrections, made after seeing failures:**
1. Self-test criteria changed from fixed thresholds to the realized true
   shares and p-values.
2. Chance correction changed from the shuffled-null mean (biased: 0.89 vs
   1.00) to adjusted-R²/ω² style.
3. Plan corrected: 304 clips per model, not 336.

**Open:** none for this step.

## 2026-10-15 — Phase 3, step 4: pilot jobs written (waiting for user to submit)

**Done:** `code/physweep/{fits,generators}.py`,
`code/experiments/{v2_run,v2_pilot_summary,v2_check_env}.py`, two
requirements files, and `slurm/v2/{cluster.env,00_setup_envs.sh,01_download_models.sh,10_pilot_a100.sh,11_pilot_h200.sh}`.
Report: `results_v2/STEP4_REPORT.md`.

**Verified (CPU):** fits reproduce the v1 refit on 630/630 trajectories;
simulator dry run 12/12 valid with θ within 2%; resume and API mode work;
env checker works; bash syntax OK.
**Checked against sources, not guessed:** pipeline classes and `__call__`
signatures from installed diffusers 0.39.0; each repo's `model_index.json`;
LTX repo file lists (allow-lists skip ~270 GB of unused checkpoints);
cosmos-guardrail requirements on PyPI (transformers ≥ 5, hence a separate env).

**New finding F8:** v1 fitted CogVideoX with dt = 1/24 although it plays at
8 fps (ĝ 9× too large); added to `01_review_analysis.md`.

**Decisions:** MAGI-1 dropped (no diffusers pipeline); the Cosmos guardrail
is kept on (license).

**Open:** nothing has run on a GPU yet. The user runs setup → download →
pilots; then `v2_pilot_summary.py`.

## 2026-10-15 — HF token wired in

- The user accepted the Cosmos license and put `HF_TOKEN` in `4-ICLR/.env`.
- Verified without printing it: the token is valid (user rasulkhanbayov,
  fine-grained); Cosmos gated files return HTTP 200 with it and 401 without.
- `slurm/v2/cluster.env` now reads ONLY the `HF_TOKEN` line from `.env`. It
  does not source the file, because `.env` also sets `HF_HOME` to the old v1
  cache in the 89% full home dir. Checked: jobs get a 37-char token and
  `HF_HOME` on `/export/hbku-research`.
- `.env` permissions changed 644 → 600 (was readable by all users on the
  shared filesystem); `.env` added to `4-ICLR/.gitignore`.

## 2026-10-16 — Phase 3, step 4: pilot results checked

**Ran (user):** env setup, download (8/8 repos, 455 GB), pilot arrays
425708 (A100 ×5) and 425709 (H200 ×4). 8/9 models produced 12 clips each.
Cosmos failed: its guardrail needs a second gated repo,
`nvidia/Cosmos-1.0-Guardrail` (403; verified with curl).

**Found by inspecting frames and stored tracks, then fixed (post-pilot, logged):**
1. Fit window: landing and resting frames corrupted fits (Wan2.2-A14B
   ĝ −0.92 → ~0 after the fix). Projectile and slide now fit pre-contact only.
2. Amendment 2: `invalid_camera` (HunyuanVideo clip with the floor line
   drifting 17–25 px). Added a camera-drift artifact to the injection test
   (65/65 rejected).
3. Runner: retry errored clips; DynamiCrafter timeout 1800 s; shard index fix.
4. New `v2_rescore.py`; the pilot was re-scored.

**Verified after the fixes:** positive control PASS ×3 styles, 0 false
rejections; injection unchanged; dry run 12/12.

**Open (user):** (1) accept the `nvidia/Cosmos-1.0-Guardrail` license; (2)
choose cost option A or B for CogVideoX1.5 / HunyuanVideo-1.5 (STEP4_REPORT.md).

## 2026-10-16 — Option B chosen; Cosmos guardrail license accepted

**Verified:** `nvidia/Cosmos-1.0-Guardrail` now returns HTTP 200 with the
user's token (was 403). The 480p HunyuanVideo-1.5 I2V repo uses the same
pipeline class and transformer architecture (54 layers) as 720p; only
target_size differs (640 vs 960). The pipeline sizes its output from the input
aspect ratio and crops, so an 848×480 canvas is used.

**Changed:** `generators.py` sets cogvideox15_i2v to 49 frames (was 81), and
hunyuan15_i2v to the 480p_i2v repo, 848×480, 33 frames (was 720p, 61).
`01_download_models.sh` lists the 480p repo.
**New jobs:** `02_download_extra.sh` (480p Hunyuan, Cosmos guardrail files,
Qwen3Guard), `12_repilot_a100.sh` (CogVideoX1.5), and `13_repilot_h200.sh`
(Hunyuan 480p, Cosmos); all write to run `pilot_b`.

**Verified (CPU):** canvas round trip at 848×480 and 1360×768: projectile and
slide within 1–3%; bouncing ball ~10% low (0.63–0.64 vs 0.70), the known
few-bounce precision floor; all labelled valid.

## 2026-10-17 — Option-B re-pilot checked (jobs 426446-426448)

**Results (re-scored with the current rules):**
- HunyuanVideo-1.5 480p/33 frames: 116 s/clip (was 1200), 8/12 valid (was 4).
  All 4 projectile clips valid and confirmed (ĝ 5.7/8.4 at g = 5; 10.2/10.2 at
  g = 15): the first within-scene response to the request seen so far.
  Preliminary (n = 4).
- CogVideoX1.5 at 49 frames: 493 s/clip (was 1021), but 1/12 valid (was 4/12
  at 81). Frames show the ball sliding, growing, then disappearing, so the
  shortened clip changes the model's output. Recommend reverting to its native
  81 frames.
- Cosmos: loaded with the guardrail, but all 12 clips errored
  (`_execution_device`).

**Fixed (post-pilot, logged):**
1. cosmos-guardrail 0.3.2 bug: CosmosSafetyChecker.device reads `.device`
   from plain nn.Module wrappers. Reproduced on CPU, then fixed by answering
   device/dtype from parameters (`generators._fix_cosmos_guardrail_device`);
   the guardrail still runs (verified). New job `14_repilot_cosmos.sh`.
2. Amendment 3: HunyuanVideo draws contact shadows inside the floor strip
   (verified: thin dark components in rows 235–243 under the ball), which
   counted as a second object. The object mask and the v2 blob tracker
   (`centroid_track_above`) now ignore rows at or below the floor line.
   Injection test gained a "shadow" case: 65/65 valid, median error
   0.1–3.5%. Positive control unchanged (PASS ×3); all artifacts still rejected.

**Guardrail prompt check (CPU, the exact text guardrail):** 1/19 design
prompts is blocked — g = 25 ("...violent rapid acceleration downward"), a
false positive: the blocklist fuzzy-matched "violet". Needs a user decision.

**Open (user):** (1) CogVideoX1.5 back to 81 frames? (2) The g = 25 prompt for
Cosmos: reword for all models, or record the cell as blocked? (3) Submit
`14_repilot_cosmos.sh`.

## 2026-10-17 — User decisions applied

1. CogVideoX1.5 reverted to its native 81 frames (`generators.py`). Projected
   main sweep ≈ 140 GPU-h + Cosmos.
2. g > 16 gravity prompt reworded for ALL models: "violent rapid acceleration
   downward" → "very rapid acceleration downward" (`prompts.py`; the only v1
   wording change). Verified on CPU with the exact Cosmos text guardrail:
   0/57 prompts blocked (default, terse and verbose variants).
3. The user is submitting `14_repilot_cosmos.sh`.

## 2026-10-17 — Cosmos re-pilot (job 426941): second device bug, fixed

Clip 1 generated (317 s) with the guardrail running, so the first fix works.
Clips 2–12 failed: "index is on cpu, ... cuda:0" in the T5 text encoder.
Cause, checked in the installed source: `pipeline_cosmos2_video2world.py`
moves the safety checker to CPU after every check (lines 615, 790), and
`DiffusionPipeline.device` returns the first module of the SORTED component
names (`_get_signature_keys` returns `sorted(...)`), which is
`safety_checker`. So after the first call, inputs were created on CPU.
Fix: `generators._pin_execution_device` pins the Cosmos pipeline's execution
device to the GPU it was loaded on (single GPU, no offload); the guardrail is
untouched. Mechanism tested on CPU with a toy pipeline. Needs one more
re-pilot: `14_repilot_cosmos.sh` (resumes; retries the 11 errored clips).

## 2026-10-18 — Phase 3, step 4 DONE (Cosmos re-pilot job 426984)

Cosmos: 11/11 retried clips generated (~290 s/clip), no errors, guardrail on
and blocking nothing, camera shift 0. All 12 invalid on genuine output
problems (teleporting/swelling ball, vanishing slide ball, drifting ball with
specks), checked by frame inspection. Final per-model settings and costs are
in STEP4_REPORT.md: ≈ 164 GPU-h for the 304-clip text-channel sweep of all
9 models. Next: step 5 (main sweep jobs).

## 2026-10-18 — Phase 3, step 5: main sweep jobs written (waiting for user to submit)

**Done:** `physweep/runio.py` (per-shard files), `experiments/v2_analyze.py`,
task files + `20_sweep_{a100,h200}.sh` + `submit_sweep.sh` + `30_analyze.sh`.
Report: `results_v2/STEP5_REPORT.md`.
**Verified (CPU):** sharded dry run (3 concurrent shards, 304 records, resume
OK); task parsing; shards cover each design exactly once (3800 clips);
analysis on the simulator gives β ≈ 1 and request share 1.00, and API mode
matches the seeded run.
**Estimate:** ≈ 190 GPU-h (main 164 + API 27); < 15 GB disk.
**Open:** the user submits `submit_sweep.sh`; afterwards `30_analyze.sh`.

## 2026-10-21 — Phase 3, step 5 DONE: main sweep results

**Ran (user):** `submit_sweep.sh`: main 9 × 304 and API 7 × 152 clips, 0
errors. Measured 192.5 GPU-h.
**Done (me):** rescored all 3800 clips on CPU (16 parallel processes); ran
`v2_analyze.py` (+ the new `--confirmed-only` option); frame-checked the
extreme valid values (real behaviours: decelerating falls, energy-gaining
bounces).
**Headline:** no model faithful in-range (β CI ∋ 0 in 24/24 pairs). Noise
share significant in 14/22 pairs, scene in 6/22, request in 4/22; the same
picture on confirmed-only clips. API vs seeded β CIs overlap 16/16. Details
in `results_v2/STEP5_REPORT.md`.
**Next:** step 6, the frame-implied channel (E-C).

## 2026-10-21 — Phase 3, step 6: frame channel written (pilot not yet run)

**Done:** `conditioning.py` (neutral prompts, pair/prefix modes,
model-rate prefix rendering, `prefix_clip_frames`); `generators.py`
(per-model frame settings, `LTX2ConditionPipeline` conditions, simulator
pair/prefix stand-ins); `v2_run.py` (key-interval dt, prefix exclusion,
`key_frame_err_px`); `v2_rescore.py` (uses the stored dt and n_given); sweep
workers accept extra arguments; pilot task files. Report:
`results_v2/STEP6_REPORT.md`.
**Design decision (mine, stated in the report):** neutral prompt in the frame
channel, so θ enters only through the frames.
**Verified (CPU):** text, pair and prefix dry runs all 12/12 valid
(projectile and slide ≤ 3% error, ball within its known floor); 2 timing
bugs caught and fixed before any GPU run.
**Open:** the user submits the frame-channel pilot.

## 2026-10-28 — Pause for CVPR: storage plan, provenance, archive, restore kit

**User decisions:** pause with the step 6 pilot unfinished (it was never submitted); HF archive repo
private for now. No deletions, no upload, no git commands this session.
**Done:**
- Inventory of both filesystems: `STORAGE_PLAN.md` (hbku-research 96% full; ~579 GiB of this project
  can go: HF cache 546G, envs 22G, runs 10.6G; home 45G: DynamiCrafter 34G, v1 env 11G). Other projects
  only measured (fwf_data 590G, somw 288G, fwf_ckpts 127G).
- `code/experiments/reproduce_numbers.py` + `PROVENANCE.md` (generated): 622 numbers from `paper/main.tex`,
  `paper/appendix.tex` and the six step reports, each recomputed from archived files. 582 match,
  12 MISMATCH, 6 superseded, 11 qualitative, 9 unarchived, 2 external. Recreated the unsaved VERSION3
  Tier-0 analyses inside it (SDI, Holm, label-permutation null with rng seed 0, TOST, GPU-hours) and the
  seeded-vs-API valid-rate test (Fisher exact; the original test was not saved, it gives 5/21 as reported).
- Mismatches found (none changes a conclusion): main.tex's three plausibility correlations are attached
  to the wrong models (data: LTX 0.019, DC -0.164, CogVideoX 0.075); CogVideoX's scores are not "1 or 5"
  (11 clips scored 3); dispersion range 0.03–0.13 excludes the paper's own ±0.2; "μ̂≈1.80 across the whole
  grid" holds in-range only; appendix still has the old ω grid {0.5,1,8,12}; VLM time 0.17 h not 0.3 h;
  STEP1 46/65 → 45/65 (injection re-run for amendment 3) and 360 → 345; STEP5 label changes 0–11, Hunyuan
  median at g=25 3.65.
- Pinned every model: `generators.REVISIONS` (12 repos, each = the only cached snapshot = refs/main),
  passed as `revision=` to `from_pretrained`; `v2_run.py` records it in run_meta.
- `env/`: conda + pip lock files of physweep2, physweep2-cosmos, dynamicrafter_venv and the v1 env;
  `hf_snapshots.json` (commit + every file, size, blob id per repo); `weights_sha256.txt`; DynamiCrafter
  commit 859021927d8e and its patched `inference.py` (3 lines vs upstream, checked against GitHub).
- Copied the step 4–6 CPU dry runs from the session scratchpad to `results_v2/dryruns/` (they were only
  in /tmp); froze the v1 VLM-scoring file times in `provenance/v1_file_times.json`.
- Archive tooling `archive/` (layout, upload with `--upload` only, data restore, weights restore),
  `restore.sh`, `RESTORE.md`, `RESUME.md`, `archive/dataset_card.md` (license table from a fetched check:
  HunyuanVideo-1.5 bars showing outputs in EU/UK/KR; LTX-2 revenue clause unclear; DynamiCrafter weight
  repos carry Apache-2.0). START HERE + number rule added at the top of `CLAUDE.md`.
**Verified:**
- DynamiCrafter checkpoints' sha256 = HF LFS oids at the pinned commits; all 12 HF snapshots verify
  against the recorder; all three lock files resolve in a pip dry run (66/66, 84/84, 87/87).
- Staging build (symlinks, no upload): 5,574 files, 9.47 GB, manifest 12 min; snapshot tarball has no
  .env/external/results/caches.
- Restore test from staging into scratch (sample: all small files + LTX-2's 304 main-run videos): 1,945
  files sha256-verified, re-run skips all; `v2_rescore.py` on the restored videos gives a byte-identical
  `clips_rescored.jsonl`; `v2_analyze.py` on restored data byte-identical (4 files); the full number check
  on restored data gives an identical ledger (622 entries, same input hashes), also in a minimal
  conda helper env (11 s).
- Found and fixed while testing: system python3 has no ensurepip, so the restore uses conda envs; the
  old dynamicrafter_venv depends on the v1 env's Python (deleting one breaks the other).
**Not done (needs the user):** git commit/push; the HF upload (`archive/upload_to_hf.py --upload`), its
full-download verification, and every deletion group in `STORAGE_PLAN.md`.
