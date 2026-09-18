from __future__ import annotations

"""Locked live Round 2 fixture: DanganLock x Bastard München.

The session is pristine at 0:00 and advances only when invoked with a positive
narration step. It never previews later steps and never searches seeds.
"""

import hashlib
import json
import sys

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from runner_v13 import MatchSessionV13
from run_tournament_round1_v13 import PACK_PATH, build_registered_team

HOME_KEY = "danganlock"
AWAY_KEY = "bastard_munchen"
FIXTURE_ID = "A3"
SEED_BASIS = "interdimensional-16|2026-09-18|round-2|A3|danganlock|bastard_munchen|live"
SEED = int(hashlib.sha256(SEED_BASIS.encode("utf-8")).hexdigest()[:8], 16)


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
        venue_context={"mode": "neutral", "source": "interdimensional_tournament_live"},
    )
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
        raise SystemExit("usage: python live_interdimensional_a3.py STEP")
    step = int(sys.argv[1])
    result = run_to_step(step)
    print("LIVE_PACKET_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("LIVE_PACKET_END")


if __name__ == "__main__":
    main()
