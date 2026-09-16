from __future__ import annotations

"""Compare the v1.3 candidate with a large collection of real matches.

The benchmark deliberately lives outside the match engine. It is a diagnostic
harness, not a calibration target: no number produced here is read by the engine
while a match is being simulated.

Core real-match data are downloaded from the public datasets/football-datasets
GitHub mirror of Football-Data.co.uk. Only directly comparable match-level
fields are used in the core index (score, shots, shots on target, fouls,
corners and cards). Provider-specific concepts such as xG, tactical-foul
intent, second balls and goalkeeper 1v1 labels are intentionally excluded.

Because the source collection consists of league matches with designated home
and away teams, the synthetic comparison population uses the explicit v1.3
``home_away`` venue context. Neutral and shared-stadium fixtures remain separate
engine modes and are not mixed into this league benchmark.
"""

import argparse
import csv
import io
import json
import math
import random
import statistics
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Iterable

from engine import make_generic_team
from engine_experiment_v13 import MatchEngine


RESERVED_OFFICIAL_FINAL_SEED = 1810131239
SOURCE_FILE = Path(__file__).with_name("data") / "real_match_benchmark_sources.json"
BENCHMARK_VENUE_MODE = "home_away"

CORE_METRICS = (
    "goals_per_match",
    "shots_per_match",
    "sot_per_match",
    "fouls_per_match",
    "corners_per_match",
    "yellow_per_match",
    "red_per_match",
    "home_goals_per_match",
    "away_goals_per_match",
    "home_win_rate",
    "draw_rate",
    "away_win_rate",
    "zero_zero_rate",
    "btts_rate",
    "over_2_5_rate",
    "clean_sheet_rate",
)

# Floors stop an unusually stable three-season sample from making a tiny
# difference look infinitely important. They are diagnostic tolerances, not
# desired engine targets.
SCALE_FLOORS = {
    "goals_per_match": 0.16,
    "shots_per_match": 1.40,
    "sot_per_match": 0.70,
    "fouls_per_match": 2.20,
    "corners_per_match": 0.75,
    "yellow_per_match": 0.70,
    "red_per_match": 0.045,
    "home_goals_per_match": 0.12,
    "away_goals_per_match": 0.12,
    "home_win_rate": 0.035,
    "draw_rate": 0.030,
    "away_win_rate": 0.035,
    "zero_zero_rate": 0.020,
    "btts_rate": 0.035,
    "over_2_5_rate": 0.045,
    "clean_sheet_rate": 0.045,
}

METRIC_WEIGHTS = {
    "goals_per_match": 1.40,
    "shots_per_match": 1.10,
    "sot_per_match": 1.10,
    "fouls_per_match": 0.75,
    "corners_per_match": 0.75,
    "yellow_per_match": 0.75,
    "red_per_match": 0.65,
    "home_goals_per_match": 0.70,
    "away_goals_per_match": 0.70,
    "home_win_rate": 0.65,
    "draw_rate": 0.65,
    "away_win_rate": 0.65,
    "zero_zero_rate": 0.80,
    "btts_rate": 0.80,
    "over_2_5_rate": 0.80,
    "clean_sheet_rate": 0.70,
}

STYLES = ("balanced", "attacking", "defensive", "pressing", "direct")
STYLE_WEIGHTS = (0.34, 0.18, 0.16, 0.16, 0.16)
STRENGTHS = (72, 74, 76, 78, 80, 82, 84, 86)
STRENGTH_WEIGHTS = (0.05, 0.10, 0.16, 0.22, 0.19, 0.14, 0.09, 0.05)


def _weighted_pick(rng: random.Random, values: tuple, weights: tuple[float, ...]):
    needle = rng.random() * sum(weights)
    running = 0.0
    for value, weight in zip(values, weights):
        running += weight
        if needle <= running:
            return value
    return values[-1]


def _as_int(row: dict[str, str], key: str) -> int:
    value = str(row.get(key, "")).strip()
    if value == "":
        raise ValueError(f"missing {key}")
    return int(float(value))


def _normalise_real_row(row: dict[str, str]) -> dict[str, int]:
    return {
        "home_goals": _as_int(row, "FTHG"),
        "away_goals": _as_int(row, "FTAG"),
        "home_shots": _as_int(row, "HS"),
        "away_shots": _as_int(row, "AS"),
        "home_sot": _as_int(row, "HST"),
        "away_sot": _as_int(row, "AST"),
        "home_fouls": _as_int(row, "HF"),
        "away_fouls": _as_int(row, "AF"),
        "home_corners": _as_int(row, "HC"),
        "away_corners": _as_int(row, "AC"),
        "home_yellow": _as_int(row, "HY"),
        "away_yellow": _as_int(row, "AY"),
        "home_red": _as_int(row, "HR"),
        "away_red": _as_int(row, "AR"),
    }


def _scoreline_bucket(home: int, away: int) -> str:
    def label(value: int) -> str:
        return "4+" if int(value) >= 4 else str(int(value))

    return f"{label(home)}-{label(away)}"


def _total_goal_bucket(total: int) -> str:
    return "6+" if int(total) >= 6 else str(int(total))


def _probabilities(counter: Counter[str], keys: Iterable[str] | None = None) -> dict[str, float]:
    if keys is None:
        keys = sorted(counter)
    keys = list(keys)
    total = float(sum(counter.get(key, 0) for key in keys))
    if total <= 0.0:
        return {key: 0.0 for key in keys}
    return {key: counter.get(key, 0) / total for key in keys}


def summarise_matches(rows: list[dict[str, int]]) -> dict:
    if not rows:
        raise ValueError("Cannot summarize an empty match collection")

    matches = len(rows)
    totals = Counter()
    scorelines: Counter[str] = Counter()
    total_goals_dist: Counter[str] = Counter()
    result_dist: Counter[str] = Counter()

    for row in rows:
        hg, ag = row["home_goals"], row["away_goals"]
        total = hg + ag
        totals["goals"] += total
        totals["home_goals"] += hg
        totals["away_goals"] += ag
        totals["shots"] += row["home_shots"] + row["away_shots"]
        totals["sot"] += row["home_sot"] + row["away_sot"]
        totals["fouls"] += row["home_fouls"] + row["away_fouls"]
        totals["corners"] += row["home_corners"] + row["away_corners"]
        totals["yellow"] += row["home_yellow"] + row["away_yellow"]
        totals["red"] += row["home_red"] + row["away_red"]
        totals["zero_zero"] += int(hg == 0 and ag == 0)
        totals["btts"] += int(hg > 0 and ag > 0)
        totals["over_2_5"] += int(total >= 3)
        totals["clean_sheet"] += int(hg == 0 or ag == 0)
        if hg > ag:
            result = "H"
        elif hg < ag:
            result = "A"
        else:
            result = "D"
        totals[f"result_{result}"] += 1
        result_dist[result] += 1
        scorelines[_scoreline_bucket(hg, ag)] += 1
        total_goals_dist[_total_goal_bucket(total)] += 1

    denominator = float(matches)
    metrics = {
        "matches": matches,
        "goals_per_match": totals["goals"] / denominator,
        "shots_per_match": totals["shots"] / denominator,
        "sot_per_match": totals["sot"] / denominator,
        "fouls_per_match": totals["fouls"] / denominator,
        "corners_per_match": totals["corners"] / denominator,
        "yellow_per_match": totals["yellow"] / denominator,
        "red_per_match": totals["red"] / denominator,
        "home_goals_per_match": totals["home_goals"] / denominator,
        "away_goals_per_match": totals["away_goals"] / denominator,
        "home_win_rate": totals["result_H"] / denominator,
        "draw_rate": totals["result_D"] / denominator,
        "away_win_rate": totals["result_A"] / denominator,
        "zero_zero_rate": totals["zero_zero"] / denominator,
        "btts_rate": totals["btts"] / denominator,
        "over_2_5_rate": totals["over_2_5"] / denominator,
        "clean_sheet_rate": totals["clean_sheet"] / denominator,
    }
    return {
        "metrics": metrics,
        "scoreline_distribution": _probabilities(scorelines),
        "total_goal_distribution": _probabilities(total_goals_dist, ["0", "1", "2", "3", "4", "5", "6+"]),
        "result_distribution": _probabilities(result_dist, ["H", "D", "A"]),
    }


def _fetch_text(url: str, cache_path: Path) -> str:
    if cache_path.exists():
        return cache_path.read_text(encoding="utf-8-sig")
    request = urllib.request.Request(url, headers={"User-Agent": "amiguinhos-v13-realism-benchmark/1.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        raw = response.read().decode("utf-8-sig")
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(raw, encoding="utf-8")
    return raw


def load_real_collection(source_file: Path, cache_dir: Path) -> tuple[list[dict[str, int]], list[dict]]:
    source = json.loads(source_file.read_text(encoding="utf-8"))
    dataset = source["match_dataset"]
    pooled: list[dict[str, int]] = []
    per_dataset: list[dict] = []
    for league in dataset["leagues"]:
        for season in dataset["seasons"]:
            url = dataset["raw_url_template"].format(slug=league["slug"], season=season)
            text = _fetch_text(url, cache_dir / f"{league['slug']}-{season}.csv")
            rows: list[dict[str, int]] = []
            for raw_row in csv.DictReader(io.StringIO(text)):
                try:
                    row = _normalise_real_row(raw_row)
                except (ValueError, TypeError):
                    continue
                rows.append(row)
            if not rows:
                raise RuntimeError(f"No usable rows from {url}")
            pooled.extend(rows)
            summary = summarise_matches(rows)
            per_dataset.append({
                "league": league["name"],
                "slug": league["slug"],
                "season": season,
                "source": url,
                **summary,
            })
    return pooled, per_dataset


def _engine_match_record(engine: MatchEngine) -> dict[str, int]:
    return {
        "home_goals": int(engine.score[0]),
        "away_goals": int(engine.score[1]),
        "home_shots": int(engine.stats[0].shots),
        "away_shots": int(engine.stats[1].shots),
        "home_sot": int(engine.stats[0].on_target),
        "away_sot": int(engine.stats[1].on_target),
        "home_fouls": int(engine.stats[0].fouls),
        "away_fouls": int(engine.stats[1].fouls),
        "home_corners": int(engine.stats[0].corners),
        "away_corners": int(engine.stats[1].corners),
        "home_yellow": int(engine.stats[0].yellow),
        "away_yellow": int(engine.stats[1].yellow),
        "home_red": int(engine.stats[0].red),
        "away_red": int(engine.stats[1].red),
    }


def simulate_engine_population(count: int, start_seed: int) -> tuple[list[dict[str, int]], dict]:
    seeds = list(range(int(start_seed), int(start_seed) + int(count)))
    if RESERVED_OFFICIAL_FINAL_SEED in seeds:
        raise ValueError("Reserved official final seed cannot be used by the real-match benchmark")

    rows: list[dict[str, int]] = []
    second_half_added: list[float] = []
    stoppage_goals = 0
    all_goals = 0
    final_minutes: list[float] = []

    for seed in seeds:
        population_rng = random.Random(f"v13-real-population:{seed}")
        home_strength = _weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS)
        away_strength = _weighted_pick(population_rng, STRENGTHS, STRENGTH_WEIGHTS)
        home_style = _weighted_pick(population_rng, STYLES, STYLE_WEIGHTS)
        away_style = _weighted_pick(population_rng, STYLES, STYLE_WEIGHTS)
        home = make_generic_team(
            f"Benchmark Home {seed}",
            int(home_strength),
            str(home_style),
            seed=900000 + seed * 2,
        )
        away = make_generic_team(
            f"Benchmark Away {seed}",
            int(away_strength),
            str(away_style),
            seed=900001 + seed * 2,
        )
        engine = MatchEngine(
            home,
            away,
            seed=seed,
            venue_context={
                "mode": BENCHMARK_VENUE_MODE,
                "source": "real_league_benchmark",
            },
        )
        guard = 0
        while not engine.state.ended and guard < 7000:
            engine.step()
            guard += 1
        if guard >= 7000:
            raise RuntimeError(f"Simulation guard reached on seed {seed}")
        rows.append(_engine_match_record(engine))
        final_minutes.append(float(engine.minute))

        stop = getattr(engine, "_v13_stoppage", {}) or {}
        announced = stop.get("announced_seconds_by_marker", {}) or {}
        second_half_added.append(float(announced.get("90", 0.0)) / 60.0)
        for event in engine.state.event_log:
            if str(getattr(event.type, "value", event.type)) != "goal":
                continue
            if (event.data or {}).get("shootout"):
                continue
            all_goals += 1
            stoppage_goals += int(float(event.minute) >= 90.0)

    timing = {
        "second_half_added_minutes": statistics.mean(second_half_added) if second_half_added else 0.0,
        "stoppage_goal_share": stoppage_goals / all_goals if all_goals else 0.0,
        "final_minute_mean": statistics.mean(final_minutes) if final_minutes else 0.0,
        "goals_observed": all_goals,
    }
    return rows, timing


def _season_metric_scales(per_dataset: list[dict]) -> dict[str, float]:
    scales = {}
    for metric in CORE_METRICS:
        values = [float(row["metrics"][metric]) for row in per_dataset]
        empirical = statistics.stdev(values) if len(values) >= 2 else 0.0
        scales[metric] = max(empirical, SCALE_FLOORS[metric])
    return scales


def _metric_component(engine_value: float, real_value: float, scale: float) -> tuple[float, float]:
    z = abs(float(engine_value) - float(real_value)) / max(1e-12, float(scale))
    score = 100.0 * math.exp(-0.5 * z * z)
    return z, score


def _js_distance(left: dict[str, float], right: dict[str, float]) -> float:
    keys = sorted(set(left) | set(right))
    if not keys:
        return 0.0
    p = [max(0.0, float(left.get(key, 0.0))) for key in keys]
    q = [max(0.0, float(right.get(key, 0.0))) for key in keys]
    p_total, q_total = sum(p), sum(q)
    if p_total <= 0 or q_total <= 0:
        return 1.0
    p = [value / p_total for value in p]
    q = [value / q_total for value in q]
    m = [(a + b) / 2.0 for a, b in zip(p, q)]

    def kl(a, b):
        total = 0.0
        for x, y in zip(a, b):
            if x > 0.0:
                total += x * math.log(x / y)
        return total

    js = 0.5 * kl(p, m) + 0.5 * kl(q, m)
    return math.sqrt(max(0.0, js) / math.log(2.0))


def compare(real_summary: dict, engine_summary: dict, per_dataset: list[dict]) -> dict:
    scales = _season_metric_scales(per_dataset)
    components = []
    for metric in CORE_METRICS:
        real_value = float(real_summary["metrics"][metric])
        engine_value = float(engine_summary["metrics"][metric])
        z, score = _metric_component(engine_value, real_value, scales[metric])
        components.append({
            "name": metric,
            "kind": "scalar",
            "real": real_value,
            "engine": engine_value,
            "delta": engine_value - real_value,
            "scale": scales[metric],
            "standardised_gap": z,
            "score": score,
            "weight": METRIC_WEIGHTS[metric],
        })

    distributions = (
        ("result_distribution", 1.25),
        ("total_goal_distribution", 1.75),
        ("scoreline_distribution", 2.00),
    )
    for name, weight in distributions:
        distance = _js_distance(real_summary[name], engine_summary[name])
        score = 100.0 * (1.0 - distance)
        components.append({
            "name": name,
            "kind": "distribution",
            "distance": distance,
            "score": score,
            "weight": weight,
        })

    weight_total = sum(float(row["weight"]) for row in components)
    realism_index = sum(float(row["score"]) * float(row["weight"]) for row in components) / weight_total
    return {
        "realism_index": realism_index,
        "components": components,
        "largest_gaps": sorted(
            [row for row in components if row["kind"] == "scalar"],
            key=lambda row: float(row["standardised_gap"]),
            reverse=True,
        )[:8],
    }


def _timing_comparison(source: dict, engine_timing: dict) -> dict:
    ref = source["timing_references"]["premier_league_2024_25"]
    return {
        "reference_scope": "Premier League 2024/25",
        "reference_source": ref["source"],
        "second_half_added_minutes": {
            "real": float(ref["second_half_added_minutes"]),
            "engine": float(engine_timing["second_half_added_minutes"]),
            "delta": float(engine_timing["second_half_added_minutes"]) - float(ref["second_half_added_minutes"]),
        },
        "stoppage_goal_share": {
            "real": float(ref["stoppage_goal_share"]),
            "engine": float(engine_timing["stoppage_goal_share"]),
            "delta": float(engine_timing["stoppage_goal_share"]) - float(ref["stoppage_goal_share"]),
        },
        "engine_final_minute_mean": float(engine_timing["final_minute_mean"]),
        "note": "Supplemental only: timing reference is one competition/season and is not included in the core realism index.",
    }


def run(engine_matches: int, start_seed: int, cache_dir: Path, output: Path | None) -> dict:
    source = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
    real_rows, per_dataset = load_real_collection(SOURCE_FILE, cache_dir)
    real_summary = summarise_matches(real_rows)
    engine_rows, engine_timing = simulate_engine_population(engine_matches, start_seed)
    engine_summary = summarise_matches(engine_rows)
    comparison = compare(real_summary, engine_summary, per_dataset)
    timing = _timing_comparison(source, engine_timing)

    result = {
        "benchmark_version": 2,
        "candidate": "v1.3",
        "engine_venue_mode": BENCHMARK_VENUE_MODE,
        "real_match_count": len(real_rows),
        "engine_match_count": len(engine_rows),
        "engine_seed_range": [start_seed, start_seed + engine_matches - 1],
        "real_sources": [
            {
                "league": row["league"],
                "season": row["season"],
                "matches": int(row["metrics"]["matches"]),
                "source": row["source"],
            }
            for row in per_dataset
        ],
        "real": real_summary,
        "engine": engine_summary,
        "comparison": comparison,
        "timing_supplemental": timing,
        "guardrails": source["methodology_notes"],
    }

    print(
        f"v1.3 real-match benchmark: {len(real_rows)} real matches vs "
        f"{len(engine_rows)} engine matches"
    )
    print(f"venue_mode={BENCHMARK_VENUE_MODE}")
    print(f"realism_index={comparison['realism_index']:.2f}/100")
    print("metric                          real      engine     delta      z      score")
    for component in comparison["components"]:
        if component["kind"] != "scalar":
            continue
        print(
            f"{component['name']:<30} "
            f"{component['real']:>7.3f} "
            f"{component['engine']:>10.3f} "
            f"{component['delta']:>9.3f} "
            f"{component['standardised_gap']:>6.2f} "
            f"{component['score']:>8.1f}"
        )
    print("distribution scores:")
    for component in comparison["components"]:
        if component["kind"] == "distribution":
            print(
                f"  {component['name']}: score={component['score']:.1f} "
                f"JS_distance={component['distance']:.3f}"
            )
    print(
        "timing supplemental: "
        f"2H added real={timing['second_half_added_minutes']['real']:.2f} "
        f"engine={timing['second_half_added_minutes']['engine']:.2f}; "
        f"90+ goal share real={timing['stoppage_goal_share']['real']:.3f} "
        f"engine={timing['stoppage_goal_share']['engine']:.3f}"
    )
    print("largest standardised gaps:")
    for row in comparison["largest_gaps"]:
        print(f"  {row['name']}: z={row['standardised_gap']:.2f}, delta={row['delta']:+.3f}")

    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, indent=2, sort_keys=True), encoding="utf-8")
        print(f"json_report={output}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine-matches", type=int, default=500)
    parser.add_argument("--start-seed", type=int, default=91000)
    parser.add_argument("--cache-dir", type=Path, default=Path(".cache/real_match_benchmark"))
    parser.add_argument("--output", type=Path, default=None)
    args = parser.parse_args()
    if args.engine_matches <= 0:
        raise SystemExit("--engine-matches must be > 0")
    run(args.engine_matches, args.start_seed, args.cache_dir, args.output)
