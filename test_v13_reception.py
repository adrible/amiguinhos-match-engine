from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13_defense import MatchEngineV13Defense
from engine_experiment_v13_reception import MatchEngineV13Reception


class ReceptionMechanicsTests(unittest.TestCase):
    def engine(self):
        return MatchEngineV13Reception(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=303,
        )

    def actor(self, e):
        return next(ps for ps in e.teams[0].on_field if ps.player.position != "GK")

    def ctx(self, pressure=0.35, space=0.62):
        return {
            "pressure": pressure,
            "space": space,
            "support": 0.58,
            "space_behind": 0.52,
        }

    def test_reception_quality_uses_existing_technique_not_new_attribute(self):
        e = self.engine()
        a = self.actor(e)
        z = Zone(Band.ATT, Lane.CENTER)

        a.player.technique = 45
        low = e.reception_diagnostic(
            a, z, self.ctx(pressure=0.70, space=0.30), source="progressive_pass"
        )
        a.player.technique = 95
        high = e.reception_diagnostic(
            a, z, self.ctx(pressure=0.20, space=0.70), source="progressive_pass"
        )

        self.assertGreater(high["control_score"], low["control_score"])
        self.assertGreater(high["scan_score"], low["scan_score"])
        self.assertFalse(hasattr(a.player, "first_touch"))

    def test_harder_trajectory_reduces_control_score(self):
        e = self.engine()
        a = self.actor(e)
        z = Zone(Band.ATT, Lane.CENTER)
        ground = e.reception_diagnostic(a, z, self.ctx(), source="safe_pass")
        rebound = e.reception_diagnostic(a, z, self.ctx(), source="rebound")
        self.assertGreater(rebound["trajectory_difficulty"], ground["trajectory_difficulty"])
        self.assertGreater(ground["control_score"], rebound["control_score"])

    def test_better_control_reduces_bad_touch_weight(self):
        e = self.engine()
        a = self.actor(e)
        z = Zone(Band.MID, Lane.CENTER)

        a.player.technique = 45
        low = e.reception_diagnostic(a, z, self.ctx(0.70, 0.32), source="cross")
        a.player.technique = 95
        high = e.reception_diagnostic(a, z, self.ctx(0.20, 0.72), source="safe_pass")

        low_w = dict(e._touch_outcome_weights(low))
        high_w = dict(e._touch_outcome_weights(high))
        self.assertGreater(low_w["miscontrol"], high_w["miscontrol"])
        self.assertGreater(high_w["perfect"], low_w["perfect"])

    def test_oriented_reception_respects_wide_foot_profile(self):
        e = self.engine()
        a = self.actor(e)
        a.player.position = "LW"
        a.player.preferred_foot = "R"
        z = Zone(Band.ATT, Lane.LEFT)
        diag = e.reception_diagnostic(a, z, self.ctx(), source="progressive_pass")
        weights = dict(e._oriented_touch_weights(a, z, diag))
        self.assertGreater(weights["inside"], weights["line"])

        a.player.preferred_foot = "L"
        diag = e.reception_diagnostic(a, z, self.ctx(), source="progressive_pass")
        weights = dict(e._oriented_touch_weights(a, z, diag))
        self.assertGreater(weights["line"], weights["inside"])

    def test_first_time_probability_is_contextual(self):
        e = self.engine()
        a = self.actor(e)
        z = Zone(Band.BOX, Lane.CENTER)

        a.player.technique = 45
        a.player.vision = 45
        a.player.composure = 45
        low_diag = e.reception_diagnostic(
            a, z, self.ctx(pressure=0.82, space=0.24), source="cross"
        )
        low = e._first_time_probability(a, "shoot", low_diag)

        a.player.technique = 95
        a.player.vision = 92
        a.player.composure = 92
        high_diag = e.reception_diagnostic(
            a, z, self.ctx(pressure=0.18, space=0.76), source="cutback"
        )
        high = e._first_time_probability(a, "shoot", high_diag)

        self.assertGreater(high, low)
        self.assertEqual(
            e._first_time_probability(a, "dribble", high_diag), 0.0
        )

    def test_reception_marker_and_pending_first_time_survive_roundtrip(self):
        e = self.engine()
        a = self.actor(e)
        zone = Zone(Band.ATT, Lane.LEFT)
        e._v13_reception_marker = {
            "target": a.player.name,
            "zone": zone,
            "source": "progressive_pass",
        }
        e._v13_pending_first_time = {
            "team": 0,
            "actor": a.player.name,
            "kind": "shoot",
            "source": "cutback",
        }

        clone = MatchEngineV13Reception.from_json(e.export_json())
        self.assertEqual(clone._v13_reception_marker["target"], a.player.name)
        self.assertEqual(clone._v13_reception_marker["zone"], zone)
        self.assertEqual(
            clone._v13_pending_first_time["source"], "cutback"
        )

    def test_defensive_chain_includes_reception_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Defense, MatchEngineV13Reception))

    def test_diagnostic_is_deterministic_and_does_not_consume_rng(self):
        e = self.engine()
        a = self.actor(e)
        z = Zone(Band.ATT, Lane.CENTER)
        state = e.rng.getstate()
        one = e.reception_diagnostic(a, z, self.ctx(), source="through_ball")
        two = e.reception_diagnostic(a, z, self.ctx(), source="through_ball")
        self.assertEqual(one, two)
        self.assertEqual(e.rng.getstate(), state)


if __name__ == "__main__":
    unittest.main()
