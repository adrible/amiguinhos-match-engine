import unittest

from engine import Band, Lane, Tactics, Zone, make_generic_team
from stable_engine import MatchEngine, simulate_full_match


class StableV12Tests(unittest.TestCase):
    def test_quality_gap_is_directional(self):
        weak = make_generic_team("Weak", 75, "balanced", seed=1)
        strong = make_generic_team("Strong", 84, "balanced", seed=2)
        engine = MatchEngine(weak, strong, seed=123)
        zone = Zone(Band.ATT, Lane.CENTER)

        weak_attack = engine._spatial_context(0, zone)
        strong_attack = engine._spatial_context(1, zone)

        self.assertGreater(weak_attack["quality_gap"], 0)
        self.assertLess(strong_attack["quality_gap"], 0)

    def test_overlap_is_side_specific(self):
        tactics = Tactics(overlap_left=0.90, overlap_right=0.10)
        zone = Zone(Band.ATT, Lane.CENTER)

        left = MatchEngine._fullback_overlap_factor("LB", zone, tactics)
        right = MatchEngine._fullback_overlap_factor("RB", zone, tactics)

        self.assertGreater(left, right)

    def test_same_seed_remains_reproducible(self):
        a1 = make_generic_team("A", 75, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "attacking", seed=11)
        a2 = make_generic_team("A", 75, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "attacking", seed=11)

        m1 = simulate_full_match(a1, b1, seed=999)
        m2 = simulate_full_match(a2, b2, seed=999)

        self.assertEqual(m1.score, m2.score)
        self.assertEqual(m1.snapshot()["stats"], m2.snapshot()["stats"])


if __name__ == "__main__":
    unittest.main()
