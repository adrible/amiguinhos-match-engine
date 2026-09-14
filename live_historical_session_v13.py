from __future__ import annotations

import json
from pathlib import Path

from runner_v13 import MatchSessionV13, event_view

STATE_PATH = Path("live_sessions/brazil_germany_2014_state.json")

if STATE_PATH.exists():
    session = MatchSessionV13.from_json(STATE_PATH.read_text(encoding="utf-8"))
else:
    session = MatchSessionV13.from_fixture(
        "brazil_2014",
        "germany_2014",
        seed=20140708,
        auto_adapt=True,
        allow_extra_time=True,
    )

event = session.press_p()
STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
STATE_PATH.write_text(session.export_json(), encoding="utf-8")
print("LIVE_EVENT_JSON=" + json.dumps(event_view(event, session), ensure_ascii=False, sort_keys=True))
