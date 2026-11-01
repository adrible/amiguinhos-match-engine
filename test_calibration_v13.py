from __future__ import annotations

import unittest

from calibration_v13 import (
    MatchEngineV13UncappedAdaptationProbe,
    amiguinhos_flamengo_stress,
    player_behavior_profile,
    run_fixture_batch,
    simulate_fixture,
)


class CalibrationHarnessTests(unittest.TestCase):
    def test_batch_uses_exact_contiguous_unfiltered_seed_range(self):
        batch = run_fixture_batch(
            "amiguinhos_u21", "flamengo_u21", start_seed=17, count=3
        )
        self.assertEqual(batch["seed_policy"], "contiguous_unfiltered")
        self.assertEqual(batch["seeds"], [17, 18, 19])
        self.assertEqual([row["seed"] for row in batch["matches"]], [17, 18, 19])
        self.assertEqual(len(batch["matches"]), 3)
        self.assertEqual(
            batch["results"]["home_wins"]
            + batch["results"]["draws"]
            + batch["results"]["away_wins"],
            3,
        )

    def test_same_fixture_and_seed_are_reproducible(self):
        first = simulate_fixture("amiguinhos_u21", "flamengo_u21", 23)
        second = simulate_fixture("amiguinhos_u21", "flamengo_u21", 23)
        self.assertEqual(first, second)

    def test_fixture_statistics_remain_coherent(self):
        row = simulate_fixture("amiguinhos_u21", "flamengo_u21", 4)
        for side in ("home", "away"):
            self.assertGreaterEqual(row[side]["shots"], row[side]["on_target"])
            self.assertGreaterEqual(row[side]["on_target"], row[side]["goals"])
            self.assertGreaterEqual(row[side]["xg"], 0.0)
        self.assertGreater(row["event_count"], 0)

    def test_amiguinhos_stress_wrapper_does_not_hide_match_rows(self):
        batch = amiguinhos_flamengo_stress(start_seed=0, count=2)
        self.assertEqual(batch["fixture"], ["amiguinhos_u21", "flamengo_u21"])
        self.assertEqual(batch["count"], 2)
        self.assertEqual(len(batch["matches"]), 2)
        self.assertFalse(batch["diagnostic_engine"])

    def test_adaptation_diagnostics_are_zero_when_feature_is_disabled(self):
        batch = run_fixture_batch(
            "amiguinhos_u21", "flamengo_u21", start_seed=0, count=2,
            auto_adapt=False,
        )
        diag = batch["adaptation_diagnostics"]
        self.assertEqual(diag["team_match_observations"], 4)
        self.assertEqual(diag["total_adaptations"], 0)
        self.assertEqual(diag["mean_per_team_match"], 0.0)
        self.assertEqual(diag["max_per_team_match"], 0)
        self.assertEqual(diag["count_distribution"], {"0": 4})
        self.assertEqual(diag["team_matches_hitting_cap"], 0)
        self.assertIsNone(diag["mean_minutes_between_adaptations"])

    def test_adaptation_diagnostics_match_retained_rows(self):
        batch = run_fixture_batch(
            "amiguinhos_u21", "flamengo_u21", start_seed=0, count=2,
            auto_adapt=True,
        )
        diag = batch["adaptation_diagnostics"]
        retained_total = sum(len(row["adaptations"]) for row in batch["matches"])
        response_total = sum(batch["adaptation_responses"].values())
        self.assertEqual(diag["team_match_observations"], 4)
        self.assertEqual(diag["total_adaptations"], retained_total)
        self.assertEqual(diag["total_adaptations"], response_total)
        self.assertEqual(sum(diag["count_distribution"].values()), 4)
        self.assertLessEqual(
            diag["max_per_team_match"], diag["configured_team_cap"]
        )
        if diag["total_adaptations"]:
            self.assertIsNotNone(diag["mean_first_adaptation_minute"])

    def test_uncapped_probe_is_diagnostic_only_and_reports_its_own_cap(self):
        batch = amiguinhos_flamengo_stress(
            start_seed=0,
            count=2,
            auto_adapt=True,
            uncapped_adaptation_diagnostic=True,
        )
        self.assertTrue(batch["diagnostic_engine"])
        self.assertEqual(
            batch["adaptation_diagnostics"]["configured_team_cap"],
            MatchEngineV13UncappedAdaptationProbe.MAX_ADAPTATIONS_PER_TEAM,
        )
        self.assertEqual(
            MatchEngineV13UncappedAdaptationProbe.MAX_ADAPTATIONS_PER_TEAM, 99
        )

        canonical = amiguinhos_flamengo_stress(
            start_seed=0, count=1, auto_adapt=False
        )
        self.assertFalse(canonical["diagnostic_engine"])
        self.assertNotEqual(
            canonical["adaptation_diagnostics"]["configured_team_cap"], 99
        )

    def test_behavior_profiles_reflect_explicit_role_differences(self):
        adib = player_behavior_profile("amiguinhos_u21", "Gabriel Adib")
        mike = player_behavior_profile("amiguinhos_u21", "Mike Junior")
        remo = player_behavior_profile("amiguinhos_u21", "Remo")
        jorge = player_behavior_profile("amiguinhos_u21", "Jorge Henrique")

        self.assertEqual(adib["explicit_creativity"], 92.0)
        self.assertEqual(adib["explicit_boldness"], 86.0)
        self.assertGreater(adib["creativity"], jorge["creativity"])
        self.assertGreater(mike["creativity"], remo["creativity"])
        self.assertGreater(remo["boldness"], mike["boldness"])
        for profile in (adib, mike, remo, jorge):
            self.assertEqual(
                set(profile["contexts"]), {"mid_center", "att_center", "att_wide"}
            )
            for context in profile["contexts"].values():
                probs = context["decision_probabilities"]
                self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)


if __name__ == "__main__":
    unittest.main()
