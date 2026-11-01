from __future__ import annotations

import unittest

from engine import MatchConfig, make_generic_team
from competition_state_v13 import TournamentStateV13
from engine_experiment_v13_tournament import MatchEngineV13TournamentContext
from team_loader_v13 import load_team_v13
from tournament_runner_v13 import TournamentMatchSessionV13


class CompleteCompetitionTests(unittest.TestCase):
    def test_two_leg_final_uses_aggregate_not_second_leg_winner(self):
        t = TournamentStateV13(
            competition_id="two_leg_final",
            teams=["A", "B"],
            stages={"final": {"kind": "final", "two_legged": True}},
            fixtures=[
                {"id": "f1", "stage_id": "final", "home": "A", "away": "B", "status": "final", "score": [3, 0], "winner": "A", "leg": 1, "tie_id": "F"},
                {"id": "f2", "stage_id": "final", "home": "B", "away": "A", "status": "final", "score": [1, 0], "winner": "B", "leg": 2, "tie_id": "F"},
            ],
        )
        resolution = t.tie_resolution("F")
        self.assertEqual(resolution["winner"], "A")
        self.assertEqual(resolution["decided_by"], "aggregate")
        self.assertEqual(t.competition_status()["champion"], "A")

    def test_two_leg_promotion_playoff_promotes_tie_winner_only(self):
        t = TournamentStateV13(
            competition_id="promotion_playoff",
            teams=["A", "B"],
            stages={"po": {"kind": "playoff", "two_legged": True, "promotion_on_win": True}},
            fixtures=[
                {"id": "p1", "stage_id": "po", "home": "A", "away": "B", "status": "final", "score": [0, 2], "leg": 1, "tie_id": "P"},
                {"id": "p2", "stage_id": "po", "home": "B", "away": "A", "status": "final", "score": [0, 1], "leg": 2, "tie_id": "P"},
            ],
        )
        self.assertEqual(t.tie_resolution("P")["winner"], "B")
        self.assertEqual(t.competition_status()["promoted"], ["B"])

    def test_aggregate_tie_waits_for_explicit_decider(self):
        t = TournamentStateV13(
            competition_id="penalty_final",
            teams=["A", "B"],
            stages={"final": {"kind": "final", "two_legged": True, "away_goals": False}},
            fixtures=[
                {"id": "f1", "stage_id": "final", "home": "A", "away": "B", "status": "final", "score": [1, 0], "leg": 1, "tie_id": "F"},
                {"id": "f2", "stage_id": "final", "home": "B", "away": "A", "status": "final", "score": [1, 0], "leg": 2, "tie_id": "F"},
            ],
        )
        unresolved = t.competition_status()
        self.assertIsNone(unresolved["champion"])
        self.assertEqual(unresolved["unresolved_ties"], ["F"])
        t.record_tie_winner("F", "B", decided_by="penalties")
        resolved = t.competition_status()
        self.assertEqual(resolved["champion"], "B")
        self.assertEqual(resolved["unresolved_ties"], [])
        self.assertEqual(t.tie_resolution("F")["decided_by"], "penalties")

    def engine(self, context, seed=10701):
        return MatchEngineV13TournamentContext(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=1201),
            seed=seed,
            config=MatchConfig(allow_extra_time=True),
            tournament_context=context,
        )

    @staticmethod
    def knockout_context(aggregate_diff: int):
        return {
            "version": 1,
            "competition_id": "cup",
            "fixture_id": "leg2",
            "stage_id": "sf",
            "stage_kind": "knockout",
            "knowledge_policy": "only_final_or_currently_live_results_are_visible",
            "team_context": {
                "0": {"aggregate_diff": aggregate_diff, "two_legged": True, "decisive_leg": True, "need_goal": 0.0, "protect_result": 0.0},
                "1": {"aggregate_diff": -aggregate_diff, "two_legged": True, "decisive_leg": True, "need_goal": 0.0, "protect_result": 0.0},
            },
        }

    def test_tied_aggregate_starts_extra_time_even_if_second_leg_is_not_drawn(self):
        e = self.engine(self.knockout_context(0), 10703)
        e.stats[0].goals, e.stats[1].goals = 2, 0
        e.state.second = 90.0 * 60.0
        e.state.period_index = 1
        event = e._check_period_boundary()
        self.assertEqual(event.text_key, "regulation_end_tied")
        self.assertEqual(e.state.period_markers, [105, 120])

    def test_non_tied_aggregate_does_not_start_extra_time_for_drawn_leg(self):
        e = self.engine(self.knockout_context(1), 10705)
        e.stats[0].goals, e.stats[1].goals = 1, 1
        e.state.second = 90.0 * 60.0
        e.state.period_index = 1
        event = e._check_period_boundary()
        self.assertIsNotNone(event)
        self.assertNotEqual(event.text_key, "regulation_end_tied")
        self.assertEqual(e.state.period_markers, [45, 90])

    def test_tournament_session_starts_live_but_does_not_presimulate(self):
        t = TournamentStateV13(
            competition_id="live_group",
            teams=["amiguinhos_u21", "flamengo_u21", "river_plate_u21", "bayern_u21"],
            stages={"g": {"kind": "group", "qualify_positions": [1, 2]}},
            fixtures=[
                {"id": "main", "stage_id": "g", "home": "amiguinhos_u21", "away": "flamengo_u21", "status": "scheduled", "simultaneous_key": "r3"},
                {"id": "other", "stage_id": "g", "home": "river_plate_u21", "away": "bayern_u21", "status": "scheduled", "simultaneous_key": "r3"},
            ],
        )
        session = TournamentMatchSessionV13(t, "main", seed=10707)
        self.assertTrue(session.pristine)
        self.assertEqual(t.fixture("main")["status"], "live")
        self.assertEqual(session.engine.minute, 0.0)
        self.assertEqual(session.engine.state.event_log, [])
        session.update_simultaneous("other", 1, 0, 12.0)
        self.assertEqual(session.engine.minute, 0.0)
        self.assertEqual(session.engine.state.event_log, [])
        self.assertEqual(session.snapshot()["competition"]["simultaneous"][0]["score"], [1, 0])

    def test_tournament_session_roundtrip_preserves_match_and_competition(self):
        t = TournamentStateV13(
            competition_id="live_final",
            teams=["amiguinhos_u21", "flamengo_u21"],
            stages={"f": {"kind": "final", "allow_extra_time": True}},
            fixtures=[
                {"id": "final", "stage_id": "f", "home": "amiguinhos_u21", "away": "flamengo_u21", "status": "scheduled"},
            ],
        )
        session = TournamentMatchSessionV13(t, "final", seed=10709)
        event = session.press_p()
        restored = TournamentMatchSessionV13.from_json(session.export_json())
        self.assertEqual(session.engine.export_state(), restored.engine.export_state())
        self.assertEqual(session.tournament.to_dict(), restored.tournament.to_dict())
        self.assertEqual(session.pre_match_conditions, restored.pre_match_conditions)
        self.assertIsNotNone(event)


if __name__ == "__main__":
    unittest.main()
