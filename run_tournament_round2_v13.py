from __future__ import annotations

"""Official remaining Round 2 batch for the Interdimensional 16-team tournament.

Fixture A3 (DanganLock x Bastard München) was played live and is not rerun here.
All remaining fixtures use one deterministic seed each, with no retries.
"""

import json
from pathlib import Path

import run_tournament_round1_v13 as base

PACK_PATH = Path("data/tournaments/torneio_16_times_engine_v13.json")
RESULT_PATH = Path("artifacts/tournament_interdimensional_round2_remaining_result.json")
TOURNAMENT_BASIS = "interdimensional-16|2026-09-19|round-2|v1.3"

FIXTURES = [
    ("A4", "brazil_2002", "ajax_1995"),
    ("B3", "real_madrid_2017", "france_u20_blue_lock"),
    ("B4", "man_utd_2008", "germany_u20_tsubasa"),
    ("C3", "milan_2007", "japan_u20_tsubasa"),
    ("C4", "barcelona_2011", "france_1998"),
    ("D3", "ubers", "inazuma_japan"),
    ("D4", "teikoku", "argentina_2022"),
]

def main() -> None:
    base.TOURNAMENT_BASIS = TOURNAMENT_BASIS
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    results = [base.run_fixture(pack, *fixture) for fixture in FIXTURES]
    payload = {
        "competition": pack["competition"],
        "engine": "v1.3 active candidate",
        "round": 2,
        "live_fixture_preserved": {
            "fixture_id": "A3",
            "home_key": "danganlock",
            "away_key": "bastard_munchen",
            "score": [1, 2],
            "status": "played_live_do_not_rerun"
        },
        "configuration": {
            "venue_mode": "neutral",
            "regulation_minutes": 90,
            "allow_extra_time": False,
            "max_substitutions": 5,
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
    print("TOURNAMENT_ROUND2_RESULT_BEGIN")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print("TOURNAMENT_ROUND2_RESULT_END")

if __name__ == "__main__":
    main()

