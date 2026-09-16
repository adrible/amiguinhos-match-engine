import json
import unittest

from real_match_benchmark_v13 import (
    CORE_METRICS,
    RESERVED_OFFICIAL_FINAL_SEED,
    SOURCE_FILE,
    _js_distance,
    compare,
    simulate_engine_population,
    summarise_matches,
)


class RealMatchBenchmarkTests(unittest.TestCase):
    @staticmethod
    def _row(hg, ag, hs=12, ass=10, hst=4, ast=3, hf=11, af=12, hc=5, ac=4, hy=2, ay=2, hr=0, ar=0):
        return {
            "home_goals": hg,
            "away_goals": ag,
            "home_shots": hs,
            "away_shots": ass,
            "home_sot": hst,
            "away_sot": ast,
            "home_fouls": hf,
            "away_fouls": af,
            "home_corners": hc,
            "away_corners": ac,
            "home_yellow": hy,
            "away_yellow": ay,
            "home_red": hr,
            "away_red": ar,
        }

    def test_source_manifest_covers_five_leagues_and_three_seasons(self):
        source = json.loads(SOURCE_FILE.read_text(encoding="utf-8"))
        dataset = source["match_dataset"]
        self.assertEqual(len(dataset["leagues"]), 5)
        self.assertEqual(dataset["seasons"], ["2223", "2324", "2425"])
        self.assertIn("FTHG", dataset["required_columns"])
        self.assertIn("HR", dataset["required_columns"])

    def test_summary_uses_match_level_stats_without_hidden_targets(self):
        summary = summarise_matches([
            self._row(1, 0),
            self._row(1, 1, hs=15, ass=9, hst=6, ast=2),
        ])
        metrics = summary["metrics"]
        self.assertEqual(metrics["matches"], 2)
        self.assertAlmostEqual(metrics["goals_per_match"], 1.5)
        self.assertAlmostEqual(metrics["shots_per_match"], 23.0)
        self.assertAlmostEqual(metrics["sot_per_match"], 7.5)
        self.assertAlmostEqual(metrics["home_win_rate"], 0.5)
        self.assertAlmostEqual(metrics["draw_rate"], 0.5)
        self.assertAlmostEqual(metrics["away_win_rate"], 0.0)
        self.assertAlmostEqual(sum(summary["result_distribution"].values()), 1.0)
        self.assertAlmostEqual(sum(summary["total_goal_distribution"].values()), 1.0)
        self.assertAlmostEqual(sum(summary["scoreline_distribution"].values()), 1.0)

    def test_identical_distributions_have_zero_js_distance(self):
        dist = {"0": 0.2, "1": 0.3, "2": 0.5}
        self.assertAlmostEqual(_js_distance(dist, dist), 0.0)

    def test_identical_summary_scores_one_hundred(self):
        rows = [self._row(1, 0), self._row(1, 1), self._row(0, 2), self._row(2, 2)]
        summary = summarise_matches(rows)
        per_dataset = [
            {"metrics": dict(summary["metrics"])},
            {"metrics": dict(summary["metrics"])},
        ]
        result = compare(summary, summary, per_dataset)
        self.assertAlmostEqual(result["realism_index"], 100.0)
        for component in result["components"]:
            self.assertAlmostEqual(component["score"], 100.0)

    def test_core_metrics_are_all_present_in_summary(self):
        summary = summarise_matches([self._row(2, 1)])
        for metric in CORE_METRICS:
            self.assertIn(metric, summary["metrics"])

    def test_reserved_official_final_seed_is_rejected_before_simulation(self):
        with self.assertRaises(ValueError):
            simulate_engine_population(1, RESERVED_OFFICIAL_FINAL_SEED)


if __name__ == "__main__":
    unittest.main()
