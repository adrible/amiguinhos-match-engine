from __future__ import annotations

"""Official Round 1 batch for the Interdimensional 16-team tournament.

One deterministic seed per fixture. No seed shopping, no score targeting.
All matches run on the active v1.3 MatchEngine and use the registered tournament
pack. Brazil 2002 and DanganLock keep their canonical repository definitions.
"""

import hashlib
import json
from pathlib import Path

from engine import MatchConfig, Player, Team, Tactics
from engine_experiment_v13 import MatchEngine
from historical_2014_v13 import load_team_for_v13
from narration_packet_v13 import format_match_clock

PACK_PATH = Path("data/tournaments/torneio_16_times_engine_v13.json")
RESULT_PATH = Path("artifacts/tournament_interdimensional_round1_result.json")
TOURNAMENT_BASIS = "interdimensional-16|2026-09-18|round-1|v1.3"

FIXTURES = [
    ("A1", "danganlock", "brazil_2002"),
    ("A2", "bastard_munchen", "ajax_1995"),
    ("B1", "real_madrid_2017", "man_utd_2008"),
    ("B2", "france_u20_blue_lock", "germany_u20_tsubasa"),
    ("C1", "milan_2007", "barcelona_2011"),
    ("C2", "japan_u20_tsubasa", "france_1998"),
    ("D1", "ubers", "teikoku"),
    ("D2", "inazuma_japan", "argentina_2022"),
]

PROFILE_TRAITS = {
    "creator": ("creativity", 6),
    "playmaker": ("creativity", 6),
    "dribbler": ("creativity", 4),
    "finisher": ("boldness", 5),
    "inside_forward": ("boldness", 4),
    "speedster": ("boldness", 3),
    "leader": ("determination", 6),
    "box_to_box": ("determination", 4),
    "destroyer": ("determination", 5),
    "stopper": ("determination", 4),
    "anchor": ("determination", 4),
}

def clamp_rating(value: float) -> float:
    return max(20.0, min(99.0, float(value)))

def seed_for(fixture_id: str, home_key: str, away_key: str) -> tuple[int, str]:
    basis = f"{TOURNAMENT_BASIS}|{fixture_id}|{home_key}|{away_key}"
    seed = int(hashlib.sha256(basis.encode("utf-8")).hexdigest()[:8], 16)
    return seed, basis

def apply_behaviour(player: Player, raw: dict) -> None:
    # Deterministic profile-based behavioural layer; execution ratings remain
    # exactly those in the registered pack.
    base = float(raw.get("overall", 75))
    values = {"creativity": base, "boldness": base, "determination": base}
    for profile in raw.get("rating_profile", []):
        mapped = PROFILE_TRAITS.get(str(profile))
        if mapped:
            attr, delta = mapped
            values[attr] += delta
    for attr, value in values.items():
        setattr(player, attr, clamp_rating(value))

def build_registered_team(pack: dict, team_key: str) -> Team:
    raw = pack["teams"][team_key]
    if raw.get("mode") == "existing_engine_entry":
        return load_team_for_v13(raw.get("source_key", team_key))

    starters = []
    bench = []
    for p in raw["players"]:
        attrs = dict(p["attributes"])
        player = Player(
            name=p["name"],
            position=p["position"],
            overall=int(p["overall"]),
            preferred_foot=p.get("preferred_foot", "R"),
            **attrs,
        )
        player.number = int(p.get("number", 0))
        player.positions = list(p.get("positions", [p["position"]]))
        apply_behaviour(player, p)
        if p["squad"] == "starter":
            starters.append(player)
        else:
            bench.append(player)

    if len(starters) != 11:
        raise ValueError(f"{team_key}: expected 11 starters, got {len(starters)}")

    team = Team(
        name=raw["name"],
        starters=starters,
        bench=bench,
        tactics=Tactics(**raw["tactics"]).normalized(),
    )
    team.declared_overall = float(raw.get("overall", 0))
    team.tournament_key = team_key
    return team

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

def goals_from_log(engine: MatchEngine) -> list[dict]:
    out = []
    for event in engine.state.event_log:
        event_type = getattr(event.type, "value", str(event.type))
        if event_type != "goal":
            continue
        out.append({
            "minute": round(float(event.minute), 2),
            "team": int(event.team),
            "player": event.data.get("player") or event.data.get("scorer"),
            "assist": event.data.get("assist"),
            "data": event.data,
        })
    return out

def run_fixture(pack: dict, fixture_id: str, home_key: str, away_key: str) -> dict:
    seed, basis = seed_for(fixture_id, home_key, away_key)
    home = build_registered_team(pack, home_key)
    away = build_registered_team(pack, away_key)
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
        venue_context={"mode": "neutral", "source": "interdimensional_tournament"},
    )

    beats = 0
    while not engine.state.ended:
        engine.step()
        beats += 1
        if beats > 25000:
            raise RuntimeError(f"{fixture_id} exceeded safety beat limit")

    snapshot = engine.snapshot()
    h = compact_stats(engine.stats[0])
    a = compact_stats(engine.stats[1])
    total_poss = float(engine.stats[0].possession_seconds + engine.stats[1].possession_seconds)
    home_poss = (100.0 * float(engine.stats[0].possession_seconds) / total_poss) if total_poss else 50.0
    away_poss = 100.0 - home_poss
    mom = (snapshot.get("awards", {}).get("man_of_the_match") or {})

    return {
        "fixture_id": fixture_id,
        "group": fixture_id[0],
        "seed": seed,
        "seed_basis": basis,
        "home_key": home_key,
        "away_key": away_key,
        "home_name": home.name,
        "away_name": away.name,
        "score": [int(engine.stats[0].goals), int(engine.stats[1].goals)],
        "home": {**h, "possession_pct": round(home_poss, 1)},
        "away": {**a, "possession_pct": round(away_poss, 1)},
        "goals": goals_from_log(engine),
        "final_clock": format_match_clock(engine, float(engine.state.second)),
        "raw_minute": round(float(engine.minute), 3),
        "events": len(engine.state.event_log),
        "beats": beats,
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
        "engine": "v1.3 active candidate",
        "round": 1,
        "draw_seed": pack.get("draw_seed"),
        "old_brazil_danganlock_result": "superseded",
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
    print("TOURNAMENT_ROUND1_RESULT_BEGIN")
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))
    print("TOURNAMENT_ROUND1_RESULT_END")

if __name__ == "__main__":
    main()
