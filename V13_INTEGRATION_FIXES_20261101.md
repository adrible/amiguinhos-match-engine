# v1.3 integration repairs — 1 November 2026

## Receiver selection

The base engine started passing `action` to `_choose_target`, while ten v1.3
overrides still used the old signature. This stopped normal passes, persistence
continuation, match-flow tests and population audits with `TypeError`.

All active overrides now accept and forward the action. Passing-lane selection
also passes the actual action during its initial receiver choice. Spatial and
off-ball selection replace their legacy off-ball weighting with the existing
contextual receiver-quality formula exactly once. Explicit creative targets,
runs, combinations and rebound priorities retain their precedence. Defensive
passes keep the historical lower-layer interface, where action is not used.

Integration tests exercise every active override for attacking and defensive
passes and verify that action-specific quality reaches actual spatial selection.

## PR #6 reconciliation

The PR's intent/physics unification is retained together with the newer target
mix: bilateral high/mid/low corners, high centre and near-post options. A shared
deterministic selector chooses intention and technique before resolution;
geometry consumes that intention. Downward headers, chips and keeper nutmegs
also report their actual intended target, without a second independent draw.

Handling contributes to the spatial goalkeeper response as proposed in #6.
The regression uses an unsaturated save situation: an easy central save can
legitimately clamp both strong and weak keeper difficulty to zero.

A controlled comparison of 1,000 shots against the previous active geometry
preserved intended coordinates, actual coordinates, intended/actual regions,
technique and on-target flags exactly. Handling is the intentional goalkeeper
response change. No xG target, score quota or seed filtering was introduced.

## Branches and documentation

The integration branch incorporates the active candidate history and the PR #6
history. After integration, `v1.3-final-freeze` is updated to the validated active
tree with both histories retained, repairing its unrelated ancestry without a
force push. The former freeze commit remains reachable. PR #2 stays a draft;
`main` and the archived v1.2 are unchanged.

The freeze protocol now explicitly tests v1.2 on its archived source tree and
distinguishes a candidate snapshot from certification for the official final.
The reserved final seed was neither simulated nor unlocked.

## Validation

- Active candidate/core/match-flow/benchmark-harness battery: 796 tests passed
  on Python 3.12; the additional integration and special-technique regressions
  passed in the focused battery (20 tests, including overlapping shot tests).
- Archived v1.2: all 23 regression tests passed on its unchanged source tree.
- Python compilation and whitespace checks passed.
- Ten complete canonical smoke matches passed, including xG-ledger invariants.
- Population benchmarks and Python 3.11/3.12 verification are tracked by GitHub
  Actions on the exact integration commit. Their status is authoritative; old
  green results or this document alone do not certify the release gate.
