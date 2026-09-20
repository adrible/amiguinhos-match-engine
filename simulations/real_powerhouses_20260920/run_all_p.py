from __future__ import annotations

import hashlib
import json
from dataclasses import asdict
from pathlib import Path

from engine import MatchConfig, Player, POSITION_TEMPLATE, Tactics, Team
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13

HERE = Path(__file__).resolve().parent
FIXTURE_PATH = HERE / "fixture.json"


def clamp_rating(value: float) -> int:
    return int(max(20, min(95, round(value))))


def build_player(raw: dict) -> Player:
    name = str(raw["name"])
    position = str(raw["position"]).upper()
    overall = int(raw["overall"])
    if position not in POSITION_TEMPLATE:
        raise ValueError(f"unsupported position {position} for {name}")
    if not 1 <= overall <= 95:
        raise ValueError(f"invalid overall for {name}: {overall}")

    delta = overall - 75
    kwargs = {"name": name, "position": position, "overall": overall}
    for attr, base in POSITION_TEMPLATE[position].items():
        kwargs[attr] = clamp_rating(float(base) + delta * 0.72)

    kwargs.update({k: int(v) for k, v in raw.get("attributes", {}).items()})
    kwargs["preferred_foot"] = str(raw.get("preferred_foot", "R")).upper()
    player = Player(**kwargs)

    # Behavioural v1.3 traits are intentionally separate from execution ratings.
    for key, value in raw.get("traits", {}).items():
        setattr(player, key, float(value))
    setattr(player, "shirt_number", int(raw["number"]))
    return player


def build_team(raw: dict) -> Team:
    starters = [build_player(p) for p in raw["starters"]]
    bench = [build_player(p) for p in raw.get("bench", [])]
    if len(starters) != 11:
        raise ValueError(f'{raw["name"]}: expected exactly 11 starters')
    tactics = Tactics(**raw["tactics"]).normalized()
    return Team(name=raw["name"], starters=starters, bench=bench, tactics=tactics)


def team_card(raw: dict) -> dict:
    starters = raw["starters"]
    return {
        "name": raw["name"],
        "formation": raw["formation"],
        "starter_ovr": round(sum(float(p["overall"]) for p in starters) / 11.0, 2),
        "starters": [
            {
                "number": int(p["number"]),
                "name": p["name"],
                "position": p["position"],
                "overall": int(p["overall"]),
            }
            for p in starters
        ],
        "bench": [
            {
                "number": int(p["number"]),
                "name": p["name"],
                "position": p["position"],
                "overall": int(p["overall"]),
            }
            for p in raw.get("bench", [])
        ],
        "tactics": raw["tactics"],
    }


def compact_packet(packet: dict) -> dict:
    main = packet["main_event"]
    return {
        "clock": packet["clock"],
        "score": packet["score"],
        "emotion": packet.get("contextual_emotion"),
        "circulation_summary": packet.get("circulation_summary"),
        "main_event": {
            "type": main.get("type"),
            "team_name": main.get("team_name"),
            "text_key": main.get("text_key"),
            "facts": main.get("facts", {}),
        },
        "bridge_events": [
            {
                "clock": ev.get("clock"),
                "type": ev.get("type"),
                "team_name": ev.get("team_name"),
                "text_key": ev.get("text_key"),
                "facts": ev.get("facts", {}),
            }
            for ev in packet.get("bridge_events", [])
        ],
        "continuity": {
            "possession_before": packet.get("continuity", {}).get("possession_before"),
            "possession_after": packet.get("continuity", {}).get("possession_after"),
            "restart_resolved": packet.get("continuity", {}).get("restart_resolved"),
            "pending_before": packet.get("continuity", {}).get("pending_before"),
            "pending_after": packet.get("continuity", {}).get("pending_after"),
        },
    }


def compact_stats(engine: MatchEngine, team_index: int) -> dict:
    st = engine.stats[team_index]
    total_possession = float(engine.stats[0].possession_seconds + engine.stats[1].possession_seconds)
    poss = 50.0 if total_possession <= 0 else 100.0 * float(st.possession_seconds) / total_possession
    return {
        "goals": int(st.goals),
        "shots": int(st.shots),
        "on_target": int(st.on_target),
        "blocked": int(st.blocked),
        "posts": int(st.posts),
        "xg": round(float(st.xg), 3),
        "big_chances": int(st.big_chances),
        "corners": int(st.corners),
        "fouls": int(st.fouls),
        "yellow": int(st.yellow),
        "red": int(st.red),
        "offsides": int(st.offsides),
        "saves": int(st.saves),
        "final_third_entries": int(st.final_third_entries),
        "possession_pct": round(poss, 1),
        "substitutions": int(engine.teams[team_index].substitutions),
    }


def main() -> None:
    payload = json.loads(FIXTURE_PATH.read_text(encoding="utf-8"))
    home_raw, away_raw = payload["teams"]
    home = build_team(home_raw)
    away = build_team(away_raw)

    seed_basis = payload["fixture"]["seed_basis"]
    seed = int(hashlib.sha256(seed_basis.encode("utf-8")).hexdigest()[:8], 16)

    config = MatchConfig(
        regulation_minutes=int(payload["fixture"]["regulation_minutes"]),
        allow_extra_time=bool(payload["fixture"]["extra_time"]),
        max_substitutions=int(payload["fixture"]["max_substitutions"]),
        allow_extra_time_substitution=False,
        relevant_threshold=2,
        direct_red_enabled=True,
        injuries_enabled=True,
        auto_tactical_adaptation=bool(payload["fixture"]["auto_tactical_adaptation"]),
    )
    engine = MatchEngine(
        home,
        away,
        seed=seed,
        config=config,
        venue_context={"mode": "neutral", "source": "real_powerhouses_all_p"},
    )
    session = MatchSessionV13(engine)
    if not session.pristine:
        raise RuntimeError("fixture must start pristine at 00:00")

    packets = []
    safety = 0
    while not session.engine.state.ended:
        packet = session.press_p_packet()
        if packet.get("narrate") or packet["main_event"]["type"] == "match_end":
            packets.append(compact_packet(packet))
        safety += 1
        if safety > 600:
            raise RuntimeError("all-p simulation exceeded 600 narration advances")

    snapshot = session.snapshot()
    result = {
        "engine": "amiguinhos-match-engine v1.3",
        "branch_base": "v1.3-spatial-creativity-boldness",
        "fixture_file": str(FIXTURE_PATH.relative_to(HERE.parent.parent)),
        "seed": seed,
        "seed_basis": seed_basis,
        "venue_mode": "neutral",
        "teams": [team_card(home_raw), team_card(away_raw)],
        "all_p_count": len(packets),
        "packets": packets,
        "final": {
            "score": [int(engine.stats[0].goals), int(engine.stats[1].goals)],
            "home": compact_stats(engine, 0),
            "away": compact_stats(engine, 1),
            "snapshot_awards": snapshot.get("awards", {}),
            "snapshot_player_ratings": snapshot.get("player_ratings", {}),
            "final_raw_minute": round(float(engine.minute), 3),
            "event_log_count": len(engine.state.event_log),
        },
    }

    print("REAL_POWERHOUSES_RESULT_BEGIN")
    print(json.dumps(result, ensure_ascii=False, separators=(",", ":")))
    print("REAL_POWERHOUSES_RESULT_END")


if __name__ == "__main__":
    main()
