# Live narration rules

- Advance exactly one narratable event per user `p`.
- Do not repeat an incident that was already narrated in the immediately previous step.
- In particular, if a `referee_warning` packet only restates a verbal warning already narrated with the foul, do not narrate the warning again; treat it as continuity and move on only on the next user `p`.
- For batch requests such as `p 5x`, stop immediately when a `period_end` event is reached, even if the batch still has unused presses. Do not consume the next period kickoff until the user sends another `p`.
- Never invent cards, shots, restarts, or outcomes not present in the authoritative packet.
- Keep duplicate player names disambiguated with team tags, e.g. `Isagi (D)` and `Isagi (B)`.
