# PhysWeep: a first-author's guide to this paper bundle

This folder is a **complete draft paper plus everything you need to run it**.
The science is not finished: the paper is written, the code works, but the
experiments are yours to run. Numbers in the paper are placeholders until you
measure them. This README is your map.

---

## 1. What the paper claims and why it matters

**One sentence:** instead of asking "does this generated video *look* physical?"
(what most benchmarks do), we ask "does the video realize the *specific* physical
parameter we conditioned it on, and does that still hold when we push the
parameter outside the everyday range?"

**The gap:** the field measures *plausibility*. But a falling ball can look
perfectly smooth while encoding the wrong gravity. Plausibility raters, including
VLM auto-raters, will not catch that. So plausibility is necessary but not
sufficient evidence that a video model "learned physics."

**The contribution (the delta over the closest work):**
- vs. Kang et al. 2025 (*How Far Is Video Generation from World Model*) and
  *The Invisible Hand of Physics* (2026): they show OOD failure and describe it
  as "case-based" nearest-example mimicry, but on **trained-from-scratch** models
  or via **internal probes**. We probe **frozen, off-the-shelf** generators as
  **black boxes**, measure a **continuous** recovered parameter under a sweep,
  and **adjudicate the failure mechanism** (global default collapse H1 vs.
  case-based clamp H2) with a model-selection rule.
- vs. plausibility benchmarks (VideoPhy, Physics-IQ, Morpheus, PhyWorldBench,
  **VBench-2.0**): they score how physical a fixed clip looks (VBench-2.0 even
  has "Physics"/"Controllability" dimensions, but via VLM/QA proxies); we **sweep
  a known control parameter** and measure exact **recovery error** and
  **extrapolation**.
- vs. property-readout work (Inferring Dynamic Physical Properties; Invisible
  Hand): they read properties from **input** videos via internal features; we
  read them from **generated** pixels with **no model access**.
- vs. physics-controllable methods (PhysChoreo, Phantom, PhysVideo): they
  **claim** control; we **audit** whether the claimed knob actually moves the
  realized parameter and whether it extrapolates.

**Why it can get cited:** it ships a reusable, model-agnostic diagnostic, a
clean conceptual separation (plausibility vs. parameter faithfulness), a named
failure-mechanism test, and an audit others can run on any new image-to-video
model, including the ones that advertise physics control.

---

## 2. The files

| File | What it is |
|---|---|
| `physweep_main.tex` | The paper source (self-contained, compiles anywhere). |
| `physweep.bib` | Bibliography. Some author lists are `{{placeholders}}` you must fill. |
| `physweep_main.bbl` | Precompiled references (lets one `pdflatex` pass resolve cites). |
| `physweep_main.pdf` | The built paper. |
| `physweep_metrics.py` | The metrics + physics fitters + a synthetic smoke test. |
| `physweep_runbook.txt` | The detailed experiment protocol. Read this before running. |
| `physweep_submission.zip` | Everything bundled for upload / Overleaf. |

**Build the paper:**
```
pdflatex physweep_main.tex
bibtex   physweep_main
pdflatex physweep_main.tex
pdflatex physweep_main.tex
```
It compiles cleanly with no errors, no undefined citations, no bad overfull
boxes. (If you skip bibtex, the shipped `.bbl` still resolves references in one
pass.)

**Template note:** the file uses a self-contained ICLR-like layout so it builds
without a venue style file that does not exist yet for ICLR 2027. Before
submitting, drop in the official `iclr2027_conference.sty` when it is released;
the section content maps over unchanged. ICLR 2027's full-paper deadline
historically lands in **late September 2026** (verify on the official CFP).

**Where each claim lives:** the plausibility-vs-faithfulness reframing is the
boxed statement in Section 1; the metrics (PRE, EG, PRI) and the one honest
theorem (about the *measurement*, not the model) are in Section 4; the systems
in Section 5; the protocol and the `>>> TO RUN` experiments in Section 7; the
placeholder result tables and the "read the outcomes honestly" paragraph in
Section 8.

---

## 3. The experiments (what to do, in order)

Full detail is in `physweep_runbook.txt`. The short version:

1. **E6 negative control + E0 pilot, first.** E6 proves your measurement works
   (feed real simulator video in, get the right parameter out). E0 checks whether
   the generator follows the conditioned parameter *at all*.
2. Then the faithfulness curve (E1), extrapolation (E2), the
   plausibility-measurement gap (E3), generality across systems (E4), the
   **failure-mechanism adjudication** (E7: H1 vs H2), the full ablations (E5:
   tracker, scale-invariance, fit-gate, conditioning length, **guidance scale**,
   prompt phrasing), the **conditioning-channel** ablation (E8: frame-implied vs
   text-specified), the **controllability audit** (E9: do models claiming control
   deliver it?), and optionally multi-parameter (E10).

**What "promising" looks like:** in-range slope near 1 and high Spearman rho,
low in-range error, **but** a clear out-of-range jump in error (Extrapolation
Gap > 0), with E7 cleanly selecting a mechanism (H1 global default collapse or
H2 case-based clamp), while plausibility scores stay high. Naming the mechanism
is itself a result.

**What "negative" looks like and what to do:** if the generator ignores the
conditioning (slope ~0 in E0), reframe to "open generators do not honor
conditioned dynamics." If it extrapolates fine (gap ~0), report the *surprising
positive*. If neither H1 nor H2 fits in E7, report the observed behavior rather
than forcing a label. **Whatever happens, the framing follows the data.**

---

## 4. The code

`physweep_metrics.py` is numpy-only and has two parts:

- **Metrics:** `pre`, `faithfulness_slope`, `spearman_rho`,
  `extrapolation_gap`, `prior_reversion_index` (H1), `case_based_index` (H2),
  `select_mechanism` (H1-vs-H2 by AIC and leave-one-out R^2),
  `within_condition_dispersion`, `bootstrap_ci`,
  `paired_bootstrap_pre_difference`, `plausibility_gap`.
- **Physics fitters** (recover a parameter from a tracked observable, label-free):
  `fit_gravity_from_trajectory`, `fit_omega_from_crossings`,
  `fit_restitution_from_bounces`.

**Run the smoke test** (verifies the code, not any model):
```
python3 physweep_metrics.py
```
You should see the fitters recover known parameters with R2 = 1.0 and the
metrics behave as expected on a synthetic "faithful-then-reverting" generator.
This confirms the analysis pipeline before you spend GPU time. It says nothing
about any real video model.

**Real analysis:** plug your tracked observables from generated videos into the
fitters to get `theta_hat`, collect them into arrays aligned with the
conditioned `theta`, then call the metric functions and the bootstrap helpers.

---

## 5. Integrity and next-steps checklist (do not skip)

- [ ] **Confirm novelty the week you submit.** Re-run the arXiv search; this
      area moves fast. Closest neighbors now: Kang et al. 2025, *The Invisible
      Hand of Physics* (2606.05328), Physics-IQ, Morpheus, VBench-2.0
      (2503.21755), *Inferring Dynamic Physical Properties* (2510.02311),
      **PhyGround** (2605.10806, reproducibility critique of VLM judges),
      **LAPG** (2606.11277, inference-time extrapolation repair), **PhyCo**
      (2604.28169, controllable physical priors), **LikePhys** (2510.11512),
      **T2VPhysBench** (2505.00337), and the physics-controllable methods
      PhysChoreo / Phantom / PhysVideo. Mark anything new, especially any paper
      recovering a parameter from generated video or adjudicating the
      OOD-failure mechanism.
- [ ] **Fill every `{{placeholder}}` author list in `physweep.bib`.** Open each
      source, confirm authors / venue / year. Entries needing this: Morpheus,
      PhyWorldBench, Inferring Dynamic Physical Properties (2510.02311), Invisible
      Hand (2606.05328), VideoREPA, TRAVL, VLM-cannot-reason (2603.07109), VLIPP,
      LTX-Video, Wan, Visual-World Roadmap (2511.08585), Evolution survey
      (2604.06339), VBench-2.0 (2503.21755), PhysChoreo (2511.20562), Phantom
      (2604.08503), How-Diffusion-Models-Memorize (2509.25705), PhyGround
      (2605.10806), PhyCo (2604.28169), LikePhys (2510.11512), and T2VPhysBench
      (2505.00337). Verify the lists already filled (Kang, VideoPhy, VideoPhy-2,
      Physics-IQ, PhyGenBench, CogVideoX, VBench, PhysVideo, Motion Forcing, LAPG)
      against the papers too.
- [ ] **Independently verify the AI-drafted proof and method.** Appendix B is now
      a *complete* consistency proof (continuous mapping theorem under stated
      assumptions A1-A3), but you must still check each step and each per-system
      identifiability claim against a known analytic case. Verify every fitter.
- [ ] **Reconcile every claim with real numbers.** Replace each
      `[RESULT PLACEHOLDER]`; rewrite the abstract, title framing, and
      contributions to match what you actually measured.
- [ ] **Anonymize** for ICLR double-blind (no names, no identifying repo links
      in the PDF) and include the **ICLR LLM-use disclosure** per the current
      author guide.
- [ ] **Get 2-3 independent human mock reviews** and resolve every issue they
      raise *before* submitting. This is the single highest-value step and the
      one this bundle cannot do for you.

---

## 6. Honest expectation setting

This bundle gives you a genuinely open wedge, a clean contribution, a neutralized
main objection (the plausibility-vs-measurement distinction and the negative
control answer "why is this not just another plausibility benchmark" and "is the
effect a measurement artifact"), and a build that will not embarrass you. It does
**not** guarantee acceptance. The ceiling is your results: if E1-E3 come back
clean and robust across seeds and systems, you have a competitive ICLR
submission. If they are messy, the honest negative/partial framing is still
publishable but weaker. Run the pilot, see which world you are in, then commit.
