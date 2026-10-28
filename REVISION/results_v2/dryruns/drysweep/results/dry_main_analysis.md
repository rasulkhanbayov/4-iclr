# Analysis of run `dry_main`

Metrics on VALID clips only. β = in-range faithfulness slope (1 = faithful, 0 = ignores the request).
Shares = chance-corrected variance shares of θ̂ (request / scene / noise); p-values from label permutation.

| model / system | clips | valid | 2nd-tracker confirmed | β in-range [95% CI] | Spearman ρ | PRE in | PRE out | request share (p) | scene share (p) | noise share (p) |
|---|---|---|---|---|---|---|---|---|---|---|
| simulator/bouncing_ball | 96 | 80 | 0 | 1.03 [1.00, 1.08] | 0.98 | 0.01 | 0.00 | 1.00 (0.002) | 0.00 (0.980) | 0.00 (1.000) |
| simulator/inclined_slide | 96 | 96 | 0 | 1.00 [1.00, 1.00] | 0.99 | 0.00 | 0.00 | 1.00 (0.002) | 0.00 (1.000) | 0.00 (1.000) |
| simulator/projectile | 112 | 112 | 0 | 1.00 [1.00, 1.00] | 0.99 | 0.00 | 0.00 | 1.00 (0.002) | 0.00 (1.000) | 0.00 (1.000) |

## Seed-free tier: `dry_main` (seeded) vs `dry_api` (API mode, fresh seed per clip)

| model / system | valid rate seeded | valid rate API | β seeded [CI] | β API [CI] | ρ seeded | ρ API |
|---|---|---|---|---|---|---|
| simulator/bouncing_ball | 0.83 | 0.83 | 1.03 [1.00, 1.08] | 1.03 [0.98, 1.12] | 0.98 | 0.98 |
| simulator/inclined_slide | 1.00 | 1.00 | 1.00 [1.00, 1.00] | 1.00 [0.99, 1.00] | 0.99 | 0.99 |
| simulator/projectile | 1.00 | 1.00 | 1.00 [1.00, 1.00] | 1.00 [1.00, 1.00] | 0.99 | 0.99 |
