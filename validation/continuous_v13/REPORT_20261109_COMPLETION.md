# Continuous engine: completion of league checkpoint

The 295-match checkpoint was produced on engine commit `0b96e9c886f67d66ed44fea1b092e75e9cd2163f`. The remaining 85 fixtures (295–379, seeds 124295–124379) were executed against source `10649110c12dca4045b02bffb9347c1ba0420d8b`, before the advantage fix in this branch. Comparing those GitHub commits shows only checkpoint and context data changed; no engine or validation script changed. All 85 completed without recorded failures. A parity check with the observer enabled passed for fixture 295. Other fixtures did not run that check.

The runs use 20 generic strength-80 teams, not historical squads, and the reference is EPL 2015/16. They compare distributions, not predictions of historical results. The 295-game totals are from the checked-in checkpoint; 85 new per-fixture summaries and compact shot frames are in `validation_remaining_85_20261109.json.gz`. The new archive omits full tracking and player frames. Its `engine_code_sha256` was verified against the original source; the local reconstruction's Git commit identifier is not the original GitHub commit.

| Metric | 380 simulated | Real reference |
|---|---:|---:|
| Goals/game | 7.071 | 2.700 |
| Shots/game | 37.042 | 26.074 |
| Non-penalty shot distance | 12.503 m | 16.632 m |
| Passes/game | 786.042 | 970.050 |
| Pass accuracy | 67.19% | 76.60% |

Simulated penalties: 339/380, 0.892 per match; shots attributed to crosses: 6,354/380, 16.72 per match. These values identify priorities for investigation, not causal proof. The metric and source definitions must be checked before comparing categories with real events. The 380-game result is for the pre-fix engine and does not validate the corrected engine.

## Advantage correction

Previously both physical-foul paths released the ball before the referee decided whether to play advantage. The referee could therefore announce advantage after control had already ended. The correction preserves possession and pending play on advantage and releases the ball only if play is stopped. Focused tests cover each branch; the new tests are included in the continuous CI workflow.

Local checks: 51 continuous tests passed in a reconstructed source environment; the reserved-final protocol module was substituted with an inert stub, so this does not validate that protocol. One complete post-fix match and observer parity passed. A separate save/load check matched 60 steps after restoring at step 60; this is limited evidence, not a complete determinism certification. No official final seed was accessed.

No calibration improvement is claimed for the advantage fix. The corrected engine still needs an independently replicated league benchmark and investigation of chance creation, penalties, crossing attribution, save/load and determinism before promotion.
