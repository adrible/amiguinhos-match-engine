from __future__ import annotations

import unittest

from engine import Band, DEF_C, EventType, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine
from engine_experiment_v13_restarts import MatchEngineV13Restarts


class RestartIntelligenceTests(unittest.TestCase):
    def engine(self, seed=8201):
        return MatchEngine(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def test_canonical_engine_contains_restart_layer(self):
        self.assertTrue(issubclass(MatchEngine, MatchEngineV13Restarts))

    def test_goal_kick_can_be_armed_without_creating_a_chance(self):
        e = self.engine()
        e._arm_goal_kick(1)
        self.assertEqual(e.state.restart, "goal_kick")
        self.assertEqual(e.state.restart_team, 1)
        self.assertEqual(e.state.possession, 1)
        self.assertEqual(e.state.zone, DEF_C)
        self.assertIsNone(e.state.pending)

    def test_directness_and_press_shift_goal_kick_preferences(self):
        e = self.engine(seed=8203)
        e.set_tactics(0, directness=0.05, counter=0.30)
        e.set_tactics(1, pressing=0.20, defensive_line=0.35)
        patient = e.goal_kick_plan_diagnostic(0)
        e.set_tactics(0, directness=0.95, counter=0.85)
        e.set_tactics(1, pressing=0.90, defensive_line=0.80)
        direct = e.goal_kick_plan_diagnostic(0)
        self.assertGreater(direct["weights"]["long_target"], patient["weights"]["long_target"])
        self.assertLess(direct["weights"]["short_build"], patient["weights"]["short_build"])

    def test_goal_kick_resolution_is_contextual_and_consumes_time(self):
        e = self.engine(seed=8205)
        e.state.event_log.append(e._emit(EventType.MISS, 1, 2, "shot_missed"))
        e._arm_goal_kick(0)
        before = e.state.second
        event = e.step()
        self.assertGreater(e.state.second, before)
        self.assertIn(
            event.text_key,
            {
                "goal_kick_short_build",
                "goal_kick_fullback_release",
                "goal_kick_midfield_clip",
                "goal_kick_long_target",
                "goal_kick_turnover",
            },
        )
        self.assertIsNone(e.state.restart)
        self.assertIsNone(e.state.pending)

    def test_goal_kick_roundtrip_remains_deterministic(self):
        e = self.engine(seed=8207)
        e._arm_goal_kick(0)
        clone = MatchEngine.from_json(e.export_json())
        a, b = e.step(), clone.step()
        self.assertEqual((a.type, a.team, a.text_key, a.data), (b.type, b.team, b.text_key, b.data))
        self.assertEqual(e.export_state(), clone.export_state())

    def test_defensive_free_kick_prefers_retention_over_direct_shot(self):
        e = self.engine(seed=8209)
        diag = e.free_kick_plan_diagnostic(0, Zone(Band.DEF, Lane.CENTER))
        self.assertEqual(diag["weights"]["direct_shot"], 0.0)
        self.assertGreater(diag["weights"]["short_restart"], diag["weights"]["delivery"])

    def test_dangerous_central_free_kick_has_real_shot_option(self):
        e = self.engine(seed=8211)
        diag = e.free_kick_plan_diagnostic(0, Zone(Band.ATT, Lane.CENTER))
        self.assertGreater(diag["weights"]["direct_shot"], 0.0)
        self.assertGreater(diag["weights"]["delivery"], 0.0)

    def test_deliberate_defensive_free_kick_is_not_forced_cross(self):
        e = self.engine(seed=8213)
        e.state.second = 20.0 * 60.0
        e.state.restart = "free_kick"
        e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.DEF, Lane.CENTER)
        e.state.possession = 0
        e.quick_free_kick_diagnostic = lambda *args, **kwargs: {"active": False}
        event = e.step()
        self.assertIn(
            event.text_key,
            {"free_kick_short_restart", "free_kick_short_intercepted", "free_kick_delivery_progression", "free_kick_delivery_lost"},
        )
        self.assertNotEqual(event.text_key, "free_kick_delivery_pending")


if __name__ == "__main__":
    unittest.main()
