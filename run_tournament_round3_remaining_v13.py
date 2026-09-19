from __future__ import annotations

"""Official remaining Round 3 batch for the Interdimensional 16-team tournament.

A5 (DanganLock x Ajax 1995) was played live and A6 (Brasil 2002 x Bastard München)
was already finalized. This script simulates the six remaining Group B/C/D fixtures.

Each fixture receives the standings context that existed before its own kickoff.
The sibling match in the same group remains scheduled, so there is no knowledge
of a simultaneous future result.
"""

import hashlib
import json
from pathlib import Path

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
import run_tournament_round1_v13 as base
from tournament_state_v13 import TournamentStateV13

PACK_PATH = Path("data/tournaments/torneio_16_times_engine_v13.json")
RESULT_PATH = Path("artifacts/tournament_interdimensional_round3_remaining_result.json")
TOURNAMENT_BASIS = "interdimensional-16|2026-09-19|round-3|v1.3"

GROUPS = {
    "B": ["real_madrid_2017", "france_u20_blue_lock", "man_utd_2008", "germany_u20_tsubasa"],
    "C": ["barcelona_2011", "france_1998", "milan_2007", "japan_u20_tsubasa"],
    "D": ["inazuma_japan", "ubers", "argentina_2022", "teikoku"],
}

PRIOR = {
    "B": [
        ("B1", "real_madrid_2017", "man_utd_2008", 0, 1),
        ("B2", "france_u20_blue_lock", "germany_u20_tsubasa", 4, 2),
        ("B3", "real_madrid_2017", "france_u20_blue_lock", 3, 2),
        ("B4", "man_utd_2008", "germany_u20_tsubasa", 4, 5),
    ],
    "C": [
        ("C1", "milan_2007", "barcelona_2011", 1, 2),
        ("C2", "japan_u20_tsubasa", "france_1998", 0, 0),
        ("C3", "milan_2007", "japan_u20_tsubasa", 0, 1),
        ("C4", "barcelona_2011", "france_1998", 2, 3),
    ],
    "D": [
        ("D1", "ubers", "teikoku", 2, 3),
        ("D2", "inazuma_japan", "argentina_2022", 1, 1),
        ("D3", "ubers", "inazuma_japan", 3, 2),
        ("D4", "teikoku", "argentina_2022", 4, 2),
    ],
}

FIXTURES = [
    ("B5", "B", "real_madrid_2017", "germany_u20_tsubasa"),
    ("B6", "B", "france_u20_blue_lock", "man_utd_2008"),
    ("C5", "C", "barcelona_2011", "japan_u20_tsubasa"),
    ("C6", "C", "france_1998", "milan_2007"),
    ("D5", "D", "inazuma_japan", "teikoku"),
    ("D6", "D", "ubers", "argentina_2022"),
]

ROUND3_BY_GROUP = {
    "B": [("B5", "real_madrid_2017", "germany_u20_tsubasa"), ("B6", "france_u20_blue_lock", "man_utd_2008")],
    "C": [("C5", "barcelona_2011", "japan_u20_tsubasa"), ("C6", "france_1998", "milan_2007")],
    "D": [("D5", "inazuma_japan", "teikoku"), ("D6", "ubers", "argentina_2022")],
}


def seed_for(fixture_id: str, home_key: str, away_key: str) -> tuple[int, str]:
    basis = f"{TOURNAMENT_BASIS}|{fixture_id}|{home_key}|{away_key}"
    seed = int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)
    return seed, basis


def tournament_for(group: str) -> TournamentStateV13:
    fixtures = []
    for fid, home, away, hg, ag in PRIOR[group]:
        fixtures.append({
            "id": fid, "stage_id": f"group_{group.lower()}", "group": group,
            "home": home, "away": away, "status": "final", "score": [hg, ag],
        })
    for fid, home, away in ROUND3_BY_GROUP[group]:
        fixtures.append({
            "id": fid, "stage_id": f"group_{group.lower()}", "group": group,
            "home": home, "away": away, "status": "scheduled", "score": [0, 0],
        })
    return TournamentStateV13(
        competition_id="interdimensional-16-20260918",
        teams=GROUPS[group],
        stages={
            f"group_{group.lower()}": {
                "kind": "group",
                "name": f"Grupo {group}",
                "group": group,
                "groups": {group: GROUPS[group]},
                "qualify_positions": [1, 2],
                "points": {"win": 3, "draw": 1, "loss": 0},
                "tiebreakers": ["points", "goal_difference", "goals_for", "wins", "team"],
            }
        },
        fixtures=fixtures,
    )


def run_fixture(pack: dict, fixture_id: str, group: str, home_key: str, away_key: str) -> dict:
    seed, basis = seed_for(fixture_id, home_key, away_key)
    home = base.build_registered_team(pack, home_key)
    away = base.build_registered_team(pack, away_key)
    config = MatchConfig(
        regulation_minutes=90,
        allow_extra_time=False,
        max_substitutions=5,
        allow_extra_time_substitution=False,
        relevant_threshold=2,
        direct_red_enabled=True,
        injuries_enabled=True,
        auto_tactical_adaptation=True,
    )
    engine = MatchEngine(
        home,
        away,
        seed=seed,
        config=config,
        venue_context={"mode": "neutral", "source": "interdimensional_tournament_round3"},
    )
    tournament = tournament_for(group)
    tournament.update_live(fixture_id, 0, 0, 0.0)
    engine.set_tournament_context(tournament.context_for_fixture(fixture_id))

    original_step = engine.step
    def tournament_aware_step():
        hg, ag = engine.score
        tournament.update_live(fixture_id, hg, ag, engine.minute)
        engine.set_tournament_context(tournament.context_for_fixture(fixture_id))
        return original_step()
    engine.step = tournament_aware_step

    beats = 0
    while not engine.state.ended:
        engine.step()
        beats += 1
        if beats > 25000:
            raise RuntimeError(f"{fixture_id} exceeded safety beat limit")

    snapshot = engine.snapshot()
    h = base.compact_stats(engine.stats[0])
    a = base.compact_stats(engine.stats[1])
    total_poss = float(engine.stats[0].possession_seconds + engine.stats[1].possession_seconds)
    h["possession_pct"] = round(100.0 * float(engine.stats[0].possession_seconds) / total_poss, 1) if total_poss else 50.0
    a["possession_pct"] = round(100.0 - h["possession_pct"], 1)
    mom = snapshot.get("awards", {}).get("man_of_the_match") or {}

    return {
        "fixture_id": fixture_id,
        "group": group,
        "seed": seed,
        "seed_basis": basis,
        "home_key": home_key,
        "away_key": away_key,
        "home_name": home.name,
        "away_name": away.name,
        "score": [int(engine.score[0]), int(engine.score[1])],
        "home": h,
        "away": a,
        "goals": base.goals_from_log(engine),
        "man_of_the_match": {
            "player": mom.get("player"),
            "team_name": mom.get("team_name"),
            "rating": mom.get("rating"),
        },
        "final_clock": snapshot.get("display_clock"),
        "raw_minute": round(float(engine.minute), 3),
        "beats": beats,
        "events": len(engine.state.event_log),
    }


def main() -> None:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    results = [run_fixture(pack, *fixture) for fixture in FIXTURES]
    payload = {
        "competition": pack["competition"],
        "engine": "v1.3 active candidate",
        "round": 3,
        "configuration": {
            "venue_mode": "neutral",
            "regulation_minutes": 90,
            "allow_extra_time": False,
            "max_substitutions": 5,
            "injuries_enabled": True,
            "direct_red_enabled": True,
            "auto_tactical_adaptation": True,
            "tournament_context": True,
            "simultaneous_sibling_result_hidden": True,
            "seed_policy": "one SHA-256-derived deterministic seed per fixture; no retries",
        },
        "already_finalized_round3": {
            "A5": {"home": "danganlock", "away": "ajax_1995", "score": [2, 3]},
            "A6": {"home": "brazil_2002", "away": "bastard_munchen", "score": [1, 2]},
        },
        "fixtures": results,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print("TOURNAMENT_ROUND3_RESULT_BEGIN")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print("TOURNAMENT_ROUND3_RESULT_END")


if __name__ == "__main__":
    main()
