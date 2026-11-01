from __future__ import annotations

import unittest

from engine import Band, Event, EventType, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13_match_flow_realism import MatchEngineV13MatchFlowRealism


class MatchFlowRealismTests(unittest.TestCase):
    def make_engine(self, seed: int = 123) -> MatchEngineV13MatchFlowRealism:
        return MatchEngineV13MatchFlowRealism(
            make_generic_team("Home", 78, "balanced", seed=1001),
            make_generic_team("Away", 78, "balanced", seed=1002),
            seed=seed,
        )

    def test_failed_wide_cross_has_real_corner_route(self):
        engine = self.make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        ctx = {"pressure": 0.68, "space": 0.34}
        cross = engine.corner_turnover_probability(zone, "cross_stopped", ctx)
        weak = engine.corner_turnover_probability(Zone(Band.MID, Lane.CENTER), "cross_stopped", ctx)
        self.assertGreater(cross, 0.30)
        self.assertEqual(weak, 0.0)

    def test_wide_through_ball_deflection_can_run_behind_but_central_one_cannot(self):
        engine = self.make_engine()
        ctx = {"pressure": 0.72, "space": 0.30}
        wide = engine.corner_turnover_probability(Zone(Band.ATT, Lane.RIGHT), "through_ball_cleared", ctx)
        central = engine.corner_turnover_probability(Zone(Band.ATT, Lane.CENTER), "through_ball_cleared", ctx)
        self.assertGreater(wide, 0.0)
        self.assertEqual(central, 0.0)

    def test_forced_deflection_arms_corner_instead_of_generic_turnover(self):
        engine = self.make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        actor = engine._choose_actor(0, zone)
        engine.corner_turnover_probability = lambda *args, **kwargs: 1.0
        event = engine._turnover(0, actor, zone, "cross_stopped", {"pressure": 0.7, "space": 0.3})
        self.assertEqual(event.type, EventType.CORNER)
        self.assertEqual(engine.state.restart, "corner")
        self.assertEqual(engine.state.restart_team, 0)
        self.assertEqual(engine.stats[0].corners, 1)
        self.assertEqual(event.data["corner_cause"], "deflection_or_clearance")

    def test_contextual_corner_clearance_has_bounded_recorner_route(self):
        engine = self.make_engine()
        event = Event(
            engine.minute,
            1,
            EventType.PROGRESSION,
            2,
            "corner_cleared_contextual",
            {"delivery_quality": 0.78, "contact_probability": 0.64},
        )
        probability = engine.corner_reclear_probability(event)
        self.assertGreater(probability, 0.10)
        self.assertLessEqual(probability, 0.21)
        unrelated = Event(engine.minute, 1, EventType.PROGRESSION, 2, "carry_success", {})
        self.assertEqual(engine.corner_reclear_probability(unrelated), 0.0)

    def test_save_can_lead_to_corner_without_erasing_save_semantics(self):
        engine = self.make_engine()
        p = PendingAction(
            team=0,
            actor=engine._choose_actor(0, Zone(Band.BOX, Lane.CENTER)).player.name,
            kind="shoot",
            zone=Zone(Band.BOX, Lane.CENTER),
            danger=0.66,
            pressure=0.48,
            origin="through_ball",
        )
        event = Event(engine.minute, 0, EventType.SAVE, 3, "shot_saved", {"xg": 0.32})
        probability = engine.shot_corner_probability(p, event)
        self.assertGreater(probability, 0.0)
        before_saves = engine.stats[1].saves
        engine.stats[1].saves += 1
        result = engine._arm_corner_after_shot(0, p, event, probability)
        self.assertEqual(result.type, EventType.SAVE)
        self.assertTrue(result.data["corner_awarded"])
        self.assertEqual(engine.stats[1].saves, before_saves + 1)
        self.assertEqual(engine.stats[0].corners, 1)
        self.assertEqual(engine.state.restart, "corner")

    def test_dribble_contact_is_more_foul_prone_than_safe_pass(self):
        engine = self.make_engine()
        zone = Zone(Band.MID, Lane.CENTER)
        actor = engine._choose_actor(0, zone)
        defender = engine._choose_defender(1, zone)
        ctx = {"pressure": 0.62}
        safe = engine.contact_foul_probability(0, actor, defender, zone, "safe_pass", ctx)
        dribble = engine.contact_foul_probability(0, actor, defender, zone, "dribble", ctx)
        self.assertGreater(dribble, safe)
        self.assertLessEqual(dribble, 0.115)

    def test_booked_defender_manages_borderline_contact_without_immunity(self):
        engine = self.make_engine()
        zone = Zone(Band.MID, Lane.CENTER)
        actor = engine._choose_actor(0, zone)
        defender = engine._choose_defender(1, zone)
        ctx = {"pressure": 0.62}
        unbooked = engine.contact_foul_probability(0, actor, defender, zone, "dribble", ctx)
        defender.yellow = 1
        booked = engine.contact_foul_probability(0, actor, defender, zone, "dribble", ctx)
        self.assertGreater(unbooked, booked)
        self.assertGreater(booked, 0.0)
        self.assertLess(booked / unbooked, 0.65)
        self.assertGreater(booked / unbooked, 0.40)

    def test_box_contact_extension_is_conservative(self):
        engine = self.make_engine()
        zone = Zone(Band.BOX, Lane.CENTER)
        actor = engine._choose_actor(0, zone)
        defender = engine._choose_defender(1, zone)
        ctx = {"pressure": 0.58}
        self.assertEqual(engine.contact_foul_probability(0, actor, defender, zone, "safe_pass", ctx), 0.0)
        self.assertLess(engine.contact_foul_probability(0, actor, defender, zone, "dribble", ctx), 0.04)

    def test_forced_ordinary_contact_uses_existing_referee_pipeline(self):
        engine = self.make_engine()
        zone = Zone(Band.MID, Lane.CENTER)
        actor = engine._choose_actor(0, zone)
        engine.contact_foul_probability = lambda *args, **kwargs: 1.0
        before = engine.stats[1].fouls
        event = engine._execute_decision(
            0,
            actor,
            zone,
            "progressive_pass",
            {"pressure": 0.64, "space": 0.42, "support": 0.55, "space_behind": 0.32},
        )
        self.assertIn(event.type, {EventType.FOUL, EventType.PENALTY})
        self.assertEqual(engine.stats[1].fouls, before + 1)
        self.assertTrue(event.data["ordinary_contact"])
        self.assertEqual(event.data["contact_action"], "progressive_pass")
        self.assertIn("foul_type", event.data)

    def test_diagnostics_do_not_mutate_player_attributes(self):
        engine = self.make_engine()
        zone = Zone(Band.ATT, Lane.LEFT)
        actor = engine._choose_actor(0, zone)
        defender = engine._choose_defender(1, zone)
        before_actor = actor.player.__dict__.copy()
        before_defender = defender.player.__dict__.copy()
        engine.corner_turnover_probability(zone, "cross_stopped", {"pressure": 0.6, "space": 0.4})
        engine.contact_foul_probability(0, actor, defender, zone, "cross", {"pressure": 0.6})
        self.assertEqual(before_actor, actor.player.__dict__)
        self.assertEqual(before_defender, defender.player.__dict__)

    def test_canonical_entrypoint_contains_match_flow_realism_layer(self):
        from engine_experiment_v13 import MatchEngine

        self.assertTrue(issubclass(MatchEngine, MatchEngineV13MatchFlowRealism))


if __name__ == "__main__":
    unittest.main()
