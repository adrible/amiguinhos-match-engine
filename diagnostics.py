from collections import Counter
from statistics import mean
import sys

from engine import make_generic_team, simulate_full_match


def bucket_xg(x):
    if x < 0.05:
        return "<0.05"
    if x < 0.15:
        return "0.05-0.14"
    if x < 0.30:
        return "0.15-0.29"
    return ">=0.30"


def run(n=1000):
    rows = []
    scorelines = Counter()
    quality = Counter()

    for i in range(n):
        home = make_generic_team("Home", 75, "balanced", seed=10_000 + i)
        away = make_generic_team("Away", 75, "balanced", seed=20_000 + i)
        e = simulate_full_match(home, away, seed=30_000 + i)

        scorelines[e.score] += 1
        shots = sum(s.shots for s in e.stats)
        on_target = sum(s.on_target for s in e.stats)
        xg = sum(s.xg for s in e.stats)
        big = sum(s.big_chances for s in e.stats)
        fouls = sum(s.fouls for s in e.stats)
        cards = sum(s.yellow + s.red for s in e.stats)

        for ev in e.state.event_log:
            if "xg" in ev.data and ev.type.value in {
                "goal", "save", "miss", "block", "post"
            }:
                quality[bucket_xg(float(ev.data["xg"]))] += 1

        rows.append(
            (sum(e.score), shots, on_target, xg, big, fouls, cards, e.match_flow)
        )

    print(f"Matches: {n}")
    print(f"Goals/match:       {mean(r[0] for r in rows):.3f}")
    print(f"Shots/match:       {mean(r[1] for r in rows):.3f}")
    print(f"On target/match:   {mean(r[2] for r in rows):.3f}")
    print(f"xG/match:          {mean(r[3] for r in rows):.3f}")
    print(f"Big chances/match: {mean(r[4] for r in rows):.3f}")
    print(f"Fouls/match:       {mean(r[5] for r in rows):.3f}")
    print(f"Cards/match:       {mean(r[6] for r in rows):.3f}")
    print(f"0-0 rate:          {scorelines[(0, 0)] / n:.3%}")

    print("\nChance-quality buckets:")
    total = sum(quality.values()) or 1
    for key in ("<0.05", "0.05-0.14", "0.15-0.29", ">=0.30"):
        print(f"  {key:10s}: {quality[key]:6d} ({quality[key] / total:6.2%})")

    print("\nMost common scorelines:")
    for (h, a), count in scorelines.most_common(12):
        print(f"  {h}-{a}: {count:5d} ({count / n:6.2%})")


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    run(n)
