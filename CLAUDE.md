# PhysWeep — ICLR submission tracker

This file is the persistent memory for this project. Read it fully at the start
of every session before doing anything else. Update it immediately after any
experiment, decision, or environment change — not at the end of a session.

## 0. Current state / next action

**Status as of 2026-07-04:** Instance verified, paper bundle read, metrics
smoke test PASSED. Git repo pushed to `https://github.com/rasulkhanbayov/4-iclr`
(auth: paste a GitHub PAT when asked, used one-off via `-c http.extraheader`,
never persisted to disk — see git log for the pattern). Python env built in
`/workspace/4-iclr/.venv` (torch cu128 + diffusers stack, see Section 6).

**The rendering engine now exists** (it did not before this session):
`physweep/render.py` (6 sweep axes across 5 systems) + `physweep/track.py`
(blob-centroid tracker + the pixel<->physics unit conversion) +
`physweep/configs/systems.yaml` (exact grids). Full render -> track -> fit
pipeline validated on GROUND-TRUTH synthetic trajectories (no generator
involved) for every system — this is essentially E6's method already proven
out per-system; E6 proper still needs to be run as a first-class logged
experiment (aggregate PRE/slope/R^2 with bootstrap CIs across all systems and
seeds, written to Section 5) before it counts as done. See Section 2 for
per-system validated error rates, three deliberate grid/setup deviations from
the paper's illustrative draft (all forced by physical/timing constraints,
documented with rationale), and two expected (non-bug) low-fidelity regimes.
Two fitters were added to `physweep_metrics.py` that the paper's system table
requires but the shipped code was missing (`fit_zeta_from_envelope`,
`fit_friction_from_slide`) — same style as the existing fitters, original
smoke test still passes unchanged.

**E6 (negative control) is now DONE and PASSED** (2026-07-04): PRE(in)=0.0031,
slope(in)=1.0001, mean fit R^2=0.986 pooled across all 6 systems, 203
measurements. See Section 5 for full per-system breakdown. One more bug was
found and fixed along the way: `fit_omega_from_crossings`'s R^2 (against an
undamped sine) badly underrated real damped-oscillation fits; added
`damped_sine_r2()` to `physweep_metrics.py` as the correct gate for that
system.

**E0 (pilot gate) is now DONE** (2026-07-04). **Decision: REFRAME.** LTX-Video
does not detectably honor the conditioned gravity in this setup — slope(in)
95% CI = [-1.14, 0.00] (includes 0), most clips failed the fit-quality gate
(80% dropped), and visual inspection shows the ball staying essentially
stationary near the ground regardless of the stated gravity, rather than
falling. This was reached only after ruling out two pipeline bugs as the
cause (see Section 5 for the full account) — the null result looks like a
genuine behavioral finding, not an artifact, but read the caveats in Section
5 before treating it as final (single model, single conditioning-channel
design, small resolution relative to native, C2 not C1).

**Next action (per the runbook's own guidance for this outcome):** reframe
the story to "open generators do not honor conditioned dynamics" for this
setup, OR try to strengthen the conditioning before concluding — e.g. retry
with the ball positioned clearly mid-air (not near the ground, which the
model may read as "at rest") before fully committing to the reframe. This is
a real decision point worth discussing with the user before proceeding to
E1-E9 under either framing. Do not skip ahead in the experiment order in
Section 3 until this is resolved. Do not write any number into the paper
that was not produced by an actual run recorded in Section 5.

---

## 1. The paper in one look

**Claim:** most video-physics benchmarks measure *plausibility* ("does this
look physical") which a model can satisfy while encoding the wrong physical
parameter. PhysWeep instead measures *parameter faithfulness*: condition a
frozen, off-the-shelf image-to-video generator on a known physical parameter
theta (e.g. gravity g), generate a continuation, recover theta_hat from the
generated pixels with a label-free tracker + closed-form physics fit, and
measure recovery error in-range and out-of-range (extrapolation).

**Contributions:**
1. Reframing: plausibility vs. parameter faithfulness as distinct axes.
2. Metrics: PRE (Parameter Recovery Error), faithfulness slope, Spearman rho,
   Extrapolation Gap (EG), and two failure-form indices — PRI (H1, global
   prior reversion) vs CBI (H2, case-based clamp to range edge) — with a
   model-selection rule (AIC + leave-one-out R^2) to adjudicate between them.
3. A controllable synthetic suite (5 systems, closed-form ground truth,
   label-free) + a controllability audit of models that *claim* physics
   control.
4. A protocol with a falsifiable, pre-committed reading of every possible
   outcome (see Section 8 of the paper / "reading outcomes honestly" below).

**Delta over closest work:** Kang et al. 2025 and "The Invisible Hand of
Physics" (2606.05328) study OOD failure on trained-from-scratch models or via
internal probes; PhysWeep probes *frozen* black-box generators, sweeps a
*continuous* parameter, and *adjudicates the failure mechanism* (H1 vs H2).
VBench-2.0 and other plausibility benchmarks score fixed clips via VLM/QA
proxies; PhysWeep sweeps a known control and measures exact recovery error.

**All results in the paper are currently `[RESULT PLACEHOLDER]`.** The paper
text, proof sketch (Appendix B), and citations are AI-drafted and must be
independently verified by the human authors before submission (see Section 7).

---

## 2. The five systems (ground truth, closed-form recovery)

**Implemented and validated end-to-end** (render -> blob-track -> fit,
ground-truth path, no generator involved yet) as of 2026-07-04. Code:
`physweep/render.py` (simulator), `physweep/track.py` (blob tracker + the
pixel-to-physics unit conversion), `physweep/configs/systems.yaml` (exact
grids, actually used — supersedes the illustrative table in the paper draft).

| System | Control theta | Recovered via | In-range grid | Out-of-range grid | Validated rel. error |
|---|---|---|---|---|---|
| Projectile | gravity g | parabola curvature | {5,7,9.8,12,15} | {1.6,3,20,25} | <0.15% |
| Damped pendulum | angular freq omega | zero-crossing period | {2,3,4,5} | {8,12} (see deviation) | <0.6% |
| Damped pendulum | damping zeta | envelope decay | {0.02,0.05,0.1} | {0.3,0.6,0.9} | <6% in-range; out-of-range often fit-gated (expected, see below) |
| Bouncing ball | restitution e | bounce-height ratio | {0.6,0.7,0.8,0.9} | {0.2,0.35,0.97} | <1.5% for e>=0.6; up to ~23% for e<=0.35 (few/small bounces, see below) |
| Spring–mass | stiffness k | oscillation period (k=m*omega_n^2) | {20,40,60,80} | {5,10,200,400} | <0.03% |
| Inclined slide | friction mu | accel. along slope | {0.1,0.2,0.3,0.4} | {0.01,0.7,1.0} | <2% |

**Three deliberate deviations from the paper's illustrative draft grids/setup
(all made 2026-07-04, all forced by physical/timing constraints, not
preference — see git history for the exact commit):**

1. **Pendulum omega out-of-range dropped {0.5, 1}.** Their oscillation
   periods (12.6s, 6.3s) exceed any realistic I2V generator clip length, and
   `fit_omega_from_crossings` needs >=2 full periods (>=2 upward zero
   crossings) to return a value at all — no clip length is both realistic
   and long enough. Kept {8, 12} only for out-of-range.
2. **Pendulum-omega and spring-mass clips extended to 180 frames (7.5s @
   24fps)**, not the base 24 frames (1s), so the lowest omega/k in each grid
   (omega=2, k=5) still completes >=2 full periods. All other systems keep
   the base T=24 spec.
3. **Inclined slide incline angle raised from an assumed 30 deg to 60 deg.**
   At 30 deg, static friction stalls all motion once mu >= tan(30)=0.577 —
   which is inside the out-of-range grid (0.7, 1.0), giving zero displacement
   and zero signal to recover mu from. 60 deg (tan=1.73) keeps the object
   sliding at every grid point including mu=1.0.

**Two expected (not bugs) low-fidelity regimes, to report honestly rather than
force a clean number:**
- **Pendulum zeta >= ~0.3** damps out within 1-2 oscillations; envelope-decay
  fit R^2 drops from ~1.0 (in-range) to 0.2-0.8 (out-of-range), and zeta=0.9
  sometimes has too few peaks to fit at all. This is genuine heavily-damped
  physics (it barely oscillates), not a pipeline defect. Gate on fit R^2 per
  the runbook's non-physical-generation-rate mechanism; report the gated rate
  as a finding for this axis.
- **Bouncing ball e <= 0.35** loses most of its energy in 1-2 bounces, so
  `fit_restitution_from_bounces`'s sqrt-ratio estimator has only 2-4 small,
  closely-spaced peaks to work from — ground-truth relative error is ~12-23%
  even with zero tracker noise, vs <1.5% for e>=0.6. This is a real precision
  floor of the estimator at low restitution within a 24-frame clip, not a
  bug; note it when reporting E1/E4 results for this system.

Added two fitters missing from the original `physweep_metrics.py` (needed for
pendulum-zeta and inclined-slide, which the paper's system table requires but
the shipped code didn't implement): `fit_zeta_from_envelope` and
`fit_friction_from_slide` / `friction_from_acceleration`. Same style/contract
as the existing fitters (numpy-only, return `(theta_hat, r2)`). The original
smoke test in `physweep_metrics.py` still passes unchanged.

Rendering: 256x256, single high-contrast disk (radius 8px), plain background,
fixed ground line — matches the paper's Appendix rendering spec exactly
except for the two clip-length overrides above.

**Two conditioning channels** (treat as a controlled axis, ablated in E8):
- **C1 frame-implied**: multiple/first+last frames imply theta; isolates dynamics.
- **C2 text-specified**: one image + text naming the regime (e.g. "on the Moon").

---

## 3. Experiment order (DO NOT REORDER)

```
E6 (negative control) + E0 (pilot gate)   <- HARD GATE, run first, together
        |
        v
E1 (faithfulness curve, in-range)
        |
        v
E2 (extrapolation + prior reversion)
        |
        v
E3 (plausibility-measurement gap)
        |
        v
E4 (generality across systems)
        |
        v
E7 (failure-mechanism adjudication: H1 vs H2)
        |
        v
E5 (robustness / ablations, full set a-f)
        |
        v
E8 (conditioning-channel ablation: C1 vs C2)
        |
        v
E9 (controllability audit on a model claiming physics control)
        |
        v
E10 (multi-parameter, OPTIONAL)
```

Rationale for the order: E6/E0 validate the measurement pipeline itself and
check the central premise cheaply before spending GPU time on the full sweep.
Everything after builds on E1's baseline curve. E5/E8 are robustness checks
that matter most once there's a real effect (from E1-E4/E7) to defend.

---

## 4. Gate conditions and flag-back triggers

**E6 — negative control.** Feed ground-truth simulator video (not a model)
through the identical tracker + fitter pipeline used for real models.
- Pass: PRE ≈ 0, slope ≈ 1, fit R² ≈ 1 for every system.
- **Fail → STOP. Fix the measurement pipeline. Do not run any generator
  until this passes.** A failure here means the tracker or fitter is broken,
  not that any video model is broken.

**E0 — pilot / decision gate.** Projectile only, LTX-Video only, 5 in-range +
3 out-of-range g values, 5 seeds each. Compute faithfulness slope beta with a
bootstrap CI.
- beta CI excludes 0 → proceed to the full study (main storyline: faithful
  in-range, investigate out-of-range).
- beta CI includes 0 → **reframe.** The story becomes "open generators do not
  honor conditioned dynamics." This is still publishable (see Section 8) but
  changes everything downstream — do not force the original framing.

**Other flag-back triggers (stop and reconsider, do not paper over):**
- Fit R² low on many generations → objects morph/teleport; report the
  non-physical rate as a finding, gate those out of PRE, do not force a fit.
- Estimated theta0 not near the physically typical value → the "reverts to
  memorized prior" interpretation may be wrong; describe what is actually
  observed instead.
- Results differ wildly across models → report per-model, do not average away.
- If neither H1 nor H2 fits in E7 → report the observed behavior, do not
  force a mechanism label.

**The framing follows the data, always.** See "reading outcomes honestly"
in Section 8 below before writing any interpretation into the paper.

---

## 5. Results log

Update this section immediately after each experiment completes — real
numbers only, with bootstrap CIs, and the date. Never estimate or fabricate a
value. If an experiment is blocked or partially run, say so explicitly.

### Smoke test (metrics pipeline self-check, not a scientific result)
- **Date:** 2026-07-04
- **Command:** `python3 physweep_metrics.py`
- **Status:** PASS
- Fitters: gravity R²=1.0000, omega R²=1.0000, restitution R²=1.0000 (all
  recovered values matched true values to displayed precision).
- Metrics on synthetic faithful-then-reverting generator: slope=0.999,
  Spearman rho=0.983, PRE(in)=0.0128, PRE(out)=0.2730, EG=0.2602,
  PRI=0.439 (alpha=0.561, theta0_est=9.20).
- Mechanism selection on synthetic H1-generated data: correctly selected H1
  (dAIC=-113.87, CBI=0.000).
- Bootstrap: slope 95% CI [0.985, 1.015]; PRE(out)-PRE(in)=0.2602
  [0.2423, 0.2770], one-sided p=0.000.
- **Conclusion:** the metrics/fitter code is verified correct. This says
  nothing about any real video model — no GPU work has occurred yet.

### E6 — Negative control
- **Status:** PASS
- **Date:** 2026-07-04
- **Command:** `.venv/bin/python experiments/e6_negative_control.py`
  (writes `results/e6_negative_control.json`)
- **Method:** ground-truth simulator continuations (physweep/render.py) run
  through the full tracker (physweep/track.py, blob centroiding) + fitter
  (physweep_metrics.py) pipeline, for all 6 sweep axes, both in-range and
  out-of-range grids, m=5 seeds per grid point (203 total measurements).
  Fit-quality gate R^2>=0.8 per the runbook.
- **Overall (pooled across all systems):** PRE(in)=0.0031 [0.0019, 0.0045],
  slope(in)=1.0001 [1.00008, 1.00023], PRE(out)=0.0060 [0.0031, 0.0095],
  mean fit R^2=0.986, fit-quality-dropped rate=1.5% (mostly heavily-damped
  pendulum-zeta cases, expected per Section 2).
- **Per-system PRE(in)/slope(in)/R^2:** projectile 0.0006/1.000/1.000;
  pendulum_omega 0.0014/1.000/0.9996; pendulum_zeta 0.0007/1.004/0.916;
  bouncing_ball 0.0147/1.151/0.964; spring_mass 0.0001/1.000/1.000;
  inclined_slide 0.0010/0.997/1.000. (bouncing_ball's slope=1.151 in-range is
  the one system worth watching going forward — still passes the coarse E6
  bar but is the least clean of the six; see Section 2's note on low-e
  restitution precision.)
- **Verdict: PASS.** PRE(in)~0, slope(in)~1, R^2~1 as required. The
  measurement pipeline is validated. Proceed to E0.
- **Bug found and fixed during this run:** `fit_omega_from_crossings`'s
  returned R^2 (fit against an UNDAMPED sine) badly under-reported fit
  quality for real damped oscillations at higher omega (R^2 as low as 0.43 at
  omega=12 despite <0.6% recovery error) — this would have wrongly gated out
  good measurements. Added `damped_sine_r2()` to physweep_metrics.py and used
  it (with a zeta estimate) as the actual gate for the pendulum_omega system
  in this experiment. See git history for the full investigation.

### E0 — Pilot / decision gate
- **Status:** DONE. **Decision: REFRAME** ("conditioning not detectably
  honored" in this setup) — see caveats below before treating as final.
- **Date:** 2026-07-04
- **Model:** LTX-Video (`Lightricks/LTX-Video`, diffusers format), inference
  only. System: projectile only, 5 in-range g + 3 out-of-range g, m=5 seeds.

- **Result:** slope(in) = -0.5164, 95% CI [-1.1389, 0.0000] (includes 0).
  PRE(in) = 1.0174 [0.8912, 1.1436]. Fit-quality (R^2>=0.8) dropped rate =
  80% (32/40 clips) — either the tracker lost the disk entirely (NaN, ~45%
  of clips) or the fit was poor. Of the 4 gated in-range points (all from a
  single seed), 2 recovered g_hat~=0 and 2 recovered NEGATIVE g_hat.
  Full data: `results/e0_pilot.json`.

- **Visual root-cause check (not just trusting the fitted number):**
  inspected generated frames directly for several clips (`results/debug_e0_case*.png`).
  The ball starts near the ground line in the conditioning frame and, across
  every g value and prompt tested (including "extremely strong gravity like
  Jupiter, violent rapid acceleration"), it stays essentially STATIONARY for
  the whole clip — it does not fall, regardless of what the text says. Where
  the tracker returned a negative g_hat, the ball's shape had deformed into a
  blob at the last frame (an artifact), which is what actually drove the
  spurious "negative gravity" fit — not real upward motion. This looks like
  a case of the model reading "ball resting near a ground line" as an
  at-rest scene and not overriding that with text-specified dynamics, not
  generic noise or a broken pipeline.

- **Caveats before treating this as a final result (important):**
  1. **Conditioning channel was forced to C2 (text-specified), not the
     paper's default C1 (frame-implied)** — see the pipeline-bug account
     below. A C2-only null result supports "this model doesn't respond to
     TEXT-specified gravity here," which is weaker than a true C1 failure
     (frame-implied motion, the paper's primary channel, was never
     successfully tested).
  2. Generation resolution (512x512) is still well below LTX-Video's native
     ~704x1216 — improved stability over 256x256 (see below) but still
     possibly out-of-distribution enough to affect fidelity.
  3. The conditioning image places the ball ADJACENT to the ground line
     (per physweep/render.py's projectile launch point) — plausibly readable
     by the model as "already landed," biasing toward the stationary
     response seen. A conditioning frame with the ball clearly mid-air might
     behave differently and hasn't been tried.
  4. Single model (LTX-Video only), single prompt template, 30 inference
     steps, guidance_scale=3.0 (defaults, not tuned).
  These caveats mean "REFRAME to conditioning-not-honored" is the right call
  for THIS exact setup, but a genuinely careful E0 write-up should say so
  explicitly rather than claim a clean general negative result about C1
  frame-implied conditioning, which was never actually tested end-to-end.

- **Full account of getting here (two real pipeline bugs found and fixed
  before this result could be trusted; kept in full because a future session
  could otherwise waste time rediscovering them):**
  1. **First attempt (C1, single-frame):** conditioned on only the
     projectile's first rendered frame. Produced exactly repeating g_hat
     values per seed regardless of g_true (e.g. seed 0 always gave
     g_hat=-0.009 no matter the actual g). Root cause: `simulate_projectile`
     picks the initial launch velocity so the arc returns to the SAME y0 at
     t=0 always — position at t=0 never depends on g by construction, so a
     single first frame carries zero gravity signal. Not a generator
     failure; an experiment design bug.
  2. **Second attempt (proper C1, first+middle frame via LTXConditionPipeline):**
     switched to `LTXConditionPipeline` (supports multi-frame/first+last
     conditioning) and picked the trajectory's MIDDLE frame as the second
     condition (the last frame turned out to ALSO be g-independent for the
     same symmetric-arc reason — verified directly). Hit a real diffusers
     0.39.0 bug: `LTXConditionPipeline.__call__` never computes/passes `mu`
     to the scheduler's `set_timesteps`, while `LTXImageToVideoPipeline`
     does — crashes with "`mu` must be passed when `use_dynamic_shifting`
     is...True" (confirmed true in the shipped scheduler_config.json).
     Wrote `physweep/ltx_patch.py` to compute `mu` exactly as the working
     pipeline does (matched video_sequence_length, not an approximation) and
     inject it. This fixed the crash, but the pipeline STILL produced pure
     noise by mid-clip regardless of fix — confirmed this is
     `LTXConditionPipeline`-specific and not our scene/resolution by testing
     the exact same real photographic image, at LTX-Video's own documented
     native resolution (704x512) and example prompt, through both pipelines:
     `LTXImageToVideoPipeline` stayed clean and coherent through frame 24;
     `LTXConditionPipeline` (patched) dissolved into a noisy painterly mess
     by frame 24. Concluded `LTXConditionPipeline` has additional problems
     in this diffusers version beyond the missing `mu`, not worth chasing
     further. `physweep/ltx_patch.py` is kept (documents a real, reproducible
     diffusers bug) but is NOT currently used by any experiment script.
  3. **Final approach (C2, single-frame + explicit text):** switched to the
     reliable `LTXImageToVideoPipeline`, single first-frame conditioning,
     with gravity magnitude and a qualitative descriptor stated explicitly
     in the prompt (see `gravity_prompt()` in `experiments/e0_pilot.py`).
     Generation is stable and clean at 512x512 (verified visually) — this is
     what actually ran and produced the numbers above.
  - Also fixed along the way: `transformers` 5.13.0 (the version `pip`
    resolved by default) cannot load LTX-Video's T5 tokenizer (`spiece.model`)
    — it misroutes through a tiktoken BPE parser and crashes. Downgraded to
    `transformers>=4.44,<5` (landed on 4.57.6), which loads it correctly.
    Pinned in `requirements.txt`.

### E1 — Faithfulness curve
- **Status:** NOT STARTED (blocked on E6+E0)

### E2 — Extrapolation
- **Status:** NOT STARTED

### E3 — Plausibility-measurement gap
- **Status:** NOT STARTED

### E4 — Generality across systems
- **Status:** NOT STARTED

### E7 — Failure-mechanism adjudication
- **Status:** NOT STARTED

### E5 — Robustness / ablations
- **Status:** NOT STARTED

### E8 — Conditioning-channel ablation
- **Status:** NOT STARTED

### E9 — Controllability audit
- **Status:** NOT STARTED

### E10 — Multi-parameter (optional)
- **Status:** NOT STARTED / not committed to

---

## 6. Environment / setup

**Instance:** Vast.ai container, NVIDIA A100-SXM4-40GB, CUDA 12.8 (driver
570.133.20), ~549 GB disk. **`/workspace` is NOT a persistent volume** —
everything is lost on recycle/destroy. Persistence plan:
- Code, paper source, configs, metrics, results tables/CSVs, this file →
  git, remote `https://github.com/rasulkhanbayov/4-iclr`.
- Large binary artifacts (generated videos, model weights, checkpoints) →
  excluded from git via `.gitignore`; push to Hugging Face Hub or an rclone
  remote instead once one is configured. **Do not let large artifacts pile up
  only in `/workspace` — sync or discard them after each experiment.**

**Python env:** project-local venv at `/workspace/4-iclr/.venv` (NOT the
shared `/venv/main` — that venv's `site-packages`/`bin` are root-owned and
installs there fail with permission errors; do not fight this, use `.venv`).
`.venv` is gitignored (large/regenerable). Recreate anytime with:
```
python3 -m venv /workspace/4-iclr/.venv
source /workspace/4-iclr/.venv/bin/activate
pip install torch --index-url https://download.pytorch.org/whl/cu128
pip install -r requirements.txt
```
**Installed as of 2026-07-04:** torch 2.11.0+cu128 (CUDA confirmed available,
sees the A100-SXM4-40GB), numpy 2.5.0, scipy, opencv-python-headless, pillow,
imageio(+ffmpeg), diffusers 0.39.0, transformers==4.57.6 (see pin note
below), accelerate, safetensors, sentencepiece, tiktoken, huggingface_hub.
Pinned in `requirements.txt`. Metrics smoke test re-verified passing inside
`.venv` (identical output to the system-python run — see Section 5).

**transformers pin (important, will bite again if bumped):** `pip install
transformers` resolves to 5.13.0 by default, which CANNOT load LTX-Video's T5
tokenizer — `transformers` 5.x's tokenizer-conversion path misroutes the
tokenizer's `spiece.model` (SentencePiece format) through a tiktoken BPE
parser and crashes (`ValueError: Error parsing line ... in spiece.model`).
Fixed by pinning `transformers>=4.44,<5` (landed on 4.57.6). Also needed:
`pip install tiktoken` (transformers imports it lazily and errors without it
even when not actually using tiktoken-format files).

**HF_HOME gotcha (will bite every new script/shell):** the instance's default
`HF_HOME` (`/workspace/.hf_home`) is ROOT-OWNED — any `huggingface_hub`/
`diffusers` download fails with `PermissionError`. Use a project-local cache
instead: `/workspace/4-iclr/.hf_home` (already gitignored). **A shell
`export HF_HOME=...` does NOT persist to a fresh Bash tool call / new
background process** — every script that touches HF Hub must set it itself
at the top: `os.environ["HF_HOME"] = ".../4-iclr/.hf_home"` (force-set, not
`setdefault`, since the wrong value is already present in the environment,
not merely unset). See `experiments/e0_pilot.py` top of `main()`-adjacent
imports for the pattern.

**To do before E6/E0 (update this list as it's done):**
- [x] Create `requirements.txt` pinning exact versions.
- [x] Install torch with a CUDA 12.8 wheel (matches A100 compute capability
      8.0 and driver_max_cuda 12.8).
- [x] Write the deterministic 2D rendering engine for all 6 sweep axes across
      5 systems (`physweep/render.py`) — validated against every fitter on
      ground-truth trajectories, see Section 2.
- [x] Implement the tracker: blob centroiding (`physweep/track.py`), per the
      paper's "robust here" claim for high-contrast synthetic scenes.
      CoTracker3 deferred to the E5(a) tracker-swap ablation.
- [x] Save the exact in-range/out-of-range grids per system to
      `physweep/configs/systems.yaml` (cite in Appendix C at write-up time).
- [x] Install LTX-Video (I2V mode): `Lightricks/LTX-Video`, diffusers format,
      ~28GB (dominated by the T5-XXL text encoder). Loads at 14.25GB VRAM on
      CUDA — comfortably within the paper's 24GB target and the A100's 40GB.
- [x] Run and log E6 (aggregate, all systems): PASS, see Section 5.
- [x] Run and log E0 (LTX-Video pilot): DONE, decision=REFRAME (with
      caveats) — see Section 5 for the full account, including two real
      pipeline bugs found and fixed (`LTXConditionPipeline`'s missing `mu`,
      documented in `physweep/ltx_patch.py`; single-frame conditioning
      carrying zero theta signal) before the result could be trusted.
- [ ] **Open decision needed before E1:** either accept the reframe
      ("conditioning not honored" for this model/setup) and adjust the paper's
      framing accordingly, or first retry E0 with a stronger/fairer test of
      C1 (frame-implied) conditioning — e.g. reposition the projectile launch
      clearly mid-air so it doesn't visually read as "at rest," since that
      was flagged as a plausible confound. See Section 5 caveats.

**Models queue (frozen, inference-only, in this order):**
1. LTX-Video (Lightricks), I2V — start here, lightest/fastest.
2. CogVideoX-5B-I2V (Tsinghua/Zhipu).
3. Stable Video Diffusion or DynamiCrafter (I2V).
4. Optional: quantized Wan I2V if it fits in 40GB (full Wan needs ~65-80GB,
   skip unless it fits — A100-40GB is borderline, verify quantized VRAM
   before attempting).
5. For E9 only: a model that claims physics controllability (PhysChoreo /
   Phantom / PhysVideo), if weights are available.

All runs are inference-only — no training anywhere in this project.

---

## 7. Integrity checklist (do not skip before submission)

- [ ] Re-run the arXiv novelty search the week of submission (field moves
      fast). Named neighbors to re-check: Kang et al. 2025, Invisible Hand of
      Physics (2606.05328), Physics-IQ, Morpheus, VBench-2.0 (2503.21755),
      Inferring Dynamic Physical Properties (2510.02311), PhyGround
      (2605.10806), LAPG (2606.11277), PhyCo (2604.28169), LikePhys
      (2510.11512), T2VPhysBench (2505.00337), PhysChoreo, Phantom, PhysVideo.
- [ ] Fill every `{{placeholder}}` author list in `physweep.bib` (see README
      Section 5 for the full list of entries needing this).
- [ ] Independently verify the AI-drafted consistency proof (Appendix B) and
      every physics fitter against a known analytic case.
- [ ] Replace every `[RESULT PLACEHOLDER]` with real measured numbers +
      bootstrap CIs; rewrite abstract/title/contributions to match what was
      actually measured (framing follows data, not the reverse).
- [ ] Anonymize for ICLR double-blind (no names, no identifying repo links in
      the submission PDF — note the public GitHub repo used during
      development must not be linked/identifiable in the final PDF).
- [ ] Include the ICLR LLM-use disclosure per the current author guide.
- [ ] Get 2-3 independent human mock reviews before submitting.

---

## 8. Reading the outcomes honestly (pre-committed, from the paper)

Whatever E0-E9 actually show, report it as one of:
1. **Faithful in-range, fails out-of-range**, H1 or H2 selected — the
   headline story; naming the mechanism is itself the contribution.
2. **No conditioning effect** (beta ≈ 0) — reframe to "open generators do not
   honor conditioned dynamics." Still useful, still publishable.
3. **Faithful even out-of-range** (EG ≈ 0) — a surprising positive result;
   report it as such, do not suppress it.
4. **Neither H1 nor H2 fits** — report the observed behavior directly, do
   not force a mechanism label.

The abstract, title, and contributions get rewritten to match whichever of
these actually happened. Never let the pre-written narrative override a real
result.

---

## 9. Build the paper

```
pdflatex physweep_main.tex
bibtex   physweep_main
pdflatex physweep_main.tex
pdflatex physweep_main.tex
```
Compiles cleanly as-is (shipped `.bbl` resolves refs in one pass if bibtex is
skipped). Needs the real ICLR 2027 `.sty` file dropped in before final
submission (not released yet as of paper drafting; ICLR 2027 full-paper
deadline is historically late September — verify on the official CFP).
