from __future__ import annotations

from collections import Counter, defaultdict
from statistics import mean
import json
import sys

from engine import EventType, make_generic_team, simulate_full_match
from team_loader import load_team


SHOT_TYPES = {
    EventType.GOAL,
    EventType.SAVE,
    EventType.MISS,
    EventType.BLOCK,
    EventType.POST,
}
STYLES = ["balanced", "attacking", "defensive", "pressing", "direct"]
TIERS = [75, 80, 83, 84]


def bucket_xg(x: float) -> str:
    if x < 0.05:
        return "<0.05"
    if x < 0.15:
        return "0.05-0.14"
    if x < 0.30:
        return "0.15-0.29"
    return ">=0.30"


def player_from_shot_event(ev):
    for key in ("shooter", "scorer", "taker"):
        if ev.data.get(key):
            return ev.data[key]
    return None


def danger_participants(ev):
    names = []
    for key in ("creator", "receiver", "actor", "target", "runner", "next_player"):
        value = ev.data.get(key)
        if isinstance(value, str) and value:
            names.append(value)
    return names


def fresh_amiguinhos():
    return load_team("amiguinhos_u21")


def run(n_per_tier: int = 1000):
    tier_rows = {}
    quality = Counter()
    origins = Counter()
    shot_count = Counter()
    player_xg = defaultdict(float)
    player_goals = Counter()
    danger_involvement = Counter()
    danger_creation = Counter()
    total_matches = 0

    for strength in TIERS:
        wins = draws = losses = 0
        gf = ga = 0
        tier_metrics = []

        for i in range(n_per_tier):
            style = STYLES[i % len(STYLES)]
            am = fresh_amiguinhos()
            opp = make_generic_team(
                f"Generic {strength} {style}",
                strength=strength,
                style=style,
                seed=100_000 + strength * 10_000 + i,
            )

            # Alternate sides so any accidental home/away asymmetry is averaged out.
            if i % 2 == 0:
                engine = simulate_full_match(am, opp, seed=500_000 + strength * 10_000 + i)
                aidx, oidx = 0, 1
            else:
                engine = simulate_full_match(opp, am, seed=500_000 + strength * 10_000 + i)
                aidx, oidx = 1, 0

            a_goals = engine.stats[aidx].goals
            o_goals = engine.stats[oidx].goals
            gf += a_goals
            ga += o_goals
            if a_goals > o_goals:
                wins += 1
            elif a_goals == o_goals:
                draws += 1
            else:
                losses += 1

            total_poss = (
                engine.stats[aidx].possession_seconds
                + engine.stats[oidx].possession_seconds
            ) or 1.0
            tier_metrics.append({
                "xgf": engine.stats[aidx].xg,
                "xga": engine.stats[oidx].xg,
                "shots_for": engine.stats[aidx].shots,
                "shots_against": engine.stats[oidx].shots,
                "sot_for": engine.stats[aidx].on_target,
                "sot_against": engine.stats[oidx].on_target,
                "big_for": engine.stats[aidx].big_chances,
                "big_against": engine.stats[oidx].big_chances,
                "corners_for": engine.stats[aidx].corners,
                "corners_against": engine.stats[oidx].corners,
                "fouls_for": engine.stats[aidx].fouls,
                "fouls_against": engine.stats[oidx].fouls,
                "cards_for": engine.stats[aidx].yellow + engine.stats[aidx].red,
                "cards_against": engine.stats[oidx].yellow + engine.stats[oidx].red,
                "possession": 100.0 * engine.stats[aidx].possession_seconds / total_poss,
            })

            for ev in engine.state.event_log:
                if ev.team != aidx:
                    continue

                if ev.type in SHOT_TYPES and "xg" in ev.data:
                    xg = float(ev.data["xg"])
                    quality[bucket_xg(xg)] += 1
                    origin = str(ev.data.get("origin") or (
                        "penalty" if "penalty" in ev.text_key else "unknown"
                    ))
                    origins[origin] += 1
                    player = player_from_shot_event(ev)
                    if player:
                        shot_count[player] += 1
                        player_xg[player] += xg
                        if ev.type == EventType.GOAL:
                            player_goals[player] += 1

                if ev.type == EventType.DANGER:
                    participants = danger_participants(ev)
                    for player in set(participants):
                        danger_involvement[player] += 1
                    creator = ev.data.get("creator") or ev.data.get("actor")
                    if isinstance(creator, str):
                        danger_creation[creator] += 1

            total_matches += 1

        def avg(key):
            return mean(r[key] for r in tier_metrics)

        tier_rows[strength] = {
            "matches": n_per_tier,
            "W": wins,
            "D": draws,
            "L": losses,
            "win_pct": 100.0 * wins / n_per_tier,
            "draw_pct": 100.0 * draws / n_per_tier,
            "loss_pct": 100.0 * losses / n_per_tier,
            "gf_pg": gf / n_per_tier,
            "ga_pg": ga / n_per_tier,
            "gd_pg": (gf - ga) / n_per_tier,
            "xgf_pg": avg("xgf"),
            "xga_pg": avg("xga"),
            "shots_for_pg": avg("shots_for"),
            "shots_against_pg": avg("shots_against"),
            "sot_for_pg": avg("sot_for"),
            "sot_against_pg": avg("sot_against"),
            "big_for_pg": avg("big_for"),
            "big_against_pg": avg("big_against"),
            "corners_for_pg": avg("corners_for"),
            "corners_against_pg": avg("corners_against"),
            "fouls_for_pg": avg("fouls_for"),
            "fouls_against_pg": avg("fouls_against"),
            "cards_for_pg": avg("cards_for"),
            "cards_against_pg": avg("cards_against"),
            "possession_pct": avg("possession"),
        }

    players = sorted(
        set(shot_count) | set(danger_involvement) | set(danger_creation),
        key=lambda p: (-player_xg[p], -shot_count[p], p),
    )
    player_rows = {
        p: {
            "shots_pg": shot_count[p] / total_matches,
            "xg_pg": player_xg[p] / total_matches,
            "goals_pg": player_goals[p] / total_matches,
            "goals_per_xg": (player_goals[p] / player_xg[p]) if player_xg[p] > 0 else None,
            "danger_involvement_pg": danger_involvement[p] / total_matches,
            "danger_creation_pg": danger_creation[p] / total_matches,
        }
        for p in players
    }

    result = {
        "n_per_tier": n_per_tier,
        "total_matches": total_matches,
        "tiers": tier_rows,
        "chance_quality_counts": dict(quality),
        "shot_origin_counts": dict(origins),
        "players": player_rows,
    }

    print("=== AMIGUINHOS U21 CALIBRATION ===")
    print(f"Matches per tier: {n_per_tier} | Total: {total_matches}")
    for strength in TIERS:
        r = tier_rows[strength]
        print(
            f"OVR {strength}: W/D/L {r['win_pct']:.1f}/{r['draw_pct']:.1f}/{r['loss_pct']:.1f}% | "
            f"GF-GA {r['gf_pg']:.2f}-{r['ga_pg']:.2f} | "
            f"xG {r['xgf_pg']:.2f}-{r['xga_pg']:.2f} | "
            f"Shots {r['shots_for_pg']:.2f}-{r['shots_against_pg']:.2f} | "
            f"Big {r['big_for_pg']:.2f}-{r['big_against_pg']:.2f} | "
            f"Poss {r['possession_pct']:.1f}%"
        )

    print("\nChance quality:")
    qtotal = sum(quality.values()) or 1
    for key in ("<0.05", "0.05-0.14", "0.15-0.29", ">=0.30"):
        print(f"  {key:10s}: {quality[key]:6d} ({100.0 * quality[key] / qtotal:5.1f}%)")

    print("\nShot origins:")
    for origin, count in origins.most_common():
        print(f"  {origin:16s}: {count:6d} ({100.0 * count / qtotal:5.1f}%)")

    print("\nPlayer attacking profile (per match, all tiers):")
    for p in players:
        r = player_rows[p]
        print(
            f"  {p:20s} shots {r['shots_pg']:.3f} | xG {r['xg_pg']:.3f} | "
            f"goals {r['goals_pg']:.3f} | danger inv {r['danger_involvement_pg']:.3f} | "
            f"created {r['danger_creation_pg']:.3f}"
        )

    print("\nCALIBRATION_JSON=" + json.dumps(result, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    run(n)
