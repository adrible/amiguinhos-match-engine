from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_game_management import MatchEngineV13GameManagement
from engine_experiment_v13_set_piece_routines import MatchEngineV13SetPieceRoutines
from team_loader_v13 import load_team_v13


class SetPieceRoutineTests(unittest.TestCase):
    def engine(self, seed=10301):
        return MatchEngineV13SetPieceRoutines(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=808),
            seed=seed,
        )

    def test_canonical_entrypoint_contains_set_piece_layer(self):
        self.assertTrue(issubclass(MatchEngineV13SetPieceRoutines, MatchEngineV13GameManagement))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13SetPieceRoutines))

    def test_corner_routine_diagnostic_is_normalized_and_rng_pure(self):
        e = self.engine(10303)
        state = e.rng.getstate()
        diag = e.corner_routine_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        self.assertAlmostEqual(sum(diag["weights"].values()), 1.0, places=9)
        self.assertEqual(state, e.rng.getstate())

    def test_repeated_routine_gets_diversity_penalty(self):
        e = self.engine(10305)
        before = e.corner_routine_diagnostic(0, Zone(Band.ATT, Lane.LEFT))["weights"]["near_screen"]
        for _ in range(3):
            e._record_routine(0, "corner", "near_screen")
        after = e.corner_routine_diagnostic(0, Zone(Band.ATT, Lane.LEFT))["weights"]["near_screen"]
        self.assertLess(after, before)

    def test_active_routine_biases_existing_plan_without_forcing_it(self):
        e = self.engine(10307)
        zone = Zone(Band.ATT, Lane.LEFT)
        base = super(MatchEngineV13SetPieceRoutines, e).corner_plan_diagnostic(0, zone)
        e._v13_active_corner_routine = "short_triangle"
        tuned = e.corner_plan_diagnostic(0, zone)
        self.assertGreater(tuned["weights"]["short_corner"], base["weights"]["short_corner"])
        self.assertGreater(tuned["weights"]["near_post"], 0.0)

    def test_keeper_up_is_real_corner_target_candidate(self):
        e = self.engine(10309)
        e.state.second = 90.0 * 60.0
        e.stats[0].goals, e.stats[1].goals = 0, 1
        zone = Zone(Band.ATT, Lane.LEFT)
        e._activate_keeper_up(0, seconds=60.0)
        diag = e.keeper_set_piece_attack_diagnostic(0, zone)
        self.assertTrue(diag["eligible"])
        self.assertGreater(diag["target_probability"], 0.0)
        self.assertTrue(diag["goal_exposed"])

    def test_keeper_never_joins_when_not_chasing_late(self):
        e = self.engine(10311)
        e.state.second = 75.0 * 60.0
        e._activate_keeper_up(0, seconds=60.0)
        diag = e.keeper_set_piece_attack_diagnostic(0, Zone(Band.ATT, Lane.LEFT))
        self.assertFalse(diag["eligible"])
        self.assertEqual(diag["target_probability"], 0.0)

    def test_routine_usage_survives_roundtrip(self):
        e = self.engine(10313)
        e._record_routine(0, "corner", "far_overload")
        e._record_routine(1, "free_kick", "second_phase")
        clone = MatchEngineV13SetPieceRoutines.from_json(e.export_json())
        self.assertEqual(e._v13_set_piece_usage, clone._v13_set_piece_usage)
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type.value, a.text_key, a.data), (b.minute, b.team, b.type.value, b.text_key, b.data))


if __name__ == "__main__":
    unittest.main()
