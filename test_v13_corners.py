from __future__ import annotations

import unittest

from engine import Band, EventType, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_corners import MatchEngineV13Corners
from engine_experiment_v13_roles import MatchEngineV13Roles


class ContextualCornerTests(unittest.TestCase):
    def engine(self, seed=8601):
        return MatchEngineV13Corners(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    @staticmethod
    def arm_corner(e, team=0, lane=Lane.LEFT):
        e.state.restart = "corner"
        e.state.restart_team = team
        e.state.restart_zone = Zone(Band.ATT, lane)
        e.state.possession = team
        e.state.zone = Zone(Band.ATT, lane)
        e.state.phase = "restart"

    def test_canonical_entrypoint_uses_corner_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Corners, MatchEngineV13Roles))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13Corners))

    def test_plan_is_normalized_and_rng_pure(self):
        e = self.engine()
        state = e.rng.getstate()
        first = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        second = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        self.assertEqual(first, second)
        self.assertEqual(e.rng.getstate(), state)
        self.assertAlmostEqual(sum(first["weights"].values()), 1.0)
        self.assertEqual(set(first["weights"]), set(e.CORNER_PATTERNS))

    def test_patient_style_raises_short_corner_share(self):
        e = self.engine(seed=8603)
        e.set_tactics(0, directness=0.05, cross_frequency=0.10)
        patient = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.RIGHT))
        e.set_tactics(0, directness=0.95, cross_frequency=0.90)
        direct = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.RIGHT))
        self.assertGreater(patient["weights"]["short_corner"], direct["weights"]["short_corner"])

    def test_strong_keeper_reduces_central_delivery_share(self):
        e = self.engine(seed=8605)
        keeper = e._goalkeeper(1)
        for attr in ("handling", "gk_positioning", "reflexes", "strength", "anticipation"):
            setattr(keeper.player, attr, 45)
        weak = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        for attr in ("handling", "gk_positioning", "reflexes", "strength", "anticipation"):
            setattr(keeper.player, attr, 95)
        strong = e.corner_plan_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        self.assertLess(strong["weights"]["central_delivery"], weak["weights"]["central_delivery"])

    def test_short_corner_is_a_restart_not_an_automatic_chance(self):
        e = self.engine(seed=8607)
        self.arm_corner(e)
        base = e.corner_plan_diagnostic(0, e.state.restart_zone)
        e.corner_plan_diagnostic = lambda *args, **kwargs: {**base, "weights": {"short_corner": 1.0, "near_post": 0.0, "central_delivery": 0.0, "far_post": 0.0}}
        event = e.step()
        self.assertIn(event.text_key, {"corner_short_combination", "corner_short_intercepted"})
        self.assertIsNone(e.state.pending)
        self.assertIsNone(e.state.restart)

    def test_armed_contact_waits_for_next_public_step(self):
        e = self.engine(seed=8609)
        taker = e._corner_taker(0)
        target = e._corner_target(0, taker, Zone(Band.ATT, Lane.LEFT), "near_post")
        defender = e._corner_defender(1)
        delivery = {"cross_type": "whipped", "delivery_quality": 0.72}
        event = e._arm_corner_contact(
            0,
            taker,
            target,
            defender,
            Zone(Band.ATT, Lane.LEFT),
            "near_post",
            delivery,
            0.72,
            0.62,
            0.64,
            0.70,
            0.66,
        )
        self.assertEqual(event.text_key, "corner_delivery_pending")
        self.assertEqual(event.type, EventType.CORNER)
        self.assertIsNotNone(e.state.pending)
        self.assertEqual(e.state.pending.origin, "corner")
        self.assertEqual(e.state.pending.kind, "shoot")
        before_events = len(e.state.event_log)
        e.step()
        self.assertEqual(len(e.state.event_log), before_events + 1)

    def test_second_ball_reads_existing_reaction_system(self):
        e = self.engine(seed=8611)
        taker = e._corner_taker(0)
        zone = Zone(Band.BOX, Lane.CENTER)
        attackers = [ps for ps in e.teams[0].on_field if ps.player.name != taker.player.name and ps.player.position.upper() != "GK"]
        for ps in attackers:
            for attr in ("anticipation", "off_ball", "pace", "positioning", "composure"):
                setattr(ps.player, attr, 48)
        low = e.corner_second_ball_diagnostic(0, taker, zone, 0.60)
        for ps in attackers:
            for attr in ("anticipation", "off_ball", "pace", "positioning", "composure"):
                setattr(ps.player, attr, 94)
        high = e.corner_second_ball_diagnostic(0, taker, zone, 0.60)
        self.assertGreater(high["attack_score"], low["attack_score"])
        self.assertGreater(high["attacker_win_probability"], low["attacker_win_probability"])

    def test_corner_restart_roundtrip_preserves_same_future(self):
        e = self.engine(seed=8613)
        self.arm_corner(e, team=0, lane=Lane.RIGHT)
        clone = MatchEngineV13Corners.from_json(e.export_json())
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type, a.text_key, a.data), (b.minute, b.team, b.type, b.text_key, b.data))
        self.assertEqual(e.export_state(), clone.export_state())

    def test_pending_corner_delivery_survives_roundtrip(self):
        e = self.engine(seed=8615)
        taker = e._corner_taker(0)
        target = e._corner_target(0, taker, Zone(Band.ATT, Lane.RIGHT), "far_post")
        defender = e._corner_defender(1)
        e._arm_corner_contact(
            0,
            taker,
            target,
            defender,
            Zone(Band.ATT, Lane.RIGHT),
            "far_post",
            {"cross_type": "floated", "delivery_quality": 0.68},
            0.66,
            0.58,
            0.62,
            0.72,
            0.61,
        )
        clone = MatchEngineV13Corners.from_json(e.export_json())
        self.assertIsNotNone(clone.state.pending)
        self.assertEqual(clone.state.pending.origin, "corner")
        self.assertEqual(clone._v13_cross_context, e._v13_cross_context)
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type, a.text_key, a.data), (b.minute, b.team, b.type, b.text_key, b.data))


if __name__ == "__main__":
    unittest.main()
