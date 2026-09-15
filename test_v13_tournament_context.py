from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_awards import MatchEngineV13Awards
from engine_experiment_v13_tournament import MatchEngineV13TournamentContext
from team_loader_v13 import load_team_v13
from tournament_state_v13 import TournamentMatchBridgeV13, TournamentStateV13


class TournamentAwareEngineTests(unittest.TestCase):
    def engine(self, seed=10601, context=None):
        return MatchEngineV13TournamentContext(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=1001),
            seed=seed,
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

    def test_canonical_entrypoint_contains_tournament_layer(self):
        self.assertTrue(issubclass(MatchEngineV13TournamentContext, MatchEngineV13Awards))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13TournamentContext))

    def test_context_update_is_rng_pure(self):
        e = self.engine(10603)
        state = e.rng.getstate()
        e.set_tournament_context(self.context(need_goal=0.9))
        self.assertEqual(state, e.rng.getstate())

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
        self.assertEqual(attrs, a.player.__dict__)

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


if __name__ == "__main__":
    unittest.main()
