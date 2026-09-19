# Spatial execution and live narration revision

Base: tournament-interdimensional-20260918 at 2444e4d (contains the current
v1.3-spatial-creativity-boldness code). Historical fixtures and their saved
press counters are unchanged. Replaying their seeds under new physics produces
new matches: use the original commit to reproduce an already-played fixture.

## Shots

The base resolver calculates situation xG first. The v1.3 hook then chooses the
intended goal region and samples independent horizontal/vertical execution
errors before any outcome roll. The actual legal body part and the final
prepared pressure are already available at that point.

Coordinates are metres, viewed by the attacker: x in [-3.66, 3.66] and height z
in [0, 2.44]. A projected ball outside that rectangle misses; contact with the
frame is geometric. Blocked shots retain only a projected crossing point and
have no actual goal-plane crossing. Low shots may skid/bounce.

Execution spread depends on skill, composure, fatigue, pressure, balance, actual
foot, shot type and distance. Aiming near a boundary adds the natural risk of
missing it. All intended regions can fail. Center, low/mid/high corners,
near-post, wrong-foot and chips are available, with contextual headers,
downward headers, volleys, first-time shots, toe pokes and outside-foot shots.

Keeper lateral position depends on the attacking lane and positioning. Reach
distance, height and flight time change the conditional save/goal probability.
Reflexes, positioning, agility, reach, jumping and one-on-one ability have
different weights for different balls. Handling and velocity affect spills.
Optional 0–100 roster attributes: gk_reach, gk_jump, gk_agility, balance,
weak_foot. Missing values use documented attribute-derived fallbacks, not
invented player-specific ratings.

This is a coarse spatial model, not a full 3D flight simulator. Shot distance
is estimated from the pitch band. Penalties retain their existing specialist
resolver. There are no target scores, goal quotas, forced counterattacks or
team-name bonuses. Per-shot xG, intended/actual coordinates and keeper position
are retained in the canonical ledger; xG is never calculated from placement.

## Creative play and keeper exposure

Special passes are considered only with a contextual purpose: avoid the weak
foot/solve an awkward angle, release support under pressure, disguise a line,
or pass over/around a defender. Creativity and boldness influence attempts;
technique, vision, composure, pressure and technique difficulty influence
execution. Success reduces effective defensive pressure; failed execution
increases it and therefore the actual risk of a lost ball. An executed trick
still does not guarantee a completed pass. Existing no-touch dummies are made
visible rather than replaced with cosmetic passes.

Successful meaningful feints and special passes reach narration relevance.
Failed attempts remain truthfully labelled. No hand-coded preference exists
for Sae, Bachira, Hiori, Ness or Rin: their roster attributes drive behaviour.

A keeper may join only the existing late, one-goal-deficit attacking-set-piece
context, with an additional deterministic willingness draw. Earlier periods'
stoppage time cannot make an 87th-minute situation count as the 90th minute.
Exposure persists in saved state. Return is explicit in event data. An absent
keeper cannot claim a cross, contest a one-on-one or save an unblocked ball
inside the frame; defenders can still block it and shooters can still miss.

## Live commands

- `p`: next narratable moment.
- `p 5x`, `p 10x`: exactly the next five/ten narratable moments, unless the
  period or match ends first. Every packet must be narrated, not only the last.
- Existing `p N` keeps its minimum-relevance meaning.
- API: `session.press_p_batch(5)` returns an ordered list of packets.
- Replay scripts: `python live_interdimensional_a5.py STEP COUNT`. STEP is the
  first desired press. `packets` contains the whole batch and `step` is the
  last press reached. The legacy `packet` field remains the last item.

Batching stops before the following period's kickoff. Foul/reaction/public
card/warning aftermath is grouped using normal engine steps so clock recovery,
mental effects, logs and physics remain identical to raw stepping. Deferred
advantage cards are not announced early. Resolved pending actions survive even
when the result is a low-relevance clearance. Long circulation is summarized
from actual safe passes; late-close-match/decisive-chance/exposed-goal context
controls tone, never creates incidents. No saved-step messages belong in the
user-facing commentary.

## Validation

See audits/spatial_execution_20260919 for the baseline/candidate 100-match
samples and release test output. Samples diagnose distributions; they are not
proof of calibration against real football and are not runtime constraints.

Release checks: **741 tests passed**. The live A5 script also returned five
ordered packets for `run_to_step(1, 5)`. Batch/raw-step state equality and
save/restore determinism are regression-tested.

| Per match, same generic teams and seeds 0–99 | Base | Candidate |
|---|---:|---:|
| Goals | 2.090 | 2.370 |
| Shots | 24.580 | 24.100 |
| On target | 8.340 | 9.960 |
| Situation xG | 2.285 | 2.230 |
| Goals / xG | 0.915 | 1.063 |
| 0–0 | 14% | 10% |

Ledger xG minus canonical stats is exactly zero in both runs. On-target volume
remains higher than the base and needs a larger real-match benchmark before
claiming full statistical calibration. The 100-match sample is a regression
smoke, not a universal realism score.
