from __future__ import annotations

import unittest

from calibration_v13 import (
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
