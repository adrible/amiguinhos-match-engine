from __future__ import annotations

import unittest

from tournament_state_v13 import TournamentStateV13


class TournamentStateTests(unittest.TestCase):
    def league(self):
        return TournamentStateV13(
            competition_id="league_demo",
            teams=["A", "B", "C", "D"],
            stages={
                "league": {
                    "kind": "league",
                    "promotion_positions": [1, 2],
                    "relegation_positions": [4],
                    "champion_position": 1,
                }
            },
            fixtures=[
                {"id": "ab", "stage_id": "league", "home": "A", "away": "B", "status": "final", "score": [2, 0]},
                {"id": "ac", "stage_id": "league", "home": "A", "away": "C", "status": "final", "score": [1, 0]},
                {"id": "ad", "stage_id": "league", "home": "A", "away": "D", "status": "final", "score": [3, 0]},
                {"id": "bc", "stage_id": "league", "home": "B", "away": "C", "status": "final", "score": [2, 1]},
                {"id": "bd", "stage_id": "league", "home": "B", "away": "D", "status": "final", "score": [1, 0]},
                {"id": "cd", "stage_id": "league", "home": "C", "away": "D", "status": "final", "score": [1, 0]},
            ],
        )

    def test_complete_league_resolves_champion_promotion_and_relegation(self):
        t = self.league()
        table = t.standings("league")
        self.assertEqual([row["team"] for row in table], ["A", "B", "C", "D"])
        status = t.competition_status()
        self.assertEqual(status["champion"], "A")
        self.assertEqual(status["promoted"], ["A", "B"])
        self.assertEqual(status["relegated"], ["D"])

    def test_scheduled_simultaneous_fixture_does_not_leak_future_score(self):
        t = TournamentStateV13(
            competition_id="group_demo",
            teams=["A", "B", "C", "D"],
            stages={"g": {"kind": "group", "qualify_positions": [1, 2]}},
            fixtures=[
                {"id": "g1", "stage_id": "g", "home": "A", "away": "B", "status": "live", "score": [0, 0], "minute": 62, "simultaneous_key": "r3"},
                {"id": "g2", "stage_id": "g", "home": "C", "away": "D", "status": "scheduled", "score": [9, 9], "simultaneous_key": "r3"},
            ],
        )
        self.assertEqual(t.simultaneous_visible("g1"), [])
        context = t.context_for_fixture("g1")
        self.assertEqual(context["simultaneous"], [])
        t.update_live("g2", 1, 0, 63.0)
        visible = t.simultaneous_visible("g1")
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["score"], [1, 0])

    def test_two_leg_aggregate_changes_live_need_goal(self):
        t = TournamentStateV13(
            competition_id="cup_demo",
            teams=["A", "B"],
            stages={"sf": {"kind": "knockout", "two_legged": True, "away_goals": False}},
            fixtures=[
                {"id": "leg1", "stage_id": "sf", "home": "A", "away": "B", "status": "final", "score": [1, 2], "tie_id": "tie1", "leg": 1},
                {"id": "leg2", "stage_id": "sf", "home": "B", "away": "A", "status": "live", "score": [0, 1], "minute": 70, "tie_id": "tie1", "leg": 2},
            ],
        )
        tied = t.context_for_fixture("leg2")["team_context"]["1"]
        self.assertEqual(tied["aggregate_diff"], 0)
        t.update_live("leg2", 1, 1, 84.0)
        behind = t.context_for_fixture("leg2")["team_context"]["1"]
        self.assertEqual(behind["aggregate_diff"], -1)
        self.assertGreater(behind["need_goal"], 0.6)
        self.assertTrue(behind["need_win"])

    def test_away_goals_rule_is_optional_and_explicit(self):
        t = TournamentStateV13(
            competition_id="old_rule",
            teams=["A", "B"],
            stages={"ko": {"kind": "knockout", "two_legged": True, "away_goals": True}},
            fixtures=[
                {"id": "l1", "stage_id": "ko", "home": "A", "away": "B", "status": "final", "score": [1, 1], "tie_id": "t", "leg": 1},
                {"id": "l2", "stage_id": "ko", "home": "B", "away": "A", "status": "live", "score": [0, 0], "minute": 88, "tie_id": "t", "leg": 2},
            ],
        )
        a = t.context_for_fixture("l2")["team_context"]["1"]
        self.assertLess(a["aggregate_diff"], 0)
        self.assertGreater(a["need_goal"], 0.5)

    def test_pre_match_conditions_compare_win_draw_and_loss_without_mutation(self):
        t = TournamentStateV13(
            competition_id="group_outcomes",
            teams=["A", "B", "C"],
            stages={"g": {"kind": "group", "qualify_positions": [1, 2]}},
            fixtures=[
                {"id": "old1", "stage_id": "g", "home": "A", "away": "C", "status": "final", "score": [1, 0]},
                {"id": "old2", "stage_id": "g", "home": "B", "away": "C", "status": "final", "score": [2, 0]},
                {"id": "last", "stage_id": "g", "home": "A", "away": "B", "status": "scheduled"},
            ],
        )
        before = t.to_dict()
        conditions = t.pre_match_conditions("last")["team_conditions"]["0"]
        self.assertGreater(conditions["win"]["points"], conditions["draw"]["points"])
        self.assertGreater(conditions["draw"]["points"], conditions["loss"]["points"])
        self.assertEqual(before, t.to_dict())

    def test_final_third_place_and_promotion_playoff_are_distinct(self):
        t = TournamentStateV13(
            competition_id="mixed_knockout",
            teams=["A", "B", "C", "D"],
            stages={
                "playoff": {"kind": "playoff", "promotion_on_win": True},
                "third": {"kind": "third_place"},
                "final": {"kind": "final"},
            },
            fixtures=[
                {"id": "p", "stage_id": "playoff", "home": "B", "away": "D", "status": "final", "score": [1, 1], "winner": "B"},
                {"id": "t", "stage_id": "third", "home": "C", "away": "D", "status": "final", "score": [2, 1]},
                {"id": "f", "stage_id": "final", "home": "A", "away": "B", "status": "final", "score": [1, 1], "winner": "A"},
            ],
        )
        status = t.competition_status()
        self.assertEqual(status["champion"], "A")
        self.assertEqual(status["third_place"], "C")
        self.assertEqual(status["promoted"], ["B"])
        final_context = t.context_for_fixture("f")["team_context"]["0"]
        third_context = t.context_for_fixture("t")["team_context"]["0"]
        self.assertTrue(final_context["championship_final"])
        self.assertTrue(third_context["third_place_match"])

    def test_roundtrip_preserves_live_competition_state(self):
        t = self.league()
        restored = TournamentStateV13.from_dict(t.to_dict())
        self.assertEqual(t.to_dict(), restored.to_dict())
        self.assertEqual(t.competition_status(), restored.competition_status())


if __name__ == "__main__":
    unittest.main()
