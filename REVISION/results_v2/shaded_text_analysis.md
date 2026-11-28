# Analysis of run `shaded_text`

Metrics on VALID clips only. β = in-range faithfulness slope (1 = faithful, 0 = ignores the request).
Shares = chance-corrected variance shares of θ̂ (request / scene / noise); p-values from label permutation.

| model / system | clips | valid | 2nd-tracker confirmed | β in-range [95% CI] | Spearman ρ | PRE in | PRE out | request share (p) | scene share (p) | noise share (p) |
|---|---|---|---|---|---|---|---|---|---|---|
| cosmos2_2b/bouncing_ball | 48 | 0 | 0 | — | — | — | — | — | — | — |
| cosmos2_2b/inclined_slide | 48 | 27 | 23 | -0.01 [-0.07, 0.06] | 0.37 | 1.17 | 0.63 | 0.53 (0.004) | 0.06 (0.323) | 0.06 (0.068) |
| cosmos2_2b/projectile | 56 | 2 | 1 | — | — | — | 0.96 | — | — | — |
| dynamicrafter/bouncing_ball | 48 | 3 | 0 | — | — | — | 0.62 | — | — | — |
| dynamicrafter/inclined_slide | 48 | 7 | 7 | 0.32 [-1.16, 1.70] | 0.58 | 0.63 | 0.41 | — | — | — |
| dynamicrafter/projectile | 56 | 15 | 10 | 0.00 [-0.07, 0.05] | -0.20 | 0.86 | 0.69 | 0.13 (0.583) | 0.57 (0.002) | 0.10 (0.034) |
| ltx2/bouncing_ball | 48 | 8 | 6 | 0.21 [-0.15, 0.56] | 0.05 | 0.15 | 0.07 | — | — | — |
| ltx2/inclined_slide | 48 | 45 | 45 | -0.08 [-0.28, 0.07] | 0.02 | 1.15 | 0.92 | 0.00 (0.605) | 0.19 (0.004) | 0.00 (0.413) |
| ltx2/projectile | 56 | 31 | 28 | -0.64 [-1.49, 0.09] | -0.15 | 0.91 | 0.68 | 0.10 (0.234) | 0.13 (0.088) | 0.29 (0.002) |
| wan22_i2v_a14b/bouncing_ball | 48 | 22 | 21 | 0.00 [-0.36, 0.39] | 0.17 | 0.16 | 0.20 | 0.23 (0.128) | 0.75 (0.002) | 0.00 (0.956) |
| wan22_i2v_a14b/inclined_slide | 48 | 14 | 14 | 0.01 [-0.04, 0.05] | 0.03 | 1.19 | 0.86 | — | — | — |
| wan22_i2v_a14b/projectile | 56 | 46 | 46 | 0.39 [-0.72, 1.73] | 0.21 | 1.06 | 0.67 | 0.00 (0.591) | 0.10 (0.030) | 0.07 (0.018) |
