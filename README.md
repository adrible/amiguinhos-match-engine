# Amiguinhos Match Engine

## Active engine line

**v1.3 is the only active development line.** The former v1.2 engine is preserved unchanged for historical reference on the `archive-v1.2-stable` branch at commit `ee00e47c535796d74616462b7a9975b83ad15589`; active runtime, ratings and CI no longer maintain v1.2 compatibility.

## General runtime and branches

The general active engine lives on `v1.3-spatial-creativity-boldness` and is
imported with `from engine_experiment_v13 import MatchEngine`. Spatial finishing,
creative passes, goalkeeper exposure and `MatchSessionV13.press_p_batch(N)` apply
to every fixture and competition using this runtime, not only the
interdimensional tournament. `runner_v13.py` accepts `p 5x` and `p 10x`.
Tournament branches carry fixture/session data; they are not the sole location
for engine improvements. Pin older completed matches to their original commit
for exact replay. The historical `main`/v1.2 snapshot is not the active v1.3 runtime.

## v1.3

The engine keeps outcome-blind simulation rules and adds contextual football behaviour, including:

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
- literal current player ratings;
- exact state/RNG persistence;
- real extra time and stateful live shootouts;
- interactive live `p` runner;
- contextual automatic substitutions;
- canonical per-shot xG ledger;
- quarantine of the declared official-final seed.

### One ratings source

`data/teams.json` is the canonical base source for player OVR and execution attributes on the active line. Candidate roster entries in `data/v13_rosters.json` may define an explicit replacement roster where necessary (for example a sourced opponent pool), while `data/v13_player_traits.json` contains behavioural traits only and must not duplicate execution ratings.

Creativity, boldness and determination are separate behavioural traits and do not directly add technical execution ratings.

### Shot and xG accounting

Every resolved shot is recorded once in engine state with a unique `shot_id` and its exact xG. Diagnostics read this ledger instead of reconstructing attempts from public narration events, so blocks, rebounds, corners, free kicks and penalties cannot silently disappear from xG calibration.

### Automatic substitutions

The v1.3 coach can make substitutions autonomously at stoppages. Normal changes are contextual rather than clock quotas: fatigue, card exposure, chasing the game, protecting a lead and late freshness can justify a change. Before the normal second-half substitution window, automatic changes are emergency-only, primarily injury. A pending live action is never interrupted by a substitution.

The known Amiguinhos bench remains explicit. Tournament opponents that have no bench data at all receive a deterministic, neutral reserve pool so lack of source depth does not disable substitutions. This fallback never replaces any explicitly supplied bench.

### Outcome policy

The engine never chooses a winner, score, shot count or goal total in advance. Statistics are consequences, not quotas. Multi-seed diagnostics use contiguous, unfiltered schedules and retain all results.

The official final seed is reserved and must never be previewed, dry-run, calibration-tested or seed-shopped. Only the explicit live official-final runner may unlock it when the real simulation starts.

## Calibração geral em campo neutro

A revisão de 19/09/2026 calibra a precisão espacial e sua conversão, preservando o xG da situação. Em `mode="neutral"`, nenhum lado recebe vantagem de torcida, familiaridade ou viagem, inclusive com metadados antigos assimétricos. Use `compare_general_engine_v13.py --neutral` para comparar agregados sem distinguir mando. Resultados, limitações e reprodução: [calibração neutra](NEUTRAL_CALIBRATION_v13_20260919.md).

A [revisão de contato e disciplina de 20/09/2026](CONTACT_CALIBRATION_v13_20260920.md) considera espaço livre no contato faltoso e reforça a reincidência na decisão de amarelo. Inclui validação independente e diagnóstico pareado da ordem dos times, com as regressões do índice global documentadas.

[Alvos do chute e passes criativos](TARGET_PASS_VARIETY_v13_20260920.md): meio alto e cantos bilaterais explícitos, técnicas de primeira ligadas à recepção e escolha ponderada de passes difíceis; comparação real e regressões documentadas.

[Calibração de ritmo e ambiente](CADENCE_CALIBRATION_v13_20260920.md): clima invariável à ordem dos times, menor dispersão de ritmo e validação de 300 confrontos nas duas ordens (600 partidas por versão), com incerteza e resultados individuais preservados.
