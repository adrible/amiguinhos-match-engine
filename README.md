# Amiguinhos Match Engine

## Stable engine

`main` remains the frozen **v1.2 stable** line. The v1.3 candidate is developed separately and must not be treated as stable until explicitly promoted.

## v1.3 candidate

The candidate keeps the core outcome-blind simulation rules and adds contextual football behaviour, including:

- geospatial decisions by pitch band and lane;
- creativity as perception of non-obvious options;
- boldness/ousadia as willingness to accept justified risk;
- off-ball movement and anticipation;
- body orientation and preferred foot;
- contextual defensive intelligence;
- marking, handoffs, cover and communication;
- coordinated offside line and overload reactions;
- contextual defensive execution errors;
- pair familiarity/shared understanding;
- tactical adaptation with hysteresis;
- determination/raça under adversity;
- literal evolved v1.3 player ratings;
- exact state/RNG persistence;
- real extra time and stateful live shootouts;
- interactive live `p` runner;
- contextual automatic substitutions;
- quarantine of the declared official-final seed.

### Literal evolved ratings

The higher Amiguinhos ratings in v1.3 are **absolute current ratings**, not runtime buffs. If the v1.3 JSON says `passing: 88`, the loader sets passing to exactly 88. It does not add a delta to the v1.2 value.

Creativity, boldness and determination are separate behavioural traits and do not directly add technical execution ratings.

### Automatic substitutions

The v1.3 coach can make substitutions autonomously at stoppages. Normal changes are contextual rather than clock quotas: fatigue, card exposure, chasing the game, protecting a lead and late freshness can justify a change. Before the normal second-half substitution window, automatic changes are emergency-only, primarily injury. A pending live action is never interrupted by a substitution.

The known Amiguinhos bench remains explicit. Tournament opponents that have no bench data at all receive a deterministic, neutral candidate-only reserve pool so lack of source depth does not disable substitutions. This fallback does not alter stable v1.2 and does not replace any explicitly supplied bench.

### Outcome policy

The engine never chooses a winner, score, shot count or goal total in advance. Statistics are consequences, not quotas. Multi-seed diagnostics use contiguous, unfiltered schedules and retain all results.

The official final seed is reserved and must never be previewed, dry-run, calibration-tested or seed-shopped. Only the explicit live official-final runner may unlock it when the real simulation starts.
