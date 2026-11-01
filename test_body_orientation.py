from __future__ import annotations

import unittest

from engine import Band, Lane, PendingAction, Player, PlayerState, Tactics, Zone, make_generic_team
from engine_experiment_v13_body import MatchEngineV13Body


CTX = {"pressure": 0.42, "space": 0.58, "space_behind": 0.48, "support": 0.55}


def ps(position="AM", foot="R", **kw):
    d = dict(
        name="P", position=position, overall=80,
        pace=80, passing=82, vision=84, technique=84, dribbling=82,
        crossing=82, finishing=82, long_shots=82, heading=76,
        composure=84, anticipation=84, off_ball=84, strength=76,
        preferred_foot=foot,
    )
    d.update(kw)
    return PlayerState(Player(**d))


class BodyOrientationTests(unittest.TestCase):
    def setUp(self):
        a = make_generic_team("A", 78, "balanced", seed=1)
        b = make_generic_team("B", 78, "balanced", seed=2)
        self.e = MatchEngineV13Body(a, b, seed=123)
        self.t = Tactics()

    def test_through_ball_reception_faces_goal_more_than_rebound(self):
        actor = ps("ST")
        z = Zone(Band.BOX, Lane.CENTER)
        through = self.e.body_orientation_diagnostic(actor, z, CTX, source="through_ball")
        rebound = self.e.body_orientation_diagnostic(actor, z, CTX, source="rebound")
        self.assertGreater(through["forward_view"], rebound["forward_view"])
        self.assertGreater(through["open_body"], rebound["open_body"])
        self.assertLess(through["turn_cost"], rebound["turn_cost"])

    def test_striker_under_pressure_can_receive_back_to_goal(self):
        actor = ps("ST", technique=72, anticipation=72, composure=72)
        z = Zone(Band.ATT, Lane.CENTER)
        p = self.e.body_orientation_diagnostic(
            actor, z,
            {"pressure": 0.92, "space": 0.18, "space_behind": 0.20, "support": 0.45},
            source="open_play",
        )
        self.assertIn(p["stance"], {"back_to_goal", "half_turn"})
        self.assertGreater(p["turn_cost"], 0.45)

    def test_facing_goal_increases_shot_share(self):
        actor = ps("AM", finishing=88, long_shots=86)
        z = Zone(Band.ATT, Lane.CENTER)
        forward = self.e.decision_probabilities(actor, z, self.t, CTX, source="through_ball")
        awkward = self.e.decision_probabilities(actor, z, self.t, CTX, source="rebound")
        self.assertGreater(forward["shoot"], awkward["shoot"])

    def test_back_to_goal_increases_safe_recycling(self):
        actor = ps("ST", technique=74, anticipation=74, composure=76)
        z = Zone(Band.ATT, Lane.CENTER)
        pressed = {"pressure": 0.88, "space": 0.18, "space_behind": 0.18, "support": 0.60}
        natural = self.e.decision_probabilities(actor, z, self.t, pressed, source="open_play")
        running = self.e.decision_probabilities(actor, z, self.t, pressed, source="through_ball")
        self.assertGreater(natural["safe_pass"], running["safe_pass"])

    def test_natural_wide_foot_favors_crossing(self):
        z = Zone(Band.ATT, Lane.LEFT)
        lefty = ps("LW", foot="L")
        righty = ps("LW", foot="R")
        p_nat = self.e.decision_probabilities(lefty, z, self.t, CTX)
        p_inv = self.e.decision_probabilities(righty, z, self.t, CTX)
        self.assertGreater(p_nat["cross"], p_inv["cross"])

    def test_inverted_wide_foot_favors_shooting(self):
        z = Zone(Band.ATT, Lane.LEFT)
        lefty = ps("LW", foot="L", long_shots=86)
        righty = ps("LW", foot="R", long_shots=86)
        p_nat = self.e.decision_probabilities(lefty, z, self.t, CTX)
        p_inv = self.e.decision_probabilities(righty, z, self.t, CTX)
        self.assertGreater(p_inv["shoot"], p_nat["shoot"])

    def test_orientation_does_not_change_player_attributes(self):
        actor = ps("AM")
        before = (actor.effective("technique"), actor.effective("passing"), actor.effective("finishing"))
        _ = self.e.body_orientation_diagnostic(actor, Zone(Band.ATT, Lane.CENTER), CTX, source="through_ball")
        after = (actor.effective("technique"), actor.effective("passing"), actor.effective("finishing"))
        self.assertEqual(before, after)

    def test_same_seed_remains_reproducible(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Body(a1, b1, seed=999)
        e2 = MatchEngineV13Body(a2, b2, seed=999)
        for _ in range(180):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual((x1.type, x1.team, x1.text_key, x1.data), (x2.type, x2.team, x2.text_key, x2.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
