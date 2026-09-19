from __future__ import annotations

"""Interdimensional Tournament — quarterfinal first legs (DanganLock fixture excluded).

Runs only the first leg of the three non-DanganLock quarterfinal ties on the
active v1.3 candidate. A first-leg draw is valid: there is no extra time and no
penalty shootout. One deterministic seed per fixture; no retries.
"""

import hashlib
import json
from pathlib import Path

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from narration_packet_v13 import format_match_clock
import run_tournament_round1_v13 as base

PACK_PATH = Path("data/tournaments/torneio_16_times_engine_v13.json")
RESULT_PATH = Path("artifacts/tournament_interdimensional_quarterfinals_leg1_non_dangan_result.json")
TOURNAMENT_BASIS = "interdimensional-16|2026-09-19|quarterfinals|leg-1|v1.3"

FIXTURES = [
    ("QF1-L1", "ajax_1995", "argentina_2022"),
    # QF2-L1 Royal Academy / Teikoku x DanganLock intentionally preserved for live play.
    ("QF3-L1", "real_madrid_2017", "japan_u20_tsubasa"),
    ("QF4-L1", "france_1998", "man_utd_2008"),
]


def seed_for(fixture_id: str, home_key: str, away_key: str) -> tuple[int, str]:
    basis = f"{TOURNAMENT_BASIS}|{fixture_id}|{home_key}|{away_key}"
    return int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16), basis


def run_fixture(pack: dict, fixture_id: str, home_key: str, away_key: str) -> dict:
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
        venue_context={"mode": "neutral", "source": "interdimensional_quarterfinals_leg1"},
    )

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
    hp = 100.0 * float(engine.stats[0].possession_seconds) / total_poss if total_poss else 50.0
    ap = 100.0 - hp

    if engine.score[0] > engine.score[1]:
        leg_winner_side = 0
        leg_winner_key = home_key
        leg_winner_name = home.name
    elif engine.score[1] > engine.score[0]:
        leg_winner_side = 1
        leg_winner_key = away_key
        leg_winner_name = away.name
    else:
        leg_winner_side = None
        leg_winner_key = None
        leg_winner_name = None

    mom = (snapshot.get("awards", {}).get("man_of_the_match") or {})
    return {
        "fixture_id": fixture_id,
        "leg": 1,
        "tie_status": "open_for_second_leg",
        "home_key": home_key,
        "away_key": away_key,
        "home_name": home.name,
        "away_name": away.name,
        "score": [int(engine.score[0]), int(engine.score[1])],
        "leg_winner_side": leg_winner_side,
        "leg_winner_key": leg_winner_key,
        "leg_winner_name": leg_winner_name,
        "seed": seed,
        "seed_basis": basis,
        "home": {**h, "possession_pct": round(hp, 1)},
        "away": {**a, "possession_pct": round(ap, 1)},
        "goals": base.goals_from_log(engine),
        "final_clock": format_match_clock(engine, float(engine.state.second)),
        "raw_minute": round(float(engine.minute), 3),
        "beats": beats,
        "events": len(engine.state.event_log),
        "man_of_the_match": {
            "player": mom.get("player"),
            "team_name": mom.get("team_name"),
            "rating": mom.get("rating"),
        },
    }


def main() -> None:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    results = [run_fixture(pack, *fixture) for fixture in FIXTURES]
    payload = {
        "competition": pack["competition"],
        "stage": "quarterfinals",
        "leg": 1,
        "format": "two_legged",
        "engine": "v1.3 active candidate",
        "excluded_fixture": {
            "fixture_id": "QF2-L1",
            "home_key": "teikoku",
            "away_key": "danganlock",
            "status": "preserved_for_live_play",
        },
        "configuration": {
            "venue_mode": "neutral",
            "regulation_minutes": 90,
            "allow_extra_time": False,
            "penalty_shootout": False,
            "max_substitutions": 5,
            "allow_extra_time_substitution": False,
            "injuries_enabled": True,
            "direct_red_enabled": True,
            "auto_tactical_adaptation": True,
            "seed_policy": "one SHA-256-derived deterministic seed per fixture; no retries",
        },
        "fixtures": results,
    }
    RESULT_PATH.parent.mkdir(parents=True, exist_ok=True)
    RESULT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    print("INTERDIMENSIONAL_QF_LEG1_NON_DANGAN_RESULT_BEGIN")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print("INTERDIMENSIONAL_QF_LEG1_NON_DANGAN_RESULT_END")


if __name__ == "__main__":
    main()
