from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_corners import MatchEngineV13Corners
from engine_experiment_v13_throwins import MatchEngineV13ThrowIns


class ContextualThrowInTests(unittest.TestCase):
    def engine(self, seed=8701):
        return MatchEngineV13ThrowIns(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def test_canonical_entrypoint_uses_throw_in_layer(self):
        self.assertTrue(issubclass(MatchEngineV13ThrowIns, MatchEngineV13Corners))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13ThrowIns)

    def test_central_turnover_never_becomes_throw_in(self):
        e = self.engine()
        diag = e.throw_in_from_turnover_diagnostic(
            0,
            Zone(Band.MID, Lane.CENTER),
            "progressive_pass_failed",
            {"pressure": 0.8, "space": 0.2},
        )
        self.assertFalse(diag["eligible"])
        self.assertEqual(diag["out_probability"], 0.0)

    def test_cleared_cross_is_more_likely_out_than_failed_long_ball(self):
        e = self.engine(seed=8703)
        zone = Zone(Band.ATT, Lane.LEFT)
        ctx = {"pressure": 0.55, "space": 0.45}
        cleared = e.throw_in_from_turnover_diagnostic(0, zone, "cross_cleared", ctx)
        long_ball = e.throw_in_from_turnover_diagnostic(0, zone, "long_ball_failed", ctx)
        self.assertGreater(cleared["out_probability"], long_ball["out_probability"])
        self.assertGreater(cleared["retain_throw_probability"], long_ball["retain_throw_probability"])

    def test_ball_out_is_one_public_step_and_restart_is_next(self):
        e = self.engine(seed=8705)
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() != "GK")
        zone = Zone(Band.ATT, Lane.RIGHT)
        original = e.throw_in_from_turnover_diagnostic
        e.throw_in_from_turnover_diagnostic = lambda *args, **kwargs: {
            "eligible": True,
            "out_probability": 1.0,
            "retain_throw_probability": 1.0,
            "reason": "cross_cleared",
            "zone": e._zone_data(zone),
        }
        first = e._turnover(0, actor, zone, "cross_cleared", {"pressure": 0.5, "space": 0.5}, severity=0.4)
        e.throw_in_from_turnover_diagnostic = original
        self.assertEqual(first.text_key, "ball_out_throw_in")
        self.assertEqual(e.state.restart, "throw_in")
        self.assertIsNone(e.state.pending)
        second = e.step()
        self.assertIn(second.text_key, {"throw_in_completed", "throw_in_lost"})
        self.assertIsNone(e.state.restart)
        self.assertIsNone(e.state.pending)

    def test_opponent_throw_mirrors_attack_relative_zone(self):
        e = self.engine(seed=8707)
        actor = next(ps for ps in e.teams[0].on_field if ps.player.position.upper() != "GK")
        zone = Zone(Band.ATT, Lane.LEFT)
        diag = {"out_probability": 0.4, "retain_throw_probability": 0.2}
        e._arm_throw_in(0, actor, zone, "bad_safe_pass", 1, diag)
        self.assertEqual(e.state.restart_team, 1)
        self.assertEqual(e.state.restart_zone, zone.mirror())
        self.assertEqual(e.state.possession, 1)

    def test_plan_is_normalized_rng_pure_and_reads_directness(self):
        e = self.engine(seed=8709)
        zone = Zone(Band.MID, Lane.RIGHT)
        state = e.rng.getstate()
        e.set_tactics(0, directness=0.05, width=0.40)
        patient = e.throw_in_plan_diagnostic(0, zone)
        self.assertEqual(e.rng.getstate(), state)
        self.assertAlmostEqual(sum(patient["weights"].values()), 1.0)
        e.set_tactics(0, directness=0.95, width=0.75)
        direct = e.throw_in_plan_diagnostic(0, zone)
        self.assertGreater(patient["weights"]["short_return"], direct["weights"]["short_return"])
        self.assertGreater(direct["weights"]["down_line"], patient["weights"]["down_line"])

    def test_long_throw_is_derived_not_a_new_player_attribute(self):
        e = self.engine(seed=8711)
        zone = Zone(Band.ATT, Lane.LEFT)
        taker = e._throw_in_taker(0, zone)
        before = e.throw_in_plan_diagnostic(0, zone)["long_throw_quality"]
        for attr in ("strength", "crossing", "technique", "passing"):
            setattr(taker.player, attr, 95)
        after = e.throw_in_plan_diagnostic(0, zone)["long_throw_quality"]
        self.assertGreater(after, before)
        self.assertFalse(hasattr(taker.player, "long_throw"))
        self.assertFalse(hasattr(taker.player, "throw_in"))

    def test_throw_in_restart_roundtrip_preserves_future(self):
        e = self.engine(seed=8713)
        e.state.restart = "throw_in"
        e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.MID, Lane.LEFT)
        e.state.possession = 0
        e.state.zone = e.state.restart_zone
        e.state.phase = "restart"
        clone = MatchEngineV13ThrowIns.from_json(e.export_json())
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type, a.text_key, a.data), (b.minute, b.team, b.type, b.text_key, b.data))
        self.assertEqual(e.export_state(), clone.export_state())

    def test_same_seed_full_sequence_remains_deterministic(self):
        a, b = self.engine(seed=8715), self.engine(seed=8715)
        sig_a, sig_b = [], []
        for _ in range(30):
            ea, eb = a.step(), b.step()
            sig_a.append((ea.minute, ea.team, ea.type.value, ea.text_key, ea.data))
            sig_b.append((eb.minute, eb.team, eb.type.value, eb.text_key, eb.data))
        self.assertEqual(sig_a, sig_b)


if __name__ == "__main__":
    unittest.main()
