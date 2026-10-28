# Resume here (paused 2026-10-28 for CVPR)

The PhysWeep revision for Image and Vision Computing is paused while you write CVPR papers. Data is
archived on Hugging Face (`rasulkhanbayov/physweep-revision-archive`, private). Weights and environments
are deleted, but their exact versions are recorded. To rebuild, see `RESTORE.md`. For where any number
comes from, see `PROVENANCE.md`.

## Where we stopped

- Steps 1–5 of `02_revision_plan.md` are done (validity layer, structured scenes, decoupled seeds,
  pilots, the main text-channel sweep on 9 models + the API-mode tier). Results are in
  `results_v2/STEP1..5_REPORT.md` and `results_v2/main_text_analysis.md`.
- Step 6 (frame-implied channel): code written and CPU dry-run tested (`results_v2/STEP6_REPORT.md`). The
  GPU pilot was **never submitted**; you chose to pause with it unfinished.
- Not started: step 7 (plausibility rater upgrade, Qwen3-VL-30B-A3B), the shaded-style OOD ablation,
  step 9 (dataset release), step 10 (figures from real frames; Figure 2 is yours in PaperBanana),
  step 11 (rewrite in `elsarticle` for IVC), step 12 (final verification).
- `paper/main.tex` is still the submitted WACV text with v1 numbers; only Table 1's ω grid is fixed.

## Open items found while archiving (fix during the rewrite)

`PROVENANCE.md` → "Problems found" lists 12 numbers that do not match the data. They are all small and
none changes a conclusion:
- main.tex: the three plausibility correlations are attached to the wrong models; CogVideoX's scores are
  not "1 or 5, never 2–4" (11 clips scored 3); "within-seed dispersion 0.03–0.13" excludes the paper's
  own ±0.2; "μ̂≈1.80 across the whole grid" holds in-range only.
- appendix.tex: the ω out-of-range grid still says {0.5, 1, 8, 12} (F7 was fixed only in main.tex); the
  VLM pass's "0.3 h" is 0.17 h of logged scoring time.
- STEP1/STEP5 reports: four small slips (46/65 → 45/65 after amendment 3; 360 → 345; label changes
  0–11, not 1–11; Hunyuan median at g = 25 is 3.65).
- Unreproducible from data: the 25.3 GB / 14.25 GB VRAM figures and "A100 40 GB" (v1 never logged them;
  the Panther v1 runs used A100 80 GB PCIe), and the step 3 repeated-draw test (119/120, 0/40), which
  was never saved. To recreate it, add a fixed-seed repeated-draw mode to `v2_design_selftest.py`.
- Licenses (see the archive's README): HunyuanVideo-1.5 outputs may not be shown in the EU/UK/South
  Korea, and LTX-2 has an unclear revenue clause. Resolve both before making any clips public (step 9).
  The appendix's "DynamiCrafter weights: research/non-commercial" is the model-card wording; the weight
  repos themselves carry an Apache-2.0 file.

## First commands when you are back

```bash
cd "/export/home/rakh90100/Rasul_research_ideas (2)/4-ICLR"     # after git clone/pull
bash REVISION/restore.sh data              # 9.5 GB, sha256-checked
bash REVISION/restore.sh check             # all numbers recompute; counts must match PROVENANCE.md
# for step 6 (frame-channel pilot), on a shared server:
bash REVISION/restore.sh envs
bash REVISION/restore.sh weights step6     # ~319 GB, several hours
cd REVISION/slurm/v2
sbatch --array=0-0 20_sweep_a100.sh "$PWD/pilot_frame_a100.tasks"
sbatch --array=0-2 20_sweep_h200.sh "$PWD/pilot_frame_h200.tasks"
```

Then ask Claude to check the pilot (key-frame errors first) and decide between a full frame-channel
sweep of 304 clips (~46 GPU-h) or 152 (~23 GPU-h).
