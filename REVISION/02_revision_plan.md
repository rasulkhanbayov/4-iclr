# Phase 2 — Revision plan

Date: 2026-10-15. Builds on `01_review_analysis.md`. Nothing below has been run
yet. GPU jobs will be written as SLURM scripts for you to submit.

## 1. Venue decision: Image and Vision Computing (recommended)

| | Image and Vision Computing | Pattern Recognition | Neural Networks |
|---|---|---|---|
| Scope | Computer vision and image interpretation; explicitly encourages quantitative comparison and performance evaluation | Broad pattern recognition and ML; favours new methods | Neural-network models, learning theory, computational neuroscience, applications |
| Fit for an evaluation and benchmark paper on video generators | **Strong**: tracking, motion analysis and performance evaluation are core topics | Medium: an evaluation paper must show a methodological contribution | **Weak**: reviewers will look for a neural-network contribution, and we have none |
| Impact factor (aggregators disagree; check JCR) | ~4–5, Q1 | ~7.5+, Q1 | ~6–8, Q1 |
| Length | Not confirmed (no strict limit found) | 20–35 double-spaced single-column pages incl. figures and refs; appendices excluded | Not checked in detail |

**Recommendation: Image and Vision Computing.** Its reviewers are vision
people who will value the tracking and measurement-validity work, and it states
that it wants quantitative evaluation. Pattern Recognition is the stretch
option: move there only if the decoupled-seed experiment (§4, E-B) gives a
clean, strong result on current models. Neural Networks does not fit the
contribution.

Consequences of moving to a journal:
- There is no "Datasets track". The dataset concern (K1/M2) becomes "state the
  contribution clearly", and releasing the benchmark data strengthens it.
- There is room for visual evidence and the closed-model tier (no 8-page cap).
- Format switches to Elsevier `elsarticle`, plus highlights, a data
  availability statement, CRediT roles, and an optional graphical abstract.

## 2. The new story (problem → motivation → method → validation)

- **Problem.** A user asks an image-to-video model for specific physics, e.g.
  "the ball falls under Moon gravity". Does the generated motion actually realize
  that value? Current benchmarks score whether motion *looks* physical, and
  cannot tell.
- **Why it matters.** Generators are being sold and studied as controllable
  world simulators (robotics data, simulation, education). A clip can look
  perfect while realizing the wrong parameter, and plausibility scores miss it.
- **Method.** PhysWeep is a measurement protocol: render a physical scene with a
  known parameter θ, ask the generator to realize θ, recover θ̂ from the pixels
  with tracking plus a closed-form fit, and **accept a measurement only if it
  passes validity checks**. Then report how far θ̂ moves with θ, and *what
  instead determines θ̂*: the request, the scene, or the sampling noise.
- **Validation.** A simulator positive control; artifact-injection tests that
  show the validity checks reject fragmented, duplicated or deforming objects;
  two independent trackers; a visual audit; and a released dataset so every
  number can be re-checked.
- **Findings.** These will be rewritten from the new runs. The seed claim
  survives only if the noise share stays large once the scene is held fixed.

## 3. Every verified point mapped to an action (ordered by impact)

| # | Action | Review points closed | Type |
|---|---|---|---|
| 1 | **Measurement validity layer.** Add checks beyond $R^2$: single connected object per frame, stable object area (no ballooning), minimum observed displacement, blob-vs-CoTracker3 agreement, plus artifact-injection tests (synthetic fragmentation, duplication, scaling) proving the checks catch them. Re-run on all 630 saved clips and recompute every published number. | N1, T6, F3–F5 | code + reanalysis (CPU) |
| 2 | **Fix the scenes.** Draw the physics: slope for the slide, pivot and rod for the pendulum, wall and spring coil for the spring-mass, floor for the ball. Add a second "shaded" style to test the out-of-distribution concern. Fix the Table 1 grid (F7). Rerun the positive control on the new scenes. | F2, T3 (OOD), F7 | code (CPU) |
| 3 | **Decouple the seed.** Separate `scene_seed` (renderer) from `noise_seed` (generator) in every experiment script, fully crossed with θ. Add a three-way variance decomposition (request / scene / noise) to the metrics. | N2, M4, T3 | code (CPU) |
| 4 | **Pilot jobs** on the new models: 8–10 clips each to measure time, VRAM and validity rate. | K2, M7 | GPU (small) |
| 5 | **Main sweep (E-B)** on old and new models under the decoupled design, saving every video. | N2, M4, K2, F6 | GPU (main cost) |
| 6 | **Frame-implied channel (E-C)** where θ is in the frames, on models that accept multiple frames or video. | F1 | GPU |
| 7 | **Plausibility rater upgrade (E-D):** one larger current VLM on H200, or scope the claim down to "one 7B rater". | T7 | GPU (small) or writing |
| 8 | **Closed-model tier (E-E, optional):** seed-free metrics (PRE, β, ρ, EG, validity rate) through one or two commercial APIs. SDI is reported only where an API exposes a repeatable seed. | T2, M6 | API cost |
| 9 | **Dataset release:** scenes, prompts, all generated clips, both trackers' tracks, validity labels, θ̂, and a hand-audited subset, on Hugging Face with a datasheet. | K1, M2 | packaging |
| 10 | **Figures from real frames:** new teaser with frames and θ̂ curves; scene gallery; failure-mode gallery with overlaid tracks (including the artifact cases); tracker-disagreement figure; new pipeline figure (Figure 2, your PaperBanana prompt is in `figure2_paperbanana_prompt.md`). | T1, M3, N3, K4, T5 | figures |
| 11 | **Rewrite** in `elsarticle`: new intro following §2; define every acronym at first use (RSS, FDI, SDI, AIC, ICC); move the proof to an appendix; retract the "split-default" claim unless it survives step 1; remove "it is not tracking noise"; scope VLM claims. | M1, K3, M5, T4, N4 | writing |
| 12 | Final verification: every number re-derived from new result files; compile check. | all | — |

No review point is left as "inaccurate", so there are no misreadings to defend
against. T5 was confirmed against the submitted PDF.

## 4. New experiments

### E-B: decoupled seed sweep (core)
- **Design:** θ (all in-range + the lowest and highest out-of-range value)
  × 4 scene seeds × 4 noise seeds, on projectile (7 θ, 112 clips), bouncing
  ball (6 θ, 96) and inclined slide (6 θ, 96): **304 clips per model**
  (corrected in step 3 from 336). Every clip saves its video.
- **Analysis:** variance of θ̂ split into request, scene and noise shares
  (random-effects decomposition), computed only on clips that pass validity;
  slope β and PRE as before.
- **Models (all confirmed on Hugging Face, 2026-10-15):**
  - Old (for continuity): LTX-Video, CogVideoX-5B-I2V, DynamiCrafter-512.
  - New, A100-40GB: Wan2.2-TI2V-5B, CogVideoX1.5-5B-I2V.
  - New, H200: Wan2.2-I2V-A14B, HunyuanVideo-1.5 I2V (replaces HunyuanVideo-I2V);
    optional MAGI-1 (autoregressive).
  - World model, frame-capable: Cosmos-Predict2-2B-Video2World (gated, needs
    you to accept the license on HF).
  - LTX-2 (19B, H200), added 2026-10-15.
- **GPU-hours (rough, pending step-4 pilots):** old models ~30 h total (known
  per-clip times); new models ~3–8 min/clip, so about 17–45 h each and roughly
  100–200 h for four or five new models.
- **What would change the claims:**
  - Noise share large with scene fixed → "the noise picks the physics" survives,
    now properly controlled.
  - Scene share dominates → the finding becomes "the conditioning layout picks
    the physics". Still a real result, but the seed framing goes.
  - Request share large on new models → current generators do honor the
    parameter, and the headline becomes model-dependent.
  - Most clusters fail validity → the seed finding is demoted to a caveat, and
    the paper centres on the measurement protocol plus the benchmark.

### E-C: frame-implied channel
θ is put into the frames (first plus middle or last frame, or a short
conditioning clip) on DynamiCrafter-interp, Cosmos Video2World, and a Wan
first/last-frame model if feasible. ~20–40 GPU-h.

### E-D: plausibility rater
Re-score the saved clips with a larger current VLM on H200. ~5–10 GPU-h. If it
also fails to track validity, the claim generalizes; if it succeeds, the claim
is restricted to the 7B rater.

### E-E: closed models (optional)
Seed-free tier on one or two commercial APIs. Cost depends on API pricing and
needs your API keys; skip if there's no budget.

## 5. Storage and compute

- Home is 89% full (112 GB free). Model weights (~350–450 GB for the new
  models), the HF cache and new videos go to
  `/export/hbku-research/rakh90100/physweep_revision/` (writable, 4.1 TB free).
- Queues: `gpu-A100` (`a100_hbku`) and `gpu-H200` (`h200_hbku`), as used by your
  other projects.
- Jobs will set `HF_HOME` and output paths through variables at the top of
  each script.

## 6. What to cut

- The proof sketch and the misspecification proposition move to the appendix;
  the main text keeps the statement and the intuition.
- The "split-default" section, unless it survives the validity checks.
- The long "Design gaps" and LLM-statement paragraphs move to a short
  limitations section and the journal's declarations.
- The joint (ω, ζ) pendulum null result moves to the supplement.

## 7. Decisions (2026-10-15)

1. **Journal:** Image and Vision Computing. Approved.
2. **Models:** the E-B list, **plus LTX-2** (`Lightricks/LTX-2`, 19B; bf16, fp8
   and fp4 weights; not gated; runs on H200). The user will accept the Cosmos
   license on `nvidia/Cosmos-Predict2-2B-Video2World` (gated "auto"; diffusers
   format present). Jobs that download Cosmos need an HF token on the cluster.
3. **GPU budget** of ~150–300 GPU-hours: approved.
4. **API budget (E-E): none. Closed models are dropped (2026-10-15).** The
   cost table below is kept for the record only. Open-source replacement:
   - **Two-tier protocol instead of a closed-model run.** *Tier 1 (seed-free):*
     PRE, β, ρ, EG and validity rate. It needs only "submit image + prompt,
     receive video", so it applies to any API. *Tier 2 (seed-resolved):* the
     request/scene/noise decomposition, which needs repeatable seeds. We show
     Tier 1 works without seed control by running it on the open models with a
     fresh, never-reused noise seed per clip ("API mode"), and checking that its
     numbers agree with the seeded runs.
   - **Text change for T2/M6:** drop "model-agnostic". State that Tier 1
     applies to any queryable generator, that Tier 2 needs seed access, and
     that closed models were not evaluated, for cost reasons.
   - **Use the newest open models as the "current state of the art"
     answer** to K2/M7. Checked on HF on 2026-10-15:
     **HunyuanVideo-1.5 I2V** (Dec 2025, diffusers) *replaces*
     HunyuanVideo-I2V (Mar 2025); **MAGI-1** (autoregressive, a different
     architecture family; updated Jun 2026) is added as optional.
   - **Open plausibility raters (E-D):** Qwen3-VL-30B-A3B-Instruct on H200.
     The 235B variant needs several GPUs and is skipped.

### E-E cost estimate

Seed-free design per API model: 3 systems × 7 θ × 4 scene seeds × 2 samples =
168 clips, plus about 20 pilot clips.

| Service | Price (source) | Clip length | Cost per model (~190 clips) |
|---|---|---|---|
| Veo 3.1 Fast, 720p | $0.10/s (Google's Gemini API pricing page) | 8 s | ~$150 |
| Veo 3.1 Lite, 720p | $0.05/s (same page) | 8 s | ~$75 |
| Kling 3.0, 720p, no audio | ~$0.084/s (aggregator) | 5 s | ~$80 |
| Runway Gen-4 Turbo | ~$0.05/s (aggregator) | 5 s | ~$50 |
| Veo 3.1 Standard | $0.40/s | 8 s | ~$610 (not recommended) |

**Recommended:** Veo 3.1 Fast + Kling 3.0, about **$230, or $300 with a 30%
buffer** for retries and failed generations. The cheapest meaningful option is
Runway alone (~$65 with buffer). Prices are as of Oct 2026; the Kling and
Runway figures come from aggregators and need checking on the providers' pages.
Whether each API exposes a repeatable seed is still unverified; SDI is reported
only where one does.
