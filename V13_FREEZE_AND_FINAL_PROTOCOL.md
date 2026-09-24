# v1.3 — Freeze and Official Final Protocol

## Purpose

This document defines the gate that must be satisfied before the v1.3 candidate
is frozen for the Regional Internacional U21 final.  It is intentionally
result-agnostic: no score, winner, shot count, xG value or Amiguinhos success
rate is a release target.

The official v1.2 remains frozen and is not modified by this protocol.

## Freeze gate

Before v1.3 can be treated as the final-match candidate, the exact candidate
head must satisfy all of the following:

1. Python 3.11 and 3.12 candidate CI are green.
2. The frozen v1.2 regression suite remains green.
3. All v1.3 behavioural/regression tests are green.
4. The 100-match generic smoke completes with coherent statistical invariants.
5. Amiguinhos U21 x Flamengo U21 calibration runs the complete contiguous,
   unfiltered seed range 0..99.  No result may be dropped or replaced.
6. Tactical-adaptation stress runs a declared contiguous range with adaptation
   enabled and reports response distribution, cap hits and temporal spacing.
7. Persistence/restore preserves exact future RNG/event sequence.
8. The live `p` runner begins at 0:00 with no precomputed event queue.
9. Knockout continuation supports real extra time and a stateful penalty
   shootout in which one public step resolves at most one penalty kick.
10. The official final seed remains inaccessible to calibration/stress tools.

Any behavioural engine change after the freeze gate invalidates the freeze and
requires the full gate to run again.  Documentation-only changes do not alter
match behaviour but still must not redefine the official seed protocol.

## Official final seed

Match identity string:

`amiguinhos_u21|flamengo_u21|regional_internacional_u21|final`

Derivation rule, declared before the official live simulation:

1. Compute SHA-256 of the UTF-8 identity string.
2. Take the first 8 hexadecimal characters.
3. Interpret them as an unsigned hexadecimal integer.

Declared SHA-256:

`6be46927575f409c1dec1e9509214db2a47583884dd52f3851efa117d0d32e80`

Declared official seed:

**1810131239** (`0x6be46927`)

The seed is derived from match identity only.  It was not chosen from a list of
simulated outcomes and must never be replaced because of a future result.

## Seed quarantine

The exact pair `amiguinhos_u21` / `flamengo_u21` with seed `1810131239` is
reserved for the official live final.  `calibration_v13.py` must reject that
fixture+seed before loading teams or constructing an engine.

The normal live runner must also reject the reserved fixture+seed.  It may be
unlocked only through the explicit official-final entry point when the real
interactive final is intentionally started.

No CI smoke, calibration batch, preview, dry run or debugging session may use
the official seed.

## Official live configuration

The explicit official-final runner uses:

- home: `amiguinhos_u21`
- away: `flamengo_u21`
- seed: `1810131239`
- contextual tactical adaptation: enabled
- extra time: enabled
- live advancement: `p`, one relevant continuation at a time
- shootout, if required: one penalty kick per public step

Creating or advancing the official session before the intended live final is
outside protocol.

## No seed shopping

After the official seed is declared, neither an undesirable score nor an
unexpected event is grounds to change it.  If a genuine engine bug is found
before the official match begins, fix the bug, rerun the full freeze gate, keep
the same official seed, and do not inspect the official fixture on that seed as
part of validation.
