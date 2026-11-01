"""Exercise receiver selection through the real layered v1.3 runtime."""
import unittest
from unittest.mock import patch

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine


class TargetActionIntegrationTests(unittest.TestCase):
    def fixture(self):
        return MatchEngine(make_generic_team("A", 80, seed=11),
                           make_generic_team("B", 80, seed=22), seed=451)

    def test_every_active_override_accepts_action_for_both_pass_directions(self):
        engine = self.fixture()
        actor = next(ps for ps in engine.teams[0].on_field if ps.player.position == "CM")
        zone = Zone(Band.ATT, Lane.CENTER)
        for cls in type(engine).__mro__:
            if not cls.__module__.startswith("engine_experiment_v13"):
                continue
            if "_choose_target" not in cls.__dict__:
                continue
            for attacking in (True, False):
                for action in ("safe_pass", "progressive_pass", "cross", "cutback", "through_ball"):
                    with self.subTest(layer=cls.__name__, attacking=attacking, action=action):
                        target = cls._choose_target(engine, 0, zone, attacking=attacking,
                                                    exclude=actor.player.name, action=action)
                        self.assertIn(target, engine.teams[0].on_field)
                        self.assertNotEqual(target.player.name, actor.player.name)
                        self.assertNotEqual(target.player.position, "GK")

    def test_contextual_action_reaches_spatial_weighting(self):
        engine = self.fixture()
        with patch.object(engine, "_action_target_weights", wraps=engine._action_target_weights) as weights:
            for action in ("cross", "cutback", "through_ball"):
                engine._choose_target(0, Zone(Band.ATT, Lane.CENTER), action=action)
                self.assertEqual(weights.call_args.args[1], action)

    def test_aerial_and_ground_passes_prefer_different_receivers(self):
        engine = self.fixture()
        aerial, runner = engine.teams[0].on_field[1:3]
        for ps in (aerial, runner):
            for attr in ("off_ball", "anticipation", "finishing", "composure", "heading", "strength"):
                setattr(ps.player, attr, 70)
        aerial.player.heading, aerial.player.strength = 98, 94
        runner.player.finishing, runner.player.composure = 98, 94
        weights = [(aerial, 1.), (runner, 1.)]
        cross = engine._action_target_weights(weights, "cross")
        through = engine._action_target_weights(weights, "through_ball")
        self.assertGreater(cross[0][1], cross[1][1])
        self.assertGreater(through[1][1], through[0][1])
