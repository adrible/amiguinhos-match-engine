# v1.3 candidate integration notes — body orientation

Layer order:

1. `engine_experiment_v13_spatial.py` — geospatial decisions + creativity + boldness
2. `engine_experiment_v13_offball.py` — off-ball movement + short-horizon anticipation
3. `engine_experiment_v13_body.py` — body orientation + preferred-foot reception

The body layer is experimental and must not replace frozen v1.2 until it is validated against the real GitHub `stable_engine` in CI.

## Local validation performed

- 40 unit/regression tests passed.
- 100-match smoke completed without crash.
- Smoke aggregate: 2.400 goals/match, 24.440 shots/match, 9.810 shots on target/match, 2.457 xG/match.

These smoke numbers are diagnostics, not calibration targets.

## Important semantics

- body orientation changes action naturalness, not stored player attributes;
- preferred foot is contextual: natural wide foot helps crossing, inverted foot helps inside shooting/combination;
- through balls/transitions tend to produce more forward-facing reception;
- rebounds/corners tend to produce less clean setup;
- headers are not modified by preferred-foot logic;
- v1.2 remains frozen and untouched.
