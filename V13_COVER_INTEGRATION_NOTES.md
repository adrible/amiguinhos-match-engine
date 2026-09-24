# v1.3 Defensive Cover Integration Notes

## New layer

`engine_experiment_v13_cover.py` extends `MatchEngineV13Marking` and adds one
contextual cover relationship behind the primary defender/marker.

Supported cover relationships:

- `cover_depth`: protects depth when a defender jumps to press or a lane is exposed;
- `cover_inside`: protects the inside channel when the first defender contains/presses wide;
- `protect_cutback`: protects the return pass/box space when a wide defender blocks a cross;
- `protect_vacated_zone`: protects the space left by a defender tracking a runner.

## Structural invariants

- There is still exactly one primary defensive intention per beat.
- Coverage is subordinate to that intention; it is not a second independent response.
- At most one contextual cover relationship is active per beat.
- The covering defender must be different from the primary defender and the active marker.
- Primary safety intentions (`cover_depth`, `protect_box`, `block_shot`,
  `close_cutback`, `delay`) do not receive a second safety layer.
- Coverage never modifies player attributes.
- Coverage modifies only the relevant spatial trade-off/control variables.
- Strict man marking and live hand-offs reduce clean cover availability.
- Frozen v1.2 files remain untouched.

## Trade-offs

- `cover_depth` repairs only part of the depth exposure created by pressing; it cannot
  turn pressure into a separate full-strength depth shield.
- `cover_inside` closes the inside channel but concedes a small amount of width.
- `protect_cutback` improves return-pass/box protection but slightly reduces direct
  pressure and pulls a defender inward.
- `protect_vacated_zone` restores balance behind runner tracking at a small pressure cost.

## Local validation

- 63 unit/regression tests passed.
- 7 new defensive-cover tests passed.
- Same-seed reproducibility remained intact.
- Player attributes remain unchanged by the cover layer.
- A covering defender is kept distinct from the primary defender/active marker.

### Paired smoke comparison — same 120 seeds

Marking/handoff candidate:
- 2.308 goals/match
- 24.750 shots/match
- 9.175 shots on target/match
- 2.176 xG/match
- 0.558 big chances/match
- 13.33% 0-0

Marking/handoff + defensive cover:
- 2.283 goals/match
- 24.817 shots/match
- 9.167 shots on target/match
- 2.179 xG/match
- 0.567 big chances/match
- 13.33% 0-0

Paired mean difference (cover - marking):
- -0.025 goals/match
- +0.067 shots/match
- -0.008 shots on target/match
- +0.004 xG/match
- +0.008 big chances/match
- 0.00 percentage points in 0-0 rate

This is a diagnostic, not a target or quota. On this sample the new layer changed
structural defensive behaviour while aggregate chance creation remained essentially
unchanged.
