from __future__ import annotations

"""Outcome-blind discipline audit for the real-match benchmark population.

This diagnostic intentionally uses the same deterministic population generator,
venue mode and seed range as ``real_match_benchmark_v13.py``.  It does not alter
engine behaviour and does not read target card rates while a match is running.
Its purpose is to distinguish referee-model effects from synthetic-population
attribute effects before any further discipline calibration is attempted.
"""

import argparse
from collections import Counter
import json
import random
import statistics

from engine import EventType, make_generic_team
from engine_experiment_v13 import MatchEngine
from real_match_benchmark_v13 import (
    BENCHMARK_VENUE_MODE,
    RESERVED_OFFICIAL_FINAL_SEED,
    STRENGTHS,
    STRENGTH_WEIGHTS,
    STYLES,
    STYLE_WEIGHTS,
    _weighted_pick,
)


def _summary(values: list[float]) -> dict[str, float]:
    if not values:
        return {"mean": 0.0, "pstdev": 0.0, "min": 0.0, "max": 0.0}
    return {
        "mean": statistics.mean(values),
        "pstdev": statistics.pstdev(values),
        "min": min(values),
        "max": max(values),
    }


def _correlation(left: list[float], right: list[float]) -> float:
    if len(left) < 2 or len(right) != len(left):
        return 0.0
    if statistics.pstdev(left) == 0.0 or statistics.pstdev(right) == 0.0:
        return 0.0
    return statistics.correlation(left, right)


def run(count: int = 300, start_seed: int = 91000) -> dict:
    if count <= 0:
        raise ValueError("count must be positive")
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    if RESERVED_OFFICIAL_FINAL_SEED in seeds:
        raise ValueError("Reserved official final seed cannot be used by diagnostics")

    player_aggression: list[float] = []
    player_discipline: list[float] = []
    team_aggression: list[float] = []
    team_discipline: list[float] = []
    aggression_minus_discipline: list[float] = []
    strengths: list[int] = []
    styles: Counter[str] = Counter()

    totals: Counter[str] = Counter()
    card_types: Counter[str] = Counter()
    card_reasons: Counter[str] = Counter()
    original_foul_cards: Counter[str] = Counter()
    incident_types: Counter[str] = Counter()
    ordinary_contact_cards: Counter[str] = Counter()
    referee_styles: Counter[str] = Counter()

    for seed in seeds:
        population_rng = random.Random(f"v13-real-population:{seed}")
        home_strength = int(_weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS))
        away_strength = int(_weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS))
        home_style = str(_weighted_pick(population_rng, STYLES, STYLE_WEIGHTS))
        away_style = str(_weighted_pick(population_rng, STYLES, STYLE_WEIGHTS))
        strengths.extend([home_strength, away_strength])
        styles.update([home_style, away_style])

        home = make_generic_team(
            f"Benchmark Home {seed}",
            home_strength,
            home_style,
            seed=900000 + seed * 2,
        )
        away = make_generic_team(
            f"Benchmark Away {seed}",
            away_strength,
            away_style,
            seed=900001 + seed * 2,
        )

        for team in (home, away):
            aggs = [float(player.aggression) for player in team.starters]
            discs = [float(player.discipline) for player in team.starters]
            player_aggression.extend(aggs)
            player_discipline.extend(discs)
            aggression_minus_discipline.extend(a - d for a, d in zip(aggs, discs))
            team_aggression.append(statistics.mean(aggs))
            team_discipline.append(statistics.mean(discs))

        engine = MatchEngine(
            home,
            away,
            seed=seed,
            venue_context={
                "mode": BENCHMARK_VENUE_MODE,
                "source": "discipline_population_diagnostic",
            },
        )
        guard = 0
        while not engine.state.ended and guard < 7000:
            engine.step()
            guard += 1
        if guard >= 7000:
            raise RuntimeError(f"Simulation guard reached on seed {seed}")

        referee_styles[str(engine.referee.style)] += 1
        match_fouls = sum(int(stats.fouls) for stats in engine.stats)
        match_yellows = sum(int(stats.yellow) for stats in engine.stats)
        match_reds = sum(int(stats.red) for stats in engine.stats)
        totals["fouls"] += match_fouls
        totals["yellow"] += match_yellows
        totals["red"] += match_reds

        for event in engine.state.event_log:
            data = event.data or {}
            if event.type == EventType.CARD:
                card_types[str(data.get("card", "unknown"))] += 1
                card_reasons[str(data.get("reason", "unknown"))] += 1
            if event.text_key == "referee_warning":
                totals["warnings"] += 1

            if event.text_key not in {
                "foul_incident",
                "advantage_played",
                "penalty_awarded_contextual",
            }:
                continue
            foul_type = str(data.get("foul_type", "unknown"))
            incident_types[foul_type] += 1
            totals["primary_incidents"] += 1
            totals["spa_incidents"] += int(bool(data.get("spa")))
            totals["dogso_incidents"] += int(bool(data.get("dogso")))
            totals["persistent_incidents"] += int(int(data.get("foul_count", 0)) >= 3)
            ordinary = bool(data.get("ordinary_contact"))
            totals["ordinary_contact_incidents"] += int(ordinary)

            card = data.get("card")
            if card:
                card_name = str(card)
                original_foul_cards[card_name] += 1
                if ordinary:
                    ordinary_contact_cards[card_name] += 1
                if card_name == "yellow":
                    totals["first_yellow_original_foul"] += 1
                    totals["spa_first_yellow"] += int(bool(data.get("spa")))
                    totals["persistent_first_yellow"] += int(int(data.get("foul_count", 0)) >= 3)
                elif card_name == "second_yellow_red":
                    totals["second_yellow_original_foul"] += 1
                elif card_name == "direct_red":
                    totals["direct_red_original_foul"] += 1

    matches = float(count)
    fouls = float(totals["fouls"])
    yellow = float(totals["yellow"])
    player_count = float(len(player_aggression)) or 1.0
    high_risk_tail = sum(
        1 for a, d in zip(player_aggression, player_discipline)
        if a >= 75.0 and d <= 65.0
    )
    aggressive_over_discipline = sum(
        1 for gap in aggression_minus_discipline if gap >= 10.0
    )

    report = {
        "count": count,
        "start_seed": start_seed,
        "seed_range": [start_seed, start_seed + count - 1],
        "seed_policy": "same_contiguous_unfiltered_range_as_real_match_benchmark",
        "official_seed_quarantined": RESERVED_OFFICIAL_FINAL_SEED,
        "venue_mode": BENCHMARK_VENUE_MODE,
        "population": {
            "team_strength": _summary([float(value) for value in strengths]),
            "styles": dict(sorted(styles.items())),
            "starter_aggression": _summary(player_aggression),
            "starter_discipline": _summary(player_discipline),
            "player_aggression_discipline_correlation": _correlation(
                player_aggression, player_discipline
            ),
            "team_mean_aggression_discipline_correlation": _correlation(
                team_aggression, team_discipline
            ),
            "aggression_minus_discipline": _summary(aggression_minus_discipline),
            "players_aggression_75_plus_discipline_65_minus_share": high_risk_tail / player_count,
            "players_aggression_minus_discipline_10_plus_share": aggressive_over_discipline / player_count,
        },
        "discipline": {
            "fouls_per_match": fouls / matches,
            "yellow_per_match": yellow / matches,
            "red_per_match": float(totals["red"]) / matches,
            "yellow_per_foul": yellow / fouls if fouls else 0.0,
            "warnings_per_match": float(totals["warnings"]) / matches,
            "primary_incidents_per_match": float(totals["primary_incidents"]) / matches,
            "ordinary_contact_incidents_per_match": float(totals["ordinary_contact_incidents"]) / matches,
            "spa_incidents_per_match": float(totals["spa_incidents"]) / matches,
            "persistent_incidents_per_match": float(totals["persistent_incidents"]) / matches,
            "first_yellow_original_foul_per_match": float(totals["first_yellow_original_foul"]) / matches,
            "second_yellow_original_foul_per_match": float(totals["second_yellow_original_foul"]) / matches,
            "direct_red_original_foul_per_match": float(totals["direct_red_original_foul"]) / matches,
            "spa_first_yellow_per_match": float(totals["spa_first_yellow"]) / matches,
            "persistent_first_yellow_per_match": float(totals["persistent_first_yellow"]) / matches,
        },
        "card_types": dict(sorted(card_types.items())),
        "card_reasons": dict(sorted(card_reasons.items())),
        "original_foul_cards": dict(sorted(original_foul_cards.items())),
        "ordinary_contact_cards": dict(sorted(ordinary_contact_cards.items())),
        "incident_types": dict(sorted(incident_types.items())),
        "referee_styles": dict(sorted(referee_styles.items())),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=300)
    parser.add_argument("--start-seed", type=int, default=91000)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.start_seed), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
