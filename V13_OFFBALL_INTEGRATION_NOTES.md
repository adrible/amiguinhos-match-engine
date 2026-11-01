# v1.3 candidate integration notes — off-ball + anticipation

Target branch when GitHub write access is available: `v1.3-spatial-creativity-boldness`.

New layer:
- `engine_experiment_v13_offball.py`
- `test_offball_anticipation.py`
- `OFF_BALL_ANTICIPATION_v13.md`

Important design contracts:
1. One active movement intention per off-ball player per beat.
2. Movement exists independently of the passer's creativity.
3. Creativity only affects perception of a qualifying hidden movement.
4. Boldness/risk only affect acceptance after perception.
5. Movement can improve situation quality modestly, never technical execution.
6. Defensive-third movement cannot teleport a player directly into the opponent box.
7. Side-specific overlap tactics affect fullback movement.
8. Short-horizon projection is deterministic and consumes no RNG.
9. Stable v1.2 remains untouched until CI + calibration.

Local validation performed on the fallback audited base engine:
- 32 unit/regression tests passed.
- 100-match smoke completed without crash.
- Smoke diagnostic (75 vs 80 generic): 2.29 goals/match, 23.97 shots/match, 9.49 SOT/match, 2.303 xG/match.

These smoke numbers are diagnostics only, not tuning targets.
