# Image-generation prompts for PhysWeep (paste into your image tool)

Three prompts below: (1) a literal architecture/pipeline diagram, (2) a
creative/conceptual illustration, (3) a three-panel failure-taxonomy
figure that fills a real gap in the paper (the three distinct failure
modes are described in prose across three separate paragraphs but never
shown together in one comparative figure). All are grounded in the
paper's actual method and real findings (main.tex) -- nothing invented.
Written for a
generic text-to-image model; trim or adjust terminology if your tool has
different conventions (aspect ratio flags, negative-prompt fields, etc).

---

## Prompt 1 — Architecture / pipeline diagram

```
Clean, modern technical diagram for a machine learning research paper, in
the style of a Nature/NeurIPS figure: flat vector illustration, white
background, thin dark-gray outlines, a restricted color palette of
muted blue, orange, and green accents, generous whitespace, sans-serif
labels, no photorealism, no 3D rendering, no drop shadows.

Show a left-to-right pipeline with five stages connected by clean arrows:

1. "GROUND TRUTH θ" — a small icon of a control dial or slider with a
   numeric value, representing a swept physical parameter (e.g. gravity).

2. "DETERMINISTIC RENDERER" — an icon of a simple 2D physics scene: a
   single high-contrast dark disk on a plain background above a thin
   ground line, mid-fall along a dashed parabolic arc, suggesting a
   synthetic simulated video frame.

3. "FROZEN VIDEO GENERATOR" — a stylized black box or locked padlock icon
   labeled "frozen weights", with a small film-strip / video-frames icon
   coming out of it, colored in a warm orange to visually separate it as
   the untrusted/black-box component from the rest of the pipeline.

4. "TRACKER + PHYSICS FIT" — an icon of a magnifying glass or crosshair
   tracking a moving dot across a few overlaid frames, next to a small
   curve-fitting icon (a scatter of points with a fitted line through
   them), representing label-free recovery of the parameter from pixels.

5. "RECOVERED θ̂ + METRICS" — a small results-card icon showing abstract
   bar-chart and error-bar glyphs, labeled with placeholder metric tags
   like "PRE", "slope", "SDI" in small caps.

Between stage 4 and stage 1, draw a dashed feedback arrow curving back
underneath the whole diagram, labeled "compare θ̂ against known θ", closing
the loop to show this is a measurement/audit process, not a generation
pipeline.

Add a small red-outlined callout box beneath stage 4 reading "fit-quality
gate: R² ≥ 0.8" with a thin dotted line pointing to the tracker+fit stage,
indicating that outputs below this threshold are excluded and marked
non-physical rather than force-fit.

Overall composition: single row, evenly spaced, landscape orientation
(wide aspect ratio, roughly 16:9 or 2:1), suitable as a paper's Figure 2
"how the audit works" diagram. No people, no logos, no watermarks, no
title text overlay beyond the stage labels described above. High
resolution, crisp vector-style edges, print-quality, readable at small
size in a two-column academic PDF.
```

---

## Prompt 2 — Creative / conceptual illustration

```
Conceptual, editorial-style illustration for the cover or teaser of a
computer vision research paper about AI video generators failing to
obey requested physics. Semi-abstract, painterly-but-clean digital
illustration style (think a high-end tech-magazine cover, not a cartoon
and not photorealistic), moody but not dark, dominant deep blue and
warm amber color palette, soft directional lighting, generous negative
space, no text or logos anywhere in the image.

Central subject: a single glowing ball or sphere caught mid-fall in front
of a simple minimalist backdrop that reads as a "requested" trajectory —
a faint, thin dashed arc of light showing the smooth path gravity SHOULD
produce (labeled subtly if any text at all, but prefer NO text). 

Overlapping and slightly out of phase with this dashed ideal arc, show two
or three semi-transparent ghost copies of the same ball frozen at
DIFFERENT points along a flatter, wrong trajectory — as if the object
ignored the requested arc and instead settled onto a fixed, shallow, almost
level path, each ghost copy rendered in a slightly different accent hue
(one in amber/orange, one in cool blue, one in soft violet) to suggest
that each copy represents a different hidden "seed" producing its own
fixed wrong answer, independent of what was actually asked for.

In the background, faintly suggest a grid of a few dozen tiny thumbnail
video-frame rectangles fading into blur and darkness at the edges of the
canvas, like a wall of many generated clips, most of them dim/desaturated
(representing clips that failed and were discarded) and a small handful
glowing brighter (representing the few that were confidently, but
wrongly, generated) — this should read as atmosphere/texture, not as a
literal diagram, and should not compete with the central ball composition.

Mood: quietly uncanny and a little unsettling in a sophisticated way — the
sense of something that looks confident and physically smooth but is
subtly, deterministically wrong, like a magic trick where the same wrong
card keeps appearing no matter which one you pick. Avoid horror, avoid
glitch-art/corruption aesthetics, avoid neon-cyberpunk cliches, avoid any
readable text, UI, HUD elements, or numbers in the image.

Composition: portrait or square aspect ratio suitable for a paper's
front-page teaser graphic or a conference poster header. Balanced,
centered subject, cinematic soft lighting, high production value, subtle
film-grain texture, no camera/lens distortion effects, no photorealistic
humans or hands, no readable typography of any kind.
```

---

## Prompt 3 — Three-panel failure-taxonomy figure (fills a real gap)

The paper's Results section describes three distinct failure modes in
three separate paragraphs ("The failure is seed-locked, not untrackable
noise," "The signature crosses architectures and physical systems," "A
third variant: a split, not a single, default") but never shows all three
side by side in one figure. This prompt asks for exactly that comparison,
as a clean three-panel scientific chart (not the painterly style of
Prompt 2) suitable as a genuine new Figure 2 or Figure 3 in the paper.

```
Clean, minimal scientific figure for a machine learning research paper,
flat vector chart style, white background, thin dark axes, a restricted
muted color palette (slate gray for reference/identity lines, burnt
orange and royal blue and plum purple for data series), sans-serif
labels, no photorealism, no gradients, no drop shadows, no decorative
elements — this should look like it belongs in the same figure family as
a matplotlib/seaborn scientific plot, precise and legible at small size
in a two-column academic PDF.

Compose exactly THREE side-by-side panels of equal size, arranged in a
single horizontal row, each panel a small labeled line/scatter chart with
its own x-axis "requested parameter θ" and y-axis "recovered parameter θ̂",
and a thin diagonal dashed gray reference line in every panel showing
what a perfectly faithful response would look like (the identity line,
θ̂ = θ).

PANEL 1, titled "Near-total inertia" (LTX-Video): a nearly flat, low, pale
line hugging the x-axis floor, barely rising at all as the x-axis value
increases — depicting a generator that produces almost no real fall or
motion regardless of the requested value. Sparse, faint data points
scattered right at this near-zero floor. Small caption beneath the panel:
"conditioned object barely moves, whatever is asked".

PANEL 2, titled "Seed-locked convergence" (CogVideoX, DynamiCrafter): TWO
distinct horizontal bands of tightly clustered data points, one band in
royal blue sitting at a fixed height and one band in burnt orange sitting
at a different fixed height, BOTH bands staying essentially flat and
horizontal all the way across the x-axis range (they do not follow the
diagonal identity line at all) — depicting two different random seeds
each locking onto their own fixed wrong answer, confidently and
consistently, independent of what was requested. Each band should look
tight and confident (small vertical scatter within the band), not noisy.
Small caption beneath the panel: "confident motion, but the wrong fixed
value depending only on the seed".

PANEL 3, titled "Split default" (DynamiCrafter, inclined slide): ONE plum
purple horizontal band on the LEFT portion of the x-axis (the "in-range"
region, marked with a subtle lighter background shading and a small
"in-range" label), which then makes a small step to a DIFFERENT, slightly
higher plum-purple horizontal band on the RIGHT portion of the x-axis (the
"out-of-range" region, marked with a subtle darker background shading and
a small "out-of-range" label) — depicting a single seed that locks onto
one fixed value in-range and an entirely different fixed value
out-of-range, rather than one constant default across the whole range.
Small caption beneath the panel: "one default in-range, a different
default out-of-range".

Add a single shared figure-level caption strip beneath all three panels
reading (as small, plain sans-serif text): "Three distinct ways generators
ignore the request: none of them follow the dashed faithful line." Do not
add any other text, legends, numbers, logos, or watermarks beyond what is
explicitly described above. Landscape orientation, wide aspect ratio
(roughly 3:1 for the three panels together), high resolution, crisp
vector-style edges, print-quality.
```

---

## Notes on grounding (why these details, not invented)

- Prompt 1's five stages map exactly to the pipeline described in
  `main.tex` Section 4 ("Suite, Pipeline, and Protocol") and Appendix S1's
  `Algorithm 1`: render → generate (frozen) → track → fit → compute
  metrics, with the R²≥0.8 fit-quality gate explicitly called out as a
  real, load-bearing part of the method (not decorative).
- Prompt 2's "one true arc, several fixed wrong ghost trajectories, each a
  different color" concept is a direct, faithful visual metaphor for the
  paper's actual headline finding: recovered θ̂ clusters by *sampling seed*
  into a small number of fixed wrong values, flat against the requested
  θ (see Figure 1 / Section 6, "The failure is seed-locked, not
  untrackable noise"). It is not a generic "AI hallucination" image — it
  specifically encodes seed-conditional convergence, which is the paper's
  real contribution.
- The "wall of thumbnail clips, some dim/discarded, a few glowing" detail
  reflects the trackability-gate finding (most clips are gated out as
  non-physical; a minority survive and are the ones showing the
  seed-locked signature) — grounded in Table 1 / Table 3's real
  trackability percentages, not generic flavor text.
- Prompt 3's three panels are each a direct visualization of a real,
  already-published paragraph in `main.tex`'s Results section, not a
  composite or invented taxonomy: Panel 1 is "The failure is seed-locked,
  not untrackable noise" (LTX-Video's near-total-inertia description);
  Panel 2 is the same paragraph's CogVideoX/DynamiCrafter seed-clustering
  finding, plus its generalization in "The signature crosses architectures
  and physical systems" (the two flat bands are literally what
  $\hat g\approx-11.4\pm0.03$ and $\hat g\approx-7.1\pm0.2$, or the
  bouncing-ball $[0.97,1.00]$ convergence, look like when plotted); Panel
  3 is "A third variant: a split, not a single, default"
  ($\hat\mu\approx1.80$ vs. two clusters at $\approx4.7$ in-range and
  $\approx7.6$ out-of-range). No panel represents a system or number not
  already in the paper.

## Suggested next step

If PaperBanana (or whatever tool you're using) supports aspect-ratio or
style-strength parameters separately from the prompt text, set:
- Prompt 1: wide/landscape, low style-strength / high prompt-adherence
  (it needs to stay a legible diagram, not get overly stylized).
- Prompt 2: portrait or square, higher style-strength is fine (it's meant
  to be evocative, not literal).
- Prompt 3: wide/landscape (roughly 3:1), low style-strength / high
  prompt-adherence, same as Prompt 1 — this is meant to read as a real
  scientific chart, so over-stylizing it will undermine its usefulness as
  an actual paper figure. If the tool tends to add unwanted numeric axis
  tick labels or legends despite the "no other text" instruction, regenerate
  rather than trying to fix it post hoc, since illegible or wrong numbers
  baked into the image are worse than none.

Generate a few variations of each and pick the one that reads clearly at
small size (test by shrinking to roughly thumbnail scale) before dropping
it into the paper or a poster.
