from __future__ import annotations

"""Locked live fixture: Brasil 2002 x DanganLock.

This module prepares a deterministic 0:00 v1.3 session and advances only when
explicitly invoked with a positive narration step. It never previews a future
step and never searches seeds.
"""

import hashlib
import json
import sys

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from historical_2014_v13 import load_team_for_v13
from runner_v13 import MatchSessionV13


HOME_KEY = "brazil_2002"
AWAY_KEY = "danganlock"
SEED_BASIS = "brazil_2002|danganlock|amiguinhos-match-engine-v1.3|live"
SEED = int(hashlib.sha256(SEED_BASIS.encode("utf-8")).hexdigest()[:8], 16)


def build_session() -> MatchSessionV13:
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
    engine = MatchEngine(
        home,
        away,
        seed=SEED,
        config=config,
        venue_context={"mode": "neutral", "source": "locked_live_fixture"},
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
        "fixture": f"{HOME_KEY} x {AWAY_KEY}",
        "step": step,
        "seed": SEED,
        "seed_basis": SEED_BASIS,
        "state_sha256": state_hash,
        "snapshot": session.snapshot(),
        "packet": packet,
    }


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("usage: python live_brazil2002_danganlock.py STEP")
    step = int(sys.argv[1])
    result = run_to_step(step)
    print("LIVE_PACKET_BEGIN")
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    print("LIVE_PACKET_END")


if __name__ == "__main__":
    main()
