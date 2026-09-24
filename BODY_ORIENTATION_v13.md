# v1.3 candidate — body orientation + preferred foot

This layer extends the spatial/creativity/boldness/off-ball candidate.

## Principle

The next decision depends not only on **where** the player is, but on **how the ball arrives** and how the player's body is oriented at reception.

A player can receive:

- facing goal;
- on the half-turn;
- back to goal;
- open on a wide lane.

The profile is generated from role, zone, pressure, space, technique, anticipation, composure, off-ball movement and pass origin.

## Preferred foot

The preferred foot is contextual rather than a flat bonus.

- natural-foot winger on his side: easier line/crossing action;
- inverted-foot winger: easier inside orientation/shooting/inside passing;
- central reception: mostly neutral.

The effect is intentionally modest and never changes the player's stored attributes.

## Reception source

Different pass origins alter body shape:

- through ball / transition: more likely to arrive facing goal;
- cutback: usually favorable shooting orientation;
- progression: modest half-turn advantage;
- rebound / corner: more chaotic, less clean body setup.

## Engine order

`location -> movement -> reception/body orientation -> perceived options -> decision -> execution`

Creativity still discovers hidden options. Boldness still evaluates risk/reward. Body orientation decides how natural each action is at that instant.
