from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_discipline_realism import MatchEngineV13DisciplineRealism


class DisciplineRealismTests(unittest.TestCase):
    def make_engine(self, seed: int = 321) -> MatchEngineV13DisciplineRealism:
        return MatchEngineV13DisciplineRealism(
            make_generic_team("Home", 78, "balanced", seed=4101),
            make_generic_team("Away", 78, "balanced", seed=4102),
            seed=seed,
        )

    def test_ordinary_contact_keeps_first_yellow_but_caps_direct_red(self):
        engine = self.make_engine()
        defender = engine._choose_defender(1, Zone(Band.MID, Lane.CENTER))
        incident = {
            "type": "trip",
            "severity": 0.42,
            "attempt_to_play_ball": True,
            "spa": False,
            "dogso": False,
            "violent": False,
            "ordinary_contact": True,
        }
        probs = engine._card_probabilities(1, defender, incident, Zone(Band.MID, Lane.CENTER), 2)
        self.assertGreater(probs["yellow"], 0.0)
        self.assertLessEqual(probs["direct_red"], 0.0008)

    def test_ordinary_repeat_has_management_margin_but_not_immunity(self):
        engine = self.make_engine()
        plain = {
            "type": "trip",
            "severity": 0.38,
            "spa": False,
            "dogso": False,
            "ordinary_contact": True,
        }
        spa = {**plain, "spa": True, "severity": 0.50}
        plain_factor = engine._second_yellow_factor(plain)
        spa_factor = engine._second_yellow_factor(spa)
        self.assertGreater(plain_factor, 0.0)
        self.assertGreater(spa_factor, plain_factor)
        self.assertLessEqual(plain_factor, 0.060)
        self.assertEqual(spa_factor, 1.0)

    def test_hard_nonordinary_foul_keeps_existing_dismissal_logic(self):
        engine = self.make_engine()
        hard = {
            "type": "reckless_tackle",
            "severity": 0.86,
            "spa": True,
            "dogso": False,
            "violent": False,
        }
        factor = engine._second_yellow_factor(hard)
        self.assertGreater(factor, 0.10)

    def test_canonical_entrypoint_contains_discipline_layer(self):
        from engine_experiment_v13 import MatchEngine

        self.assertTrue(issubclass(MatchEngine, MatchEngineV13DisciplineRealism))


if __name__ == "__main__":
    unittest.main()
