from __future__ import annotations

"""Transparent v1.3 multi-seed calibration and fixture stress harness.

The harness never searches for favourable outcomes.  A batch is exactly the
contiguous range ``start_seed .. start_seed + count - 1`` and every result is
retained.  Aggregate figures are diagnostics, not tuning targets.
"""

import argparse
import json
from collections import Counter
from statistics import mean, median
from typing import Iterable, Type

from engine import Band, Lane, MatchConfig, Zone
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import assert_calibration_seed_allowed
from team_loader_v13 import load_team_v13


class MatchEngineV13UncappedAdaptationProbe(MatchEngine):
    """Diagnostic-only engine: expose natural adaptation demand, never release."""

    MAX_ADAPTATIONS_PER_TEAM = 99


def _run_to_end(engine: MatchEngine, guard_limit: int = 5000) -> None:
    guard = 0
    while not engine.state.ended and guard < guard_limit:
        engine.step()
        guard += 1
    if guard >= guard_limit:
        raise RuntimeError(f"simulation guard reached for seed {engine.seed}")


def _event_error_counts(engine: MatchEngine) -> dict[str, int]:
    counts: Counter[str] = Counter()
    for ev in engine.state.event_log:
        payload = ev.data.get("defensive_error") if isinstance(ev.data, dict) else None
        if isinstance(payload, dict) and payload.get("type"):
            counts[str(payload["type"])] += 1
    return dict(sorted(counts.items()))


def _adaptation_distribution(matches: list[dict], engine_cls: Type[MatchEngine]) -> dict:
    """Describe coaching reactivity without imposing a tuning quota."""
    team_match_counts: list[int] = []
    intervals: list[float] = []
    first_minutes: list[float] = []
    cap = int(getattr(engine_cls, "MAX_ADAPTATIONS_PER_TEAM", 0) or 0)

    for row in matches:
        adaptations = row.get("adaptations", [])
        for team in (0, 1):
            minutes = sorted(
                float(item["minute"])
                for item in adaptations
                if int(item.get("team", -1)) == team and item.get("minute") is not None
            )
            team_match_counts.append(len(minutes))
            if minutes:
                first_minutes.append(minutes[0])
                intervals.extend(
                    later - earlier for earlier, later in zip(minutes, minutes[1:])
                )

    distribution = Counter(team_match_counts)
    cap_hits = sum(1 for value in team_match_counts if cap > 0 and value >= cap)
    observations = len(team_match_counts)
    total = sum(team_match_counts)
    return {
        "team_match_observations": observations,
        "total_adaptations": total,
        "mean_per_team_match": mean(team_match_counts) if team_match_counts else 0.0,
        "median_per_team_match": median(team_match_counts) if team_match_counts else 0.0,
        "max_per_team_match": max(team_match_counts, default=0),
        "count_distribution": {
            str(key): distribution[key] for key in sorted(distribution)
        },
        "configured_team_cap": cap,
        "team_matches_hitting_cap": cap_hits,
        "cap_hit_rate": (cap_hits / observations) if observations else 0.0,
        "mean_minutes_between_adaptations": mean(intervals) if intervals else None,
        "minimum_minutes_between_adaptations": min(intervals) if intervals else None,
        "mean_first_adaptation_minute": mean(first_minutes) if first_minutes else None,
    }


def simulate_fixture(
    home_key: str,
    away_key: str,
    seed: int,
    *,
    auto_adapt: bool = False,
    _engine_cls: Type[MatchEngine] = MatchEngine,
) -> dict:
    assert_calibration_seed_allowed(home_key, away_key, seed)

    home = load_team_v13(home_key)
    away = load_team_v13(away_key)
    config = MatchConfig(auto_tactical_adaptation=auto_adapt)
    engine = _engine_cls(home, away, seed=int(seed), config=config)
    _run_to_end(engine)

    h, a = engine.stats
    for st in (h, a):
        if st.shots < st.on_target or st.on_target < st.goals or st.xg < 0.0:
            raise AssertionError(f"statistic invariant failed on seed {seed}")

    if h.goals > a.goals:
        result = "home"
    elif a.goals > h.goals:
        result = "away"
    else:
        result = "draw"

    adaptation_history = (
        engine.adaptation_history() if hasattr(engine, "adaptation_history") else []
    )
    return {
        "seed": int(seed),
        "home_key": home_key,
        "away_key": away_key,
        "home_name": engine.teams[0].team.name,
        "away_name": engine.teams[1].team.name,
        "result": result,
        "score": [h.goals, a.goals],
        "home": {
            "goals": h.goals,
            "shots": h.shots,
            "on_target": h.on_target,
            "xg": h.xg,
            "big_chances": h.big_chances,
            "offsides": h.offsides,
            "final_third_entries": h.final_third_entries,
        },
        "away": {
            "goals": a.goals,
            "shots": a.shots,
            "on_target": a.on_target,
            "xg": a.xg,
            "big_chances": a.big_chances,
            "offsides": a.offsides,
            "final_third_entries": a.final_third_entries,
        },
        "defensive_errors": _event_error_counts(engine),
        "adaptations": [
            {
                "minute": row.get("minute"),
                "team": row.get("team"),
                "response": row.get("response"),
            }
            for row in adaptation_history
        ],
        "event_count": len(engine.state.event_log),
    }


def run_fixture_batch(
    home_key: str,
    away_key: str,
    *,
    start_seed: int = 0,
    count: int = 100,
    auto_adapt: bool = False,
    _engine_cls: Type[MatchEngine] = MatchEngine,
) -> dict:
    if count <= 0:
        raise ValueError("count must be positive")
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    matches = [
        simulate_fixture(
            home_key, away_key, seed,
            auto_adapt=auto_adapt,
            _engine_cls=_engine_cls,
        )
        for seed in seeds
    ]

    results = Counter(row["result"] for row in matches)

    def avg(side: str, field: str) -> float:
        return mean(float(row[side][field]) for row in matches)

    error_counts: Counter[str] = Counter()
    adaptation_counts: Counter[str] = Counter()
    for row in matches:
        error_counts.update(row["defensive_errors"])
        adaptation_counts.update(
            str(x["response"]) for x in row["adaptations"] if x.get("response")
        )

    return {
        "fixture": [home_key, away_key],
        "seed_policy": "contiguous_unfiltered",
        "start_seed": int(start_seed),
        "count": int(count),
        "seeds": seeds,
        "auto_adapt": bool(auto_adapt),
        "diagnostic_engine": _engine_cls is not MatchEngine,
        "results": {
            "home_wins": results["home"],
            "draws": results["draw"],
            "away_wins": results["away"],
        },
        "averages": {
            "home_goals": avg("home", "goals"),
            "away_goals": avg("away", "goals"),
            "home_xg": avg("home", "xg"),
            "away_xg": avg("away", "xg"),
            "home_shots": avg("home", "shots"),
            "away_shots": avg("away", "shots"),
            "home_on_target": avg("home", "on_target"),
            "away_on_target": avg("away", "on_target"),
            "home_big_chances": avg("home", "big_chances"),
            "away_big_chances": avg("away", "big_chances"),
        },
        "defensive_errors": dict(sorted(error_counts.items())),
        "adaptation_responses": dict(sorted(adaptation_counts.items())),
        "adaptation_diagnostics": _adaptation_distribution(matches, _engine_cls),
        "matches": matches,
    }


def player_behavior_profile(
    team_key: str,
    player_name: str,
    *,
    opponent_key: str = "flamengo_u21",
) -> dict:
    home = load_team_v13(team_key)
    away = load_team_v13(opponent_key)
    engine = MatchEngine(home, away, seed=0)
    player = engine.teams[0].by_name(player_name)
    tactics = engine.teams[0].team.tactics

    contexts = {
        "mid_center": (
            Zone(Band.MID, Lane.CENTER),
            {"pressure": 0.44, "space": 0.56, "space_behind": 0.48, "support": 0.54, "transition_threat": 0.45},
        ),
        "att_center": (
            Zone(Band.ATT, Lane.CENTER),
            {"pressure": 0.48, "space": 0.52, "space_behind": 0.54, "support": 0.56, "transition_threat": 0.50},
        ),
        "att_wide": (
            Zone(Band.ATT, Lane.RIGHT),
            {"pressure": 0.46, "space": 0.54, "space_behind": 0.50, "support": 0.58, "transition_threat": 0.48},
        ),
    }

    profiles = {}
    for label, (zone, ctx) in contexts.items():
        probs = engine.decision_probabilities(player, zone, tactics, ctx)
        hidden = engine.hidden_option_diagnostic(0, player, zone, ctx)
        profiles[label] = {
            "decision_probabilities": probs,
            "hidden_option": hidden,
        }

    return {
        "team": team_key,
        "player": player_name,
        "creativity": engine._creativity(player),
        "boldness": engine._boldness(player),
        "explicit_creativity": getattr(player.player, "creativity", None),
        "explicit_boldness": getattr(player.player, "boldness", None),
        "contexts": profiles,
    }


def amiguinhos_flamengo_stress(
    *,
    start_seed: int = 0,
    count: int = 100,
    auto_adapt: bool = False,
    uncapped_adaptation_diagnostic: bool = False,
) -> dict:
    engine_cls = (
        MatchEngineV13UncappedAdaptationProbe
        if uncapped_adaptation_diagnostic else MatchEngine
    )
    return run_fixture_batch(
        "amiguinhos_u21",
        "flamengo_u21",
        start_seed=start_seed,
        count=count,
        auto_adapt=auto_adapt,
        _engine_cls=engine_cls,
    )


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=0)
    parser.add_argument("--auto-adapt", action="store_true")
    parser.add_argument("--uncapped-adaptation-diagnostic", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.uncapped_adaptation_diagnostic and not args.auto_adapt:
        parser.error("--uncapped-adaptation-diagnostic requires --auto-adapt")

    result = amiguinhos_flamengo_stress(
        start_seed=args.start_seed,
        count=args.count,
        auto_adapt=args.auto_adapt,
        uncapped_adaptation_diagnostic=args.uncapped_adaptation_diagnostic,
    )
    if args.compact:
        result = {k: v for k, v in result.items() if k != "matches"}
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
