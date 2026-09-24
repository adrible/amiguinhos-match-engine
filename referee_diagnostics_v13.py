from __future__ import annotations

"""Outcome-blind diagnostics for the v1.3 referee / foul model.

This harness deliberately measures only disciplinary mechanics and never
selects or filters results.  It rejects the reserved official-final seed.
"""

import argparse
from collections import Counter
import json

from engine import EventType, MatchConfig
from engine_experiment_v13 import MatchEngine
from final_protocol_v13 import OFFICIAL_FINAL_SEED, assert_calibration_seed_allowed
from team_loader_v13 import load_team_v13


HOME_KEY = "amiguinhos_u21"
AWAY_KEY = "flamengo_u21"


def run_referee_diagnostics(count: int = 100, start_seed: int = 60000) -> dict:
    if count <= 0:
        raise ValueError("count must be positive")

    foul_types: Counter[str] = Counter()
    cards: Counter[str] = Counter()
    card_reasons: Counter[str] = Counter()
    injuries: Counter[str] = Counter()
    reactions: Counter[str] = Counter()
    referee_styles: Counter[str] = Counter()
    special_totals: Counter[str] = Counter()
    totals = Counter()
    per_match_rows = []

    for seed in range(start_seed, start_seed + count):
        assert_calibration_seed_allowed(HOME_KEY, AWAY_KEY, seed)
        engine = MatchEngine(
            load_team_v13(HOME_KEY),
            load_team_v13(AWAY_KEY),
            seed=seed,
            config=MatchConfig(auto_tactical_adaptation=False),
        )
        guard = 0
        while not engine.state.ended and guard < 6000:
            engine.step()
            guard += 1
        if guard >= 6000:
            raise RuntimeError(f"match did not terminate for seed {seed}")

        referee_styles[engine.referee.style] += 1
        match_totals = Counter()
        for stats in engine.stats:
            totals["fouls"] += int(stats.fouls)
            totals["yellow_stat"] += int(stats.yellow)
            totals["red_stat"] += int(stats.red)
            match_totals["fouls"] += int(stats.fouls)
            match_totals["yellow"] += int(stats.yellow)
            match_totals["red"] += int(stats.red)

        for event in engine.state.event_log:
            if event.type in {EventType.FOUL, EventType.PENALTY} and event.data.get("foul_type"):
                foul_types[str(event.data["foul_type"])] += 1
            if event.text_key == "advantage_played":
                totals["advantages"] += 1
                match_totals["advantages"] += 1
            elif event.text_key == "referee_warning":
                totals["warnings"] += 1
                match_totals["warnings"] += 1
            elif event.text_key in {"player_reaction_to_foul", "mass_confrontation"}:
                reaction_name = str(event.data.get("reaction", event.text_key))
                reactions[reaction_name] += 1
                totals["reactions"] += 1
                match_totals["reactions"] += 1
                if event.text_key == "mass_confrontation":
                    totals["mass_confrontations"] += 1
                    match_totals["mass_confrontations"] += 1
            if event.type == EventType.CARD:
                card = str(event.data.get("card", "unknown"))
                reason = str(event.data.get("reason", "unknown"))
                cards[card] += 1
                card_reasons[reason] += 1
            if event.type == EventType.INJURY and event.text_key == "medical_assessment":
                grade = str(event.data.get("grade", "unknown"))
                injuries[grade] += 1
                totals["injury_events"] += 1
                match_totals["injuries"] += 1
            if event.text_key in {
                "penalty_for_handball",
                "handball_offence",
                "var_awards_penalty_handball",
            }:
                totals["handball_decisions"] += 1
                match_totals["handball_decisions"] += 1
            if event.text_key in {
                "simulation_detected",
                "simulation_no_call",
                "penalty_awarded_after_simulation",
                "free_kick_awarded_after_simulation",
            }:
                totals["simulation_events"] += 1
                match_totals["simulation_events"] += 1
            if event.text_key.startswith("var_"):
                totals["var_events"] += 1
                match_totals["var_events"] += 1

        diagnostic = engine.referee_diagnostic()
        special = diagnostic.get("special_counts", {})
        for key, value in special.items():
            special_totals[str(key)] += int(value)
        totals["ending_heat_sum"] += float(diagnostic.get("match_heat", 0.0))

        per_match_rows.append(
            {
                "seed": seed,
                "referee_style": engine.referee.style,
                "fouls": match_totals["fouls"],
                "yellow": match_totals["yellow"],
                "red": match_totals["red"],
                "advantages": match_totals["advantages"],
                "warnings": match_totals["warnings"],
                "reactions": match_totals["reactions"],
                "mass_confrontations": match_totals["mass_confrontations"],
                "injuries": match_totals["injuries"],
                "handball_decisions": match_totals["handball_decisions"],
                "simulation_events": match_totals["simulation_events"],
                "var_events": match_totals["var_events"],
                "ending_heat": float(diagnostic.get("match_heat", 0.0)),
            }
        )

    def avg(key: str) -> float:
        return float(totals[key]) / float(count)

    return {
        "fixture": [HOME_KEY, AWAY_KEY],
        "count": count,
        "start_seed": start_seed,
        "seed_policy": "contiguous_unfiltered_outcome_blind",
        "official_seed_quarantined": OFFICIAL_FINAL_SEED,
        "averages_per_match": {
            "fouls": avg("fouls"),
            "yellow_cards": avg("yellow_stat"),
            "red_cards": avg("red_stat"),
            "advantages": avg("advantages"),
            "warnings": avg("warnings"),
            "reactions": avg("reactions"),
            "mass_confrontations": avg("mass_confrontations"),
            "injury_events": avg("injury_events"),
            "handball_decisions": avg("handball_decisions"),
            "simulation_events": avg("simulation_events"),
            "var_events": avg("var_events"),
            "ending_match_heat": avg("ending_heat_sum"),
        },
        "foul_types": dict(sorted(foul_types.items())),
        "cards": dict(sorted(cards.items())),
        "card_reasons": dict(sorted(card_reasons.items())),
        "injury_grades": dict(sorted(injuries.items())),
        "reactions": dict(sorted(reactions.items())),
        "special_counts": dict(sorted(special_totals.items())),
        "referee_styles": dict(sorted(referee_styles.items())),
        "rows": per_match_rows,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=100)
    parser.add_argument("--start-seed", type=int, default=60000)
    parser.add_argument("--compact", action="store_true")
    args = parser.parse_args()
    report = run_referee_diagnostics(args.count, args.start_seed)
    if args.compact:
        report = {k: v for k, v in report.items() if k != "rows"}
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
