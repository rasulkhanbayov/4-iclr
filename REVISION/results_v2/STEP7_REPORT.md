# Step 7 — Plausibility rater upgrade (plan E-D), run 2026-11-27

## What was run

Both raters scored every saved `main_text` clip: 9 generators × 304 clips = 2,736 clips per rater, 0
errors (SLURM job 482581, A100 80GB). Raters, pinned in `env/hf_snapshots.json`:

| rater | repo @ commit | role |
|---|---|---|
| `qwen3vl_30b_a3b` | Qwen/Qwen3-VL-30B-A3B-Instruct @ 9c4b90e1 | the plan's larger current rater |
| `qwen25vl_7b` | Qwen/Qwen2.5-VL-7B-Instruct @ cc594898 | v1's rater, re-run on the v2 clips |

Prompt: v1's verbatim (sha 152c79cfd04b628f, checked by `--self-check`). Frames: min(T, 32) uniformly
spaced, even count, long side 448 px, real timestamps. Score: greedy digit; `expected` = Σ k·p_k over the
renormalized probabilities of "1".."5" at the answer position. Code: `experiments/v2_rate_plausibility.py`;
analysis: `experiments/v2_plausibility_analysis.py` → `main_text_plausibility.{json,md}` (all numbers below
are read from that file).

## Result

The plan's decision rule: "If it also fails to track validity, the claim generalizes; if it succeeds, the
claim is restricted to the 7B rater." Outcome: **the claim generalizes to the larger rater, and the larger
rater is not better than the smaller one.**

- **Validity (AUROC of the expected score, valid vs. not valid).** Qwen3-VL-30B: 0.31–0.70 across the nine
  generators; the CI lies above 0.5 for 3 generators and **below** 0.5 for 3 (Cosmos 0.31, Hunyuan 0.38,
  DynamiCrafter 0.40: clips that pass the validity checks get *lower* plausibility). Qwen2.5-VL-7B:
  0.42–0.83, above 0.5 for 6 generators, below for 1. Neither rater separates measurable from broken clips
  consistently; the direction itself depends on the generator.
- **Faithfulness (Spearman ρ between expected score and relative parameter error, valid clips, ranked
  within model × system and pooled).** Qwen3-VL-30B: the CI includes 0 for all 9 generators. Qwen2.5-VL-7B:
  CI includes 0 for 7 of 9; CogVideoX (ρ = −0.29) and LTX-2 (ρ = −0.25) are weakly negative, i.e. slightly
  more plausible clips are slightly more faithful there. With 18 tests at the 5% level about one false
  positive is expected; the two hits are weak and do not share a rater-wide pattern.
- **Score use.** Qwen3-VL-30B almost never answers 2 (6 of 2,736) and gives 5 to 53% of clips; Qwen2.5-VL-7B
  almost never answers 5 (25 of 2,736). Each rater uses a different, compressed part of the scale — the
  same kind of degenerate use v1 found (Qwen2.5-VL-7B never answered 4 on the v1 clips).
- **Agreement between the two raters** is low: quadratic-weighted κ from −0.13 (Hunyuan) to 0.43 (Cosmos);
  Spearman ρ of expected scores −0.04 to 0.81.

## Caveats

- Bootstrap CIs resample clips; clips that share a scene seed and θ are not independent, so the CIs are
  somewhat too narrow. This does not affect the qualitative reading above (no rater-wide effect).
- One prompt, zero-shot. A prompt that names the requested parameter could rate faithfulness more directly;
  that is a different task (and would leak θ to the rater), and it is not tested here.
- No human ratings. The claim is about automated VLM raters, as in v1.

## For the paper

Replace v1's single-rater statement with: two raters (7B and a 30B mixture-of-experts model), nine
generators; plausibility does not track parameter faithfulness for either rater (0/9 and 2/9 weak
associations), tracks measurement validity inconsistently and sometimes inversely, and the two raters
agree poorly with each other. Any number used in the text must be registered in
`experiments/reproduce_numbers.py` first.
