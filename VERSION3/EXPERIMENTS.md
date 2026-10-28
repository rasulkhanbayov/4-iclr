# PhysWeep: experimental design audit and what to run

I cannot run experiments. What follows is (a) a deep audit of the design as it
stands and (b) a specification precise enough to execute without further design
work. Tiers are ordered by acceptance value per hour.

**Tier 0 needs no GPU and no new generation.** It runs on per-clip records you
already have. It is the only tier that fits before August 28, and it closes
three of the six real gaps below.

---

## Part 1 — Audit findings

### A. Baselines: the largest weakness, and it is specific, not generic

The paper tests LTX-Video, CogVideoX-5B-I2V and DynamiCrafter-512. All are
2023–24. The gap is not "somewhat behind"; it is behind **within the two
families the paper itself tests**, and it omits precisely the models credited
with physical coherence.

| Model | Status as of Aug 2026 | Why it matters here |
|---|---|---|
| **Wan 2.2** | Most versatile open model; MoE diffusion backbone | Reported as producing *the most physically coherent motion from a still frame*. A physics-faithfulness paper that omits it omits the strongest case against its own finding. |
| **Wan 1.3B** | 8.19 GB VRAM, Apache 2.0 | Fits the consumer GPU you already used. No hardware excuse. |
| **HunyuanVideo 1.5** | 80 GB base; INT8 on 24 GB | Reported to *excel at natural motion and physics* — fluids, cloth, object interaction. |
| **LTX 2.5** | 32 GB with FP8 | **Natively supports first-and-last-frame conditioning** — the exact capability whose absence in LTXConditionPipeline forced your single biggest protocol deviation. |
| **CogVideoX-1.5** | 40 GB+ | Later release in a family you already test. |

**Reviewer framing to expect:** *"The claim is that video generators do not
realize conditioned physics. The evidence is three models from before the
current generation, none among those known for physical coherence, and one
tested at a version whose successor fixes the conditioning pipeline the authors
report as broken."* That is hard to answer without data.

**Minimum credible fix:** Wan 1.3B on the projectile axis, in-range grid, 5
seeds. One row. Roughly one GPU-day, and it converts the objection from fatal
to scoped.

### B. Controls: one was mislabelled, one is missing

**B1. Terminology — now corrected in the paper.** Running simulator video (where
θ *is* realized) through the pipeline and recovering β = 1.0001 is a **positive**
control: a known signal the instrument must detect. The paper called it a
*negative* control in three of four places. Fixed throughout.

**B2. There is no negative control.** Nothing demonstrates the pipeline reports
*nothing* when nothing is there. Without it, "β indistinguishable from zero" is
calibrated only by its own CI. A **label-permutation null** fixes this at zero
GPU cost — see T0.7. Cheapest genuine strengthening available.

**B3. No generator-side positive control.** No case where a generator is *known*
to respond and the pipeline detects it. Force Prompting (NeurIPS 2025) built a
CogVideoX-based model that does respond to a physics control signal; running
PhysWeep on it would show the audit detects control when control exists. Higher
cost, high value, and it directly answers "maybe your pipeline cannot see
conditioning at all."

### C. Confounds

**C1. Clip length is confounded with model identity.** Native budgets differ:
LTX 24 frames, CogVideoX 49 trimmed to 24, DynamiCrafter 16. Your own ablation
found a **frame-budget floor** on CogVideoX (0/40 clips gate at ~25 frames). So
cross-model *trackability* comparisons are not clean. Within-model conclusions
are unaffected. Now stated in Limitations; fixing it properly means re-running
at a matched frame budget.

**C2. Prompt space barely searched.** Two templates. The headline is that *text*
conditioning does not work; a reviewer will say you did not try hard enough. You
did test extreme phrasings ("extremely strong gravity, like Jupiter"), but not
systematically.

**C3. Denoising steps never varied.** Guidance scale was swept; step count was
not. Given a seed-determinism claim, whether more steps escape the seed's basin
is directly on point and cheap.

### D. Mechanism isolation

**D1. Initial noise vs. intermediate noise is not separated.** The seed fixes
both. Xu et al. (WACV 2025) distinguish them. Since the paper now positions its
finding as the dynamical counterpart of their appearance result, not separating
these is the obvious next question, and the one a reviewer who knows that paper
will ask.

**D2. SDI is unfilled.** The paper proves PRI cannot identify the mechanism and
supplies the statistic that can, then leaves its column empty. See T0.1.

### E. Statistics

- **E1.** No power analysis; m ≥ 5 is unjustified against CIs as wide as [−6.185, 6.850].
- **E2.** No equivalence test (TOST).
- **E3.** Multiplicity correction applied to the six paired bootstraps but not to the five slope intervals.

### F. Generalization

- **F1.** No held-out system: all five were used while developing the pipeline.
- **F2.** No comparison against an established benchmark (VideoPhy, VBench-2.0) showing the metric adds information a published score does not. For an Evaluation & Dataset paper this is a normal expectation.

---

## Part 2 — What to run

### Tier 0 — reanalysis only, no GPU, hours

**T0.1 SDI + FDI on all adjudicated pairs** `[DONE — verified 2026-08-26]`

```python
from physweep_metrics import (seed_determination_index,
                              variance_decomposition, classify_regime)
```

Gated clips only; bootstrap CIs over (θ, seed). Fills Table 3's SDI column.
Already computed and present in `main.tex`'s Table 3 (`tab:e2`); independently
re-verified against `results/*.json` directly, all 8 values match exactly
(LTX/projectile 0.995, CogVideoX/projectile 0.919, DynamiCrafter/projectile
0.343, LTX/bouncing-ball 0.985, CogVideoX/bouncing-ball 0.997,
DynamiCrafter/bouncing-ball 0.997, LTX/inclined-slide 0.511,
DynamiCrafter/inclined-slide 0.176). This `[BLOCKING]` tag was stale.

| Result | Reading, committed in advance | Actual (5/8 pairs) |
|---|---|---|
| SDI > 0.6 on the seed-clustered pairs | Headline confirmed and measured. Switch to the "Seed Picks the Physics" title (one-line swap in `main.tex`). | Confirmed on all projectile and bouncing-ball pairs. |
| SDI 0.3–0.6 | Soften to "the seed accounts for X% of the variance". | LTX/inclined-slide (0.511), DynamiCrafter/projectile (0.343). |
| SDI < 0.3 | **Headline is wrong.** The behavior is unstructured noise. Report as a trackability + null-faithfulness result. | DynamiCrafter/inclined-slide (0.176). |

**Net reading**: the seed-locked signature is real and decisively confirmed
on 5 of the 8 adjudicated pairs (SDI≥0.92), softened on 2, and genuinely
NOT established on 1 (DynamiCrafter/inclined-slide). This is a MIXED result,
not a uniform one — do not switch the title to a claim that holds for all
eight pairs; report per-pair as `main.tex` already does.

**T0.2 SDI on the simulator positive control** `[DONE — verified 2026-08-26]`
Same functions on the reconstructed ground-truth control measurements
(re-ran `experiments/e6_negative_control.py`'s own render/track/fit
functions directly, since the saved `results/e6_negative_control.json`
stores only aggregates, not per-clip rows). Result: **SDI = 0.000, FDI ≈
1.000** (variance-decomposition theta-share $0.99999998$) on $200$ gated
clips — confirms the control is NOT itself seed-locked, exactly as
expected, which is what makes the T0.1 seed-locking finding on the real
generators trustworthy rather than an artifact of the SDI estimator
itself. This `[BLOCKING]` tag was also stale.

**T0.7 Label-permutation null** `[DONE — verified 2026-08-26, closes gap B2]`
Shuffle θ labels against clips within each model×axis, refit β, repeat 10,000×.
Report the null distribution and where the observed β sits in it. Turns "β is
indistinguishable from zero" from a CI statement into a calibrated one, and it
is the negative control the pipeline currently lacks. **Zero GPU.**
Already computed and present in `main.tex`'s "One design gap closed"
paragraph; independently re-implemented (not in `physweep_metrics.py`,
written fresh) and re-run on all 5 slope-estimable pairs: LTX/projectile
$p=0.673$, CogVideoX/projectile $p=0.583$, DynamiCrafter/projectile
$p=0.914$, LTX/inclined-slide $p=0.557$, DynamiCrafter/inclined-slide
$p=0.828$ -- range $0.557$--$0.914$, matching the paper's claimed
$0.56$--$0.91$ closely. This `[closes gap B2]` tag's implied
not-yet-done status was stale.

**T0.3 Per-seed slopes.** Fit β within each seed (≥3 gated grid points). If
within-seed β is also ≈ 0, that is strictly stronger than the pooled null and
belongs in the abstract.

**T0.4 Holm-adjusted p-values.** `holm_adjust()` is in the code.

**T0.5 TOST equivalence** against a pre-specified smallest effect of interest
(β = 0.2 is defensible).

**T0.6 Power analysis.** Given observed dispersion, what β would 5 seeds detect
at 80% power? Answers "why five seeds" before it is asked.

**T0.8 Ship per-clip records.** One CSV: model, axis, θ, seed, θ̂, fit R², gated,
VLM score. Highest-leverage artifact in the submission — it converts every
number from "trust us" to "check us", which is what this track rewards.

### Tier 1 — new generation, about one GPU-day

**T1.1 Photorealistic-texture projectile control** `[decisive]`
Identical physics, grid and seeds; photorealistic ball and background, one
model. Trackability rises **and** SDI stays high → the stimulus-domain
objection is answered outright. Trackability rises **and** β → 1 → the finding
was a stimulus artifact; report it, and far better found by you than by a
reviewer.

**T1.2 Wan 1.3B on projectile** `[closes gap A]`
8.19 GB, fits your GPU. The interesting outcome is not the obvious one: if Wan
is *also* seed-locked, the signature survived a generation of scaling, which is
the stronger paper.

**T1.3 Matched frame budget** `[closes C1]` — re-run one axis at a common frame
count across all three models.

**T1.4 Denoising-step sweep** `[closes C3]` — four step counts, one model, one axis.

### Tier 2 — if time allows

- **T2.1 Initial vs. intermediate noise** `[closes D1]` — fix one, vary the other. Localizes the mechanism and directly extends Xu et al.
- **T2.2 LTX 2.5 frame-implied conditioning** — native first-and-last-frame support removes the reason the channel comparison is DynamiCrafter-only.
- **T2.3 Human plausibility subset** — 100 clips, 3 raters, same 1–5 scale.
- **T2.4 Benchmark cross-check** — score the same clips with VideoPhy or VBench-2.0 and report rank correlation with PRE and with trackability.

---

## If you can only do three things

**T0.1 + T0.2 + T0.7.** One afternoon, no GPU. They fill the paper's own
headline statistic, validate it against an existing control, and add the missing
negative control. Nothing else here comes close per hour spent.

**If you can add one GPU-day:** T1.2 (Wan 1.3B). It is the objection a reviewer
opens with, and the paper now openly states the model was within your budget.
