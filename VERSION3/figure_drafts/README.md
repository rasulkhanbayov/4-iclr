# Figure drafts (not yet in main.tex)

Standalone TikZ figures, each compilable on its own via `standalone.tex`
(pass the figure's `.tex` file as an argument, or just build `preview.tex`
to see all of them on one page). None of these are wired into `main.tex` or
`appendix.tex` -- copy in whichever ones you want, where you want them.

All numbers used are the paper's own real, already-published results
(pulled from `main.tex`'s Results section and Table 3) -- nothing here is
invented data. Where a figure needs finer per-clip detail than what's in
the paper's tables (e.g. the seed-cluster scatter), the underlying values
are the same reconstructions documented in `CLAUDE.md`.

## Contents

1. **`fig_pipeline.tex`** -- creative/explanatory: the full audit pipeline
   as a flow diagram (theta -> render -> generate -> track+fit -> theta_hat
   -> metrics), a good Figure-2-style "how it works" diagram for the
   Suite/Pipeline section.
2. **`fig_dataset_examples.tex`** -- dataset examples: a 2x3 grid of
   schematic frame-strip sketches, one per system (projectile, pendulum,
   bouncing ball, spring-mass, inclined slide), showing what a conditioning
   sequence + swept theta looks like for each.
3. **`fig_seed_scatter.tex`** -- results example: a clean scatter/strip
   plot of recovered theta-hat vs requested theta for the CogVideoX
   projectile seed-clustering result (the same data as Figure 1 panel a,
   but as a standalone, more classically "results plot" style figure with
   all 5 seeds shown, not just the 2 headline ones).
4. **`fig_mechanism_shapes.tex`** -- creative/explanatory: a clean 3-panel
   schematic of prior reversion vs case clamping vs seed-conditional
   default, redrawn as a cleaner standalone version of Fig 1 panel (c),
   suitable for the Metrics or Problem section.
5. **`fig_sdi_bars.tex`** -- results example: a horizontal bar chart of the
   8 adjudicated pairs' SDI values, colored by whether they clear the 0.6 /
   0.3 reading thresholds from EXPERIMENTS.md -- a compact alternative or
   companion to Table 3 for a talk/poster or as a supplementary figure.
6. **`fig_coverage_heatmap.tex`** -- results example: the coverage table
   redrawn as an actual heatmap figure (not a text table), which reads
   faster than tab:coverage for a reader skimming.
7. **`fig_failure_taxonomy.tex`** -- creative: a small icon-style taxonomy
   figure summarizing the three failure modes found (near-total inertia,
   seed-locked convergence, split-default), one icon+label per mode, meant
   as a compact visual summary for the abstract-adjacent teaser space or a
   talk slide.

## Build

```
cd figure_drafts
pdflatex preview.tex     # all seven on one multi-page PDF, if pdflatex is available
```

No `pdflatex` was available in the environment these were authored in, so
none of these have been compiled or visually verified -- check spacing,
overlaps, and column-width fit before using any of them for real.
