from __future__ import annotations

import unittest

from engine import Band, EventType, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_quick_free_kick import MatchEngineV13QuickFreeKick
from engine_experiment_v13_tactical_memory import MatchEngineV13TacticalMemory
from engine_experiment_v13_individual_adaptation import MatchEngineV13IndividualAdaptation
from engine_experiment_v13_player_habits import MatchEngineV13PlayerHabits
from engine_experiment_v13_tempo_control import MatchEngineV13TempoControl
from engine_experiment_v13_transition_choice import MatchEngineV13TransitionChoice
from engine_experiment_v13_keeper_crosses import MatchEngineV13KeeperCrosses
from engine_experiment_v13_restarts import MatchEngineV13Restarts
from engine_experiment_v13_rebounds import MatchEngineV13Rebounds
from engine_experiment_v13_injuries import MatchEngineV13Injuries
from engine_experiment_v13_roles import MatchEngineV13Roles


class MatchIntelligenceTests(unittest.TestCase):
    def engine(self, seed=1201):
        return MatchEngineV13KeeperCrosses(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    @staticmethod
    def ctx(pressure=0.46, space=0.56, space_behind=0.48):
        return {
            "pressure": pressure,
            "space": space,
            "space_behind": space_behind,
            "support": 0.58,
            "defensive_quality": 0.55,
        }

    def outfielder(self, e, team=0):
        return next(ps for ps in e.teams[team].on_field if ps.player.position.upper() not in {"GK", "CB"})

    def test_layer_order_and_canonical_entrypoint(self):
        self.assertTrue(issubclass(MatchEngineV13TacticalMemory, MatchEngineV13QuickFreeKick))
        self.assertTrue(issubclass(MatchEngineV13IndividualAdaptation, MatchEngineV13TacticalMemory))
        self.assertTrue(issubclass(MatchEngineV13PlayerHabits, MatchEngineV13IndividualAdaptation))
        self.assertTrue(issubclass(MatchEngineV13TempoControl, MatchEngineV13PlayerHabits))
        self.assertTrue(issubclass(MatchEngineV13TransitionChoice, MatchEngineV13TempoControl))
        self.assertTrue(issubclass(MatchEngineV13KeeperCrosses, MatchEngineV13TransitionChoice))
        self.assertTrue(issubclass(MatchEngineV13Restarts, MatchEngineV13KeeperCrosses))
        self.assertTrue(issubclass(MatchEngineV13Rebounds, MatchEngineV13Restarts))
        self.assertTrue(issubclass(MatchEngineV13Injuries, MatchEngineV13Rebounds))
        self.assertTrue(issubclass(MatchEngineV13Roles, MatchEngineV13Injuries))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13Roles)

    def test_memory_requires_repetition_inside_match(self):
        e = self.engine()
        actor = self.outfielder(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != actor.player.name and ps.player.position.upper() != "GK")
        zone = {"band": "mid", "lane": "center"}
        for i in range(2):
            e.state.second += 45.0
            e._emit(EventType.PROGRESSION, 0, 1, "progression", actor=actor.player.name, target=target.player.name, kind="through_ball", zone=zone)
        early = e.tactical_memory_diagnostic(1, 0, player_name=actor.player.name, pattern="vertical_progression")
        self.assertFalse(early["learned"])
        e.state.second += 45.0
        e._emit(EventType.PROGRESSION, 0, 1, "progression", actor=actor.player.name, target=target.player.name, kind="through_ball", zone=zone)
        learned = e.tactical_memory_diagnostic(1, 0, player_name=actor.player.name, pattern="vertical_progression")
        self.assertTrue(learned["learned"])
        self.assertEqual(learned["sample_count"], 3)

    def test_individual_adaptation_has_depth_tradeoff(self):
        e = self.engine(seed=1203)
        actor = self.outfielder(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != actor.player.name and ps.player.position.upper() != "GK")
        zone_data = {"band": "att", "lane": "center"}
        for _ in range(4):
            e.state.second += 30.0
            e._emit(EventType.DANGER, 0, 2, "danger_created", creator=actor.player.name, receiver=target.player.name, kind="through_ball", zone=zone_data)
        diag = e.individual_adaptation_diagnostic(1, actor, Zone(Band.ATT, Lane.CENTER), "through_ball", self.ctx())
        self.assertTrue(diag["active"])
        self.assertGreater(diag["pressure_delta"], 0.0)
        self.assertGreater(diag["depth_tradeoff"], 0.0)
        self.assertIsNotNone(diag["defender"])

    def test_habits_are_derived_from_existing_attributes(self):
        e = self.engine(seed=1205)
        actor = self.outfielder(e, 0)
        for attr in ("crossing", "vision", "technique", "composure"):
            setattr(actor.player, attr, 94)
        actor.player.position = "RW"
        high = e.player_habit_profile(actor)
        for attr in ("crossing", "vision", "technique", "composure"):
            setattr(actor.player, attr, 48)
        low = e.player_habit_profile(actor)
        self.assertGreater(high["early_cross"], low["early_cross"])
        self.assertFalse(hasattr(actor.player, "early_cross"))
        self.assertFalse(hasattr(actor.player, "carry_first"))

    def test_tempo_accelerates_real_transition(self):
        e = self.engine(seed=1207)
        actor = self.outfielder(e, 0)
        e.state.transition_boost = 0.78
        fast = e.tempo_control_diagnostic(0, actor, Zone(Band.MID, Lane.CENTER), self.ctx(0.35, 0.68, 0.70))
        self.assertEqual(fast["mode"], "accelerate")
        self.assertLess(fast["clock_scale"], 1.0)

    def test_tempo_can_circulate_to_protect_lead(self):
        e = self.engine(seed=1209)
        actor = self.outfielder(e, 0)
        e.stats[0].goals = 2
        e.stats[1].goals = 1
        e.state.second = 80.0 * 60.0
        diag = e.tempo_control_diagnostic(0, actor, Zone(Band.MID, Lane.CENTER), self.ctx())
        self.assertEqual(diag["mode"], "circulate")
        self.assertGreater(diag["clock_scale"], 1.0)

    def test_tempo_marker_survives_roundtrip(self):
        e = self.engine(seed=1210)
        actor = self.outfielder(e, 0)
        zone = Zone(Band.MID, Lane.CENTER)
        e.state.possession = 0
        e.state.zone = zone
        e._v13_current_open_actor = actor.player.name
        e._v13_tempo_marker = {
            "team": 0,
            "actor": actor.player.name,
            "zone": zone,
            "mode": "circulate",
            "strength": 0.75,
            "clock_scale": 1.0675,
            "pressure": 0.46,
            "transition": 0.0,
            "score_diff": 1,
        }
        scale_before = e.combination_clock_scale(0)
        payload = e.export_state()
        self.assertEqual(payload["v13_tempo_marker"]["zone"], {"band": Band.MID.value, "lane": Lane.CENTER.value})

        clone = MatchEngineV13KeeperCrosses.from_json(e.export_json())
        self.assertEqual(clone._v13_tempo_marker, e._v13_tempo_marker)
        clone._v13_current_open_actor = actor.player.name
        self.assertAlmostEqual(clone.combination_clock_scale(0), scale_before)

    def test_transition_choice_reads_rest_defense_and_team_quality(self):
        e = self.engine(seed=1211)
        for ps in e.teams[0].on_field:
            if ps.player.position.upper() != "GK":
                ps.player.pace = 92
                ps.player.off_ball = 92
                ps.player.anticipation = 90
        e.set_tactics(0, counter=0.90, mentality=0.50)
        high = e.transition_choice_diagnostic(0, Zone(Band.MID, Lane.CENTER), 0.82)
        low = e.transition_choice_diagnostic(0, Zone(Band.MID, Lane.CENTER), 0.18)
        self.assertGreater(high["advantage"], low["advantage"])
        self.assertEqual(high["mode"], "counterattack")
        self.assertIn(low["mode"], {"consolidate", "reset"})

    def test_transition_plan_survives_roundtrip(self):
        e = self.engine(seed=1213)
        e._switch_possession(0, Zone(Band.MID, Lane.CENTER), transition=0.72)
        self.assertIsNotNone(e._v13_transition_plan)
        clone = MatchEngineV13KeeperCrosses.from_json(e.export_json())
        self.assertEqual(clone._v13_transition_plan["mode"], e._v13_transition_plan["mode"])
        self.assertAlmostEqual(clone._v13_transition_plan["advantage"], e._v13_transition_plan["advantage"])

    def test_tactical_memory_survives_roundtrip(self):
        e = self.engine(seed=1215)
        actor = self.outfielder(e, 0)
        target = next(ps for ps in e.teams[0].on_field if ps.player.name != actor.player.name and ps.player.position.upper() != "GK")
        e._emit(EventType.PROGRESSION, 0, 1, "progression", actor=actor.player.name, target=target.player.name, kind="switch", zone={"band": "mid", "lane": "left"})
        clone = MatchEngineV13KeeperCrosses.from_json(e.export_json())
        self.assertEqual(clone._v13_tactical_memory, e._v13_tactical_memory)

    def test_same_seed_remains_deterministic(self):
        a, b = self.engine(seed=1217), self.engine(seed=1217)
        sig_a, sig_b = [], []
        for _ in range(24):
            ea, eb = a.step(), b.step()
            sig_a.append((ea.minute, ea.type.value, ea.text_key, ea.team, ea.data))
            sig_b.append((eb.minute, eb.type.value, eb.text_key, eb.team, eb.data))
        self.assertEqual(sig_a, sig_b)

    def test_save_load_continuation_remains_deterministic(self):
        e = self.engine(seed=1219)
        for _ in range(15):
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
