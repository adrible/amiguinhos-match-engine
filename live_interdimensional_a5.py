from __future__ import annotations

"""Locked live Round 3 Group A fixture: DanganLock x Ajax 1995.

The session starts pristine at 0:00 and advances only by narration step.
Tournament context includes all finalized Group A results, including the
administrative 3-0 W.O. awarded to DanganLock over Bastard München.
"""

import hashlib
import json
import sys

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13
from run_tournament_round1_v13 import PACK_PATH, build_registered_team
from tournament_state_v13 import TournamentStateV13

HOME_KEY = "danganlock"
AWAY_KEY = "ajax_1995"
FIXTURE_ID = "A5"
SEED_BASIS = "interdimensional-16|2026-09-19|round-3|A5|danganlock|ajax_1995|live"
SEED = int(hashlib.sha256(SEED_BASIS.encode("utf-8")).hexdigest()[:8], 16)


def build_tournament() -> TournamentStateV13:
    return TournamentStateV13(
        competition_id="interdimensional-16-20260918",
        teams=["danganlock", "brazil_2002", "bastard_munchen", "ajax_1995"],
        stages={
            "group_a": {
                "kind": "group",
                "name": "Grupo A",
                "group": "A",
                "groups": {
                    "A": ["danganlock", "brazil_2002", "bastard_munchen", "ajax_1995"]
                },
                "qualify_positions": [1, 2],
                "points": {"win": 3, "draw": 1, "loss": 0},
                "tiebreakers": ["points", "goal_difference", "goals_for", "wins", "team"],
            }
        },
        fixtures=[
            {"id":"A1","stage_id":"group_a","group":"A","home":"danganlock","away":"brazil_2002","status":"final","score":[0,1]},
            {"id":"A2","stage_id":"group_a","group":"A","home":"bastard_munchen","away":"ajax_1995","status":"final","score":[3,4]},
            {"id":"A3","stage_id":"group_a","group":"A","home":"danganlock","away":"bastard_munchen","status":"final","score":[3,0],"metadata":{"administrative_result":"W.O.","field_score":[1,2]}},
            {"id":"A4","stage_id":"group_a","group":"A","home":"brazil_2002","away":"ajax_1995","status":"final","score":[2,5]},
            {"id":"A5","stage_id":"group_a","group":"A","home":"danganlock","away":"ajax_1995","status":"scheduled","score":[0,0]},
            {"id":"A6","stage_id":"group_a","group":"A","home":"brazil_2002","away":"bastard_munchen","status":"final","score":[1,2]},
        ],
    )


def build_session() -> MatchSessionV13:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    home = build_registered_team(pack, HOME_KEY)
    away = build_registered_team(pack, AWAY_KEY)
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
        seed=SEED,
        config=config,
        venue_context={"mode":"neutral","source":"interdimensional_tournament_live"},
    )
    tournament = build_tournament()
    tournament.update_live(FIXTURE_ID, 0, 0, 0.0)
    engine.set_tournament_context(tournament.context_for_fixture(FIXTURE_ID))

    # Refresh competition context before every raw engine beat. This matters in
    # the final group match: DanganLock can remain qualified while trailing by
    # a limited margin, so generic "losing = chase" logic would be incorrect.
    original_step = engine.step
    def tournament_aware_step():
        home_goals, away_goals = engine.score
        tournament.update_live(FIXTURE_ID, home_goals, away_goals, engine.minute)
        engine.set_tournament_context(tournament.context_for_fixture(FIXTURE_ID))
        return original_step()
    engine.step = tournament_aware_step

    session = MatchSessionV13(engine)
    if not session.pristine:
        raise RuntimeError("live fixture must be pristine at construction")
    return session


def run_to_step(step: int) -> dict:
    if step < 1:
        raise ValueError("step must be >= 1; step 0 is preparation only")
    session = build_session()
    packet = None
    for _ in range(step):
        packet = session.press_p_packet()
    assert packet is not None
    state_hash = hashlib.sha256(session.export_json().encode("utf-8")).hexdigest()
    return {
        "fixture_id": FIXTURE_ID,
        "fixture": f"{HOME_KEY} x {AWAY_KEY}",
        "step": step,
        "seed": SEED,
        "seed_basis": SEED_BASIS,
        "state_sha256": state_hash,
        "state_json": json.loads(session.export_json()),
        "snapshot": session.snapshot(),
        "packet": packet,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python live_interdimensional_a5.py STEP")
    step = int(sys.argv[1])
    result = run_to_step(step)
    print("LIVE_PACKET_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("LIVE_PACKET_END")


if __name__ == "__main__":
    main()
