# PhysWeep — ICLR submission tracker

This file is the persistent memory for this project. Read it fully at the start
of every session before doing anything else. Update it immediately after any
experiment, decision, or environment change — not at the end of a session.

## 0. Current state / next action

**Status as of 2026-07-04:** Instance verified, paper bundle read, metrics
smoke test PASSED. Git repo initialized locally, remote push to
`https://github.com/rasulkhanbayov/4-iclr` in progress (empty repo, safe to
push to). No model weights installed yet. No experiments run yet.

**Next action:** finish git remote setup and push initial commit, then set up
the Python inference env (torch + diffusers + LTX-Video), then run **E6**
(negative control) and **E0** (pilot gate) together — these are hard gates,
nothing else may run before both pass. See Section 4 for pass/fail criteria.

Do not skip ahead in the experiment order in Section 3. Do not write any
number into the paper that was not produced by an actual run recorded in
Section 5.

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

| System | Control theta | Recovered via | In-range | Out-of-range |
|---|---|---|---|---|
| Projectile | gravity g | parabola curvature | 5–15 | 1 (Moon-like), 25 (Jupiter-like) |
| Damped pendulum | angular freq omega | zero-crossing period | typical | very short/long period |
| Damped pendulum | damping zeta | envelope decay | light damping | heavy/near-critical |
| Bouncing ball | restitution e | bounce-height ratio | 0.6–0.9 | 0.2, 0.99 |
| Spring–mass | stiffness k | oscillation period | typical | very stiff/soft |
| Inclined slide | friction mu | accel. along slope | moderate | near-frictionless/high |

All rendered from a small deterministic 2D engine (no downloads, no labels).
Exact grids must be saved to a config file and cited in Appendix C when
defined — see Section 6 "Environment / setup" for where this lives once created.

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
- **Status:** NOT STARTED

### E0 — Pilot / decision gate
- **Status:** NOT STARTED

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
imageio(+ffmpeg), diffusers 0.39.0, transformers 5.13.0, accelerate,
safetensors, sentencepiece, huggingface_hub. Pinned in `requirements.txt`.
Metrics smoke test re-verified passing inside `.venv` (identical output to
the system-python run — see Section 5).

**To do before E6/E0 (update this list as it's done):**
- [x] Create `requirements.txt` pinning exact versions.
- [x] Install torch with a CUDA 12.8 wheel (matches A100 compute capability
      8.0 and driver_max_cuda 12.8).
- [ ] Install LTX-Video (I2V mode) — verify current HF repo id, license, and
      VRAM footprint at install time; this is the first model to bring up
      (lightest/fastest per the runbook).
- [ ] Write the deterministic 2D rendering engine for the 5 systems (Section
      2) — produces conditioning frames + ground-truth theta. This does not
      exist in the repo yet; `physweep_metrics.py` only has the metrics and
      fitters, not the renderer.
- [ ] Decide and implement the tracker: CoTracker3, or start with simple
      color-blob centroiding (simpler, and the paper says it's "robust here"
      for high-contrast synthetic scenes) — blob centroiding first is the
      pragmatic MVP path; CoTracker becomes the E5(a) tracker-swap ablation.
- [ ] Save the exact in-range/out-of-range grids per system to a config file
      (the runbook requires this, cited in Appendix C).

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
