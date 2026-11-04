"""Independent equal-strength venue controls; no runtime calibration."""
import argparse
import json
from pathlib import Path
import sys
import subprocess

p = argparse.ArgumentParser()
p.add_argument("--engine-root", type=Path, required=True)
p.add_argument("--output", type=Path, required=True)
a = p.parse_args()
sys.path.insert(0, str(a.engine_root.resolve()))
from engine import make_generic_team
from engine_experiment_v13 import MatchEngine
from narration_packet_v13 import _public_clock_components

rows = []
for mode in ("neutral", "home_away"):
    for seed in range(113100, 113124):
        e = MatchEngine(make_generic_team("Control A", 80, "balanced", seed=1001),
                        make_generic_team("Control B", 80, "balanced", seed=2002),
                        seed=seed, venue_context=mode)
        for _ in range(7000):
            if e.state.ended:
                break
            e.step()
        if not e.state.ended:
            raise AssertionError(f"Guard on {mode}/{seed}")
        halftime = next(float(ev.minute) for ev in e.state.event_log
                        if ev.type.value == "period_end" and ev.data.get("marker") == 45)
        first_played = halftime-45.
        second_played = e.minute-first_played-90.
        announced = e._v13_stoppage["announced_seconds_by_marker"]
        goals = [ev for ev in e.state.event_log if ev.type.value == "goal" and not ev.data.get("shootout")]
        late_public = sum(_public_clock_components(e, ev.minute*60.)[0] >= 90.*60. for ev in goals)
        rows.append({"mode": mode, "seed": seed, "score": list(e.score),
                     "goals_90plus_public": late_public,
                     "first_added_played": first_played, "second_added_played": second_played,
                     "second_added_announced": float(announced.get("90", 0.))/60.})
        if (seed-113100+1) % 8 == 0:
            print(f"{mode}: {seed-113100+1}/24", flush=True)
result = {"engine_commit": subprocess.check_output(["git", "-C", str(a.engine_root), "rev-parse", "HEAD"], text=True).strip(),
          "seed_policy": "113100..113123 contiguous, both venue modes", "matches": rows,
          "scope": "Small controlled sensitivity experiment, not a league-level calibration target"}
a.output.write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
