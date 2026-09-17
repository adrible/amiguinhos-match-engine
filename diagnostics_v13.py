from __future__ import annotations

import sys
from statistics import mean

from engine import make_generic_team
from engine_experiment_v13 import MatchEngine


XG_BINS = (
    ("0.00-0.05", 0.00, 0.05),
    ("0.05-0.10", 0.05, 0.10),
    ("0.10-0.20", 0.10, 0.20),
    ("0.20-0.40", 0.20, 0.40),
    ("0.40+", 0.40, 1.01),
)


def _collect_shots(engine: MatchEngine) -> list[tuple[float, int]]:
    """Read canonical shot attempts from engine state, never from public events."""
    coverage = engine.shot_ledger_coverage()
    if not coverage["complete"]:
        raise AssertionError(
            "shot-ledger coverage failed: "
            f"ledger={coverage['ledger_by_team']} expected={coverage['expected_by_team']}"
        )
    return [
        (float(row["xg"]), int(bool(row["goal"])))
        for row in engine.shot_ledger_diagnostic()
    ]


def _bin_for_xg(xg: float) -> str:
    for label, low, high in XG_BINS:
        if low <= xg < high:
            return label
    return XG_BINS[-1][0]


def _print_xg_calibration(shots: list[tuple[float, int]], stats_xg: float) -> None:
    print("xg->goal calibration (diagnostic only; no target forcing)")
    ledger_xg = sum(xg for xg, _ in shots)
    goals = sum(goal for _, goal in shots)
    print(
        "overall: "
        f"shots={len(shots)} "
        f"sum_xg={ledger_xg:.3f} "
        f"goals={goals} "
        f"goals_minus_xg={goals - ledger_xg:+.3f} "
        f"goal_to_xg={(goals / ledger_xg if ledger_xg else 0.0):.3f} "
        f"ledger_vs_stats_xg={ledger_xg - stats_xg:+.9f}"
    )
    for label, _, _ in XG_BINS:
        rows = [(xg, goal) for xg, goal in shots if _bin_for_xg(xg) == label]
        if not rows:
            print(f"{label}: shots=0")
            continue
        count = len(rows)
        sum_xg = sum(xg for xg, _ in rows)
        bin_goals = sum(goal for _, goal in rows)
        expected_rate = sum_xg / count
        actual_rate = bin_goals / count
        print(
            f"{label}: "
            f"shots={count} "
            f"avg_xg={expected_rate:.4f} "
            f"goal_rate={actual_rate:.4f} "
            f"goals={bin_goals} "
            f"sum_xg={sum_xg:.3f} "
            f"delta_rate={actual_rate - expected_rate:+.4f} "
            f"goal_to_xg={(bin_goals / sum_xg if sum_xg else 0.0):.3f}"
        )


def run(n: int = 100) -> None:
    rows = []
    all_shots: list[tuple[float, int]] = []
    stats_xg_total = 0.0
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

        match_shots = _collect_shots(engine)
        if len(match_shots) != a.shots + b.shots:
            raise AssertionError(
                f"shot-ledger coverage failed on seed {seed}: "
                f"{len(match_shots)} ledger rows for {a.shots + b.shots} shots"
            )
        ledger_xg = sum(xg for xg, _ in match_shots)
        stats_xg = float(a.xg + b.xg)
        if abs(ledger_xg - stats_xg) > 1e-8:
            raise AssertionError(
                f"shot-ledger xg mismatch on seed {seed}: "
                f"ledger={ledger_xg:.12f} stats={stats_xg:.12f}"
            )

        all_shots.extend(match_shots)
        stats_xg_total += stats_xg
        rows.append(
            (
                a.goals + b.goals,
                a.shots + b.shots,
                a.on_target + b.on_target,
                stats_xg,
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
    _print_xg_calibration(all_shots, stats_xg_total)


if __name__ == "__main__":
    run(int(sys.argv[1]) if len(sys.argv) > 1 else 100)
