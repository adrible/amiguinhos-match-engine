from __future__ import annotations

"""Direct 9-match batch: Brasil 2002 x DanganLock.

Runs nine complete independent matches with the exact locked live-fixture
configuration, changing only the deterministic seed. No narration stepping is
used.
"""

import hashlib
import json
from statistics import mean

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from historical_2014_v13 import load_team_for_v13
from narration_packet_v13 import format_match_clock

HOME_KEY = "brazil_2002"
AWAY_KEY = "danganlock"
BASE_SEED_BASIS = "brazil_2002|danganlock|amiguinhos-match-engine-v1.3|live"
MATCH_COUNT = 9


def seed_for(index: int) -> tuple[int, str]:
    basis = f"{BASE_SEED_BASIS}|direct-batch|{index}"
    seed = int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)
    return seed, basis


def build_engine(seed: int) -> MatchEngine:
    home = load_team_for_v13(HOME_KEY)
    away = load_team_for_v13(AWAY_KEY)
    config = MatchConfig(
        regulation_minutes=90,
        allow_extra_time=False,
        max_substitutions=3,
        allow_extra_time_substitution=False,
        relevant_threshold=2,
        direct_red_enabled=True,
        injuries_enabled=True,
        auto_tactical_adaptation=True,
    )
    return MatchEngine(
        home,
        away,
        seed=seed,
        config=config,
        venue_context={"mode": "neutral", "source": "locked_live_fixture"},
    )


def compact_stats(row) -> dict:
    return {
        "goals": int(row.goals),
        "shots": int(row.shots),
        "on_target": int(row.on_target),
        "blocked": int(row.blocked),
        "xg": round(float(row.xg), 3),
        "corners": int(row.corners),
        "fouls": int(row.fouls),
        "offsides": int(row.offsides),
        "yellow": int(row.yellow),
        "red": int(row.red),
        "saves": int(row.saves),
        "big_chances": int(row.big_chances),
        "final_third_entries": int(row.final_third_entries),
    }


def run_match(index: int) -> dict:
    seed, basis = seed_for(index)
    engine = build_engine(seed)

    beats = 0
    while not engine.state.ended:
        engine.step()
        beats += 1
        if beats > 20000:
            raise RuntimeError(f"match {index} exceeded safety beat limit")

    snapshot = engine.snapshot()
    home_stats = compact_stats(engine.stats[0])
    away_stats = compact_stats(engine.stats[1])
    total_possession = float(engine.stats[0].possession_seconds + engine.stats[1].possession_seconds)
    if total_possession > 0:
        home_poss = 100.0 * float(engine.stats[0].possession_seconds) / total_possession
    else:
        home_poss = 50.0
    away_poss = 100.0 - home_poss

    awards = snapshot.get("awards", {})
    mom = awards.get("man_of_the_match") or {}

    return {
        "match": index,
        "seed": seed,
        "seed_basis": basis,
        "score": [int(engine.stats[0].goals), int(engine.stats[1].goals)],
        "home": {**home_stats, "possession_pct": round(home_poss, 1)},
        "away": {**away_stats, "possession_pct": round(away_poss, 1)},
        "final_clock": format_match_clock(engine, float(engine.state.second)),
        "raw_minute": round(float(engine.minute), 3),
        "events": len(engine.state.event_log),
        "man_of_the_match": {
            "player": mom.get("player"),
            "team_name": mom.get("team_name"),
            "rating": mom.get("rating"),
        },
    }


def main() -> None:
    matches = [run_match(i) for i in range(1, MATCH_COUNT + 1)]

    home_wins = sum(1 for m in matches if m["score"][0] > m["score"][1])
    draws = sum(1 for m in matches if m["score"][0] == m["score"][1])
    away_wins = MATCH_COUNT - home_wins - draws

    summary = {
        "matches": MATCH_COUNT,
        "home_wins": home_wins,
        "draws": draws,
        "away_wins": away_wins,
        "avg_home_goals": round(mean(m["score"][0] for m in matches), 3),
        "avg_away_goals": round(mean(m["score"][1] for m in matches), 3),
        "avg_total_goals": round(mean(sum(m["score"]) for m in matches), 3),
        "avg_home_xg": round(mean(m["home"]["xg"] for m in matches), 3),
        "avg_away_xg": round(mean(m["away"]["xg"] for m in matches), 3),
        "avg_total_xg": round(mean(m["home"]["xg"] + m["away"]["xg"] for m in matches), 3),
        "avg_home_shots": round(mean(m["home"]["shots"] for m in matches), 3),
        "avg_away_shots": round(mean(m["away"]["shots"] for m in matches), 3),
        "avg_total_shots": round(mean(m["home"]["shots"] + m["away"]["shots"] for m in matches), 3),
        "avg_home_on_target": round(mean(m["home"]["on_target"] for m in matches), 3),
        "avg_away_on_target": round(mean(m["away"]["on_target"] for m in matches), 3),
        "avg_home_possession": round(mean(m["home"]["possession_pct"] for m in matches), 3),
        "avg_away_possession": round(mean(m["away"]["possession_pct"] for m in matches), 3),
        "avg_home_fouls": round(mean(m["home"]["fouls"] for m in matches), 3),
        "avg_away_fouls": round(mean(m["away"]["fouls"] for m in matches), 3),
        "avg_yellows": round(mean(m["home"]["yellow"] + m["away"]["yellow"] for m in matches), 3),
        "avg_reds": round(mean(m["home"]["red"] + m["away"]["red"] for m in matches), 3),
    }

    result = {
        "fixture": f"{HOME_KEY} x {AWAY_KEY}",
        "configuration": {
            "regulation_minutes": 90,
            "allow_extra_time": False,
            "max_substitutions": 3,
            "allow_extra_time_substitution": False,
            "relevant_threshold": 2,
            "direct_red_enabled": True,
            "injuries_enabled": True,
            "auto_tactical_adaptation": True,
            "venue_mode": "neutral",
        },
        "matches": matches,
        "summary": summary,
    }

    print("BATCH_RESULT_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("BATCH_RESULT_END")


if __name__ == "__main__":
    main()
