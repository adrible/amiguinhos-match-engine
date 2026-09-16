from __future__ import annotations

"""Outcome-blind shot-accuracy audit for the real-match benchmark population.

The audit subclasses the canonical v1.3 engine only to observe inputs/outputs of
``_resolve_shot``.  It never changes the pending action, RNG stream or outcome.
It uses the same synthetic population, venue context and contiguous seed range
as ``real_match_benchmark_v13.py`` and keeps the official final seed quarantined.
"""

import argparse
from collections import Counter, defaultdict
import json
import random
import statistics

from engine import PendingAction, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from real_match_benchmark_v13 import (
    BENCHMARK_VENUE_MODE,
    RESERVED_OFFICIAL_FINAL_SEED,
    STRENGTHS,
    STRENGTH_WEIGHTS,
    STYLES,
    STYLE_WEIGHTS,
    _weighted_pick,
)


class ShotAuditEngine(CanonicalMatchEngine):
    def __init__(self, *args, **kwargs):
        self.shot_audit: list[dict] = []
        super().__init__(*args, **kwargs)

    def _resolve_shot(self, p: PendingAction):
        team = int(p.team)
        before = {
            "shots": int(self.stats[team].shots),
            "on_target": int(self.stats[team].on_target),
            "goals": int(self.stats[team].goals),
            "blocked": int(self.stats[team].blocked),
            "posts": int(self.stats[team].posts),
            "xg": float(self.stats[team].xg),
        }
        event = super()._resolve_shot(p)
        after = {
            "shots": int(self.stats[team].shots),
            "on_target": int(self.stats[team].on_target),
            "goals": int(self.stats[team].goals),
            "blocked": int(self.stats[team].blocked),
            "posts": int(self.stats[team].posts),
            "xg": float(self.stats[team].xg),
        }
        if after["shots"] > before["shots"]:
            data = event.data or {}
            actual_danger = float(data.get("danger", p.danger))
            actual_pressure = float(data.get("pressure", p.pressure))
            if data.get("goalkeeper_one_v_one"):
                actual_danger = float(data.get("one_v_one_base_danger", p.danger)) + float(
                    data.get("one_v_one_danger_delta", 0.0)
                )
                actual_pressure = float(data.get("one_v_one_base_pressure", p.pressure)) + float(
                    data.get("one_v_one_pressure_delta", 0.0)
                )
            self.shot_audit.append({
                "team": team,
                "band": p.zone.band.value,
                "lane": p.zone.lane.value,
                "origin": str(p.origin or "unknown"),
                "body_part": str(p.body_part or "foot"),
                "danger": max(0.0, min(1.0, actual_danger)),
                "pressure": max(0.0, min(1.0, actual_pressure)),
                "xg": max(0.0, after["xg"] - before["xg"]),
                "on_target": after["on_target"] - before["on_target"],
                "goal": after["goals"] - before["goals"],
                "blocked": after["blocked"] - before["blocked"],
                "post": after["posts"] - before["posts"],
                "event_type": str(getattr(event.type, "value", event.type)),
                "text_key": str(event.text_key),
                "goalkeeper_one_v_one": bool(data.get("goalkeeper_one_v_one")),
            })
        return event


def _xg_bucket(value: float) -> str:
    if value < 0.05:
        return "<0.05"
    if value < 0.10:
        return "0.05-0.099"
    if value < 0.20:
        return "0.10-0.199"
    if value < 0.35:
        return "0.20-0.349"
    return "0.35+"


def _pressure_bucket(value: float) -> str:
    if value < 0.30:
        return "<0.30"
    if value < 0.50:
        return "0.30-0.499"
    if value < 0.70:
        return "0.50-0.699"
    return "0.70+"


def _danger_bucket(value: float) -> str:
    if value < 0.35:
        return "<0.35"
    if value < 0.55:
        return "0.35-0.549"
    if value < 0.75:
        return "0.55-0.749"
    return "0.75+"


def _group_summary(records: list[dict], key_fn) -> dict:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for row in records:
        grouped[str(key_fn(row))].append(row)
    out = {}
    for key in sorted(grouped):
        rows = grouped[key]
        attempts = len(rows)
        out[key] = {
            "attempts": attempts,
            "share": attempts / len(records) if records else 0.0,
            "on_target_rate": sum(int(row["on_target"]) for row in rows) / attempts,
            "goal_rate": sum(int(row["goal"]) for row in rows) / attempts,
            "block_rate": sum(int(row["blocked"]) for row in rows) / attempts,
            "post_rate": sum(int(row["post"]) for row in rows) / attempts,
            "mean_xg": statistics.mean(float(row["xg"]) for row in rows),
            "mean_pressure": statistics.mean(float(row["pressure"]) for row in rows),
            "mean_danger": statistics.mean(float(row["danger"]) for row in rows),
        }
    return out


def run(count: int = 300, start_seed: int = 91000) -> dict:
    if count <= 0:
        raise ValueError("count must be positive")
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    if RESERVED_OFFICIAL_FINAL_SEED in seeds:
        raise ValueError("Reserved official final seed cannot be used by shot diagnostics")

    records: list[dict] = []
    totals: Counter[str] = Counter()
    styles: Counter[str] = Counter()

    for seed in seeds:
        population_rng = random.Random(f"v13-real-population:{seed}")
        home_strength = int(_weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS))
        away_strength = int(_weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS))
        home_style = str(_weighted_pick(population_rng, STYLES, STYLE_WEIGHTS))
        away_style = str(_weighted_pick(population_rng, STYLES, STYLE_WEIGHTS))
        styles.update([home_style, away_style])
        home = make_generic_team(
            f"Benchmark Home {seed}", home_strength, home_style,
            seed=900000 + seed * 2,
        )
        away = make_generic_team(
            f"Benchmark Away {seed}", away_strength, away_style,
            seed=900001 + seed * 2,
        )
        engine = ShotAuditEngine(
            home,
            away,
            seed=seed,
            venue_context={
                "mode": BENCHMARK_VENUE_MODE,
                "source": "shot_accuracy_diagnostic",
            },
        )
        guard = 0
        while not engine.state.ended and guard < 7000:
            engine.step()
            guard += 1
        if guard >= 7000:
            raise RuntimeError(f"Simulation guard reached on seed {seed}")

        totals["shots"] += sum(int(stats.shots) for stats in engine.stats)
        totals["on_target"] += sum(int(stats.on_target) for stats in engine.stats)
        totals["goals"] += sum(int(stats.goals) for stats in engine.stats)
        totals["blocked"] += sum(int(stats.blocked) for stats in engine.stats)
        totals["posts"] += sum(int(stats.posts) for stats in engine.stats)
        records.extend(engine.shot_audit)

    attempts = len(records)
    audited_on_target = sum(int(row["on_target"]) for row in records)
    audited_goals = sum(int(row["goal"]) for row in records)
    audited_blocked = sum(int(row["blocked"]) for row in records)
    audited_posts = sum(int(row["post"]) for row in records)
    audited_xg = sum(float(row["xg"]) for row in records)
    matches = float(count)

    report = {
        "count": count,
        "start_seed": start_seed,
        "seed_range": [start_seed, start_seed + count - 1],
        "seed_policy": "same_contiguous_unfiltered_range_as_real_match_benchmark",
        "official_seed_quarantined": RESERVED_OFFICIAL_FINAL_SEED,
        "venue_mode": BENCHMARK_VENUE_MODE,
        "styles": dict(sorted(styles.items())),
        "match_totals": {
            "shots_per_match": totals["shots"] / matches,
            "sot_per_match": totals["on_target"] / matches,
            "goals_per_match": totals["goals"] / matches,
            "sot_per_shot": totals["on_target"] / totals["shots"] if totals["shots"] else 0.0,
            "goals_per_sot": totals["goals"] / totals["on_target"] if totals["on_target"] else 0.0,
        },
        "audited_resolve_shot": {
            "attempts": attempts,
            "attempts_per_match": attempts / matches,
            "on_target_rate": audited_on_target / attempts if attempts else 0.0,
            "goal_rate": audited_goals / attempts if attempts else 0.0,
            "block_rate": audited_blocked / attempts if attempts else 0.0,
            "post_rate": audited_posts / attempts if attempts else 0.0,
            "mean_xg": audited_xg / attempts if attempts else 0.0,
            "unobserved_shots_per_match": (totals["shots"] - attempts) / matches,
            "unobserved_sot_per_match": (totals["on_target"] - audited_on_target) / matches,
        },
        "by_band": _group_summary(records, lambda row: row["band"]),
        "by_origin": _group_summary(records, lambda row: row["origin"]),
        "by_body_part": _group_summary(records, lambda row: row["body_part"]),
        "by_xg": _group_summary(records, lambda row: _xg_bucket(float(row["xg"]))),
        "by_pressure": _group_summary(records, lambda row: _pressure_bucket(float(row["pressure"]))),
        "by_danger": _group_summary(records, lambda row: _danger_bucket(float(row["danger"]))),
        "one_v_one": _group_summary(
            records,
            lambda row: "gk_1v1" if row["goalkeeper_one_v_one"] else "ordinary",
        ),
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("count", nargs="?", type=int, default=300)
    parser.add_argument("--start-seed", type=int, default=91000)
    args = parser.parse_args()
    print(json.dumps(run(args.count, args.start_seed), ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
