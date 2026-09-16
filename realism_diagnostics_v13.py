from __future__ import annotations

import argparse
from collections import Counter
from statistics import mean, median

from engine import EventType, make_generic_team
from engine_experiment_v13 import MatchEngine


RESERVED_OFFICIAL_FINAL_SEED = 1810131239


def percentile(values: list[float], q: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(float(v) for v in values)
    pos = (len(ordered) - 1) * q
    low = int(pos)
    high = min(len(ordered) - 1, low + 1)
    frac = pos - low
    return ordered[low] * (1.0 - frac) + ordered[high] * frac


def run(count: int = 500, start_seed: int = 70000) -> None:
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    if RESERVED_OFFICIAL_FINAL_SEED in seeds:
        raise ValueError("Reserved official final seed cannot be used by diagnostics")

    final_minutes: list[float] = []
    first_half_added: list[float] = []
    second_half_added: list[float] = []
    goals_per_match: list[int] = []
    late_goals = 0
    very_late_goals = 0
    stoppage_goals = 0
    time_waste_attempts = 0
    time_waste_cards = 0
    tactical_foul_attempts = 0
    tactical_fouls = 0
    tactical_foul_cards = 0
    load_injuries = 0
    load_forced_off = 0
    one_v_ones = 0
    one_v_one_goals = 0
    live_penalties = 0
    live_penalty_goals = 0
    second_balls = 0
    second_ball_attack_wins = 0
    red_matches = 0
    red_cards = 0
    goal_minutes: list[float] = []
    scorelines: Counter[str] = Counter()
    time_waste_by_restart: Counter[str] = Counter()
    one_v_one_choices: Counter[str] = Counter()
    keeper_one_v_one_choices: Counter[str] = Counter()
    penalty_styles: Counter[str] = Counter()
    penalty_targets: Counter[str] = Counter()

    for seed in seeds:
        home = make_generic_team("Realism A", 78, "balanced", seed=71001)
        away = make_generic_team("Realism B", 78, "balanced", seed=72002)
        engine = MatchEngine(home, away, seed=seed)
        guard = 0
        while not engine.state.ended and guard < 7000:
            engine.step()
            guard += 1
        if guard >= 7000:
            raise RuntimeError(f"Simulation guard reached on seed {seed}")

        final_minutes.append(float(engine.minute))
        h, a = engine.score
        goals_per_match.append(h + a)
        scorelines[f"{h}-{a}"] += 1

        stop = getattr(engine, "_v13_stoppage", {}) or {}
        announced = stop.get("announced_seconds_by_marker", {}) or {}
        first_half_added.append(float(announced.get("45", 0.0)) / 60.0)
        second_half_added.append(float(announced.get("90", 0.0)) / 60.0)

        clock = getattr(engine, "_v13_clock_behaviour", {}) or {}
        time_waste_attempts += sum(int(v) for v in clock.get("waste_attempts", [0, 0]))
        time_waste_cards += sum(int(v) for v in clock.get("waste_cards", [0, 0]))

        tactical = getattr(engine, "_v13_tactical_fouls", {}) or {}
        tactical_foul_attempts += sum(int(v) for v in tactical.get("attempts", [0, 0]))
        tactical_fouls += sum(int(v) for v in tactical.get("committed", [0, 0]))
        tactical_foul_cards += sum(int(v) for v in tactical.get("cards", [0, 0]))

        match_reds = engine.stats[0].red + engine.stats[1].red
        red_cards += match_reds
        red_matches += int(match_reds > 0)

        for event in engine.state.event_log:
            data = event.data or {}
            if event.type == EventType.GOAL and not data.get("shootout"):
                minute = float(event.minute)
                goal_minutes.append(minute)
                late_goals += int(minute >= 70.0)
                very_late_goals += int(minute >= 85.0)
                stoppage_goals += int(minute >= 90.0)
            if event.text_key == "deliberate_time_wasting":
                time_waste_by_restart[str(data.get("restart", "unknown"))] += 1
            if event.text_key == "muscular_load_injury":
                load_injuries += 1
                load_forced_off += int(not bool(data.get("can_continue", True)))
            if data.get("goalkeeper_one_v_one"):
                one_v_ones += 1
                one_v_one_goals += int(event.type == EventType.GOAL)
                one_v_one_choices[str(data.get("attacker_1v1_choice", "unknown"))] += 1
                keeper_one_v_one_choices[str(data.get("keeper_1v1_choice", "unknown"))] += 1
            if event.text_key in {"penalty_goal", "penalty_saved", "penalty_missed"} and not data.get("shootout"):
                live_penalties += 1
                live_penalty_goals += int(event.type == EventType.GOAL)
                penalty_styles[str(data.get("penalty_style", "unknown"))] += 1
                penalty_targets[str(data.get("penalty_target", "unknown"))] += 1
            if data.get("second_ball_live"):
                second_balls += 1
                second_ball_attack_wins += int(event.text_key in {"second_ball_attack_continues", "second_ball_attack_recovers"})

    matches = float(count)
    goals = sum(goals_per_match)
    print(f"v1.3 realism heavy audit: {count} matches, seeds {start_seed}..{start_seed + count - 1}")
    print(f"goals/match={mean(goals_per_match):.3f}")
    print(f"final_minute mean={mean(final_minutes):.2f} median={median(final_minutes):.2f} p95={percentile(final_minutes, 0.95):.2f}")
    print(f"1H_added_minutes mean={mean(first_half_added):.3f} median={median(first_half_added):.2f} p95={percentile(first_half_added, 0.95):.2f}")
    print(f"2H_added_minutes mean={mean(second_half_added):.3f} median={median(second_half_added):.2f} p95={percentile(second_half_added, 0.95):.2f}")
    print(f"late_goals_70plus={late_goals} share_of_goals={(late_goals / goals if goals else 0.0):.3f}")
    print(f"very_late_goals_85plus={very_late_goals} share_of_goals={(very_late_goals / goals if goals else 0.0):.3f}")
    print(f"stoppage_goals_90plus={stoppage_goals} share_of_goals={(stoppage_goals / goals if goals else 0.0):.3f}")
    print(f"time_waste_attempts/match={time_waste_attempts / matches:.3f} cards={time_waste_cards} by_restart={dict(time_waste_by_restart)}")
    print(f"tactical_foul_candidates/match={tactical_foul_attempts / matches:.3f} committed/match={tactical_fouls / matches:.3f} cards={tactical_foul_cards}")
    print(f"load_injuries/match={load_injuries / matches:.4f} forced_off={load_forced_off}")
    print(f"gk_one_v_ones/match={one_v_ones / matches:.3f} goal_rate={(one_v_one_goals / one_v_ones if one_v_ones else 0.0):.3f}")
    print(f"gk_one_v_one_attacker_choices={dict(one_v_one_choices)}")
    print(f"gk_one_v_one_keeper_choices={dict(keeper_one_v_one_choices)}")
    print(f"live_penalties/match={live_penalties / matches:.4f} conversion={(live_penalty_goals / live_penalties if live_penalties else 0.0):.3f}")
    print(f"penalty_styles={dict(penalty_styles)} targets={dict(penalty_targets)}")
    print(f"general_second_balls/match={second_balls / matches:.3f} attacking_recovery_rate={(second_ball_attack_wins / second_balls if second_balls else 0.0):.3f}")
    print(f"red_cards/match={red_cards / matches:.3f} red_match_rate={red_matches / matches:.3f}")
    print(f"top_scorelines={scorelines.most_common(12)}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=500)
    parser.add_argument("--start-seed", type=int, default=70000)
    args = parser.parse_args()
    run(args.count, args.start_seed)
