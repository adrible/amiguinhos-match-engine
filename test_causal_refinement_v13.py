"""Behavioural invariants for discipline and conditional shot conversion."""
import random
import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine


class CausalRefinementTests(unittest.TestCase):
    def make_engine(self):
        return MatchEngine(make_generic_team('A', 78, seed=1001),
                           make_generic_team('B', 78, seed=2002), seed=1234)

    def test_neutral_execution_preserves_tiny_chance_probability(self):
        for xg in (0.0, 0.000001, 0.003, 0.01, 0.04):
            for block in (0.03, 0.2, 0.34):
                for target in (0.1, 0.3, 0.6):
                    p = MatchEngine._shot_goal_probability(xg, block, target, 72, 72)
                    self.assertAlmostEqual((1-block)*target*p, xg, places=12)

    def test_execution_modifies_conversion_after_situation_xg(self):
        xg = 0.003
        low = MatchEngine._shot_goal_probability(xg, .2, .3, 60, 80)
        equal = MatchEngine._shot_goal_probability(xg, .2, .3, 80, 80)
        high = MatchEngine._shot_goal_probability(xg, .2, .3, 90, 80)
        self.assertLess(low, equal)
        self.assertLess(equal, high)
        self.assertEqual(xg, .003)

    def test_conditional_probability_is_bounded_and_monotonic(self):
        values = [MatchEngine._shot_goal_probability(x, .34, .1, 90, 70)
                  for x in (0, .001, .005, .01, .1, .9)]
        self.assertEqual(values, sorted(values))
        self.assertTrue(all(0 <= p <= .86 for p in values))
        self.assertEqual(values[0], 0)
        self.assertTrue(0 <= MatchEngine._shot_goal_probability(.1, 1, 0, 72, 72) <= .86)

    def test_second_caution_has_same_draw_for_clear_grounds(self):
        e = self.make_engine()
        defender = e.teams[1].on_field[1]
        # Isolate sanction from the existing behavioural/effective-attribute
        # response to a booking. Identical assessment must use identical draws.
        e._card_probabilities = lambda *a: {'yellow': .4, 'direct_red': 0.0}
        for source in (False, True):
            incident = dict(type='holding', severity=.4, spa=True,
                            dogso=False, ordinary_contact=source)
            for seed in range(20):
                defender.yellow = 0; e.rng = random.Random(seed)
                first, _ = e._decide_card(1, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
                first_rng = e.rng.getstate()
                defender.yellow = 1; e.rng = random.Random(seed)
                second, _ = e._decide_card(1, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
                self.assertEqual(first is None, second is None)
                if first: self.assertEqual(second, 'second_yellow_red')
                self.assertEqual(first_rng, e.rng.getstate())

    def test_origin_flag_does_not_change_sanction_factor(self):
        e = self.make_engine()
        for severity in (.2, .5, .8):
            for spa in (False, True):
                incident = dict(type='trip', severity=severity, spa=spa, dogso=False)
                self.assertEqual(e._second_yellow_factor(incident),
                                 e._second_yellow_factor(dict(incident, ordinary_contact=True)))

    def test_box_dogso_exception_does_not_protect_violent_conduct(self):
        e = self.make_engine(); defender = e.teams[1].on_field[1]
        incident = dict(type='late_tackle', severity=.5, spa=True,
                        dogso=True, violent=False, attempt_to_play_ball=True)
        box = Zone(Band.BOX, Lane.CENTER)
        ordinary = e._card_probabilities(1, defender, incident, box, 1)
        violent = e._card_probabilities(1, defender, dict(incident, violent=True), box, 1)
        outside = e._card_probabilities(1, defender, incident, Zone(Band.ATT, Lane.CENTER), 1)
        self.assertLess(ordinary['direct_red'], outside['direct_red'])
        violent_outside = e._card_probabilities(
            1, defender, dict(incident, violent=True), Zone(Band.ATT, Lane.CENTER), 1)
        self.assertEqual(violent['direct_red'], violent_outside['direct_red'])
        self.assertGreater(violent['direct_red'], ordinary['direct_red'])

    def test_tactical_dogso_respects_direct_red_switch(self):
        for enabled in (False, True):
            e = self.make_engine(); e.config.direct_red_enabled = enabled
            e._ensure_tactical_fouls()
            e._v13_tactical_foul_rng.random = lambda: 0.0
            defender = e.teams[1].on_field[1]
            card = e._tactical_foul_card(1, defender, .98, Zone(Band.ATT, Lane.CENTER))
            self.assertEqual(card, 'direct_red' if enabled else 'yellow')

    def test_probability_helpers_preserve_rng(self):
        e = self.make_engine(); before = e.rng.getstate()
        e._shot_goal_probability(.003, .2, .3, 75, 80)
        e._second_yellow_factor(dict(type='holding', severity=.4, spa=True))
        self.assertEqual(before, e.rng.getstate())


if __name__ == '__main__':
    unittest.main()
