from __future__ import annotations

import json

from engine import MatchConfig
from engine_experiment_v13 import MatchEngine
from historical_2014_v13 import load_team_for_v13
from narration_packet_v13 import event_fact
from runner_v13 import MatchSessionV13

HOME_KEY = "brazil_2002"
AWAY_KEY = "danganlock"
SEED = 684583659

home = load_team_for_v13(HOME_KEY)
away = load_team_for_v13(AWAY_KEY)
engine = MatchEngine(
    home,
    away,
    seed=SEED,
    config=MatchConfig(
        regulation_minutes=90,
        allow_extra_time=False,
        max_substitutions=3,
        allow_extra_time_substitution=False,
        relevant_threshold=2,
        direct_red_enabled=True,
        injuries_enabled=True,
        auto_tactical_adaptation=True,
    ),
    venue_context={"mode": "neutral", "source": "locked_live_fixture"},
)

beats = 0
while not engine.state.ended:
    engine.step()
    beats += 1
    if beats > 20000:
        raise RuntimeError("safety beat limit")

session = MatchSessionV13(engine)

keep_types = {
    "danger", "shot", "goal", "save", "block", "miss", "post",
    "penalty", "card", "substitution", "injury", "period_end", "match_end",
}
highlights = []
for seq, ev in enumerate(engine.state.event_log, 1):
    typ = ev.type.value
    if typ not in keep_types:
        continue
    if typ in {"danger", "shot", "save", "block", "miss"} and int(ev.relevance) < 3:
        continue
    item = event_fact(ev, session)
    item["sequence"] = seq
    item["relevance"] = int(ev.relevance)
    highlights.append(item)

result = {
    "seed": SEED,
    "score": [engine.stats[0].goals, engine.stats[1].goals],
    "stats": session.snapshot().get("stats"),
    "awards": session.snapshot().get("awards"),
    "highlights": highlights,
}
print("HIGHLIGHTS_BEGIN")
print(json.dumps(result, ensure_ascii=False, sort_keys=True))
print("HIGHLIGHTS_END")
