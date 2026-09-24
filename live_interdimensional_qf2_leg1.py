from __future__ import annotations

"""Live Interdimensional quarterfinal QF2 first leg: Royal Academy / Teikoku x DanganLock.

This fixture is the first leg of a two-legged tie. It starts pristine at 0:00.
No extra time or penalties are allowed in leg 1. The second leg is scheduled
with reversed home/away order. Away goals are disabled.

The session advances only when the live step counter is incremented.
"""

import hashlib
import json
import sys

from competition_state_v13 import TournamentStateV13
from engine import MatchConfig, EventType
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13
from run_tournament_round1_v13 import PACK_PATH, build_registered_team

HOME_KEY = "teikoku"
AWAY_KEY = "danganlock"
FIXTURE_ID = "QF2-L1"
TIE_ID = "QF2"
SEED_BASIS = "interdimensional-16|quarterfinals|leg-1|QF2-L1|teikoku|danganlock|live"
SEED = int(hashlib.sha256(SEED_BASIS.encode("utf-8")).hexdigest()[:8], 16)


def build_tournament() -> TournamentStateV13:
    teams = [
        "ajax_1995",
        "argentina_2022",
        "teikoku",
        "danganlock",
        "real_madrid_2017",
        "japan_u20_tsubasa",
        "france_1998",
        "man_utd_2008",
    ]
    stages = {
        "quarterfinals": {
            "kind": "knockout",
            "name": "Quartas de final",
            "two_legged": True,
            "away_goals": False,
            "allow_extra_time": True,
            "promotion_on_win": False,
            "metadata": {
                "format": "home_and_away",
                "extra_time_and_penalties": "decisive_second_leg_only",
            },
        }
    }
    fixtures = [
        {"id":"QF1-L1","stage_id":"quarterfinals","tie_id":"QF1","leg":1,
         "home":"ajax_1995","away":"argentina_2022","status":"final","score":[2,1]},
        {"id":"QF1-L2","stage_id":"quarterfinals","tie_id":"QF1","leg":2,
         "home":"argentina_2022","away":"ajax_1995","status":"scheduled","score":[0,0]},

        {"id":"QF2-L1","stage_id":"quarterfinals","tie_id":"QF2","leg":1,
         "home":"teikoku","away":"danganlock","status":"scheduled","score":[0,0]},
        {"id":"QF2-L2","stage_id":"quarterfinals","tie_id":"QF2","leg":2,
         "home":"danganlock","away":"teikoku","status":"scheduled","score":[0,0]},

        {"id":"QF3-L1","stage_id":"quarterfinals","tie_id":"QF3","leg":1,
         "home":"real_madrid_2017","away":"japan_u20_tsubasa","status":"final","score":[3,0]},
        {"id":"QF3-L2","stage_id":"quarterfinals","tie_id":"QF3","leg":2,
         "home":"japan_u20_tsubasa","away":"real_madrid_2017","status":"scheduled","score":[0,0]},

        {"id":"QF4-L1","stage_id":"quarterfinals","tie_id":"QF4","leg":1,
         "home":"france_1998","away":"man_utd_2008","status":"final","score":[3,5]},
        {"id":"QF4-L2","stage_id":"quarterfinals","tie_id":"QF4","leg":2,
         "home":"man_utd_2008","away":"france_1998","status":"scheduled","score":[0,0]},
    ]
    return TournamentStateV13(
        competition_id="interdimensional-16-20260918",
        teams=teams,
        stages=stages,
        fixtures=fixtures,
    )


def build_session() -> tuple[MatchSessionV13, TournamentStateV13]:
    pack = json.loads(PACK_PATH.read_text(encoding="utf-8"))
    home = build_registered_team(pack, HOME_KEY)
    away = build_registered_team(pack, AWAY_KEY)

    # First leg: a draw is a valid final result. Extra time / penalties belong
    # only to the decisive second leg if the aggregate is level.
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
        venue_context={
            "mode": "neutral",
            "source": "interdimensional_tournament_qf_live",
        },
    )

    tournament = build_tournament()
    tournament.update_live(FIXTURE_ID, 0, 0, 0.0)
    engine.set_tournament_context(tournament.context_for_fixture(FIXTURE_ID))

    original_step = engine.step

    def tournament_aware_step():
        if not engine.state.ended:
            hg, ag = engine.score
            tournament.update_live(FIXTURE_ID, hg, ag, engine.minute)
            engine.set_tournament_context(tournament.context_for_fixture(FIXTURE_ID))

        event = original_step()

        hg, ag = engine.score
        if engine.state.ended:
            if tournament.fixture(FIXTURE_ID)["status"] != "final":
                tournament.finalize_fixture(FIXTURE_ID, hg, ag)
        else:
            tournament.update_live(FIXTURE_ID, hg, ag, engine.minute)
        engine.set_tournament_context(tournament.context_for_fixture(FIXTURE_ID))
        return event

    engine.step = tournament_aware_step
    session = MatchSessionV13(engine)
    if not session.pristine:
        raise RuntimeError("QF2 first-leg live fixture must be pristine at construction")
    return session, tournament


def ready_state() -> dict:
    session, tournament = build_session()
    context = tournament.context_for_fixture(FIXTURE_ID)
    return {
        "status": "ready",
        "fixture_id": FIXTURE_ID,
        "tie_id": TIE_ID,
        "fixture": "Royal Academy / Teikoku x DanganLock",
        "leg": 1,
        "clock": "0:00",
        "score": [0, 0],
        "pristine": bool(session.pristine),
        "two_legged": True,
        "decisive_leg": False,
        "away_goals": False,
        "allow_extra_time_this_leg": False,
        "allow_penalties_this_leg": False,
        "second_leg": "DanganLock x Royal Academy / Teikoku",
        "venue_mode": "neutral",
        "seed": SEED,
        "seed_basis": SEED_BASIS,
        "competition_context": context,
        "snapshot": session.snapshot(),
    }


def run_to_step(step: int, count: int = 1) -> dict:
    if step < 1:
        raise ValueError("step must be >= 1; step 0 is preparation only")

    session, tournament = build_session()
    for _ in range(step - 1):
        if session.engine.state.ended:
            raise ValueError("requested step is beyond the end of this match")
        session.press_p_packet()

    packets = session.press_p_batch(count)
    if not packets:
        raise ValueError("match has already ended")

    packet = packets[-1]
    state_hash = hashlib.sha256(session.export_json().encode("utf-8")).hexdigest()
    return {
        "fixture_id": FIXTURE_ID,
        "tie_id": TIE_ID,
        "fixture": "Royal Academy / Teikoku x DanganLock",
        "leg": 1,
        "step": step + len(packets) - 1,
        "first_step": step,
        "packets": packets,
        "seed": SEED,
        "seed_basis": SEED_BASIS,
        "state_sha256": state_hash,
        "state_json": json.loads(session.export_json()),
        "snapshot": session.snapshot(),
        "competition_context": tournament.context_for_fixture(FIXTURE_ID),
        "packet": packet,
    }


def main() -> None:
    if len(sys.argv) not in (2, 3):
        raise SystemExit("usage: python live_interdimensional_qf2_leg1.py STEP [COUNT]")

    step = int(sys.argv[1])
    if step == 0:
        print("LIVE_READY_BEGIN")
        print(json.dumps(ready_state(), ensure_ascii=False, sort_keys=True))
        print("LIVE_READY_END")
        return

    result = run_to_step(step, int(sys.argv[2]) if len(sys.argv) == 3 else 1)
    print("LIVE_PACKET_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("LIVE_PACKET_END")


if __name__ == "__main__":
    main()
