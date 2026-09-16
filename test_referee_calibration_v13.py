from __future__ import annotations

import unittest

from engine import Band, Lane, Zone
from engine_experiment_v13 import MatchEngine
from team_loader_v13 import load_team_v13


class RefereeCalibrationV13Tests(unittest.TestCase):
    def make_engine(self, seed=321):
        return MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
        )

    def test_ordinary_foul_has_very_low_direct_red_probability(self):
        e = self.make_engine()
        defender = e.teams[0].by_name("Jorge Henrique")
        incident = {
            "type": "trip",
            "severity": 0.45,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        p = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
        self.assertLess(p["direct_red"], 0.002)

    def test_strict_referee_does_not_create_straight_red_from_mild_contact(self):
        e = self.make_engine()
        defender = e.teams[0].by_name("Jorge Henrique")
        e.referee.strictness = 0.95
        incident = {
            "type": "trip",
            "severity": 0.38,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
            "ordinary_contact": True,
        }
        p = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
        self.assertLessEqual(p["direct_red"], 0.00035)

    def test_excessive_force_is_far_more_red_worthy_than_ordinary_trip(self):
        e = self.make_engine()
        defender = e.teams[0].by_name("Felipe")
        ordinary = {
            "type": "trip",
            "severity": 0.45,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        severe = {
            "type": "reckless_tackle",
            "severity": 0.94,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": True,
        }
        low = e._card_probabilities(0, defender, ordinary, Zone(Band.MID, Lane.CENTER), 1)
        high = e._card_probabilities(0, defender, severe, Zone(Band.MID, Lane.CENTER), 1)
        self.assertGreater(high["direct_red"], low["direct_red"] * 5.0)
        self.assertGreater(high["direct_red"], 0.10)

    def test_nonball_dogso_is_more_red_worthy_than_box_ball_attempt(self):
        e = self.make_engine()
        defender = e.teams[0].by_name("Jorge Henrique")
        base = {
            "severity": 0.70,
            "spa": True,
            "dogso": True,
            "violent": False,
        }
        ball = e._card_probabilities(
            0,
            defender,
            {**base, "type": "late_tackle", "attempt_to_play_ball": True},
            Zone(Band.BOX, Lane.CENTER),
            1,
        )
        hold = e._card_probabilities(
            0,
            defender,
            {**base, "type": "holding", "attempt_to_play_ball": False},
            Zone(Band.BOX, Lane.CENTER),
            1,
        )
        self.assertLess(ball["direct_red"], hold["direct_red"])

    def test_second_yellow_management_is_strong_for_marginal_repeat_foul(self):
        e = self.make_engine()
        marginal = {
            "type": "trip",
            "severity": 0.40,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        serious = {
            "type": "reckless_tackle",
            "severity": 0.82,
            "spa": True,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        marginal_factor = e._second_yellow_factor(marginal)
        serious_factor = e._second_yellow_factor(serious)
        self.assertLessEqual(marginal_factor, 0.05)
        self.assertGreater(marginal_factor, 0.0)
        self.assertGreater(serious_factor, marginal_factor * 3.0)
        self.assertLess(serious_factor, 0.45)

    def test_spa_repeat_retains_more_second_yellow_pressure_than_routine_repeat(self):
        e = self.make_engine()
        routine = {
            "type": "holding",
            "severity": 0.48,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": False,
            "violent": False,
        }
        spa = {**routine, "spa": True}
        routine_factor = e._second_yellow_factor(routine)
        spa_factor = e._second_yellow_factor(spa)
        self.assertGreater(spa_factor, routine_factor)
        self.assertLessEqual(spa_factor, 0.09)
        self.assertGreater(spa_factor, 0.0)

    def test_ordinary_contact_has_more_second_yellow_management_than_same_generic_trip(self):
        e = self.make_engine()
        generic = {
            "type": "trip",
            "severity": 0.42,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        ordinary = {**generic, "ordinary_contact": True}
        generic_factor = e._second_yellow_factor(generic)
        ordinary_factor = e._second_yellow_factor(ordinary)
        self.assertGreater(generic_factor, ordinary_factor)
        self.assertGreater(ordinary_factor, 0.0)
        self.assertLessEqual(ordinary_factor, 0.038)

    def test_dogso_reduces_second_yellow_management_without_erasing_it(self):
        e = self.make_engine()
        serious = {
            "type": "reckless_tackle",
            "severity": 0.82,
            "spa": True,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        dogso = {**serious, "dogso": True}
        serious_factor = e._second_yellow_factor(serious)
        dogso_factor = e._second_yellow_factor(dogso)
        self.assertGreater(dogso_factor, serious_factor)
        self.assertLessEqual(dogso_factor, 0.55)
        self.assertLess(dogso_factor, 1.0)

    def test_hard_foul_reaction_upgrade_can_create_confrontation_without_forcing_card(self):
        e = self.make_engine(seed=909)
        attacker = e.teams[0].by_name("Felipe")
        defender = e.teams[1].by_name("João Victor")
        incident = {
            "type": "reckless_tackle",
            "severity": 0.90,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        seen_confront = False
        for _ in range(80):
            result = e._hard_foul_reaction_upgrade(
                0,
                attacker,
                1,
                defender,
                incident,
                {
                    "reaction": "verbal_protest",
                    "aggressor_response": "walks_away",
                    "mass_confrontation": False,
                    "sanctions": [],
                },
            )
            if result and result["reaction"] in {"confront", "shove"}:
                seen_confront = True
                break
        self.assertTrue(seen_confront)


if __name__ == "__main__":
    unittest.main()
