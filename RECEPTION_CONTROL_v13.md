# Contextual reception — v1.3

This layer adds four linked mechanics without new numeric player attributes.

1. **Contextual first touch** — reception quality uses technique, composure, anticipation, dribbling, pressure, space, trajectory and the legal contact surface.
2. **Oriented reception** — a controlled touch can secure, half-turn, attack forward space, move inside, stay on the line or set the next action.
3. **First-time play** — passes, crosses, cutbacks, through balls and shots may be played without a control when context and skill support it.
4. **Integration and persistence** — reception markers and pending first-time actions survive save/load; outcomes are attached to real engine events rather than producing cosmetic events or quotas.

Principles:
- no first-touch attribute was added;
- no player-name exceptions;
- same seed + same state remains deterministic;
- bad touches are possible but constrained so normal football remains dominant;
- first-time actions do not create extra shots or passes; they only change execution of an action the decision model already selected;
- the frozen v1.2 `main` branch is untouched.
