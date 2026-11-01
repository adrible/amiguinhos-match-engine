# v1.3 Candidate — Contextual Defensive Intelligence

## Principle

The defensive layer is the counterpart to the v1.3 attacking-intelligence work.
It does **not** add a generic defensive buff and does **not** let a team stack
pressing, runner tracking, passing-lane coverage and box protection at full
strength at the same time.

For each relevant defensive beat, the engine chooses **one primary defensive
intention** from the current situation:

- `press_ball` — attack the ball carrier;
- `delay` — slow the attack and buy recovery time;
- `block_lane` — occupy the most dangerous passing lane;
- `track_runner` — follow a specific run;
- `cover_depth` — protect the space behind the line;
- `contain` — stay balanced against a dribbler;
- `block_cross` — close the crossing lane;
- `close_cutback` — protect the cutback channel;
- `protect_box` — defend the central finishing area;
- `block_shot` — step into the immediate shooting line.

## Decision model

Conceptually:

`threat + zone + tactical shape + score/transition context -> primary response`

Then:

`primary response + defender role + positioning + anticipation + tackling + pace + composure -> execution quality`

The normal engine attributes still determine whether the defender succeeds.
The new layer changes the *situation* the attacker faces rather than silently
raising or lowering player attributes.

## Trade-offs

Every response has a cost. Examples:

- pressing raises immediate pressure but can expose depth;
- tracking a runner protects the run but gives the ball carrier slightly more room;
- covering depth reduces space behind but concedes some immediate pressure;
- blocking a cross commits a wide defender and can slightly loosen central cover;
- containing a dribbler reduces space without creating an automatic tackle.

This prevents the defensive side from becoming an abstract stacked shield.

## Interaction with previous v1.3 layers

The current candidate flow is:

`location -> off-ball movement -> anticipation -> body orientation -> creative perception -> boldness/risk -> attacking decision -> defensive response -> execution`

A hidden run can therefore be created by the attacker, perceived by a creative
passer, and then reacted to by an intelligent defender. None of those stages
guarantees the outcome.

## Validation

Local candidate validation after integration:

- 49 unit/regression tests passed;
- same-seed reproducibility preserved;
- 100-match smoke completed without crash;
- smoke diagnostic: 2.33 goals/match, 24.97 shots/match, 9.22 shots on target,
  2.274 xG/match, 0.73 big chances/match, 9% 0-0.

These are diagnostics only, not quotas or calibration targets.

## Important implementation guard

The engine stores the pre-defensive spatial context and **replaces** the generic
defensive response with the action-specific response later in the same beat.
It does not apply both. This is intentional and prevents accidental defensive
bonus stacking.
