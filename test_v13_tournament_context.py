from __future__ import annotations

import unittest

from engine import Band, Lane, MatchConfig, Zone, make_generic_team
from competition_state_v13 import TournamentStateV13 as CompleteTournamentStateV13
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_awards import MatchEngineV13Awards
from engine_experiment_v13_tournament import MatchEngineV13TournamentContext
from team_loader_v13 import load_team_v13
from tournament_runner_v13 import TournamentMatchSessionV13
from tournament_state_v13 import TournamentMatchBridgeV13, TournamentStateV13


class TournamentAwareEngineTests(unittest.TestCase):
    def engine(self, seed=10601, context=None, config=None):
        return MatchEngineV13TournamentContext(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=1001),
            seed=seed,
            config=config,
            tournament_context=context,
        )

    @staticmethod
    def weights(items):
        return {name: float(weight) for name, weight in items}

    @staticmethod
    def context(need_goal=0.0, protect=0.0):
        return {
            "version": 1,
            "competition_id": "demo",
            "fixture_id": "f",
            "stage_kind": "group",
            "knowledge_policy": "only_final_or_currently_live_results_are_visible",
            "team_context": {
                "0": {"need_goal": need_goal, "protect_result": protect},
                "1": {"need_goal": 0.0, "protect_result": 0.0},
            },
        }

    @staticmethod
    def knockout_context(aggregate_diff=0):
        return {
            "version": 1,
            "competition_id": "cup",
            "fixture_id": "leg2",
            "stage_kind": "knockout",
            "knowledge_policy": "only_final_or_currently_live_results_are_visible",
            "team_context": {
                "0": {"need_goal": 0.0, "protect_result": 0.0, "aggregate_diff": aggregate_diff, "two_legged": True, "decisive_leg": True},
                "1": {"need_goal": 0.0, "protect_result": 0.0, "aggregate_diff": -aggregate_diff, "two_legged": True, "decisive_leg": True},
            },
        }

    def test_canonical_entrypoint_contains_tournament_layer(self):
        self.assertTrue(issubclass(MatchEngineV13TournamentContext, MatchEngineV13Awards))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13TournamentContext))

    def test_context_update_is_rng_pure(self):
        e = self.engine(10603)
        state = e.rng.getstate()
        e.set_tournament_context(self.context(need_goal=0.9))
        self.assertEqual(state, e.rng.getstate())

    def test_no_context_preserves_underlying_match_sequence(self):
        home_a = load_team_v13("amiguinhos_u21")
        away_a = make_generic_team("Away", 80, "balanced", seed=1001)
        home_b = load_team_v13("amiguinhos_u21")
        away_b = make_generic_team("Away", 80, "balanced", seed=1001)
        a = MatchEngineV13TournamentContext(home_a, away_a, seed=10604)
        b = MatchEngineV13Awards(home_b, away_b, seed=10604)
        for _ in range(20):
            ea, eb = a.step(), b.step()
            self.assertEqual((ea.minute, ea.team, ea.type.value, ea.text_key, ea.data), (eb.minute, eb.team, eb.type.value, eb.text_key, eb.data))

    def test_competition_urgency_changes_preference_not_execution(self):
        chase = self.engine(10605, self.context(need_goal=1.0))
        protect = self.engine(10605, self.context(protect=1.0))
        for e in (chase, protect):
            e.state.second = 85.0 * 60.0
        a = chase.teams[0].by_name("Gabriel Adib")
        b = protect.teams[0].by_name("Gabriel Adib")
        attrs = dict(a.player.__dict__)
        zone = Zone(Band.MID, Lane.CENTER)
        ctx = {"pressure": 0.42, "space": 0.56, "space_behind": 0.54, "support": 0.58, "transition_threat": 0.42}
        cw = self.weights(chase._decision_weights(a, zone, chase.teams[0].team.tactics, ctx))
        pw = self.weights(protect._decision_weights(b, zone, protect.teams[0].team.tactics, ctx))
        self.assertGreater(cw["through_ball"], pw["through_ball"])
        self.assertGreater(cw["shoot"], pw["shoot"])
        self.assertLess(cw["safe_pass"], pw["safe_pass"])
        self.assertGreater(pw["shoot"], 0.0)
        self.assertEqual(attrs, a.player.__dict__)

    def test_aggregate_context_overrides_current_leg_score_for_coaching(self):
        context = self.context(protect=0.90)
        context["stage_kind"] = "knockout"
        context["team_context"]["0"].update({"aggregate_diff": 1, "decisive_leg": True})
        e = self.engine(10606, context)
        e.state.second = 82.0 * 60.0
        e.stats[0].goals, e.stats[1].goals = 0, 1
        management = e.game_management_diagnostic(0)
        self.assertEqual(management["match_score_diff"], -1)
        self.assertGreater(management["score_diff"], 0)
        self.assertTrue(management["competition_override"])
        reason = e._outgoing_reason(0, e.teams[0].by_name("Gabriel Adib"))
        self.assertIsNotNone(reason)
        self.assertEqual(reason["reason"], "tactical_protect")
        adaptation = e._adaptation_profile(0)
        self.assertEqual(adaptation["competition_target_response"], "protect_lead")
        self.assertNotEqual(adaptation["response"], "chase_game")

    def test_final_stake_without_need_goal_does_not_force_all_in(self):
        neutral = self.engine(10607, self.context())
        final = self.engine(10607, {
            **self.context(),
            "stage_kind": "final",
            "team_context": {
                "0": {"need_goal": 0.0, "protect_result": 0.0, "championship_final": True, "need_win": True},
                "1": {"need_goal": 0.0, "protect_result": 0.0, "championship_final": True, "need_win": True},
            },
        })
        actor_a = neutral.teams[0].by_name("Gabriel Adib")
        actor_b = final.teams[0].by_name("Gabriel Adib")
        zone = Zone(Band.MID, Lane.CENTER)
        ctx = {"pressure": 0.42, "space": 0.56, "space_behind": 0.54, "support": 0.58, "transition_threat": 0.42}
        self.assertEqual(
            self.weights(neutral._decision_weights(actor_a, zone, neutral.teams[0].team.tactics, ctx)),
            self.weights(final._decision_weights(actor_b, zone, final.teams[0].team.tactics, ctx)),
        )

    def test_tournament_context_survives_save_load(self):
        e = self.engine(10609, self.context(need_goal=0.83))
        clone = MatchEngineV13TournamentContext.from_json(e.export_json())
        self.assertEqual(e.tournament_context_diagnostic(), clone.tournament_context_diagnostic())
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type.value, a.text_key, a.data), (b.minute, b.team, b.type.value, b.text_key, b.data))

    def test_bridge_refreshes_simultaneous_information_without_future_leak(self):
        tournament = TournamentStateV13(
            competition_id="group_live",
            teams=["A", "B", "C", "D"],
            stages={"g": {"kind": "group", "qualify_positions": [1, 2]}},
            fixtures=[
                {"id": "main", "stage_id": "g", "home": "A", "away": "B", "status": "scheduled", "simultaneous_key": "last"},
                {"id": "other", "stage_id": "g", "home": "C", "away": "D", "status": "scheduled", "score": [8, 8], "simultaneous_key": "last"},
            ],
        )
        e = self.engine(10611)
        bridge = TournamentMatchBridgeV13(tournament, "main")
        first = bridge.attach(e)
        self.assertEqual(first["simultaneous"], [])
        second = bridge.apply_simultaneous_update(e, "other", 2, 0, 71.0)
        self.assertEqual(second["simultaneous"][0]["score"], [2, 0])
        self.assertEqual(e.tournament_context_diagnostic()["simultaneous"][0]["score"], [2, 0])

    def test_two_leg_final_uses_aggregate_not_leg_winner(self):
        tournament = CompleteTournamentStateV13(
            competition_id="two_leg_final",
            teams=["A", "B"],
            stages={"f": {"kind": "final", "two_legged": True}},
            fixtures=[
                {"id": "f1", "stage_id": "f", "home": "A", "away": "B", "status": "final", "score": [3, 0], "leg": 1, "tie_id": "F"},
                {"id": "f2", "stage_id": "f", "home": "B", "away": "A", "status": "final", "score": [1, 0], "winner": "B", "leg": 2, "tie_id": "F"},
            ],
        )
        self.assertEqual(tournament.tie_resolution("F")["winner"], "A")
        self.assertEqual(tournament.competition_status()["champion"], "A")

    def test_aggregate_not_leg_score_controls_extra_time(self):
        tied = self.engine(10613, self.knockout_context(0), MatchConfig(allow_extra_time=True))
        tied.stats[0].goals, tied.stats[1].goals = 2, 0
        tied.state.second = 90.0 * 60.0
        tied.state.period_index = 1
        event = tied._check_period_boundary()
        self.assertEqual(event.text_key, "regulation_end_tied")
        self.assertEqual(tied.state.period_markers, [105, 120])

        ahead = self.engine(10615, self.knockout_context(1), MatchConfig(allow_extra_time=True))
        ahead.stats[0].goals, ahead.stats[1].goals = 1, 1
        ahead.state.second = 90.0 * 60.0
        ahead.state.period_index = 1
        event = ahead._check_period_boundary()
        self.assertIsNotNone(event)
        self.assertNotEqual(event.text_key, "regulation_end_tied")
        self.assertEqual(ahead.state.period_markers, [45, 90])

    def test_live_standings_are_provisional_but_not_mathematically_fixed(self):
        tournament = CompleteTournamentStateV13(
            competition_id="live_table",
            teams=["A", "B"],
            stages={"l": {"kind": "league", "champion_position": 1}},
            fixtures=[
                {"id": "ab", "stage_id": "l", "home": "A", "away": "B", "status": "live", "score": [1, 0], "minute": 70},
            ],
        )
        table = tournament.standings("l")
        a = next(row for row in table if row["team"] == "A")
        self.assertEqual(a["position"], 1)
        self.assertEqual(a["points"], 3)
        self.assertEqual(a["live_unsettled_matches"], 1)
        self.assertEqual(a["min_points"], 0)
        self.assertEqual(a["max_points"], 3)
        self.assertEqual(a["remaining"], 1)

    def test_pre_match_aggregate_excludes_current_live_leg(self):
        tournament = CompleteTournamentStateV13(
            competition_id="frozen_prematch",
            teams=["A", "B"],
            stages={"ko": {"kind": "knockout", "two_legged": True}},
            fixtures=[
                {"id": "l1", "stage_id": "ko", "home": "A", "away": "B", "status": "final", "score": [2, 0], "leg": 1, "tie_id": "T"},
                {"id": "l2", "stage_id": "ko", "home": "B", "away": "A", "status": "live", "score": [1, 0], "minute": 60, "leg": 2, "tie_id": "T"},
            ],
        )
        conditions = tournament.pre_match_conditions("l2")["team_conditions"]["0"]
        self.assertEqual(conditions["aggregate_goals_for_before"], 0)
        self.assertEqual(conditions["aggregate_goals_against_before"], 2)
        self.assertEqual(conditions["aggregate_diff_before"], -2)
        self.assertEqual(conditions["goals_needed_to_level_aggregate"], 2)

    def test_live_tournament_session_starts_at_zero_without_presimulation(self):
        tournament = CompleteTournamentStateV13(
            competition_id="live_group",
            teams=["amiguinhos_u21", "flamengo_u21", "river_plate_u21", "bayern_u21"],
            stages={"g": {"kind": "group", "qualify_positions": [1, 2]}},
            fixtures=[
                {"id": "main", "stage_id": "g", "home": "amiguinhos_u21", "away": "flamengo_u21", "status": "scheduled", "simultaneous_key": "last"},
                {"id": "other", "stage_id": "g", "home": "river_plate_u21", "away": "bayern_u21", "status": "scheduled", "simultaneous_key": "last"},
            ],
        )
        session = TournamentMatchSessionV13(tournament, "main", seed=10617)
        self.assertTrue(session.pristine)
        self.assertEqual(session.engine.minute, 0.0)
        self.assertEqual(session.engine.state.event_log, [])
        session.update_simultaneous("other", 1, 0, 12.0)
        self.assertEqual(session.engine.minute, 0.0)
        self.assertEqual(session.engine.state.event_log, [])
        self.assertEqual(session.snapshot()["competition"]["simultaneous"][0]["score"], [1, 0])


if __name__ == "__main__":
    unittest.main()
