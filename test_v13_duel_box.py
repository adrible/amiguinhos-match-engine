from __future__ import annotations

import unittest

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_space_manipulation import MatchEngineV13SpaceManipulation
from engine_experiment_v13_dribbling import MatchEngineV13AdvancedDribbling
from engine_experiment_v13_one_v_one import MatchEngineV13OneVOne
from engine_experiment_v13_box_movement import MatchEngineV13BoxMovement
from engine_experiment_v13_crossing_aerial import MatchEngineV13CrossingAerial
from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_restarts import MatchEngineV13Restarts
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds


class DuelAndBoxTests(unittest.TestCase):
    def engine(self, seed=811):
        return MatchEngineV13KeeperCrosses(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    @staticmethod
    def ctx(pressure=0.50, space=0.54):
        return {
            "pressure": pressure,
            "space": space,
            "space_behind": 0.48,
            "support": 0.58,
            "defensive_quality": 0.56,
        }

    def outfielder(self, e, team=0):
        return next(ps for ps in e.teams[team].on_field if ps.player.position.upper() not in {"GK", "CB"})

    def defender(self, e, team=1):
        return next(ps for ps in e.teams[team].on_field if ps.player.position.upper() in {"CB", "LB", "RB", "DM"})

    def test_layer_order_and_canonical_entrypoint(self):
        self.assertTrue(issubclass(MatchEngineV13AdvancedDribbling, MatchEngineV13SpaceManipulation))
        self.assertTrue(issubclass(MatchEngineV13OneVOne, MatchEngineV13AdvancedDribbling))
        self.assertTrue(issubclass(MatchEngineV13BoxMovement, MatchEngineV13OneVOne))
        self.assertTrue(issubclass(MatchEngineV13CrossingAerial, MatchEngineV13BoxMovement))
        self.assertTrue(issubclass(MatchEngineV13KeeperCrosses, MatchEngineV13CrossingAerial))
        self.assertTrue(issubclass(MatchEngineV13Restarts, MatchEngineV13KeeperCrosses))
        self.assertTrue(issubclass(MatchEngineV13Rebounds, MatchEngineV13Restarts))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13Rebounds))

    def test_advanced_dribble_responds_to_real_matchup(self):
        e = self.engine()
        a, d = self.outfielder(e, 0), self.defender(e, 1)
        zone = Zone(Band.ATT, Lane.LEFT)
        for attr in ("dribbling", "technique", "pace", "composure", "strength"):
            setattr(a.player, attr, 94)
        for attr in ("tackling", "positioning", "pace", "strength", "anticipation"):
            setattr(d.player, attr, 50)
        high = e.dribble_move_diagnostic(a, d, zone, self.ctx(0.40, 0.68))
        for attr in ("dribbling", "technique", "pace", "composure", "strength"):
            setattr(a.player, attr, 50)
        for attr in ("tackling", "positioning", "pace", "strength", "anticipation"):
            setattr(d.player, attr, 94)
        low = e.dribble_move_diagnostic(a, d, zone, self.ctx(0.65, 0.36))
        self.assertGreater(high["attacker_edge"], low["attacker_edge"])
        self.assertIn(high["move"], {"shield_turn", "acceleration", "outside_touch", "body_cut", "stop_go", "step_over"})

    def test_two_footed_attacker_is_not_given_fake_weak_foot(self):
        e = self.engine(seed=813)
        a, d = self.outfielder(e, 0), self.defender(e, 1)
        a.player.preferred_foot = "BOTH"
        diag = e.one_v_one_defense_diagnostic(d, a, Zone(Band.ATT, Lane.CENTER), self.ctx())
        self.assertFalse(diag["can_show_weak_foot"])
        self.assertNotEqual(diag["stance"], "show_weak_foot")
        self.assertIsNone(diag["weak_side"])

    def test_box_movement_selects_real_runner(self):
        e = self.engine(seed=817)
        crosser = self.outfielder(e, 0)
        diag = e.box_movement_diagnostic(0, crosser, Zone(Band.ATT, Lane.RIGHT), "cross", self.ctx(0.38, 0.66))
        self.assertIsNotNone(diag["target"])
        self.assertNotEqual(diag["target"], crosser.player.name)
        self.assertIn(diag["run_type"], {"near_post", "far_post", "blindside", "penalty_spot"})
        self.assertGreater(diag["candidate_count"], 0)

    def test_cross_delivery_uses_crosser_quality(self):
        e = self.engine(seed=821)
        crosser = self.outfielder(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != crosser.player.name and ps.player.position.upper() != "GK")
        zone = Zone(Band.ATT, Lane.LEFT)
        for attr in ("crossing", "technique", "vision", "composure"):
            setattr(crosser.player, attr, 95)
        high = e.cross_delivery_diagnostic(crosser, target, zone, "cross", self.ctx(0.34, 0.62))
        for attr in ("crossing", "technique", "vision", "composure"):
            setattr(crosser.player, attr, 45)
        low = e.cross_delivery_diagnostic(crosser, target, zone, "cross", self.ctx(0.70, 0.40))
        self.assertGreater(high["delivery_quality"], low["delivery_quality"])

    def test_aerial_duel_is_not_heading_alone(self):
        e = self.engine(seed=823)
        a, d = self.outfielder(e, 0), self.defender(e, 1)
        for attr in ("heading", "strength", "anticipation", "off_ball"):
            setattr(a.player, attr, 94)
        for attr in ("heading", "strength", "anticipation", "positioning"):
            setattr(d.player, attr, 48)
        high = e.aerial_duel_diagnostic(a, d, 0.78)
        for attr in ("heading", "strength", "anticipation", "off_ball"):
            setattr(a.player, attr, 48)
        for attr in ("heading", "strength", "anticipation", "positioning"):
            setattr(d.player, attr, 94)
        low = e.aerial_duel_diagnostic(a, d, 0.42)
        self.assertGreater(high["attacker_edge"], low["attacker_edge"])

    def test_keeper_cross_command_uses_existing_keeper_attributes(self):
        e = self.engine(seed=827)
        attacker = self.outfielder(e, 0)
        defender = self.defender(e, 1)
        keeper = next(ps for ps in e.teams[1].on_field if ps.player.position.upper() == "GK")
        p = PendingAction(0, attacker.player.name, "shoot", Zone(Band.BOX, Lane.CENTER), danger=0.58, pressure=0.46, defender=defender.player.name, origin="cross", body_part="head")
        for attr in ("handling", "gk_positioning", "reflexes", "strength", "anticipation"):
            setattr(keeper.player, attr, 94)
        high = e.keeper_cross_diagnostic(keeper, p, attacker, cross_context={"cross_type": "whipped"})
        for attr in ("handling", "gk_positioning", "reflexes", "strength", "anticipation"):
            setattr(keeper.player, attr, 45)
        low = e.keeper_cross_diagnostic(keeper, p, attacker, cross_context={"cross_type": "whipped"})
        self.assertGreater(high["command_score"], low["command_score"])
        self.assertGreater(high["success_probability"], low["success_probability"])

    def test_cross_context_survives_save_load(self):
        e = self.engine(seed=829)
        e._v13_cross_context = {
            "team": 0,
            "origin": "cross",
            "target": "Runner",
            "crosser": "Creator",
            "cross_type": "whipped",
            "aerial": True,
            "delivery_quality": 0.73,
            "until_resolution": True,
        }
        clone = MatchEngineV13KeeperCrosses.from_json(e.export_json())
        self.assertEqual(clone._v13_cross_context["cross_type"], "whipped")
        self.assertAlmostEqual(clone._v13_cross_context["delivery_quality"], 0.73)

    def test_same_seed_remains_deterministic(self):
        a, b = self.engine(seed=839), self.engine(seed=839)
        out_a, out_b = [], []
        for _ in range(24):
            ea, eb = a.step(), b.step()
            out_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            out_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(out_a, out_b)

    def test_save_load_continuation_remains_deterministic(self):
        e = self.engine(seed=841)
        for _ in range(14):
            e.step()
        clone = MatchEngineV13KeeperCrosses.from_json(e.export_json())
        out_a, out_b = [], []
        for _ in range(10):
            ea, eb = e.step(), clone.step()
            out_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            out_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(out_a, out_b)


if __name__ == "__main__":
    unittest.main()
