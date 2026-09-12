from __future__ import annotations

"""Broad, outcome-blind evaluation harness for the v1.3 candidate.

This module does not tune or search seeds. It evaluates Amiguinhos against
all other tournament teams using a deterministic schedule of contiguous seed
ranges, in both home/away orientations. The official final seed is never part
of the schedule.
"""

import argparse
import json
from pathlib import Path
from statistics import mean
from typing import Iterable

from calibration_v13 import run_fixture_batch
from final_protocol_v13 import OFFICIAL_FINAL_SEED


TEAMS_PATH = Path(__file__).resolve().parent / "data" / "teams.json"


def tournament_teams() -> dict[str, dict]:
    data = json.loads(TEAMS_PATH.read_text(encoding="utf-8"))
    teams = data.get("teams", {})
    if not isinstance(teams, dict):
        raise ValueError("data/teams.json missing teams object")
    return teams


def evaluation_schedule(*, count_per_orientation: int = 12, base_seed: int = 1000) -> list[dict]:
    if count_per_orientation <= 0:
        raise ValueError("count_per_orientation must be positive")
    opponents = sorted(k for k in tournament_teams() if k != "amiguinhos_u21")
    schedule: list[dict] = []
    for index, opponent in enumerate(opponents):
        start = int(base_seed) + index * 1000
        seeds = list(range(start, start + int(count_per_orientation)))
        if OFFICIAL_FINAL_SEED in seeds:
            raise AssertionError("evaluation schedule intersects quarantined official seed")
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


def main(argv: Iterable[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--count", type=int, default=12, help="seeds per home/away orientation")
    parser.add_argument("--base-seed", type=int, default=1000)
    parser.add_argument("--auto-adapt", action="store_true")
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args(list(argv) if argv is not None else None)
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
