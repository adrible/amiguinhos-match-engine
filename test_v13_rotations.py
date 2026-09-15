from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_rotations import MatchEngineV13Rotations
from engine_experiment_v13_substitution_strategy import MatchEngineV13SubstitutionStrategy
from team_loader_v13 import load_team_v13


class PositionRotationTests(unittest.TestCase):
    def engine(self, seed=9501):
        return MatchEngineV13Rotations(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=505),
            seed=seed,
        )

    @staticmethod
    def chase_stoppage(e, minute=75.0):
        e.state.second = minute * 60.0
        e.stats[1].goals = 1
        e.state.restart = "throw_in"
        e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.ATT, Lane.RIGHT)
        e.set_tactics(0, cross_frequency=0.78)

    def test_canonical_entrypoint_uses_rotation_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Rotations, MatchEngineV13SubstitutionStrategy))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13Rotations)

    def test_rotation_diagnostic_is_rng_pure(self):
        e = self.engine(seed=9503)
        self.chase_stoppage(e)
        state = e.rng.getstate()
        _ = e.position_rotation_diagnostic(0)
        self.assertEqual(e.rng.getstate(), state)

    def test_mike_and_remo_can_form_wide_delivery_rotation(self):
        e = self.engine(seed=9505)
        self.chase_stoppage(e)
        mike = e.teams[0].by_name("Mike Junior")
        remo = e.teams[0].by_name("Remo")
        self.assertEqual((mike.player.position, remo.player.position), ("LW", "RW"))
        profile = e._pair_rotation_profile(0, mike, remo, "chase_game")
        self.assertIsNotNone(profile)
        self.assertGreater(profile["wide_delivery_gain"], 0.0)
        self.assertEqual((profile["first_to"], profile["second_to"]), ("RW", "LW"))

    def test_rotation_is_its_own_public_event_and_restart_remains(self):
        e = self.engine(seed=9507)
        self.chase_stoppage(e)
        event = e._maybe_position_rotation()
        self.assertIsNotNone(event)
        self.assertEqual(event.text_key, "position_rotation")
        self.assertEqual(e.state.restart, "throw_in")
        self.assertEqual(len(e._v13_position_rotations), 1)

    def test_rotation_cooldown_prevents_immediate_ping_pong(self):
        e = self.engine(seed=9509)
        self.chase_stoppage(e)
        event = e._maybe_position_rotation()
        self.assertIsNotNone(event)
        self.assertIsNone(e.position_rotation_diagnostic(0))
        e.state.second += (e.ROTATION_COOLDOWN_MINUTES - 0.1) * 60.0
        self.assertIsNone(e.position_rotation_diagnostic(0))

    def test_rotation_does_not_change_player_attributes(self):
        e = self.engine(seed=9511)
        self.chase_stoppage(e)
        mike = e.teams[0].by_name("Mike Junior").player
        attrs = {key: value for key, value in mike.__dict__.items() if key != "position"}
        _ = e._maybe_position_rotation()
        after = {key: value for key, value in mike.__dict__.items() if key != "position"}
        self.assertEqual(attrs, after)

    def test_rotation_history_and_positions_survive_roundtrip(self):
        e = self.engine(seed=9513)
        self.chase_stoppage(e)
        event = e._maybe_position_rotation()
        self.assertIsNotNone(event)
        clone = MatchEngineV13Rotations.from_json(e.export_json())
        self.assertEqual(e._v13_position_rotations, clone._v13_position_rotations)
        for name in (event.data["first"], event.data["second"]):
            self.assertEqual(
                e.teams[0].by_name(name).player.position,
                clone.teams[0].by_name(name).player.position,
            )
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type, a.text_key, a.data), (b.minute, b.team, b.type, b.text_key, b.data))


if __name__ == "__main__":
    unittest.main()
