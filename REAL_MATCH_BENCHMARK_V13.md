# v1.3 Real Match Benchmark

This benchmark compares the current v1.3 candidate with a large collection of real matches without feeding benchmark values back into the match engine.

## Real-match population

The core sample downloads three completed seasons (`2022/23`, `2023/24`, `2024/25`) from five major European leagues:

- Premier League
- Bundesliga
- Serie A
- La Liga
- Ligue 1

The files come from the `datasets/football-datasets` GitHub mirror of Football-Data.co.uk. Raw third-party files are not committed to this repository; the benchmark downloads them at runtime and caches them locally.

The source manifest is `data/real_match_benchmark_sources.json`.

## Core like-for-like metrics

Only fields with a direct match-level mapping are included in the core index:

- goals per match
- shots per match
- shots on target per match
- fouls per match
- corners per match
- yellow cards per match
- red cards per match
- home and away goals
- home/draw/away result rates
- 0-0 rate
- both-teams-to-score rate
- over-2.5 rate
- clean-sheet match rate
- result distribution
- total-goal distribution
- capped scoreline distribution

xG is intentionally excluded because the real-match source does not provide a like-for-like model. Engine-only labels such as `second_ball`, `goalkeeper_one_v_one`, tactical-foul intent, mismatch and micro-adjustment are also excluded from the core score until a provider with compatible definitions is added.

## Realism index

Each scalar engine metric is compared with the pooled real-match mean. The difference is divided by the observed standard deviation across the 15 league-season samples, with a conservative floor so an unusually stable real sample cannot make tiny differences appear infinitely important.

The scalar component score is:

`100 * exp(-0.5 * standardised_gap^2)`

Result, total-goal and scoreline distributions are compared with Jensen-Shannon distance and converted to a 0-100 similarity score. The final index is a weighted mean of the components.

The index is **diagnostic only**. It must never become an in-match target, quota or objective. A lower score identifies systems worth inspecting; it does not justify forcing goals, shots, cards or any other event count.

## Engine population

The benchmark uses an unfiltered contiguous seed range. Each simulated fixture independently samples a bounded generic team strength and tactical style, producing a heterogeneous population rather than 500 copies of the same 78-v-78 fixture.

The reserved official-final seed `1810131239` is explicitly rejected.

## Timing supplement

Timing is reported separately from the core index because the reference is competition-specific. The current source manifest records Premier League 2024/25 official reference values for:

- average second-half stoppage time: 6m32s
- share of goals scored in 90+: 8.4%

These values are useful diagnostics, but do not affect the multi-league core realism index.

## Running locally

```bash
python real_match_benchmark_v13.py --engine-matches 500 --output artifacts/real_match_benchmark_v13.json
```

The first run downloads the real-match CSVs into `.cache/real_match_benchmark/`; subsequent runs reuse the cache.

## CI

`.github/workflows/v13-real-match-benchmark.yml` runs:

1. benchmark compilation;
2. unit tests for the benchmark harness;
3. a 300-match engine benchmark on pull requests;
4. JSON artifact upload.

A manual workflow run defaults to 1,000 engine matches and accepts a custom sample size.

## Interpretation

Use the largest standardised gaps and distribution distances to decide what to investigate next. Prefer causal fixes. For example, if home-win rate is too low, investigate home/away context; do not increase a hidden `home_goal_probability`. If 90+ goals are low, inspect timekeeping and late-game behavior; do not add a late-goal quota.
