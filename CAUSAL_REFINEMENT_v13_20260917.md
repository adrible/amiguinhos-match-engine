# v1.3 causal refinement — 2026-09-17

Baseline: `3097bee23f3808867877366ecafd7c8afe132a5f` on
`v1.3-spatial-creativity-boldness`. This is an incremental candidate change,
not a merge to main or approval to start the official match.

## Hypotheses and accepted changes

### Second cautions

The baseline already makes booked players more cautious before a foul. It then
applies an additional, very strong sanction discount even to SPA (stopping a
promising attack), DOGSO and dangerous challenges. In 300 baseline benchmark
matches, 73 booked-player SPA incidents had mean base caution probability
43.16%, reduced to an effective 3.57%. Only two produced second cautions.

The accepted change keeps behavioural caution and the first-caution model.
It removes the extra second-caution discount for explicit caution grounds.
Marginal routine fouls retain the existing general management factor. The
`ordinary_contact` source flag no longer changes the second-caution factor:
identical football circumstances must not be sanctioned differently because
of which generator produced them. Tactical interruptions also lose their
separate 0.38 multiplier for already-booked players.

This is not a full rewrite of disciplinary recognition. Incident generation,
severity thresholds, routine-contact discretion and behavioural reaction cards
remain approximations and are not declared fully calibrated.

### Direct-red edge cases

No global direct-red increase is retained. Two specific faults are fixed:

- The tactical-DOGSO path now respects `config.direct_red_enabled`.
- The penalty-area DOGSO ball-challenge reduction cannot discount an independent
  violent-conduct ground.

The generator's ordinary violent-conduct incidents are elbow/forearm incidents
without a ball attempt. The second fix therefore primarily protects forced or
future composite incidents, rather than increasing reds throughout this sample.

Law 12 distinguishes caution/sending-off grounds and the penalty-area DOGSO
exception; prior booking does not remove an otherwise cautionable offence.
Source: [IFAB Law 12](https://www.theifab.com/laws/latest/fouls-and-misconduct/).
This patch does not claim to implement every Law 12 exception or referee error.

### Conditional conversion of tiny chances

On the baseline's 1,000 generic matches, 12,977 shots below 0.05 xG summed to
96.1225 xG. The 6% conditional goal floor was active on 11,470 of these shots.
Along the observed trajectories it raised the calculated expected goal mass to
199.5956; 208 goals were realised. Removing that floor alone gives 93.7393
expected goals, with the existing execution modifier and denominator floor.
These are conditional diagnostic sums, not forecasts of changed match paths.

The accepted resolver removes the 6% minimum. It also divides by the actual
probability of reaching the on-target stage instead of imposing a 0.08 minimum
on that denominator. A numerical epsilon protects division by zero. Thus,
for equal finisher/keeper execution and below the existing upper ceiling:

`P(unblocked) * P(on target | unblocked) * P(goal | on target) == situation xG`.

Situation xG, on-target probability, block probability, player attributes and
keeper attributes are unchanged. Finisher/keeper quality still modifies
conversion after xG. The pre-existing 0.86 conditional upper cap is retained
and remains an explicit limitation at the high-probability end.

## Isolated experiments: all results retained

Same 300 seeds, `91000..91299`, same synthetic population and home/away context.
The real reference was reloaded: 5,329 usable matches, 15 league/season files.
The index is diagnostic, not a target or percentage of realism.

| Variant | Goals/game | Yellow/game | Red/game | Realism index |
|---|---:|---:|---:|---:|
| Baseline | 2.9467 | 3.3500 | 0.0667 | 81.1644 |
| Second-caution correction only | 2.9667 | 3.4700 | 0.1700 | 82.0861 |
| Rejected broad direct-red experiment | 3.0200 | 3.4533 | 0.2500 | 79.5410 |
| Rejected direct-red experiment + shot fix | 2.8933 | 3.4500 | 0.2633 | 79.4963 |
| Accepted candidate | 2.8333 | 3.4967 | 0.1833 | 80.9787 |
| Real reference | 2.825 | 4.138 | 0.194 | — |

The rejected experiment mapped referee consistency to recognition accuracy
using `0.5 + 0.5 * consistency` for explicit dismissal signals. That mapping
was not justified by the meaning of the existing consistency attribute, which
controls judgment variability. It was removed rather than retained as an
arbitrary red-card boost. Its results are included in the JSON audit. Rejection
was a modelling decision; no seeds or individual match results were selected.

## Accepted candidate versus baseline

| Benchmark metric | Baseline | Accepted | Real reference |
|---|---:|---:|---:|
| Shots/game | 25.833 | 25.913 | 25.275 |
| On-target/game | 9.547 | 9.487 | 8.878 |
| Fouls/game | 25.640 | 25.650 | 23.839 |
| Corners/game | 9.860 | 9.830 | 9.688 |
| Home goals/game | 1.553 | 1.473 | 1.550 |
| Away goals/game | 1.393 | 1.360 | 1.275 |
| Home win | 39.67% | 38.00% | 43.6% |
| Draw | 24.00% | 24.67% | 25.2% |
| Away win | 36.33% | 37.33% | 31.2% |
| 0–0 | 7.00% | 7.67% | 6.1% |
| Both score | 54.33% | 51.67% | 54.9% |
| Over 2.5 | 52.67% | 49.00% | 53.5% |

Regressions are not hidden: home scoring and some score distributions moved
away from the reference, and the overall index fell by 0.186 points. These are
downstream outcomes of disciplinary and conversion changes. Venue logic was
neither investigated for tuning nor changed, as requested. The remaining
excess of fouls/SOT and shortage of yellows is not fixed by a global multiplier.

## Generic 1,000-match validation

Contiguous seeds `0..999`; identical fixture templates before/after.

| Metric | Baseline | Accepted |
|---|---:|---:|
| Goals/game | 2.332 | 2.231 |
| Shots/game | 24.722 | 24.735 |
| On-target/game | 8.525 | 8.520 |
| xG/game | 2.3071 | 2.3207 |
| Goals/xG | 1.0108 | 0.9613 |
| 0–0 | 10.9% | 11.8% |
| Low-bin goals / xG | 208 / 96.1225 | 93 / 96.4109 |
| Low-bin goals/xG | 2.1639 | 0.9646 |

The near-unity global baseline ratio partly concealed offsetting errors. The
accepted low bin is consistent with the removal of the artificial floor. The
global 3.87% shortfall is reported, not compensated by altering finishing or
situation xG. Execution quality, ceilings, other bins and sampling remain
relevant; this report does not declare global conversion fully calibrated.

## Heavy Audit: 500 identical seeds

| Metric | Baseline | Accepted |
|---|---:|---:|
| Goals/game | 2.506 | 2.432 |
| Reds/game | 0.070 | 0.164 |
| Games with red | 6.8% | 15.4% |
| Final minute, mean | 97.40 | 97.43 |
| First-half added minutes | 2.268 | 2.254 |
| Second-half added minutes | 5.822 | 5.856 |
| Share of goals after 90 | 8.1% | 8.1% |
| Distinct foulers/game | 14.432 | 14.426 |
| Top fouler share | 15.2% | 15.2% |
| Tactical fouls/game | 0.516 | 0.510 |
| Penalties/game | 0.172 | 0.168 |
| Penalty conversion | 72.1% | 75.0% |
| One-on-ones/game | 2.184 | 2.218 |
| One-on-one conversion | 25.9% | 25.4% |
| Second balls/game | 5.682 | 5.662 |
| Attacking second-ball recovery | 44.6% | 45.0% |
| Load injuries/game | 0.096 | 0.098 |

The foul distribution and late-match timing remain similar in this sample.
Dismissals rise without adding foul quotas; penalty and one-on-one movements
are observed downstream changes, not separate tuning. The baseline full log
was lost during an execution-environment reset; its retained measurements are
labelled as such in the JSON. The complete accepted output is preserved.

## Validation and reproduction

- 755 active core/v1.3 tests passed locally on Python 3.12; no v1.2 compatibility
  gate was restored.
- Eight new tests cover low-xG probability conservation, bounds, execution
  direction, second-caution draw consistency, source invariance, the violent
  conduct exception, tactical red configuration and RNG-pure helpers.
- Existing save/load, deterministic continuation and shot-ledger tests passed.
- Observed/control complete exported state and RNG were compared before batch
  acceptance; the observer does not consume RNG.
- Every audited match checked ledger coverage, unique shot IDs and xG sums.
- The official seed was never used to construct or advance a simulated match.
  Existing quarantine tests only verify rejection before simulation.

Run from a checkout containing the diagnostic, pointing at each desired
engine checkout (the diagnostic uses worker processes, not agents):

```sh
python causal_audit_v13.py /path/to/baseline benchmark 300 /tmp/baseline.json --verify-observer
python causal_audit_v13.py /path/to/candidate benchmark 300 /tmp/candidate.json --verify-observer
python causal_audit_v13.py /path/to/candidate generic 1000 /tmp/generic.json --verify-observer
python realism_diagnostics_v13.py 500 --start-seed 70000
```

The Heavy Audit uses seeds `70000..70499`. Its retained baseline measurements and full candidate output,
complete severity bins, chance-origin decomposition, reference distributions
and paired descriptive intervals are stored in
`audits/v13_causal_refinement_20260917/summary.json`.

No ratings, traits, venue source, official results or reserved seed changed.
The current v1.3 branch remains a candidate; main is not merged or promoted.
