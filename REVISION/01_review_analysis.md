# Phase 1 — Review analysis (WACV 2027, Submission 2935, rejected)

Date: 2026-10-15. Source of reviews: `reviews.txt`. Every verdict below was
checked against the paper source, the code, or the data. Line references are
to `.tex` source lines (the reviewers cite PDF margin numbers, which differ).

## 0. Which version the reviewers read

**`VERSION3/main.tex` (+ `VERSION3/appendix.tex`) is the submitted version.**
Evidence: both phrases the reviewers quote exist only there, "confirmed by
frame inspection" (`VERSION3/main.tex:751`, reviewer's L413) and "disagrees in
sign" (`VERSION3/main.tex:882`, reviewer's L511), and SDI/FDI, which TFF6
discusses, appear only in VERSION3 (`main.tex:561-572`). Paper ID 2935 is set
at `main.tex:20`. The `wacv-2027-author-kit-template/` copy has none of these.

**Confirmed against the submitted PDF** (`submitted/2935_PhysWeep_Does_a_Video_Gen.pdf`,
10 pages): "confirmed by frame inspection" sits at PDF line 412-413 and
"disagrees in sign" at line 510-511, exactly where the reviewer cites them.
One difference from `VERSION3/`: the submitted Figure 2 raster differs from
`VERSION3/prompt1_architecture_diagram.png` (see T5).

## 1. Summary table

Verdicts: **A** accurate, **PA** partly accurate, **I** inaccurate, **O** opinion.
"#" = how many of the four reviews (AC, Novy, TFF6, skin) raise it.

| ID | Reviewer | Point | Verdict | Severity | # | Fix type |
|---|---|---|---|---|---|---|
| M4/N2 | AC, Novy | Seed changes the conditioning scene as well as the noise | **A** | **blocking** | 2 | new experiment + reframing |
| N1 | Novy | A good curve fit does not prove a reliable measurement | **A** (worse than stated, §3) | **blocking** | 1 (+TFF6 T3/T6) | new checks + reanalysis + new figure |
| T3 | TFF6 | Seed→physics is not new; glitchy/deformed objects change tracked physics | **PA** | major | 1 (+AC M5) | reframing + reanalysis |
| T1/M3 | TFF6, AC | No frames or visual examples in paper or supplement | **A** | **blocking** | 2 | new figures |
| K1/M2 | skin, AC | No clear dataset contribution for a Datasets track | **A** | **blocking** | 2 | reframing + new artifact (or venue switch) |
| M1/K3/M5 | AC, skin | Problem → motivation → method → validation unclear | **O** (supported) | major | 2 | writing/framing |
| K2/M7 | skin, AC | Evaluated generators are outdated | **A** | major | 2 (+TFF6) | new models |
| T2/M6 | TFF6, AC | "Model-agnostic / black-box" conflicts with testing only open, seed-controllable models | **PA** | major | 2 | reframing + new metric tier + new models |
| T6 | TFF6 | Two trackers disagree in sign; why? | **A** (and larger than the paper says) | major | 1 | reanalysis + new figure |
| N3/K4 | Novy, skin | Figures 1–2 look AI-generated / poor layout and quality | **A/O** | minor→major | 2 | new figures |
| T4 | TFF6 | RSS, FDI, SDI used before definition | **PA** | minor | 1 | writing |
| T5 | TFF6 | "ideo" typo in Figure 2 | **A** (confirmed in submitted PDF) | minor | 1 | new figure |
| T7 | TFF6 | Only Qwen2.5-VL-7B as VLM rater | **A** (fact) / **PA** (implication) | minor | 1 | new experiment or scope-down |
| N4 | Novy | Niche aspect | **O** | minor | 1 | framing |

Strengths (keep): S1 plausibility-vs-faithfulness distinction is valuable (AC,
Novy); S2 honest exposure of evaluation limits, trackability rate, positive
control (Novy); S3 PRI/CBI failure-form framing is rigorous (TFF6); S4 SDI is a
good contribution (TFF6); S5 pre-committed outcomes incl. "neither" (TFF6);
S6 second-tracker check (TFF6, but see §3: it now cuts against some claims);
S7 easy to follow (skin, which contrasts with the AC's clarity complaint).

## 2. Point-by-point verdicts with evidence

### Meta-review (AC 9NWq)

**M1 — Problem, importance, and how the audit resolves it are unclear. O (supported), major.**
The abstract (`main.tex:64-92`) introduces "prior reversion", "case-based
clamping", "leave-one-out selection rule" and "seed-conditional" before any of
them is defined. The intro reaches the method at line 280 and lists three dense
contributions (297-330), two of them about failure-mechanism formalism rather
than the user-facing problem. Skin says the opposite ("easy to follow"), so this
is a judgment, but it is shared by two of four reviews and the AC.

**M2 — Dataset contribution not identified. A, blocking.** See K1.

**M3 — No frames or visual examples; visual-inspection claims uncheckable. A, blocking.** See T1.

**M4 — Seed changes the conditioning scene as well as the sampling noise. A, blocking.** See §2 Novy N2.

**M5 — Central finding not clearly motivated. O, major.** The paper motivates
the *measurement* (`main.tex:256-278`) but the seed finding is introduced as a
result, with motivation only via `xu2025goodseed` (`main.tex:292-295`).

**M6 — Model-agnostic claim conflicts with excluding closed models. PA, major.** See T2.

**M7 — Generators not current. A, major.** See K2.

### Reviewer Novy (Weak Reject)

**N1 — Passing the curve-fit test does not establish reliable measurement. A, blocking.**
The paper uses fit quality as evidence of correctness in several places:
Figure 1(b) caption "at a fit quality that rules out a tracking artifact"
(`main.tex:242-243`); the tightness argument "individual-clip fit $R^2$ up to
1.000 ... Confident, well-fit, seed-locked motion is what a model ignoring θ
produces" (`main.tex:762-773`). The positive control (`main.tex:719-725`)
validates the tracker only on clean renderer output, never on generated clips.
**The data show the reviewer is right, with concrete failures (§3, F3–F5):**
high-$R^2$ fits produced by an object breaking into fragments, a duplicated
object, and a ballooning object. Also the gated DynamiCrafter $\hat e=10.28$
outlier the paper itself excludes by hand (`main.tex:244-245`).

**N2 — Same seed controls scene rendering and generation. A, blocking.**
- Renderer: `physweep/render.py:103` seeds `rng` from `seed`; projectile draws
  `x0`, `vx` from it (`render.py:110-111`); similarly bouncing ball (`172-173`),
  pendulum (`134-138`), spring (`219-222`), slide (`255-259`).
- Generator: the same integer seeds the generator, e.g.
  `experiments/e0_pilot.py:133-139`, `e0_pilot_cogvideox.py:74-81`,
  `e0_pilot_dynamicrafter.py:164-168` (passed as `--seed`, line 76),
  `e3e5_extended.py:341,383-389`, `e4_generality.py:116-121`.
- Measured (scratch script, all six axes): **frame 0 is pixel-identical across
  every θ for a fixed seed, and differs across seeds** (max |Δ| = 0 vs 215
  grey levels). The disk's starting x moves 52–78 px (projectile), 96–162 px
  (bouncing ball), and similar for the other systems.
- So under text conditioning, the conditioning image is a function of the seed
  alone, and θ enters only through the prompt. "Seed" in the paper is
  (scene layout × noise), perfectly collinear, and SDI cannot separate them.
  The paper's own text concedes the coupling ("we draw $m$ seeded initial
  conditions and generations", `main.tex:434`) but the abstract and Figure 1
  attribute the effect to the "*sampling* seed" (`main.tex:81`, `236-237`).

**N3 — AI-style figures. A.** Figure 2 is an image-model output:
`VERSION3/figure_drafts/image_gen_prompts.md` ("Prompt 1 — Architecture /
pipeline diagram") produced `prompt1_architecture_diagram.png`, a 1327×522
raster placed at full text width (`main.tex:614`). Its text is garbled
("untrusted/video from black-box").

**N4 — "Interesting evaluation, but on a niche aspect." O, minor.** Addressed by
the motivation rewrite (controllable/physics-claiming generators, robotics and
simulation use).

### Reviewer TFF6 (Reject)

**T1 — No image or video frame in the paper or supplement. A, blocking.**
`main.tex` has one `\includegraphics` (the AI pipeline diagram, line 614); Figure 1
is plotted curves (lines 108-254). `appendix.tex` has no `\includegraphics` or
tikz figure. `VERSION3/supplementary_code/` contains code and JSON only, no
image or video. Yet the project holds 630 generated clips
(`results/e3e5_videos/`) and 9 debug frames (`results/e0_debug_evidence/`).
Both quoted claims rest on unshown evidence: L413 → `main.tex:750-751` "confirmed
by frame inspection"; L511 → `main.tex:881-884`.

**T2 — "Model-agnostic" and "without training access" vs. no closed models. PA, major.**
The claims exist: "model-agnostic audit" (`main.tex:92`), "without training
access" (`main.tex:382`), "we assume no access to its weights, data, or
activations" (`main.tex:399`). But the paper **never says** closed models were
excluded *because seeds cannot be controlled*. It just tests "three frozen open
generators" (`main.tex:653`), and closed models are not mentioned anywhere in
`main.tex` or `appendix.tex`. The reviewer's inference is still substantively
right: the crossed design and SDI (`main.tex:517-519`, `561-572`) need
repeatable seeds, which closed APIs generally do not guarantee. Their
suggestion works: PRE, β, ρ, EG and trackability need no seed, so a seed-free
tier can run on any API.

**T3 — Seed controlling physics is not new; a glitchy or deformed ball changes the tracked physics. PA, major.**
- Novelty: noise is known to govern motion. [Go-with-the-Flow](https://arxiv.org/pdf/2501.08331)
  (CVPR 2025) controls motion through noise alone; [Open-Sora 2.0](https://arxiv.org/pdf/2503.09642)
  and [LatSearch](https://arxiv.org/pdf/2603.14526) search seeds for motion quality.
  I found no prior work showing a seed *overriding an explicitly requested
  physical parameter*, so the narrow claim may be new. "Seed affects motion"
  is not.
- Mechanism: the "glitchy ball" hypothesis is **directly visible in our data**
  (§3, F3–F5). It does not explain every cluster (DynamiCrafter projectile
  seed 3 and the CogVideoX g=25 frames show one clean object), but it does
  explain several of the paper's headline clusters.

**T4 — RSS, FDI, SDI used before definition. PA, minor.**
RSS is never expanded (`main.tex:476`, `appendix.tex:74`); FDI is never
expanded anywhere (`main.tex:563`, `appendix.tex:295`); AIC (481) and ICC (1001)
are never expanded either. SDI *is* spelled out before its abbreviation is used
(`main.tex:561` → `563`), so that part is inaccurate, except that Figure 2's
raster shows "SDI" and "PRE" labels without expansion.

**T5 — "ideo" typo in Figure 2. A.** *Corrected 2026-10-15 after reading the
submitted PDF* (`submitted/2935_PhysWeep_Does_a_Video_Gen.pdf`, page 5): the
embedded raster reads "untrusted/ideo from black-box". The PNG left in
`VERSION3/` was regenerated after submission and reads "untrusted/video", which
is why the first check missed it. The figure is being replaced entirely.

**T6 — Why do two trackers disagree in sign if output is seed-locked? A, major; the disagreement is larger than the paper reports.**
From `results/e5a_cotracker_comparison.json`, on rows where *both* trackers
clear the gate: DynamiCrafter projectile r = **−0.975** (n=10), DynamiCrafter
inclined slide r = **−0.600** (n=15), DynamiCrafter bouncing ball r = −0.525
(n=3); LTX agrees (0.984, 0.997). The paper reduces this to "disagrees in sign
on a second seed" (`main.tex:881-884`), and the abstract still claims the
signature reproduces "across ... an independent tracker" (`main.tex:82-83`).
The cause is now identified by frame inspection (F3, F4): the blob tracker
averages object fragments and duplicates, while CoTracker3 follows one point.

**T7 — Only Qwen2.5-VL-7B as the VLM baseline. A (fact), PA (implication).**
Only one rater was used (`main.tex:865`; disclosed at `959-961`). The *text*
scopes the claim to "this rater ... here" (`main.tex:875`), but the section
heading "A plausibility rater sees none of this" (864) and the abstract
("a plausibility score is structurally blind", `main.tex:90-91`) generalize
beyond one 7B rater.

### Reviewer skin (Weak Reject)

**K1 — No clear dataset contribution; track fit. A, blocking.** The word
"dataset" appears only in LaTeX comments and the track option (`main.tex:2,11,27`).
Contribution 1 is "a reusable audit artifact" of renderers and code
(`main.tex:299-306`). No generated-video set, annotations, or benchmark
split is released or described.

**K2 — Table 2 models outdated. A, major.** Table 2 (`tab:coverage`,
`main.tex:683-700`) lists LTX-Video, CogVideoX-5B-I2V and DynamiCrafter-512. The
paper concedes this (`main.tex:925-930`). Several newer open I2V models exist
(e.g. Wan 2.x I2V, HunyuanVideo-I2V, later LTX/CogVideoX releases). Exact
checkpoints and VRAM fit are to be confirmed in Phase 2.

**K3 — Problem–motivation–method–validation narrative unclear. O, major.** See M1.

**K4 — Figures 1 and 2 need better layout and quality. A/O, minor (major in aggregate with N3, T1).**
Figure 1 is a three-panel tikz drawn on a ~35-unit-wide canvas and shrunk with
`\resizebox{0.995\textwidth}` (`main.tex:110`), so its text renders very small.
Figure 2 is a low-resolution AI raster (N3).

## 3. Issues I found while checking (not raised by reviewers)

These change the risk profile of the central claim and must be addressed.

- **F1 — The conditioning frame never depends on θ.** Measured for all six axes
  (frame 0 identical across θ). Text conditioning therefore asks the model to
  infer a parameter from words alone. This strengthens N2.
- **F2 — The scenes contain no physical structure.** `_blank_canvas`/`_draw_disk`
  (`render.py:40-66`) draw only a dark disk above a grey ground strip. There is
  no slope for the inclined slide, no rod or pivot for the pendulum, no spring.
  The system identity exists only in the prompt. This strongly supports TFF6's
  out-of-distribution concern and is a likely contributor to the low
  trackability.
- **F3 — DynamiCrafter projectile seed-1 "cluster" is object fragmentation.**
  Clip `dynamicrafter_projectile_seed1_6.mp4` (g=7): blob ĝ=4.24 at $R^2$=0.98,
  but the ball visibly breaks into a spray of droplets. The blob centroid tracks
  the spray, and CoTracker3 reads −1.29. Seed 3 (ĝ≈0) is a single static ball,
  and both trackers agree.
- **F4 — The named "split-default" variant (`main.tex:790-796`) is a duplicated
  object.** Clip `dynamicrafter_inclined_slide_seed0_15.mp4` shows two disks.
  Blob μ̂=4.76 vs CoTracker3 1.24 on the one jointly gated clip. The paper's
  "third variant" is very likely a tracking artifact.
- **F5 — High-$R^2$ apparent faithfulness can be an artifact too.** LTX seed 4
  projectile (e3e5 run) shows blob ĝ rising with g (0.54→14.24, $R^2$ 0.88–0.96),
  but the disk balloons and, at g=20, splits in two. CoTracker3 fails the gate
  on all of them.
- **F6 — Figure 1(a)'s CogVideoX clusters have no saved video and no
  second-tracker check.** The E0 run stored no `video_path`
  (`results/e0_pilot_cogvideox.json`), and the later e3e5 CogVideoX projectile
  run gated 0/40. The only visual evidence is three stills
  (`results/e0_debug_evidence/cogvideox_g25_seed0_*.png`), which do show one
  clean ball falling and landing. This is the paper's strongest panel, but it
  needs re-generation with videos saved.
- **F8 — CogVideoX was fitted with the wrong time step (found 2026-10-15,
  Phase 3 step 4).** `experiments/e0_pilot_cogvideox.py:95` fits CogVideoX
  output with the renderer's time axis (`t_gt`, dt = 1/24 s), but
  CogVideoX-5B plays at 8 fps. Since ĝ ∝ 1/dt², the published CogVideoX values
  (e.g. ĝ ≈ −11.4, "close to Earth gravity") correspond to about −1.3 m/s² in
  the model's own real time. Scale-free conclusions are unaffected (slope ≈ 0,
  Spearman ρ, seed shares). Absolute PRE and Figure 1(a)'s comparison of |ĝ|
  against the requested g are affected. More generally, the time base of a
  generated clip is a convention: v2 uses each model's declared playback rate,
  records it per clip, and treats scale-free statistics as primary.
- **F7 — Table 1 lists pendulum-ω out-of-range values {0.5, 1, 8, 12}**
  (`main.tex:597`), but the grid actually run is {8, 12}
  (`physweep/configs/systems.yaml:30`).

## 4. What the reviewers actually agree on (why it was rejected)

1. **The headline seed finding is not established** (AC, Novy, TFF6). The seed
   is confounded with the scene (N2, confirmed in code). The "glitchy object"
   alternative (T3) is confirmed in our own clips (F3–F5). Good fits were used
   as proof of correct measurement (N1). After my checks this is the most
   serious problem: some published clusters are tracking artifacts.
2. **No visual evidence** (AC, TFF6; figure complaints from Novy, skin). The
   claims of frame inspection and tracker behaviour cannot be checked by a
   reader, and the existing figures look AI-generated.
3. **Unclear problem, motivation, and contribution type** (AC, skin; TFF6
   implicitly). Especially, no dataset contribution for a Datasets-track paper.
4. **Model scope** (AC, TFF6, skin). Three 2023–2024 open models; a
   "model-agnostic" claim with no closed or current models.

One-off comments: undefined acronyms (T4), Figure 2 typo (T5),
single VLM rater (T7), "niche" (N4).

**What survives and should anchor the revision:** the
plausibility-vs-faithfulness distinction, the label-free recovery pipeline with
a positive control, trackability as a reported metric, the PRI/CBI framing and
pre-committed outcomes, and SDI as a statistic, once "seed" is split into
scene and noise.

## 5. Open questions for you before Phase 2

1. Do you have the submitted PDF (for Figure 2 and the line-number mapping)?
2. Which venue and deadline next? The track question (Datasets vs main) depends on it.
3. What is the GPU budget? Fixing N2/N1 properly needs new generation runs
   with videos saved.
