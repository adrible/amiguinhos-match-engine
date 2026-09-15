from __future__ import annotations

"""Broad, outcome-blind evaluation harness for the v1.3 candidate.

This module does not tune or search seeds. It evaluates Amiguinhos against
all other tournament teams using deterministic contiguous seed ranges, can
compare the exact same seeds with/without tactical adaptation, and can stress
the full knockout path (extra time + live shootout). The official final seed
is never part of any diagnostic schedule.
"""

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Iterable

from calibration_v13 import run_fixture_batch
from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import OFFICIAL_FINAL_SEED, assert_calibration_seed_allowed
from team_loader_v13 import load_team_v13


TEAMS_PATH = Path(__file__).resolve().parent / "data" / "teams.json"


def tournament_teams() -> dict[str, dict]:
    data = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    teams = data.get("teams", {})
    if not isinstance(teams, dict):
        raise ValueError("data/teams.json missing teams object")
    return teams


def _assert_safe_seed_range(start_seed: int, count: int) -> list[int]:
    if count <= 0:
        raise ValueError("count must be positive")
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    if OFFICIAL_FINAL_SEED in seeds:
        raise AssertionError("evaluation schedule intersects quarantined official seed")
    return seeds


def evaluation_schedule(*, count_per_orientation: int = 12, base_seed: int = 1000) -> list[dict]:
    if count_per_orientation <= 0:
        raise ValueError("count_per_orientation must be positive")
    opponents = sorted(k for k in tournament_teams() if k != "amiguinhos_u21")
    schedule: list[dict] = []
    for index, opponent in enumerate(opponents):
        start = int(base_seed) + index * 1000
        _assert_safe_seed_range(start, int(count_per_orientation))
        schedule.append({
            "opponent": opponent,
            "home_key": "amiguinhos_u21",
            "away_key": opponent,
            "start_seed": start,
            "count": int(count_per_orientation),
        })
        schedule.append({
            "opponent": opponent,
            "home_key": opponent,
            "away_key": "amiguinhos_u21",
            "start_seed": start,
            "count": int(count_per_orientation),
        })
    return schedule


def _amiguinhos_view(batch: dict) -> dict:
    home_is_amiguinhos = batch["fixture"][0] == "amiguinhos_u21"
    if home_is_amiguinhos:
        wins = batch["results"]["home_wins"]
        losses = batch["results"]["away_wins"]
        goals_for = batch["averages"]["home_goals"]
        goals_against = batch["averages"]["away_goals"]
        xg_for = batch["averages"]["home_xg"]
        xg_against = batch["averages"]["away_xg"]
        shots_for = batch["averages"]["home_shots"]
        shots_against = batch["averages"]["away_shots"]
    else:
        wins = batch["results"]["away_wins"]
        losses = batch["results"]["home_wins"]
        goals_for = batch["averages"]["away_goals"]
        goals_against = batch["averages"]["home_goals"]
        xg_for = batch["averages"]["away_xg"]
        xg_against = batch["averages"]["home_xg"]
        shots_for = batch["averages"]["away_shots"]
        shots_against = batch["averages"]["home_shots"]
    return {
        "wins": wins,
        "draws": batch["results"]["draws"],
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "xg_for": xg_for,
        "xg_against": xg_against,
        "shots_for": shots_for,
        "shots_against": shots_against,
    }


def run_broad_evaluation(
    *,
    count_per_orientation: int = 12,
    base_seed: int = 1000,
    auto_adapt: bool = False,
) -> dict:
    teams = tournament_teams()
    rows = []
    for spec in evaluation_schedule(
        count_per_orientation=count_per_orientation,
        base_seed=base_seed,
    ):
        batch = run_fixture_batch(
            spec["home_key"], spec["away_key"],
            start_seed=spec["start_seed"], count=spec["count"],
            auto_adapt=auto_adapt,
        )
        view = _amiguinhos_view(batch)
        rows.append({
            **spec,
            "opponent_overall": teams[spec["opponent"]].get("overall"),
            **view,
        })

    by_opponent = {}
    for opponent in sorted({row["opponent"] for row in rows}):
        pair = [row for row in rows if row["opponent"] == opponent]
        matches = sum(int(row["count"]) for row in pair)
        wins = sum(int(row["wins"]) for row in pair)
        draws = sum(int(row["draws"]) for row in pair)
        losses = sum(int(row["losses"]) for row in pair)
        by_opponent[opponent] = {
            "opponent_overall": pair[0]["opponent_overall"],
            "matches": matches,
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "points_per_match": (3 * wins + draws) / matches,
            "goals_for": mean(row["goals_for"] for row in pair),
            "goals_against": mean(row["goals_against"] for row in pair),
            "xg_for": mean(row["xg_for"] for row in pair),
            "xg_against": mean(row["xg_against"] for row in pair),
            "shots_for": mean(row["shots_for"] for row in pair),
            "shots_against": mean(row["shots_against"] for row in pair),
        }

    total_matches = sum(v["matches"] for v in by_opponent.values())
    total_wins = sum(v["wins"] for v in by_opponent.values())
    total_draws = sum(v["draws"] for v in by_opponent.values())
    total_losses = sum(v["losses"] for v in by_opponent.values())
    return {
        "seed_policy": "deterministic_contiguous_ranges_no_filtering",
        "official_seed_quarantined": OFFICIAL_FINAL_SEED,
        "count_per_orientation": int(count_per_orientation),
        "orientations_per_opponent": 2,
        "opponents": len(by_opponent),
        "total_matches": total_matches,
        "overall_results": {
            "wins": total_wins,
            "draws": total_draws,
            "losses": total_losses,
            "points_per_match": (3 * total_wins + total_draws) / total_matches,
        },
        "by_opponent": by_opponent,
        "rows": rows,
    }


def _compact_batch(batch: dict) -> dict:
    return {key: value for key, value in batch.items() if key not in {"matches", "seeds"}}


def _home_points_per_match(batch: dict) -> float:
    return (
        3 * int(batch["results"]["home_wins"]) + int(batch["results"]["draws"])
    ) / int(batch["count"])


def run_adaptation_ab(
    *,
    count: int = 120,
    start_seed: int = 30000,
) -> dict:
    """Compare identical unfiltered seeds with and without auto adaptation."""
    _assert_safe_seed_range(start_seed, count)
    without = run_fixture_batch(
        "amiguinhos_u21", "flamengo_u21",
        start_seed=start_seed, count=count, auto_adapt=False,
    )
    with_adapt = run_fixture_batch(
        "amiguinhos_u21", "flamengo_u21",
        start_seed=start_seed, count=count, auto_adapt=True,
    )
    return {
        "fixture": ["amiguinhos_u21", "flamengo_u21"],
        "seed_policy": "same_contiguous_unfiltered_range_for_both_conditions",
        "start_seed": int(start_seed),
        "count": int(count),
        "official_seed_quarantined": OFFICIAL_FINAL_SEED,
        "without_adaptation": _compact_batch(without),
        "with_adaptation": _compact_batch(with_adapt),
        "deltas_with_minus_without": {
            "amiguinhos_points_per_match": _home_points_per_match(with_adapt) - _home_points_per_match(without),
            "amiguinhos_goals": with_adapt["averages"]["home_goals"] - without["averages"]["home_goals"],
            "amiguinhos_xg": with_adapt["averages"]["home_xg"] - without["averages"]["home_xg"],
            "flamengo_goals": with_adapt["averages"]["away_goals"] - without["averages"]["away_goals"],
            "flamengo_xg": with_adapt["averages"]["away_xg"] - without["averages"]["away_xg"],
        },
    }


def _run_knockout_to_end(engine: MatchEngine, guard_limit: int = 7000) -> None:
    guard = 0
    while not engine.state.ended and guard < guard_limit:
        engine.step()
        guard += 1
    if guard >= guard_limit:
        raise RuntimeError(f"knockout simulation guard reached for seed {engine.seed}")


def run_knockout_stress(
    *,
    count: int = 120,
    start_seed: int = 40000,
    auto_adapt: bool = True,
) -> dict:
    """Stress the final-like path without ever using the official final seed."""
    seeds = _assert_safe_seed_range(start_seed, count)
    winners = {"amiguinhos": 0, "flamengo": 0}
    decided_by = {"regulation": 0, "extra_time": 0, "shootout": 0}
    goals_for = []
    goals_against = []

    for seed in seeds:
        assert_calibration_seed_allowed("amiguinhos_u21", "flamengo_u21", seed)
        engine = MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
            config=MatchConfig(
                auto_tactical_adaptation=auto_adapt,
                allow_extra_time=True,
            ),
        )
        _run_knockout_to_end(engine)

        shootout = getattr(engine, "_v13_shootout", None)
        if isinstance(shootout, dict) and shootout.get("winner") is not None:
            winner = int(shootout["winner"])
            mode = "shootout"
        else:
            if engine.score[0] == engine.score[1]:
                raise AssertionError(f"knockout ended unresolved on seed {seed}")
            winner = 0 if engine.score[0] > engine.score[1] else 1
            reached_extra_time = any(
                event.text_key == "regulation_end_tied" for event in engine.state.event_log
            )
            mode = "extra_time" if reached_extra_time else "regulation"

        winners["amiguinhos" if winner == 0 else "flamengo"] += 1
        decided_by[mode] += 1
        goals_for.append(engine.stats[0].goals)
        goals_against.append(engine.stats[1].goals)

    return {
        "fixture": ["amiguinhos_u21", "flamengo_u21"],
        "seed_policy": "contiguous_unfiltered_final_like_nonofficial_seeds",
        "start_seed": int(start_seed),
        "count": int(count),
        "auto_adapt": bool(auto_adapt),
        "allow_extra_time": True,
        "official_seed_quarantined": OFFICIAL_FINAL_SEED,
        "winners": winners,
        "decided_by": decided_by,
        "average_regulation_plus_extra_time_goals": {
            "amiguinhos": mean(goals_for),
            "flamengo": mean(goals_against),
        },
    }


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=12, help="seeds per orientation, or batch count in special modes")
    parser.add_argument("--base-seed", type=int, default=1000)
    parser.add_argument("--auto-adapt", action="store_true")
    parser.add_argument("--adaptation-ab", action="store_true")
    parser.add_argument("--knockout", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)

    if args.adaptation_ab and args.knockout:
        parser.error("--adaptation-ab and --knockout are mutually exclusive")

    if args.adaptation_ab:
        result = run_adaptation_ab(count=args.count, start_seed=args.base_seed)
    elif args.knockout:
        result = run_knockout_stress(
            count=args.count,
            start_seed=args.base_seed,
            auto_adapt=True if not args.auto_adapt else args.auto_adapt,
        )
    else:
        result = run_broad_evaluation(
            count_per_orientation=args.count,
            base_seed=args.base_seed,
            auto_adapt=args.auto_adapt,
        )
        if args.compact:
            result.pop("rows", None)

    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
