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

**E0 (pilot gate) is now DONE and CONFIRMED SOLID** (2026-07-04, two runs).
**Decision: REFRAME.** LTX-Video does not detectably honor conditioned
gravity under C2 (text-specified) conditioning — v2 (ball near ground):
slope(in) 95% CI [-1.14, 0.00]; v3 (confound check, ball moved clearly
mid-air, `ground_clearance_px=100`): slope(in) = -0.0148, 95% CI
[-0.0895, 0.0387] — an even tighter, more confidently-flat null. The
ground-adjacency confound raised after v2 is now RULED OUT. This was reached
after fixing two real pipeline bugs (zero-signal single-frame conditioning;
a genuine diffusers bug in `LTXConditionPipeline`) — see Section 5 for the
full account. Remaining scope limit: this tested C2 text-conditioning only,
not the paper's default C1 frame-implied channel (LTXConditionPipeline,
needed for real C1, was unusable in this diffusers version).

**CogVideoX-5B-I2V E0 also DONE** (2026-07-04): same headline REFRAME
decision — slope(in) = 0.0699, 95% CI [-0.17, 0.30] (includes 0) — but via a
completely different, and more interesting, mechanism than LTX-Video. Where
LTX-Video mostly fails to produce any real fall (80% of clips fail the
fit-quality gate), CogVideoX reliably produces confident, cleanly trackable
falls (only 20% dropped, R^2 up to 0.996) that converge to one of ~3 FIXED
acceleration values selected by the random seed, essentially independent of
the conditioned gravity (e.g. seed 0 gives -11.41 +/- 0.03 across all five
g-in-range values tested). This is structurally close to the paper's own H1
(global prior reversion) hypothesis, though E0 only covers the in-range
grid — it does not by itself adjudicate H1 vs H2 (that needs E7's
out-of-range test). See Section 5 for the full comparison table.

**Two independent models now agree on the headline finding** (conditioning
not detectably honored under C2), via different mechanisms. This is a
meaningfully stronger basis for the reframe than either model alone, and the
CogVideoX seed-clustering result is a concrete, promotable finding worth
following up with E7 specifically.

**Decision made (2026-07-04): accept the 2-model reframe, proceed under
"open generators do not honor conditioned dynamics" (C2 conditioning).**
**E1 is now DONE for the projectile system** (both models) — formalizes E0's
already-collected data (same grid/seeds/conditioning) into E1's official
slope/PRE/Spearman-rho statistics rather than re-spending GPU time. Both
models: slope CI includes 0, small-magnitude Spearman rho. See Section 5.

**E4 (generality across systems) — LTX-Video DONE, CogVideoX IN PROGRESS.**
LTX-Video result (2026-07-04): 4 of 5 remaining systems produced almost no
usable data at all (94-100% fit-quality dropped rate); the one system with
enough data (inclined_slide) shows a wide, zero-crossing slope CI, same
story as projectile. Two of the five systems (pendulum_omega, spring_mass)
are frame-capped at 97 generated frames (vs the ~180 ground truth needs),
confounding "ignores conditioning" with "clip too short" for those two only
— see Section 5 for the full breakdown and caveat. **CogVideoX's E4 run
started 2026-07-04, background PID (check `ps aux | grep e4_generality`),
log at `results/e4_cogvideox.log`, estimated ~10.7 HOURS** (measured: ~5.9
min/clip for the 2 frame-capped systems, ~2.3 min/clip for the other 3, 170
clips total) — this is a long-running background job, check with wide
intervals (30-60+ min), not tight polling.

**Next action:** wait for CogVideoX's E4 run to complete, then write up its
results in Section 5 next to LTX-Video's for the full 2-model x 6-system
picture. The CogVideoX seed-clustering / H1-like lead from E0 (Section 5)
remains a promising, not-yet-adjudicated follow-up for E7 (needs
out-of-range data specifically). True C1 (frame-implied) conditioning and a
third model (SVD/DynamiCrafter) remain open per-runbook items not yet
attempted. Do not write any number into the paper that was not produced by
an actual run recorded in Section 5.

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
- **Status:** DONE (two runs, v2 then v3 with a confound fix). **Decision:
  REFRAME** ("conditioning not detectably honored") — confirmed solid after
  ruling out the main plausible confound. See caveats below (the C1-vs-C2
  channel caveat still stands).
- **Date:** 2026-07-04
- **Model:** LTX-Video (`Lightricks/LTX-Video`, diffusers format), inference
  only. System: projectile only, 5 in-range g + 3 out-of-range g, m=5 seeds.

- **v2 result (ball starts near the ground, `ground_clearance_px` default
  5-15px):** slope(in) = -0.5164, 95% CI [-1.1389, 0.0000] (includes 0).
  PRE(in) = 1.0174 [0.8912, 1.1436]. Fit-quality (R^2>=0.8) dropped rate =
  80% (32/40 clips). Of the 4 gated in-range points (all one seed), 2
  recovered g_hat~=0 and 2 recovered NEGATIVE g_hat (traced to a shape
  deformation artifact at the last frame, not real upward motion).

- **v2 visual root-cause check:** inspected generated frames directly
  (`results/e0_debug_evidence/`). The ball starts near the ground line and,
  across every g value and prompt (including "extremely strong gravity like
  Jupiter, violent rapid acceleration"), stays essentially STATIONARY the
  whole clip. Flagged a plausible confound: a ball resting next to a ground
  line might read as "at rest" to the model regardless of prompt, independent
  of any real gravity-conditioning failure.

- **v3 (confound check): re-ran with `ground_clearance_px=100`** so the
  conditioning frame shows the ball clearly mid-air (verified visually first:
  `results/debug_midair_cond.png` — ball ~124px above the ground line,
  nowhere near it). Same C2 prompts, same everything else. **Result: slope(in)
  = -0.0148, 95% CI [-0.0895, 0.0387]** — a MUCH tighter CI centered right on
  0 (vs v2's wide [-1.14, 0.00]). Fit-quality dropped rate unchanged at 80%.
  Of 5 gated in-range points (spanning g=5 to g=15), every recovered g_hat
  was small and positive (0.20-0.66) regardless of the true g -- not just an
  inconclusive null, a confident flat-zero response. Full data (this is what
  `results/e0_pilot.json` currently holds; v2's JSON was overwritten, numbers
  preserved here): 40 clips, `physweep/configs/systems.yaml` grid.

- **Conclusion: the ground-adjacency confound is RULED OUT.** Moving the
  ball clearly into mid-air did not rescue a hidden gravity effect — it
  produced an even more confidently flat, near-zero slope. LTX-Video, under
  C2 (text-specified gravity) conditioning with a single first-frame image,
  does not detectably vary its generated motion with the stated gravity
  magnitude, at either ground-adjacent or clearly-airborne starting
  positions.

- **Caveats that still stand (only #3 below was resolved by v3):**
  1. **Conditioning channel was forced to C2 (text-specified), not the
     paper's default C1 (frame-implied)** — see the pipeline-bug account
     below. This result supports "this model doesn't respond to
     TEXT-specified gravity here" specifically; true frame-implied (C1)
     conditioning was never successfully tested end-to-end (LTXConditionPipeline
     was unusable — see below) and could behave differently.
  2. Generation resolution (512x512) is still below LTX-Video's native
     ~704x1216 — stable and clean at this size (verified visually) but still
     possibly out-of-distribution enough to affect fidelity.
  3. ~~Ground-adjacency confound~~ — **RESOLVED by v3**: repositioning the
     ball clearly mid-air did not change the conclusion.
  4. Single model (LTX-Video only), single prompt template family, 30
     inference steps, guidance_scale=3.0 (defaults, not tuned). A different
     prompt phrasing, higher guidance, or a different model could behave
     differently — this is E5(f) and E9 territory, not yet run.
  The remaining honest framing: **for LTX-Video under C2 text-conditioning,
  conditioning is not detectably honored** — solid within that scope, not
  yet a general claim about C1 or about "video generators" broadly.

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

### E0 (CogVideoX-5B-I2V) — second model, same pilot design
- **Status:** DONE. **Decision: REFRAME** (same headline as LTX-Video, via a
  clearly DIFFERENT mechanism). Script: `experiments/e0_pilot_cogvideox.py`.
- **Date:** 2026-07-04. **Model:** `zai-org/CogVideoX-5b-I2V` (the paper's
  "CogVideoX-5B-I2V"; THUDM's org appears to have moved to `zai-org` on HF).
  480x720 (native training resolution), 49 frames requested (trimmed to
  N_FRAMES=24 for fitting), 30 inference steps, guidance_scale=6.0 (model
  default). Same C2 text-specified prompts as LTX-Video, same projectile
  system/grid, same mid-air `ground_clearance_px=100` conditioning (applied
  from the start here, since the LTX-Video confound check already
  established it matters). ~2.3 min/clip on the A100 (much slower than
  LTX-Video's ~2s/clip); 40 clips took ~89 minutes total. Peak VRAM 25.3GB
  (with `pipe.vae.enable_tiling()` — needed at 480x720, comfortably under
  the A100's 40GB).

- **Result: slope(in) = 0.0699, 95% CI [-0.1683, 0.3048]** (includes 0).
  PRE(in) = 2.0164 [1.8221, 2.2343] — very large, consistent with recovered
  values being wildly off from the true (positive, 5-15) gravity range.
  Fit-quality dropped rate = 20% (8/40) — much lower than LTX-Video's 80%,
  because CogVideoX produces confident, cleanly trackable motion (R^2 up to
  0.996) rather than a static or noisy blob. **The conditioning is still not
  honored — just via a completely different failure mode.**

- **The mechanism (visible directly in the raw gated data, not just the
  aggregate slope):** recovered g_hat clusters tightly BY SEED, essentially
  independent of the true conditioned g (5 through 15 all tested):
  seed 0 -> -11.41 +/- 0.03 (5 g values, std well under 1%)
  seed 1 -> -11.47 +/- 0.16
  seed 3 -> -11.12 +/- 0.65
  seed 4 -> -7.08  +/- 0.17
  (seed 2 mostly failed the tracker/R^2 gate). Every one of these clips has
  R^2 > 0.87 — the model is NOT confused or noisy, it is confidently and
  smoothly generating one of a small number of fixed fall patterns, selected
  by the initial noise seed, while completely ignoring the stated gravity
  magnitude in the prompt. Visually (`results/debug_cogvideox_frame*.png`
  before cleanup — see git history if needed) the ball falls and lands
  convincingly; it just always falls at close to the same few rates.

- **Relation to the paper's own H1 hypothesis (important caveat on how far
  this claim goes):** this pattern — convergence to a small set of
  seed-selected defaults independent of theta — is structurally very close
  to what the paper calls H1 (global prior reversion to a default,
  Section~\ref{sec:problem}/Eq. eq:pri). It is a suggestive, encouraging
  sign that the paper's H1/H2 framework will have something real to
  adjudicate. **But E0 only tests the IN-RANGE grid (5-15); it says nothing
  about OUT-OF-RANGE behavior, which is what H1 vs H2 (Section 3, E7) is
  actually about** (H1 is specifically a claim about behavior once theta
  leaves the common range). Treat this as a promising pilot observation
  motivating E7, not a completed mechanism adjudication.

- **Comparison across the two models tested so far:**
  | | LTX-Video | CogVideoX-5B-I2V |
  |---|---|---|
  | slope(in) | -0.0148 [-0.09, 0.04] | 0.0699 [-0.17, 0.30] |
  | Fit-quality dropped | 80% | 20% |
  | Failure mode | near-total inertia (ball barely moves at all) | confident motion toward ~2-3 fixed seed-selected fall rates |
  | R^2 on gated clips | mediocre (0.88-0.995, but only 20% of clips gated) | strong (0.87-0.996, 80% of clips gated) |

  Both reach the same headline conclusion (conditioning not detectably
  honored) through opposite-looking behavior: LTX-Video mostly fails to
  produce a physical fall at all; CogVideoX reliably produces a physical
  fall but toward the wrong (seed-determined, not theta-determined) target.
  Two independent models agreeing on the headline result, via different
  mechanisms, is a stronger basis for the reframe than either alone — and
  the CogVideoX mechanism in particular is a concrete, promotable finding in
  its own right (motivates leading with H1-style framing once E7 actually
  tests it out-of-range).

### E1 — Faithfulness curve
- **Status:** DONE (projectile system, C2 conditioning, both models tested
  so far). Script: `experiments/e1_faithfulness.py`. Formalizes E0's
  already-collected data into E1's official statistics rather than
  re-spending GPU time — E0's projectile grid/seeds/conditioning already
  satisfies what E1 needs for this system. Other 5 systems and true C1
  conditioning remain open (E4 and future-work scope respectively).
- **Date:** 2026-07-04.

| Model | slope beta (in) | PRE(in) | Spearman rho (full grid) |
|---|---|---|---|
| LTX-Video | -0.015 [-0.090, 0.039] | 0.853 | -0.268 |
| CogVideoX-5B-I2V | 0.070 [-0.168, 0.305] | 2.016 | 0.046 |

- **Reading:** both models' slope CIs include 0 and both Spearman rho values
  are small in magnitude (LTX-Video's -0.268 is noise given the wide, zero-
  crossing slope CI, not a real inverse relationship — flagged so it isn't
  mistaken for a finding). Neither model shows a faithfulness curve that
  tracks the conditioned gravity in any direction. This is the formal E1
  confirmation of the E0 pilot's REFRAME decision, for the projectile system
  specifically. Full data: `results/e1_faithfulness.json`.

### E2 — Extrapolation
- **Status:** NOT STARTED

### E3 — Plausibility-measurement gap
- **Status:** NOT STARTED

### E4 — Generality across systems
- **Status:** LTX-Video DONE (all 5 remaining systems). CogVideoX-5B-I2V
  IN PROGRESS (started 2026-07-04, ~10.7 hour estimated runtime — see
  Section 6/below for why). Script: `experiments/e4_generality.py --model
  {ltx,cogvideox}`, covers pendulum_omega, pendulum_zeta, bouncing_ball,
  spring_mass, inclined_slide (projectile/gravity already covered by E0/E1).

- **Frame-count cap (important, affects interpretation):** pendulum_omega
  and spring_mass need ~180 frames on ground truth (E6) for the fitter to
  see >=2 oscillation periods at the lowest omega/k in their grids. Neither
  generator can practically produce clips that long (measured: CogVideoX
  takes ~5.9 min for just 97 frames, vs ~2.3 min for 49). Capped generation
  at `MAX_GEN_FRAMES=97` for both models — informative middle ground per the
  user's direction, not the full requirement. This means a fit-quality
  failure on these two systems conflates "the model doesn't honor
  conditioning" with "the clip is too short to identify the parameter even
  from a perfect video" — the results below can't cleanly separate those two
  explanations for pendulum_omega/spring_mass specifically. The other 3
  systems (pendulum_zeta, bouncing_ball, inclined_slide) use the validated
  N_FRAMES=24, so no such confound for them.

- **LTX-Video result (2026-07-04):**

| System | n_gated_in / n_total | dropped rate | slope beta (in) |
|---|---|---|---|
| pendulum_omega | 0/30 | 100% | n/a — nothing survived the gate |
| pendulum_zeta | 0/30 | 100% | n/a — nothing survived the gate |
| bouncing_ball | 1/35 | 94% | n/a — only 1 point, no CI possible |
| spring_mass | 0/40 | 100% | n/a — nothing survived the gate |
| inclined_slide | 7/35 | 69% | -0.464, 95% CI [-1.75, 1.10] |

  Four of five systems produced essentially no usable data at all (94-100%
  dropped) — even worse than projectile's already-poor showing in E0 (80%
  dropped there). Only inclined_slide yielded enough gated points for a
  slope estimate, and it too has a wide, zero-crossing CI, consistent with
  no detectable conditioning effect. Full data:
  `results/e4_{system}_ltx.json`, `results/e4_generality_ltx.json`.
  **Caveat:** for pendulum_omega/spring_mass this near-total failure is
  confounded with the frame-cap limitation above — cannot distinguish
  "ignores conditioning" from "clip too short to tell" for those two.
  bouncing_ball and inclined_slide are NOT frame-capped (use N_FRAMES=24)
  and still show very high drop rates — that result stands on its own and
  reinforces the projectile finding: LTX-Video generally fails to produce
  a trackable, physically-fittable trajectory under C2 conditioning across
  system types, not just for projectile/gravity.

- **CogVideoX-5B-I2V:** in progress — see Section 0 for live status; will be
  added here once complete.

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
