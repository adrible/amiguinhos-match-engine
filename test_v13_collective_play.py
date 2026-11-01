from __future__ import annotations

import unittest

from engine import Band, EventType, Lane, Zone, make_generic_team
from engine_experiment_v13_collective import MatchEngineV13Collective
from engine_experiment_v13_combinations import MatchEngineV13Combinations
from engine_experiment_v13_runs import MatchEngineV13Runs
from engine_experiment_v13_thirdman import MatchEngineV13ThirdMan
from engine_experiment_v13_pressing_triggers import MatchEngineV13PressingTriggers
from engine_experiment_v13_duels import MatchEngineV13Duels


class CollectivePlayTests(unittest.TestCase):
    def engine(self, seed=303):
        return MatchEngineV13Collective(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def actor(self, e, team=0):
        return next(ps for ps in e.teams[team].on_field if ps.player.position not in {"GK", "CB"})

    def ctx(self, pressure=0.42, space=0.58):
        return {
            "pressure": pressure,
            "space": space,
            "space_behind": 0.56,
            "support": 0.60,
            "defensive_quality": 0.55,
        }

    def test_layer_order(self):
        self.assertTrue(issubclass(MatchEngineV13Runs, MatchEngineV13Combinations))
        self.assertTrue(issubclass(MatchEngineV13ThirdMan, MatchEngineV13Runs))
        self.assertTrue(issubclass(MatchEngineV13PressingTriggers, MatchEngineV13ThirdMan))
        self.assertTrue(issubclass(MatchEngineV13Duels, MatchEngineV13PressingTriggers))
        self.assertTrue(issubclass(MatchEngineV13Collective, MatchEngineV13Duels))

    def test_quick_combination_memory_and_roundtrip(self):
        e = self.engine()
        a = self.actor(e)
        b = next(ps for ps in e.teams[0].on_field if ps.player.name != a.player.name and ps.player.position != "GK")
        e._v13_combination_history = [{
            "team": 0,
            "actor": a.player.name,
            "target": b.player.name,
            "second": e.state.second,
            "kind": "safe_pass",
            "first_time": False,
        }]
        diag = e.quick_combination_diagnostic(b, 0)
        self.assertTrue(diag["active"])
        self.assertEqual(diag["return_target"], a.player.name)
        clone = MatchEngineV13Collective.from_json(e.export_json())
        self.assertEqual(clone._v13_combination_history, e._v13_combination_history)

    def test_run_diagnostic_finds_space_runner(self):
        e = self.engine()
        a = self.actor(e)
        d = e.run_diagnostic(0, a, Zone(Band.ATT, Lane.LEFT), self.ctx())
        self.assertTrue(d["runner"])
        self.assertIn(d["run_type"], {"overlap", "underlap", "diagonal", "depth", "third_line", "support"})
        self.assertGreater(d["pass_into_space_probability"], 0.0)

    def test_third_man_diagnostic_excludes_originator_and_connector(self):
        e = self.engine()
        players = [ps for ps in e.teams[0].on_field if ps.player.position != "GK"]
        a, b = players[0], players[1]
        e._v13_combination_history = [{
            "team": 0,
            "actor": a.player.name,
            "target": b.player.name,
            "second": e.state.second,
            "kind": "progressive_pass",
            "first_time": False,
        }]
        d = e.third_man_diagnostic(0, b.player.name)
        self.assertTrue(d["candidate"])
        self.assertNotIn(d["candidate"], {a.player.name, b.player.name})

    def test_pressing_trigger_has_depth_tradeoff(self):
        e = self.engine()
        e.teams[1].team.tactics.pressing = 0.85
        e._emit(EventType.INFO, 0, 0, "safe_pass", actor="A", target="B", first_touch="heavy")
        d = e.pressing_trigger_diagnostic(0, Zone(Band.MID, Lane.CENTER))
        self.assertTrue(d["active"])
        self.assertEqual(d["trigger"], "heavy_touch")
        self.assertGreater(d["pressure_delta"], 0.0)
        self.assertGreater(d["depth_tradeoff"], 0.0)

    def test_steering_does_not_treat_both_as_weak_foot(self):
        e = self.engine()
        a = self.actor(e)
        a.player.preferred_foot = "BOTH"
        d = e.steering_diagnostic(a, Zone(Band.ATT, Lane.RIGHT), self.ctx())
        self.assertNotEqual(d["intent"], "weak_foot")

    def test_protection_responds_to_strength_and_pressure(self):
        e = self.engine()
        a = self.actor(e)
        a.player.strength = 95
        high = e.protection_diagnostic(a, Zone(Band.ATT, Lane.CENTER), self.ctx(0.75, 0.35))
        a.player.strength = 45
        low = e.protection_diagnostic(a, Zone(Band.ATT, Lane.CENTER), self.ctx(0.20, 0.75))
        self.assertGreater(high["score"], low["score"])

    def test_rapid_chain_shortens_clock_without_zero_time(self):
        e = self.engine()
        names = [ps.player.name for ps in e.teams[0].on_field if ps.player.position != "GK"][:4]
        e._v13_combination_history = [
            {"team": 0, "actor": names[0], "target": names[1], "second": 100.0, "kind": "safe_pass", "first_time": True},
            {"team": 0, "actor": names[1], "target": names[2], "second": 104.0, "kind": "progressive_pass", "first_time": True},
            {"team": 0, "actor": names[2], "target": names[3], "second": 108.0, "kind": "safe_pass", "first_time": False},
        ]
        e.state.second = 108.0
        e.state.possession = 0
        e._v13_current_open_actor = names[3]
        scale = e.combination_clock_scale(0)
        self.assertGreater(scale, 0.20)
        self.assertLess(scale, 0.50)

    def test_no_new_numeric_player_attributes(self):
        e = self.engine()
        a = self.actor(e)
        self.assertFalse(hasattr(a.player, "first_touch"))
        self.assertFalse(hasattr(a.player, "combination"))
        self.assertFalse(hasattr(a.player, "pressing_trigger"))

    def test_generic_smoke_is_deterministic(self):
        a = self.engine(seed=909)
        b = self.engine(seed=909)
        sig_a, sig_b = [], []
        for _ in range(30):
            ea = a.step()
            eb = b.step()
            sig_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            sig_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(sig_a, sig_b)

    def test_save_load_continuation_is_deterministic(self):
        e = self.engine(seed=777)
        for _ in range(18):
            e.step()
        clone = MatchEngineV13Collective.from_json(e.export_json())
        out1, out2 = [], []
        for _ in range(12):
            a = e.step()
            b = clone.step()
            out1.append((a.minute, a.type.value, a.text_key, a.team, a.data))
            out2.append((b.minute, b.type.value, b.text_key, b.team, b.data))
        self.assertEqual(out1, out2)


if __name__ == "__main__":
    unittest.main()
