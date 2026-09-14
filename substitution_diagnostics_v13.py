from __future__ import annotations

"""Batch diagnostics for the v1.3 autonomous substitution coach.

Seeds are contiguous and unfiltered.  The report is descriptive only: it does
not tune toward a preferred result or a preferred number of substitutions.
"""

import argparse
import json
from collections import Counter
from statistics import mean, median

from engine import EventType, MatchConfig
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import assert_calibration_seed_allowed
from team_loader_v13 import load_team_v13


def run_substitution_batch(
    count: int = 100,
    *,
    start_seed: int = 50000,
    home_key: str = "amiguinhos_u21",
    away_key: str = "flamengo_u21",
    auto_adapt: bool = True,
) -> dict:
    if count <= 0:
        raise ValueError("count must be positive")

    per_team_match: list[int] = []
    minutes: list[float] = []
    reasons: Counter[str] = Counter()
    first_half: list[dict] = []
    matches_with_subs = 0
    maximum = 0

    for seed in range(int(start_seed), int(start_seed) + int(count)):
        assert_calibration_seed_allowed(home_key, away_key, seed)
        engine = MatchEngine(
            load_team_v13(home_key),
            load_team_v13(away_key),
            seed=seed,
            config=MatchConfig(auto_tactical_adaptation=bool(auto_adapt)),
        )
        guard = 0
        while not engine.state.ended and guard < 5000:
            engine.step()
            guard += 1
        if guard >= 5000:
            raise RuntimeError(f"simulation guard reached for seed {seed}")

        match_total = 0
        for team in (0, 1):
            team_events = [
                ev
                for ev in engine.state.event_log
                if ev.type == EventType.SUBSTITUTION
                and int(ev.team) == team
                and bool(ev.data.get("auto"))
            ]
            count_team = len(team_events)
            per_team_match.append(count_team)
            maximum = max(maximum, count_team)
            match_total += count_team
            for ev in team_events:
                minute = float(ev.minute)
                reason = str(ev.data.get("reason", "unknown"))
                minutes.append(minute)
                reasons[reason] += 1
                if minute < 45.0:
                    first_half.append(
                        {
                            "seed": seed,
                            "team": team,
                            "minute": minute,
                            "reason": reason,
                            "out": ev.data.get("out"),
                            "in": ev.data.get("in_player"),
                        }
                    )
        if match_total:
            matches_with_subs += 1

    invalid_first_half = [row for row in first_half if row["reason"] != "injury"]
    if invalid_first_half:
        raise AssertionError(
            "non-emergency automatic substitution occurred before half-time: "
            f"{invalid_first_half[:3]}"
        )

    observations = len(per_team_match)
    total = sum(per_team_match)
    return {
        "fixture": [home_key, away_key],
        "seed_policy": "contiguous_unfiltered",
        "start_seed": int(start_seed),
        "count": int(count),
        "auto_adapt": bool(auto_adapt),
        "official_seed_used": False,
        "matches_with_auto_substitutions": matches_with_subs,
        "team_match_observations": observations,
        "total_auto_substitutions": total,
        "mean_per_team_match": mean(per_team_match) if per_team_match else 0.0,
        "median_per_team_match": median(per_team_match) if per_team_match else 0.0,
        "max_per_team_match": maximum,
        "mean_minute": mean(minutes) if minutes else None,
        "first_minute": min(minutes) if minutes else None,
        "last_minute": max(minutes) if minutes else None,
        "first_half_auto_substitutions": len(first_half),
        "first_half_non_injury_substitutions": len(invalid_first_half),
        "reason_counts": dict(sorted(reasons.items())),
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=50000)
    parser.add_argument("--no-auto-adapt", action="store_true")
    args = parser.parse_args()
    result = run_substitution_batch(
        count=args.count,
        start_seed=args.start_seed,
        auto_adapt=not args.no_auto_adapt,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
