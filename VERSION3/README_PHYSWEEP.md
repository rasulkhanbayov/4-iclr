# PhysWeep -- WACV 2027 submission bundle

Post-experiment finalization pass. Read `REDFLAGS.txt` first: it lists every
item you still have to supply, with file and line number.

---

## Deadline reality check

WACV 2027 Round 2 paper deadline: **August 28, 2026 AoE**.
Supplementary material deadline: **August 30, 2026 AoE**.
Round 2 has **no rebuttal stage**; reviews and final decisions arrive together
on October 9, 2026.

Before you upload anything, settle the routing question in `REDFLAGS.txt`
item B2. If your paper received "Revise and Resubmit" in Round 1, the correct
action is a revision plus a one-page rebuttal attached to your **existing
Round 1 submission**, not a new Round 2 entry. Submitting a substantially
similar paper as a new Round 2 submission is grounds for desk rejection.

---

## Read EXPERIMENTS.md first

The single highest-value action left is T0.1 + T0.2 in `EXPERIMENTS.md`: an
afternoon of reanalysis on records you already have, no GPU. The paper now
*proves* that its previously-reported statistics cannot establish its headline
claim, and supplies the statistic that can. Running it is not optional.

## The reframe (read this first)

The draft you sent led with a null result. It now leads with the seed-locked
convergence, which is the strongest thing your data support and the part that
does **not** depend on the attrition problem. Title, abstract, contributions,
and conclusion were restructured accordingly, and the headline claim is now
stated conditionally. See `REDFLAGS.txt` section E for the full list. The
original title is preserved as a commented line in `main.tex` if you disagree.

## What the paper now claims

The framing was rebuilt to match the numbers rather than the pre-experiment
hypothesis. Concretely:

**Headline, and supported.** Conditional on producing physically trackable
motion, none of three frozen open generators detectably honors a
text-specified physical parameter, and two of the three converge to a small
number of fixed, wrong values selected by the sampling seed rather than the
request. On CogVideoX the recovered gravity is -11.4 +/- 0.03 under one seed
and -7.1 +/- 0.2 under another, at every requested value in range. This
replicates across two model families, four axes, and an independent tracker.
A simulator-video negative control recovers the swept parameter with slope
1.0001, so the estimator is not the problem.

**Claimed, and reported as a negative result.** Neither of the two mechanisms
the literature proposes (prior reversion, case clamping) fits. AIC prefers the
prior-reversion shape but held-out R-squared is negative throughout, because
the reversion target is seed- or regime-conditional rather than one global
default. This is reported as the finding, not buried.

**Claimed, and reported as a measurement result.** A single VLM plausibility
rater does not track tracker fit quality on this stimulus distribution.

**No longer claimed.** The previous draft's abstract said "six physics
systems" (it is five systems, six axes) and read as a general statement about
video generators. It now scopes to the three models and the synthetic suite
actually tested, and concedes priority on recovering physics from generated
pixels to Thozhiyoor et al. (CVPR 2026) and Li et al. (ICML 2025).

---

## The objection that decides this paper

Between 37.5% and 100% of clips fail the fit-quality gate depending on model
and axis. On most model-axis pairs there is no slope at all, and on the rest
the slope comes from a survivor subset that is not a random sample.

Two readings are consistent with that, and your data cannot separate them:

1. these models do not condition on a requested physical parameter, or
2. minimalist synthetic 2D scenes are far enough outside their training
   distribution that they cannot render trackable motion of any kind, in
   which case the null slope says little about their physics.

The nuisance ablations rule out rendering scale, guidance, prompt template
and tracker. The negative control rules out the estimator. Nothing rules out
stimulus domain. Thozhiyoor et al. obtained usable trajectories from
current-generation models on photorealistic stimuli where you largely do not.

The Limitations section now states this plainly and names the decisive
experiment: run the same sweep on a photorealistic rendering of these systems,
or on a current-generation generator, and show whether the gate rate falls.
If you have three days and any spare GPU time, that single experiment is worth
more than any further editing.

---

## Files

| File | What it is |
|---|---|
| `main.tex` | The paper. Body ends at the bottom of page 8. |
| `appendix.tex` | Supplementary. Compiles standalone to its own PDF. |
| `preamble.tex` | Shared macros, including the red-flag macros. |
| `main.bib` | Bibliography, 47 entries. Last seven were added in this pass. |
| `main.bbl` | Precompiled bibliography, so one pdflatex pass resolves refs. |
| `wacv.sty`, `ieeenat_fullname.bst` | Venue style files, unmodified. |
| `rebuttal.tex` | Venue rebuttal template, unmodified. Round 1 route only. |
| `physweep_metrics.py` | Metrics, bootstrap, mechanism selection, smoke test. |
| `main.pdf`, `appendix.pdf` | Built PDFs with all red flags visible. |
| `REDFLAGS.txt` | Every outstanding item, with file and line. |

## Building

```
pdflatex main.tex
bibtex   main
pdflatex main.tex
pdflatex main.tex

pdflatex appendix.tex
pdflatex appendix.tex
```

`main.bbl` ships precompiled, so a single `pdflatex main.tex` also resolves
references if BibTeX is unavailable.

**After any edit, re-check the page limit.** Confirm no body text appears on
page 9 of `main.pdf`. WACV rejects papers over eight pages without review, and
the body currently ends within about three lines of the page-8 boundary.

## Running the analysis code

```
python3 physweep_metrics.py            # smoke test, 28 checks
python3 physweep_metrics.py --verbose  # with per-check detail
```

numpy only. The smoke test validates every fitter against closed-form ground
truth and, importantly, checks that `select_mechanism` **can** fire: it detects
prior reversion when prior reversion is really present, detects clamping when
clamping is really present, and returns "neither" on a seed-conditional
default. Without those three checks, "neither everywhere" in the paper would
be uninformative, because a selector that never fires would produce the same
output.

The smoke test also found a real limitation, now documented in the
supplementary: CBI is not identifiable when an out-of-range grid lies entirely
on one side of the in-range band, because the clamp prediction becomes
constant. Only pendulum damping is affected and no reported result depends
on it.

---

## Where each claim lives

| Claim | Where |
|---|---|
| Estimator is valid | Results, "Negative control" |
| No in-range conditioning response | Table 2, and Results opening |
| Gate-dropped rates are a primary result | Table 2 col. 3, Table 3 col. 3 |
| Seed-clustered fixed defaults | Figure 1, "Two distinct failure mechanisms" |
| Reproduces across model families | "Generality across sweep axes", Table 3 |
| Split-default variant | "A third mechanism variant" |
| Neither mechanism fits | Table 4 and its paragraph |
| VLM rater does not track coherence | "The plausibility contrast" |
| Not a tracker/scale/guidance/prompt artifact | "Robustness and ablations" |
| Frame channel does not rescue it | "Conditioning channel" |
| Attrition bounds everything | Limitations, first paragraph |

---

## Before you submit

1. Fill every item in `REDFLAGS.txt`. Nothing was guessed.
2. Verify the seven new bibliography entries. Three carry placeholder
   corporate authors; no author names were invented. WACV desk-rejects
   papers citing non-existent material.
3. Have a human author re-derive Proposition 1 and its supplementary proof
   line by line. The LLM-use statement asserts this was done, and the previous
   appendix carried a note saying it was still outstanding. Make the statement
   true before you rely on it.
4. Ship the per-clip result records with the supplementary code if you
   possibly can. That is the difference between a reviewer taking your numbers
   on trust and being able to check them.
5. Re-check anonymity: no author names, institutions, absolute paths, or
   licence headers in the supplementary code.
6. Confirm the page count one final time on the exact PDF you upload.
7. Get **two or three independent human mock reviews**. Treat anything they
   raise that is unresolved as blocking. Nothing in this pass substitutes for
   that, and the attrition objection above is exactly what a domain expert
   will hit first.

## What was not verified

- No raw results or analysis output were provided with the bundle, so every
  number in the paper was checked for internal consistency only. None was
  reproduced from source. Four numbers that contradicted the tables were
  removed rather than reconciled.
- Proposition 1 was not re-derived line by line during this pass.
- The scoop search read the Thozhiyoor et al. project page in full but not the
  CVPR paper itself, so the precise overlap with your projectile fitter is
  inferred from its abstract and method description.
