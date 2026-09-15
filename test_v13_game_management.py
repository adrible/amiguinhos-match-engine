from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_environment import MatchEngineV13Environment
from engine_experiment_v13_game_management import MatchEngineV13GameManagement
from team_loader_v13 import load_team_v13


class GameManagementTests(unittest.TestCase):
    def engine(self, seed=10101):
        return MatchEngineV13GameManagement(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=707),
            seed=seed,
        )

    @staticmethod
    def weight_map(items):
        return {name: float(weight) for name, weight in items}

    def test_canonical_entrypoint_contains_game_management_layer(self):
        self.assertTrue(issubclass(MatchEngineV13GameManagement, MatchEngineV13Environment))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13GameManagement))

    def test_late_lead_consumes_more_clock_than_late_deficit(self):
        lead = self.engine(10103)
        chase = self.engine(10103)
        for e in (lead, chase):
            e.state.second = 84.0 * 60.0
        lead.stats[0].goals, lead.stats[1].goals = 1, 0
        chase.stats[0].goals, chase.stats[1].goals = 0, 1
        self.assertGreater(
            lead.game_management_diagnostic(0)["clock_factor"],
            chase.game_management_diagnostic(0)["clock_factor"],
        )

    def test_numerical_state_reads_real_on_field_count(self):
        e = self.engine(10105)
        before = e.numerical_context_diagnostic(0)
        removed = next(ps for ps in e.teams[0].on_field if ps.player.position != "GK")
        e.teams[0].on_field.remove(removed)
        after = e.numerical_context_diagnostic(0)
        self.assertEqual(before["player_difference"], 0)
        self.assertEqual(after["player_difference"], -1)
        self.assertEqual(after["short_handed"], 1)

    def test_short_handed_team_pays_small_extra_fatigue_cost(self):
        full = self.engine(10107)
        short = self.engine(10107)
        removed = next(ps for ps in short.teams[0].on_field if ps.player.position != "GK")
        short.teams[0].on_field.remove(removed)
        name = next(ps.player.name for ps in short.teams[0].on_field if ps.player.position != "GK")
        full._advance_clock(60.0, 0)
        short._advance_clock(60.0, 0)
        self.assertLess(short.teams[0].by_name(name).energy, full.teams[0].by_name(name).energy)

    def test_late_score_changes_preference_not_execution_attributes(self):
        lead = self.engine(10109)
        chase = self.engine(10109)
        for e in (lead, chase):
            e.state.second = 85.0 * 60.0
        lead.stats[0].goals, lead.stats[1].goals = 2, 1
        chase.stats[0].goals, chase.stats[1].goals = 1, 2
        a = lead.teams[0].by_name("Gabriel Adib")
        b = chase.teams[0].by_name("Gabriel Adib")
        attrs = dict(a.player.__dict__)
        zone = Zone(Band.MID, Lane.CENTER)
        ctx = {"pressure": 0.42, "space": 0.56, "space_behind": 0.54, "support": 0.58, "transition_threat": 0.42}
        lw = self.weight_map(lead._decision_weights(a, zone, lead.teams[0].team.tactics, ctx))
        cw = self.weight_map(chase._decision_weights(b, zone, chase.teams[0].team.tactics, ctx))
        self.assertGreater(lw["safe_pass"], cw["safe_pass"])
        self.assertLess(lw["through_ball"], cw["through_ball"])
        self.assertEqual(attrs, a.player.__dict__)

    def test_same_seed_remains_deterministic(self):
        a, b = self.engine(10111), self.engine(10111)
        for _ in range(35):
            ea, eb = a.step(), b.step()
            self.assertEqual((ea.minute, ea.team, ea.type.value, ea.text_key, ea.data), (eb.minute, eb.team, eb.type.value, eb.text_key, eb.data))
        self.assertEqual(a.export_state(), b.export_state())


if __name__ == "__main__":
    unittest.main()
