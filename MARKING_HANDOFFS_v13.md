# v1.3 Candidate — Zonal / Individual Marking and Hand-offs

## Principle

The defence now answers two separate questions on every relevant beat:

1. **What is the primary defensive response?** (`press_ball`, `track_runner`, `cover_depth`, etc.)
2. **How is the threat organised/marked?** (`zonal`, `man`, or `hybrid`)

Only one response and one marking organisation are active for that beat. This is
not a return to stacked defensive bonuses.

## Marking modes

- `zonal`: protects the dangerous lane/area first; runner hand-offs are relatively easy;
- `man`: stays attached to the concrete runner for longer and accepts more structural displacement;
- `hybrid`: protects shape but hands a concrete runner between defenders when the run crosses zones.

The mode emerges from compactness, pressing, line height, transition/depth threat,
ball zone and whether a concrete runner has been identified.

## Marking hand-off

A runner has a current zone and, when movement is available, a projected zone
0.7–2.3 seconds ahead. The engine compares:

`current marker in the new zone` vs `best local marker in the new zone`

A hand-off only happens when the new defender is materially better placed and the
handoff quality is sufficient. Individual marking has a higher switching threshold;
zonal marking switches more freely.

Handoff quality uses both defenders' anticipation, positioning, composure and
discipline. Hidden/blind-side runs are harder to exchange.

## Important invariants

- one defender cannot mark two disconnected threats in the same assignment;
- marking does not alter player attributes;
- a runner crossing from wide to central space can be handed from a fullback to a CB/DM;
- strict man marking can be dragged by a decoy, creating a small structural cost;
- zonal marking protects lanes better but controls a specific runner less tightly;
- no mode guarantees a stop.

## Interaction with the v1.3 attack model

The full conceptual sequence is now:

`location -> off-ball movement -> anticipation -> body orientation -> creative perception -> boldness/risk -> attacking decision -> defensive response -> marking organisation/handoff -> execution`

This means Félix can drag a marker, Remo can attack the newly opened blind-side
space, a creative passer can perceive it, and the defence can either stay man,
pass Remo to another defender, or protect the zone. The result is still resolved
by the normal attributes and context.
