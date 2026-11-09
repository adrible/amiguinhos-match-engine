import unittest

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13_continuous import MatchEngineV13Continuous
from spatial_shot_v13 import shot_geometry


class AerialCalibrationTests(unittest.TestCase):
    def test_first_contact_respects_pace_pressure_and_heading_skill(self):
        p = MatchEngineV13Continuous._aerial_control_probability
        self.assertLess(p(.7, 20., .5), p(.7, 5., .5))
        self.assertLess(p(.7, 12., .8), p(.7, 12., .1))
        self.assertGreater(p(.9, 12., .5), p(.4, 12., .5))
        self.assertLess(p(.7, 12., .5, .1), p(.7, 12., .5, 0.))

    def test_header_dispersion_uses_contact_difficulty(self):
        f = MatchEngineV13Continuous._header_spread_multiplier
        self.assertGreater(f(.7, 20., .5), f(.7, 5., .5))
        self.assertGreater(f(.7, 12., .8), f(.7, 12., .1))
        self.assertLess(f(.9, 12., .5), f(.4, 12., .5))

    def test_contact_adjustment_widens_only_requested_geometry(self):
        e = MatchEngineV13Continuous(make_generic_team('A', 80, seed=1),
                                     make_generic_team('B', 80, seed=2), seed=129801)
        player = e.teams[0].on_field[-1]
        keeper = e._goalkeeper(1)
        p = PendingAction(0, player.player.name, 'shoot', Zone(Band.BOX, Lane.CENTER),
                          .4, .5, body_part='head')
        base = e.shot_selection_diagnostic(player, p, keeper)
        normal = shot_geometry(e, p, player, keeper, base)
        increased = shot_geometry(e, p, player, keeper,
                                  {**base, 'contact_spread_multiplier': 1.4})
        self.assertAlmostEqual(increased['shot_execution_spread'],
                               normal['shot_execution_spread'] * 1.4)
        self.assertEqual(normal, shot_geometry(e, p, player, keeper, base))


if __name__ == '__main__':
    unittest.main()
