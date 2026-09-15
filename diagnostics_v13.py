from __future__ import annotations

import sys
from statistics import mean

from engine import make_generic_team
from engine_experiment_v13 import MatchEngine


def run(n: int = 100) -> None:
    rows = []
    for seed in range(n):
        home = make_generic_team("Candidate A", 78, "balanced", seed=1001)
        away = make_generic_team("Candidate B", 78, "balanced", seed=2002)
        engine = MatchEngine(home, away, seed=seed)
        guard = 0
        while not engine.state.ended and guard < 5000:
            engine.step()
            guard += 1
        if guard >= 5000:
            raise RuntimeError(f"Simulation guard reached on seed {seed}")
        a, b = engine.stats
        for st in (a, b):
            if st.shots < st.on_target or st.on_target < st.goals or st.xg < 0:
                raise AssertionError(f"Statistic invariant failed on seed {seed}")
        rows.append(
            (
                a.goals + b.goals,
                a.shots + b.shots,
                a.on_target + b.on_target,
                a.xg + b.xg,
                a.big_chances + b.big_chances,
                int(a.goals == 0 and b.goals == 0),
            )
        )

    print(f"v1.3 candidate smoke: {n} matches")
    print(f"goals/match={mean(r[0] for r in rows):.3f}")
    print(f"shots/match={mean(r[1] for r in rows):.3f}")
    print(f"sot/match={mean(r[2] for r in rows):.3f}")
    print(f"xg/match={mean(r[3] for r in rows):.3f}")
    print(f"big_chances/match={mean(r[4] for r in rows):.3f}")
    print(f"zero_zero_rate={100.0 * mean(r[5] for r in rows):.1f}%")


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
