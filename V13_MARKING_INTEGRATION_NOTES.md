# v1.3 Marking / Handoff Integration Notes

## New layer

`engine_experiment_v13_marking.py` extends `MatchEngineV13Defense` and adds:

- dynamic marking organisation: `zonal`, `man`, `hybrid`;
- runner projection from the existing off-ball movement model;
- current marker vs projected-zone marker comparison;
- marking hand-offs when the runner crosses band/lane;
- mode-specific stickiness (man > hybrid > zonal);
- handoff quality from anticipation/positioning/composure/discipline;
- blind-side/hiddenness penalty to handoff recognition;
- distinct defender assignment for multiple projected threats in diagnostics;
- small structural cost when strict individual marking is dragged by a decoy.

## Invariants

- The original contextual defensive layer still chooses exactly one primary defensive intention.
- The marking layer chooses exactly one marking organisation for the beat.
- A defender cannot be assigned to two disconnected threats in the multi-threat diagnostic.
- No attacker or defender attributes are modified by marking.
- Marking affects spatial context/runner control only; execution still uses normal attributes.
- Frozen v1.2 files were not modified.

## Local validation

- 56 unit/regression tests passed.
- 7 new marking/handoff tests passed.
- A forced synthetic diagonal/blind-side run produced an actual defender hand-off and changed marker.
- Same-seed reproducibility remained intact.

### Paired smoke comparison — same 120 seeds

Defense-only candidate:
- 2.000 goals/match
- 24.258 shots/match
- 8.683 shots on target/match
- 2.067 xG/match
- 0.725 big chances/match

Defense + marking/handoff:
- 1.975 goals/match
- 24.383 shots/match
- 8.617 shots on target/match
- 2.072 xG/match
- 0.725 big chances/match

The aggregate chance creation remained essentially unchanged in this diagnostic.
The 0-0 rate differed on the small sample (10.8% vs 15.8%), so it should not be
used as a calibration target; a larger batch is required before interpreting it.
