from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine
from engine_experiment_v13_spatial import MatchEngineV13Spatial


class GoalkeeperAttackingReceiverEligibilityTests(unittest.TestCase):
    def _engine(self, cls):
        home = make_generic_team("Home", 78, "balanced", seed=101)
        away = make_generic_team("Away", 78, "balanced", seed=202)
        return cls(home, away, seed=303)

    @staticmethod
    def _first_outfielder(engine):
        return next(ps for ps in engine.teams[0].on_field if ps.player.position.upper() != "GK")

    @staticmethod
    def _goalkeeper(engine):
        return next(ps for ps in engine.teams[0].on_field if ps.player.position.upper() == "GK")

    def test_goalkeeper_absent_from_spatial_target_probabilities(self):
        engine = self._engine(MatchEngineV13Spatial)
        actor = self._first_outfielder(engine)
        goalkeeper = self._goalkeeper(engine)
        for band in (Band.DEF, Band.MID, Band.ATT, Band.BOX):
            probs = engine.target_probabilities(0, actor, Zone(band, Lane.CENTER))
            self.assertNotIn(goalkeeper.player.name, probs)
            self.assertAlmostEqual(sum(probs.values()), 1.0, places=9)

    def test_goalkeeper_never_drawn_as_attacking_target(self):
        engine = self._engine(MatchEngineV13Spatial)
        actor = self._first_outfielder(engine)
        for band in (Band.DEF, Band.MID, Band.ATT, Band.BOX):
            zone = Zone(band, Lane.CENTER)
            for _ in range(2000):
                target = engine._choose_target(0, zone, attacking=True, exclude=actor.player.name)
                self.assertNotEqual(target.player.position.upper(), "GK")

    def test_goalkeeper_never_becomes_open_play_actor_outside_defensive_third(self):
        engine = self._engine(MatchEngineV13Spatial)
        for band in (Band.MID, Band.ATT, Band.BOX):
            zone = Zone(band, Lane.CENTER)
            for _ in range(2000):
                actor = engine._choose_actor(0, zone)
                self.assertNotEqual(actor.player.position.upper(), "GK")

    def test_forced_goalkeeper_target_is_rejected_in_canonical_engine(self):
        engine = self._engine(MatchEngine)
        actor = self._first_outfielder(engine)
        goalkeeper = self._goalkeeper(engine)
        engine._v13_forced_target = {
            "team": 0,
            "actor": actor.player.name,
            "target": goalkeeper.player.name,
            "action": "through_ball",
        }
        target = engine._choose_target(0, Zone(Band.ATT, Lane.CENTER), attacking=True, exclude=actor.player.name)
        self.assertNotEqual(target.player.position.upper(), "GK")
        self.assertIsNone(engine._v13_forced_target)

    def test_canonical_safe_pass_outside_defensive_third_never_targets_goalkeeper(self):
        engine = self._engine(MatchEngine)
        actor = self._first_outfielder(engine)
        for band in (Band.MID, Band.ATT, Band.BOX):
            zone = Zone(band, Lane.CENTER)
            for _ in range(500):
                target = engine._choose_target(
                    0, zone, attacking=False, exclude=actor.player.name
                )
                self.assertNotEqual(target.player.position.upper(), "GK")

    def test_quick_combination_cannot_promote_goalkeeper_into_advanced_open_play(self):
        engine = self._engine(MatchEngine)
        goalkeeper = self._goalkeeper(engine)
        outfielder = self._first_outfielder(engine)
        engine._ensure_combination_state()
        engine._v13_combination_history = [{
            "team": 0,
            "actor": outfielder.player.name,
            "target": goalkeeper.player.name,
            "second": float(engine.state.second),
            "kind": "safe_pass",
            "first_time": False,
        }]
        zone = Zone(Band.ATT, Lane.CENTER)
        for _ in range(200):
            actor = engine._choose_actor(0, zone)
            self.assertNotEqual(actor.player.position.upper(), "GK")

    def test_goalkeeper_cannot_choose_open_play_shot_without_keeper_up(self):
        engine = self._engine(MatchEngine)
        goalkeeper = self._goalkeeper(engine)
        zone = Zone(Band.ATT, Lane.CENTER)
        tactics = engine.teams[0].team.tactics
        ctx = engine._context(goalkeeper, zone)
        for _ in range(200):
            decision = engine._choose_decision(goalkeeper, zone, tactics, ctx)
            self.assertNotEqual(decision, "shoot")


if __name__ == "__main__":
    unittest.main()
