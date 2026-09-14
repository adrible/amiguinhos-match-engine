from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_scanning import MatchEngineV13Scanning
from engine_experiment_v13_passing_texture import MatchEngineV13PassingTexture
from engine_experiment_v13_deception import MatchEngineV13Deception
from engine_experiment_v13_transition_structure import MatchEngineV13TransitionStructure
from engine_experiment_v13_space_manipulation import MatchEngineV13SpaceManipulation


class AdvancedCollectiveTests(unittest.TestCase):
    def engine(self, seed=707):
        return MatchEngineV13SpaceManipulation(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def actor(self, e, team=0):
        return next(
            ps
            for ps in e.teams[team].on_field
            if ps.player.position.upper() not in {"GK", "CB"}
        )

    @staticmethod
    def ctx(pressure=0.45, space=0.58, support=0.62):
        return {
            "pressure": pressure,
            "space": space,
            "space_behind": 0.52,
            "support": support,
            "defensive_quality": 0.56,
            "transition_threat": 0.50,
        }

    def test_layer_order_and_canonical_entrypoint(self):
        self.assertTrue(issubclass(MatchEngineV13PassingTexture, MatchEngineV13Scanning))
        self.assertTrue(issubclass(MatchEngineV13Deception, MatchEngineV13PassingTexture))
        self.assertTrue(issubclass(MatchEngineV13TransitionStructure, MatchEngineV13Deception))
        self.assertTrue(issubclass(MatchEngineV13SpaceManipulation, MatchEngineV13TransitionStructure))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13SpaceManipulation))

    def test_scanning_changes_information_and_decision_time_without_new_attribute(self):
        e = self.engine()
        a = self.actor(e)
        zone = Zone(Band.ATT, Lane.CENTER)
        for attr in ("vision", "anticipation", "composure", "technique"):
            setattr(a.player, attr, 95)
        high = e.scanning_diagnostic(a, zone, self.ctx(0.34, 0.72, 0.70))
        for attr in ("vision", "anticipation", "composure", "technique"):
            setattr(a.player, attr, 45)
        low = e.scanning_diagnostic(a, zone, self.ctx(0.68, 0.36, 0.42))
        self.assertGreater(high["scan_quality"], low["scan_quality"])
        self.assertLess(high["decision_seconds"], low["decision_seconds"])
        self.assertFalse(hasattr(a.player, "scanning"))
        self.assertFalse(hasattr(a.player, "decision_speed"))

    def test_pass_arrival_quality_changes_next_reception(self):
        e = self.engine()
        a = self.actor(e)
        zone = Zone(Band.MID, Lane.CENTER)
        base_marker = {"target": a.player.name, "zone": zone, "source": "safe_pass"}

        e._v13_reception_marker = {
            **base_marker,
            "pass_delivery": "overhit",
            "pass_shape": "driven",
            "pass_delivery_score": 0.30,
            "delivery_control_delta": -0.075,
            "delivery_trajectory_delta": 0.060,
        }
        bad = e.reception_diagnostic(a, zone, self.ctx(), source="safe_pass")

        e._v13_reception_marker = {
            **base_marker,
            "pass_delivery": "ahead",
            "pass_shape": "ground",
            "pass_delivery_score": 0.84,
            "delivery_control_delta": 0.040,
            "delivery_trajectory_delta": -0.025,
        }
        good = e.reception_diagnostic(a, zone, self.ctx(), source="safe_pass")
        self.assertGreater(good["control_score"], bad["control_score"])
        self.assertLess(good["trajectory_difficulty"], bad["trajectory_difficulty"])

    def test_pass_delivery_marker_survives_roundtrip(self):
        e = self.engine(seed=711)
        a = self.actor(e)
        zone = Zone(Band.MID, Lane.LEFT)
        e._v13_reception_marker = {
            "target": a.player.name,
            "zone": zone,
            "source": "progressive_pass",
            "pass_delivery": "slightly_behind",
            "pass_shape": "driven",
            "pass_delivery_score": 0.53,
            "delivery_control_delta": -0.035,
            "delivery_trajectory_delta": 0.025,
        }
        clone = MatchEngineV13SpaceManipulation.from_json(e.export_json())
        marker = clone._v13_reception_marker
        self.assertEqual(marker["pass_delivery"], "slightly_behind")
        self.assertEqual(marker["pass_shape"], "driven")
        self.assertAlmostEqual(marker["delivery_control_delta"], -0.035)

    def test_deception_probability_uses_existing_technical_traits(self):
        e = self.engine(seed=713)
        a = self.actor(e)
        zone = Zone(Band.ATT, Lane.RIGHT)
        for attr in ("technique", "vision", "dribbling", "composure"):
            setattr(a.player, attr, 95)
        setattr(a.player, "boldness", 90)
        high = e.deception_diagnostic(a, zone, "through_ball", self.ctx(0.52, 0.55, 0.64))
        for attr in ("technique", "vision", "dribbling", "composure"):
            setattr(a.player, attr, 45)
        setattr(a.player, "boldness", 35)
        low = e.deception_diagnostic(a, zone, "through_ball", self.ctx(0.52, 0.55, 0.64))
        self.assertGreater(high["attempt_probability"], low["attempt_probability"])

    def test_rest_defense_responds_to_structure_not_team_identity(self):
        e = self.engine(seed=719)
        zone = Zone(Band.ATT, Lane.LEFT)
        structural = [
            ps for ps in e.teams[0].on_field
            if ps.player.position.upper() in {"CB", "DM", "LB", "RB"}
        ]
        for ps in structural:
            for attr in ("positioning", "anticipation", "tackling", "pace"):
                setattr(ps.player, attr, 94)
        high = e.rest_defense_diagnostic(0, zone)
        for ps in structural:
            for attr in ("positioning", "anticipation", "tackling", "pace"):
                setattr(ps.player, attr, 48)
        low = e.rest_defense_diagnostic(0, zone)
        self.assertGreater(high["quality"], low["quality"])

    def test_counterpress_has_explicit_depth_tradeoff_and_persists(self):
        e = self.engine(seed=727)
        a = self.actor(e, 1)
        e.state.possession = 1
        e.state.zone = Zone(Band.MID, Lane.CENTER)
        e._v13_current_open_actor = a.player.name
        baseline = e._spatial_context(1, e.state.zone)
        e._v13_counterpress_marker = {
            "pressing_team": 0,
            "target_team": 1,
            "until": e.state.second + 30.0,
            "intensity": 0.72,
            "pressure_delta": 0.05,
            "depth_tradeoff": 0.045,
            "rest_defense_quality": 0.68,
        }
        pressured = e._spatial_context(1, e.state.zone)
        self.assertGreaterEqual(pressured["pressure"], baseline["pressure"])
        self.assertGreaterEqual(pressured["space_behind"], baseline["space_behind"])

        clone = MatchEngineV13SpaceManipulation.from_json(e.export_json())
        self.assertIsNotNone(clone._v13_counterpress_marker)
        self.assertAlmostEqual(clone._v13_counterpress_marker["intensity"], 0.72)

    def test_overload_to_isolate_reads_far_side_option(self):
        e = self.engine(seed=733)
        actor = self.actor(e)
        zone = Zone(Band.ATT, Lane.LEFT)
        high = e.space_manipulation_diagnostic(
            0, actor, zone, self.ctx(0.34, 0.72, 0.82)
        )
        low = e.space_manipulation_diagnostic(
            0, actor, zone, self.ctx(0.72, 0.38, 0.34)
        )
        self.assertIsNotNone(high["far_side_target"])
        self.assertGreater(high["overload_score"], low["overload_score"])
        self.assertGreaterEqual(high["isolation_score"], 0.0)

    def test_same_seed_remains_deterministic(self):
        a = self.engine(seed=741)
        b = self.engine(seed=741)
        sig_a, sig_b = [], []
        for _ in range(24):
            ea, eb = a.step(), b.step()
            sig_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            sig_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(sig_a, sig_b)

    def test_save_load_continuation_remains_deterministic(self):
        e = self.engine(seed=743)
        for _ in range(15):
            e.step()
        clone = MatchEngineV13SpaceManipulation.from_json(e.export_json())
        out_a, out_b = [], []
        for _ in range(10):
            a, b = e.step(), clone.step()
            out_a.append((a.minute, a.type.value, a.text_key, a.team, a.data))
            out_b.append((b.minute, b.type.value, b.text_key, b.team, b.data))
        self.assertEqual(out_a, out_b)


if __name__ == "__main__":
    unittest.main()
