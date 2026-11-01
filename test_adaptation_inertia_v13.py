from __future__ import annotations

import unittest

from engine import MatchConfig, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_adaptation_inertia import MatchEngineV13AdaptationInertia


def make_engine(seed: int = 123) -> MatchEngineV13AdaptationInertia:
    a = make_generic_team("A", 79, "balanced", seed=10)
    b = make_generic_team("B", 80, "balanced", seed=20)
    return MatchEngineV13AdaptationInertia(
        a,
        b,
        seed=seed,
        config=MatchConfig(auto_tactical_adaptation=True),
    )


class TacticalAdaptationInertiaTests(unittest.TestCase):
    def test_canonical_entrypoint_uses_progressive_inertia(self):
        # New candidate layers may sit above inertia; the architectural invariant
        # is that the canonical engine still includes progressive inertia in its
        # inheritance chain rather than having to be exactly that class object.
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13AdaptationInertia))

    def test_first_adaptation_threshold_is_unchanged(self):
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("protect_depth", 0),
            0.60,
        )
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("chase_game", 0),
            0.62,
        )

    def test_repeated_adaptations_require_progressively_stronger_evidence(self):
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("protect_depth", 1),
            0.645,
        )
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("protect_depth", 2),
            0.70,
        )
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("chase_game", 1),
            0.645,
        )
        self.assertAlmostEqual(
            MatchEngineV13AdaptationInertia._stable_threshold("chase_game", 2),
            0.68,
        )

    def test_second_adaptation_waits_eighteen_minutes(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {"minute": 60.0, "team": 0, "response": "protect_depth"}
        ]
        e.stats[0].goals = 0
        e.stats[1].goals = 2

        e.state.second = 77 * 60
        blocked = e._adaptation_profile(0)
        self.assertEqual(blocked["response"], "chase_game")
        self.assertFalse(blocked["eligible"])
        self.assertIn("progressive_adaptation_inertia", blocked["blocked_reasons"])
        self.assertEqual(
            blocked["progressive_inertia"]["required_cooldown_minutes"], 18.0
        )

        e.state.second = 78 * 60
        allowed = e._adaptation_profile(0)
        self.assertEqual(allowed["response"], "chase_game")
        self.assertTrue(allowed["eligible"])

    def test_third_adaptation_waits_twenty_four_minutes_but_remains_possible(self):
        e = make_engine()
        e._v13_adaptation_history = [
            {"minute": 40.0, "team": 0, "response": "protect_depth"},
            {"minute": 65.0, "team": 0, "response": "protect_wide"},
        ]
        e.stats[0].goals = 0
        e.stats[1].goals = 2

        e.state.second = 88 * 60
        blocked = e._adaptation_profile(0)
        self.assertEqual(blocked["response"], "chase_game")
        self.assertFalse(blocked["eligible"])
        self.assertIn("progressive_adaptation_inertia", blocked["blocked_reasons"])
        self.assertEqual(
            blocked["progressive_inertia"]["required_cooldown_minutes"], 24.0
        )

        e.state.second = 89 * 60
        allowed = e._adaptation_profile(0)
        self.assertEqual(allowed["response"], "chase_game")
        self.assertTrue(allowed["eligible"])
        self.assertTrue(allowed["stability_gate"]["progressive_inertia"])

    def test_inertia_diagnostic_is_rng_pure(self):
        e = make_engine(seed=777)
        before = e.rng.getstate()
        _ = e.tactical_adaptation_diagnostic(0)
        after = e.rng.getstate()
        self.assertEqual(before, after)


if __name__ == "__main__":
    unittest.main()
