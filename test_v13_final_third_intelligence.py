from __future__ import annotations

import unittest
from unittest.mock import patch

from engine import Band, Lane, PendingAction, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_crossing_aerial import MatchEngineV13CrossingAerial
from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_finishing import MatchEngineV13AdvancedFinishing
from engine_experiment_v13_shot_preparation import MatchEngineV13ShotPreparation
from engine_experiment_v13_passing_lanes import MatchEngineV13PassingLanes
from engine_experiment_v13_line_breaking import MatchEngineV13LineBreaking
from engine_experiment_v13_pressing_traps import MatchEngineV13PressingTraps
from engine_experiment_v13_quick_free_kick import MatchEngineV13QuickFreeKick


class FinalThirdIntelligenceTests(unittest.TestCase):
    def engine(self, seed=907):
        return MatchEngineV13KeeperCrosses(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    @staticmethod
    def ctx(pressure=0.46, space=0.56):
        return {
            "pressure": pressure,
            "space": space,
            "space_behind": 0.52,
            "support": 0.58,
            "defensive_quality": 0.56,
        }

    def attacker(self, e, team=0):
        return next(
            ps for ps in e.teams[team].on_field
            if ps.player.position.upper() in {"ST", "AM", "LW", "RW", "CM"}
        )

    def defender(self, e, team=1):
        return next(
            ps for ps in e.teams[team].on_field
            if ps.player.position.upper() in {"CB", "LB", "RB", "DM"}
        )

    def test_layer_order_and_canonical_entrypoint(self):
        self.assertTrue(issubclass(MatchEngineV13AdvancedFinishing, MatchEngineV13CrossingAerial))
        self.assertTrue(issubclass(MatchEngineV13ShotPreparation, MatchEngineV13AdvancedFinishing))
        self.assertTrue(issubclass(MatchEngineV13PassingLanes, MatchEngineV13ShotPreparation))
        self.assertTrue(issubclass(MatchEngineV13LineBreaking, MatchEngineV13PassingLanes))
        self.assertTrue(issubclass(MatchEngineV13PressingTraps, MatchEngineV13LineBreaking))
        self.assertTrue(issubclass(MatchEngineV13QuickFreeKick, MatchEngineV13PressingTraps))
        self.assertTrue(issubclass(MatchEngineV13KeeperCrosses, MatchEngineV13QuickFreeKick))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13KeeperCrosses)

    def test_finishing_uses_shooter_and_keeper_context(self):
        e = self.engine()
        shooter = self.attacker(e, 0)
        defender = self.defender(e, 1)
        keeper = e._goalkeeper(1)
        p = PendingAction(
            0, shooter.player.name, "shoot", Zone(Band.BOX, Lane.CENTER),
            danger=0.66, pressure=0.38, defender=defender.player.name,
            origin="through_ball", body_part="foot",
        )
        for attr in ("finishing", "technique", "composure", "long_shots"):
            setattr(shooter.player, attr, 94)
        for attr in ("gk_positioning", "one_on_one"):
            setattr(keeper.player, attr, 50)
        high = e.shot_selection_diagnostic(shooter, p, keeper)
        for attr in ("finishing", "technique", "composure", "long_shots"):
            setattr(shooter.player, attr, 48)
        for attr in ("gk_positioning", "one_on_one"):
            setattr(keeper.player, attr, 94)
        low = e.shot_selection_diagnostic(shooter, p, keeper)
        self.assertGreater(high["execution_quality"], low["execution_quality"])
        self.assertGreater(high["keeper_difficulty"], low["keeper_difficulty"])

    def test_shot_preparation_creates_block_window_tradeoff(self):
        e = self.engine(seed=911)
        shooter = self.attacker(e, 0)
        defender = self.defender(e, 1)
        p_low = PendingAction(0, shooter.player.name, "shoot", Zone(Band.BOX, Lane.CENTER), danger=0.62, pressure=0.28, defender=defender.player.name, origin="cutback")
        p_high = PendingAction(0, shooter.player.name, "shoot", Zone(Band.BOX, Lane.CENTER), danger=0.62, pressure=0.82, defender=defender.player.name, origin="open_play")
        low = e.shot_preparation_diagnostic(shooter, p_low)
        high = e.shot_preparation_diagnostic(shooter, p_high)
        self.assertGreaterEqual(high["block_window"], low["block_window"])
        self.assertGreater(high["seconds"], 0.0)

    def test_passing_lane_closes_against_better_readers(self):
        e = self.engine(seed=919)
        actor = self.attacker(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != actor.player.name and ps.player.position.upper() != "GK")
        defenders = [ps for ps in e.teams[1].on_field if ps.player.position.upper() != "GK"]
        zone = Zone(Band.MID, Lane.CENTER)
        for d in defenders:
            for attr in ("positioning", "anticipation", "pace", "tackling"):
                setattr(d.player, attr, 94)
        closed = e.passing_lane_diagnostic(0, actor, target, zone, "progressive_pass", self.ctx())
        for d in defenders:
            for attr in ("positioning", "anticipation", "pace", "tackling"):
                setattr(d.player, attr, 45)
        open_lane = e.passing_lane_diagnostic(0, actor, target, zone, "progressive_pass", self.ctx())
        self.assertGreater(closed["interception_risk"], open_lane["interception_risk"])
        self.assertLess(closed["openness"], open_lane["openness"])

    def test_line_breaking_rewards_real_creator_and_runner_quality(self):
        e = self.engine(seed=929)
        actor = self.attacker(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != actor.player.name and ps.player.position.upper() != "GK")
        zone = Zone(Band.ATT, Lane.CENTER)
        for attr in ("passing", "vision", "technique"):
            setattr(actor.player, attr, 94)
        for attr in ("off_ball", "anticipation", "pace"):
            setattr(target.player, attr, 94)
        high = e.line_break_diagnostic(0, actor, target, zone, "through_ball", {**self.ctx(0.34, 0.68), "passing_lane_openness": 0.76})
        for attr in ("passing", "vision", "technique"):
            setattr(actor.player, attr, 48)
        for attr in ("off_ball", "anticipation", "pace"):
            setattr(target.player, attr, 48)
        low = e.line_break_diagnostic(0, actor, target, zone, "through_ball", {**self.ctx(0.72, 0.34), "passing_lane_openness": 0.30})
        self.assertGreater(high["score"], low["score"])
        self.assertGreaterEqual(high["lines_broken"], low["lines_broken"])
        self.assertGreater(high["advantage_created"], low["advantage_created"])

    def test_pressing_trap_has_depth_tradeoff(self):
        e = self.engine(seed=937)
        zone = Zone(Band.MID, Lane.CENTER)
        state = e.rng.getstate()
        baseline = MatchEngineV13LineBreaking._spatial_context(e, 0, zone)
        e.rng.setstate(state)
        forced = {"active": True, "trap_score": 0.80, "activation_probability": 0.30, "bait_lane": "left", "mid_block": False, "mid_block_score": 0.60, "defensive_reading": 0.78}
        with patch.object(e, "pressing_trap_diagnostic", return_value=forced):
            trapped = e._spatial_context(0, zone)
        self.assertGreater(trapped["pressure"], baseline["pressure"])
        self.assertGreater(trapped["space_behind"], baseline["space_behind"])

    def test_mid_block_protects_center(self):
        e = self.engine(seed=941)
        zone = Zone(Band.MID, Lane.CENTER)
        forced = {"active": False, "trap_score": 0.55, "activation_probability": 0.20, "bait_lane": "right", "mid_block": True, "mid_block_score": 0.72, "defensive_reading": 0.74}
        state = e.rng.getstate()
        baseline = MatchEngineV13LineBreaking._spatial_context(e, 0, zone)
        e.rng.setstate(state)
        with patch.object(e, "pressing_trap_diagnostic", return_value=forced):
            mid = e._spatial_context(0, zone)
        self.assertLess(mid["space"], baseline["space"])
        self.assertTrue(mid["mid_block"])

    def test_quick_free_kick_can_create_immediate_play(self):
        e = self.engine(seed=947)
        e.state.restart = "free_kick"
        e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.MID, Lane.RIGHT)
        forced = {"active": True, "advantage": 0.78, "attempt_probability": 0.38, "target_quality": 0.82, "referee_busy": False, "direct_shot_zone": False}
        with patch.object(e, "quick_free_kick_diagnostic", return_value=forced):
            event = e._resolve_restart()
        self.assertTrue(event.data.get("quick_free_kick"))
        self.assertIsNone(e.state.restart)

    def test_quick_free_kick_waits_if_referee_has_pending_business(self):
        e = self.engine(seed=953)
        taker = self.attacker(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != taker.player.name and ps.player.position.upper() != "GK")
        e._review_queue = [{"kind": "dummy_review"}]
        diag = e.quick_free_kick_diagnostic(0, Zone(Band.MID, Lane.CENTER), taker, target)
        self.assertFalse(diag["active"])
        self.assertTrue(diag["referee_busy"])

    def test_no_new_numeric_player_attributes(self):
        e = self.engine(seed=959)
        p = self.attacker(e, 0)
        for name in ("shot_type", "finishing_style", "line_breaking", "pressing_trap", "quick_free_kick"):
            self.assertFalse(hasattr(p.player, name))

    def test_same_seed_remains_deterministic(self):
        a, b = self.engine(seed=967), self.engine(seed=967)
        out_a, out_b = [], []
        for _ in range(22):
            ea, eb = a.step(), b.step()
            out_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            out_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(out_a, out_b)

    def test_save_load_continuation_remains_deterministic(self):
        e = self.engine(seed=971)
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
