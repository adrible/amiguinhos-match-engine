from __future__ import annotations

import unittest

from engine import EventType, MID_C, make_generic_team
from engine_experiment_v13 import MatchEngine


class KickoffV13Tests(unittest.TestCase):
    def engine(self, seed=8101):
        return MatchEngine(
            make_generic_team("Home", 80, "balanced", seed=101),
            make_generic_team("Away", 80, "balanced", seed=202),
            seed=seed,
        )

    def test_new_match_remains_pristine_until_first_step(self):
        e = self.engine()
        self.assertEqual(e.minute, 0.0)
        self.assertEqual(e.state.event_log, [])
        self.assertIsNone(e.state.pending)
        self.assertIsNone(e.state.restart)
        self.assertEqual(e.state.zone, MID_C)
        self.assertEqual(sum(st.shots for st in e.stats), 0)

    def test_first_step_resolves_contextual_kickoff_without_presimulating_chance(self):
        e = self.engine(seed=8103)
        kickoff_team = e.state.kickoff_team
        event = e.step()
        self.assertEqual(event.data["kickoff_team"], kickoff_team)
        self.assertIn(
            event.data["pattern"],
            {"short_recycle", "wide_release", "vertical_probe", "direct_launch"},
        )
        self.assertIn(
            event.text_key,
            {
                "kickoff_short_recycle",
                "kickoff_wide_release",
                "kickoff_vertical_probe",
                "kickoff_direct_launch",
                "kickoff_turnover",
            },
        )
        self.assertGreater(e.state.second, 0.0)
        self.assertIsNone(e.state.pending)
        self.assertEqual(sum(st.shots for st in e.stats), 0)
        self.assertEqual(sum(st.goals for st in e.stats), 0)

    def test_directness_changes_plan_weights_without_forcing_outcome(self):
        e = self.engine(seed=8105)
        team = e.state.kickoff_team
        e.set_tactics(team, directness=0.05, risk=0.25, counter=0.35)
        patient = e.kickoff_plan_diagnostic(team)
        e.set_tactics(team, directness=0.95, risk=0.70, counter=0.80)
        direct = e.kickoff_plan_diagnostic(team)
        self.assertGreater(
            direct["weights"]["direct_launch"],
            patient["weights"]["direct_launch"],
        )
        self.assertLess(
            direct["weights"]["short_recycle"],
            patient["weights"]["short_recycle"],
        )

    def test_score_and_minute_shift_kickoff_intent(self):
        e = self.engine(seed=8107)
        team = 0
        e.state.second = 82.0 * 60.0
        e.stats[0].goals = 0
        e.stats[1].goals = 1
        chasing = e.kickoff_plan_diagnostic(team)
        e.stats[0].goals = 2
        e.stats[1].goals = 1
        protecting = e.kickoff_plan_diagnostic(team)
        chase_attack = chasing["weights"]["vertical_probe"] + chasing["weights"]["direct_launch"]
        protect_attack = protecting["weights"]["vertical_probe"] + protecting["weights"]["direct_launch"]
        self.assertGreater(chase_attack, protect_attack)
        self.assertGreater(
            protecting["weights"]["short_recycle"],
            chasing["weights"]["short_recycle"],
        )

    def test_after_goal_kickoff_belongs_to_conceding_team(self):
        e = self.engine(seed=8109)
        e.state.event_log.clear()
        e.state.second = 31.0 * 60.0
        e.stats[0].goals = 1
        e.state.restart = "kickoff"
        e.state.restart_team = 1
        e.state.restart_zone = MID_C
        e.state.possession = 1
        e._emit(EventType.GOAL, 0, 5, "goal", scorer="Home scorer")
        event = e.step()
        self.assertEqual(event.data["kickoff_team"], 1)
        self.assertEqual(event.data["reason"], "after_goal")
        self.assertGreater(e.minute, 31.0)

    def test_halftime_arms_real_kickoff_for_other_team(self):
        e = self.engine(seed=8111)
        e.step()
        e.state.pending = None
        e.state.restart = None
        e.state.second = 45.0 * 60.0
        boundary = e.step()
        self.assertEqual(boundary.type, EventType.PERIOD_END)
        self.assertEqual(e.state.restart, "kickoff")
        self.assertEqual(e.state.restart_team, 1 - e.state.kickoff_team)
        restart = e.step()
        self.assertEqual(restart.data["kickoff_team"], 1 - e.state.kickoff_team)
        self.assertEqual(restart.data["reason"], "period_restart")

    def test_initial_kickoff_roundtrip_is_deterministic(self):
        e = self.engine(seed=8113)
        clone = MatchEngine.from_json(e.export_json())
        a = e.step()
        b = clone.step()
        self.assertEqual(
            (a.minute, a.type, a.team, a.relevance, a.text_key, a.data),
            (b.minute, b.type, b.team, b.relevance, b.text_key, b.data),
        )
        self.assertEqual(e.export_state(), clone.export_state())

    def test_same_seed_same_kickoff(self):
        a = self.engine(seed=8115)
        b = self.engine(seed=8115)
        ea, eb = a.step(), b.step()
        self.assertEqual(
            (ea.minute, ea.type, ea.team, ea.text_key, ea.data),
            (eb.minute, eb.type, eb.team, eb.text_key, eb.data),
        )


if __name__ == "__main__":
    unittest.main()
