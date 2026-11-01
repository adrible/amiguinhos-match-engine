from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_cover import MatchEngineV13Cover


CTX = {
    "pressure": 0.44,
    "space": 0.56,
    "space_behind": 0.58,
    "support": 0.52,
    "wide_space": 0.10,
    "defending_availability": 1.0,
}


def make_engine(seed=123):
    a = make_generic_team("Attack", 79, "balanced", seed=10)
    b = make_generic_team("Defence", 80, "balanced", seed=20)
    return MatchEngineV13Cover(a, b, seed=seed)


class DefensiveCoverTests(unittest.TestCase):
    def test_pressing_cover_uses_distinct_second_defender(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.96
        e.teams[1].team.tactics.compactness = 0.80
        e.teams[1].team.tactics.defensive_line = 0.62
        ctx = dict(CTX, pressure=0.32, space_behind=0.42)
        d = e.coverage_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx, kind="open_play")
        self.assertEqual(d["intent"], "press_ball")
        self.assertTrue(d["active"])
        self.assertEqual(d["coverage_type"], "cover_depth")
        self.assertNotEqual(d["primary_defender"], d["cover_defender"])
        if d["marker"] is not None:
            self.assertNotEqual(d["marker"], d["cover_defender"])

    def test_cover_depth_repairs_press_exposure_without_becoming_super_shield(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.98
        e.teams[1].team.tactics.compactness = 0.88
        e.teams[1].team.tactics.defensive_line = 0.72
        ctx = dict(CTX, pressure=0.30, space_behind=0.35)
        d = e.coverage_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx, kind="open_play")
        self.assertTrue(d["active"])
        # Primary press intentionally exposes depth. Cover may reduce that cost,
        # but should not turn the press into an unrelated giant depth bonus.
        self.assertGreaterEqual(d["adjusted"]["space_behind"], d["base"]["space_behind"] - 0.012)

    def test_wide_cross_creates_cutback_cover_with_tradeoff(self):
        e = make_engine()
        e.teams[1].team.tactics.compactness = 0.88
        d = e.coverage_diagnostic(0, Zone(Band.ATT, Lane.LEFT), CTX, kind="cross")
        self.assertEqual(d["intent"], "block_cross")
        self.assertTrue(d["active"])
        self.assertEqual(d["coverage_type"], "protect_cutback")
        self.assertGreater(d["adjusted"]["pass_lane_control"], 0.0)
        # Marginal trade-off of the cover itself: protecting the cutback pulls
        # the second defender inward, so it concedes a little extra width.
        # The primary block-cross action may still leave total wide space lower
        # than the raw context, which is correct and should not fail this test.
        self.assertGreater(d["effects"]["wide_space_delta"], 0.0)

    def test_primary_safety_intent_does_not_stack_secondary_cover(self):
        e = make_engine()
        d = e.coverage_diagnostic(
            0,
            Zone(Band.BOX, Lane.CENTER),
            dict(CTX, pressure=0.65, space=0.25, space_behind=0.25),
            kind="shoot",
        )
        self.assertIn(d["intent"], {"block_shot", "protect_box"})
        self.assertFalse(d["active"])
        self.assertIsNone(d["coverage_type"])

    def test_cover_quality_responds_to_defensive_intelligence(self):
        hi = make_engine(seed=7)
        lo = make_engine(seed=7)
        for engine, value in ((hi, 94), (lo, 58)):
            engine.teams[1].team.tactics.pressing = 0.96
            engine.teams[1].team.tactics.compactness = 0.90
            engine.teams[1].team.tactics.defensive_line = 0.70
            for ps in engine.teams[1].on_field:
                if ps.player.position.upper() in {"CB", "DM", "CM", "LB", "RB"}:
                    ps.player.positioning = value
                    ps.player.anticipation = value
                    ps.player.composure = value
                    ps.player.discipline = value
        ctx = dict(CTX, pressure=0.30, space_behind=0.38)
        dh = hi.coverage_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx)
        dl = lo.coverage_diagnostic(0, Zone(Band.MID, Lane.CENTER), ctx)
        self.assertTrue(dh["active"])
        self.assertTrue(dl["active"])
        self.assertGreater(dh["coverage_quality"], dl["coverage_quality"])

    def test_cover_does_not_modify_player_attributes(self):
        e = make_engine()
        e.teams[1].team.tactics.pressing = 0.96
        e.teams[1].team.tactics.compactness = 0.86
        attacker = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() == "ST")
        before = (attacker.effective("pace"), attacker.effective("off_ball"), attacker.effective("finishing"))
        _ = e.coverage_diagnostic(0, Zone(Band.MID, Lane.CENTER), CTX)
        after = (attacker.effective("pace"), attacker.effective("off_ball"), attacker.effective("finishing"))
        self.assertEqual(before, after)

    def test_same_seed_reproducible_with_cover_layer(self):
        a1 = make_generic_team("A", 78, "balanced", seed=10)
        b1 = make_generic_team("B", 80, "balanced", seed=20)
        a2 = make_generic_team("A", 78, "balanced", seed=10)
        b2 = make_generic_team("B", 80, "balanced", seed=20)
        e1 = MatchEngineV13Cover(a1, b1, seed=999)
        e2 = MatchEngineV13Cover(a2, b2, seed=999)
        for _ in range(220):
            if e1.state.ended or e2.state.ended:
                break
            x1 = e1.step()
            x2 = e2.step()
            self.assertEqual((x1.type, x1.team, x1.text_key, x1.data), (x2.type, x2.team, x2.text_key, x2.data))
        self.assertEqual(e1.snapshot(), e2.snapshot())


if __name__ == "__main__":
    unittest.main()
