# Live narration rules

- Advance exactly one narratable event per user `p`.
- Do not repeat an incident that was already narrated in the immediately previous step.
- User-facing narration must never mention `p`, press/advance counts, `step`, `sequence`, command names, or labels such as `4º p`. Commands remain an internal control interface only; present each returned moment only by match clock and football action.
- Foul, immediate reaction and public warning/card are one packet. Do not repeat aftermath or count suppressed records as a press.
- For batch requests such as `p 5x`, stop immediately when a `period_end` event is reached, even if the batch still has unused presses. Do not consume the next period kickoff until the user sends another `p`.
- Never invent cards, shots, restarts, or outcomes not present in the authoritative packet.
- Keep duplicate player names disambiguated with team tags, e.g. `Isagi (D)` and `Isagi (B)`.

- `p 5x` / `p 10x`: call `press_p_batch(5)` / `press_p_batch(10)` and narrate EVERY returned packet, in order, as `tempo — lance`. Never show only the last packet.
- Live replay scripts accept `STEP COUNT`: STEP is the first requested press, and the output includes all `packets` plus the final `step`. Pin historical matches to their original commit; a revised engine changes seeded replay.
- A pending setup must be resolved from `resolved_pending_action`, including clearances and keeper claims, before moving to a new attack.
- Target is intention. Describe the outcome using actual placement; do not narrate an intended top-corner shot as executed there after a miss or block.
- Use circulation summaries and emotional context only when supported by the packet. Omit saved steps and internal metrics from user-facing commentary.
