from __future__ import annotations

import unittest

from engine import make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_positions import MatchEngineV13Positions
from engine_experiment_v13_throwins import MatchEngineV13ThrowIns
from team_loader_v13 import load_team_v13


class MultiPositionTests(unittest.TestCase):
    def engine(self, seed=9101):
        return MatchEngineV13Positions(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=303),
            seed=seed,
        )

    def test_canonical_entrypoint_contains_position_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Positions, MatchEngineV13ThrowIns))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13Positions))

    def test_initial_deployment_separates_natural_and_match_position(self):
        e = self.engine()
        joao = e.teams[0].by_name("João Peixoto")
        mike = e.teams[0].by_name("Mike Junior")
        self.assertEqual(joao.player.position, "LB")
        self.assertEqual(e.natural_position(joao.player), "CB")
        self.assertEqual(mike.player.position, "LW")
        self.assertEqual(e.natural_position(mike.player), "CM")

    def test_known_secondary_familiarity_is_explicit_and_rng_pure(self):
        e = self.engine(seed=9103)
        jorge = e.teams[0].by_name("Jorge Henrique").player
        state = e.rng.getstate()
        diag = e.position_profile_diagnostic(jorge)
        self.assertEqual(e.rng.getstate(), state)
        self.assertEqual(diag["natural_position"], "RB")
        self.assertEqual(diag["familiarity"]["RB"], 1.0)
        self.assertGreater(diag["familiarity"]["DM"], diag["familiarity"]["CM"])

    def test_single_position_specialist_is_not_silently_made_versatile(self):
        e = self.engine(seed=9105)
        white = next(p for p in e.teams[0].bench if p.name == "Rodrigo White")
        self.assertEqual(e.position_familiarity(white, "LB"), 1.0)
        self.assertEqual(e.position_familiarity(white, "RB"), 0.0)
        self.assertLess(e.position_assignment_fit("RB", white), 0.52)

    def test_secondary_position_improves_replacement_fit(self):
        e = self.engine(seed=9107)
        jorge = e.teams[0].by_name("Jorge Henrique")
        arthur = next(p for p in e.teams[0].bench if p.name == "Arthur Peixoto")
        self.assertEqual(jorge.player.position, "RB")
        self.assertGreaterEqual(e.position_assignment_fit("RB", arthur), 0.86)

    def test_straight_substitution_preserves_vacated_slot(self):
        e = self.engine(seed=9109)
        event = e.substitute(0, "Jorge Henrique", "Arthur Peixoto")
        arthur = e.teams[0].by_name("Arthur Peixoto")
        self.assertEqual(arthur.player.position, "RB")
        self.assertEqual(event.data["natural_position"], "DM")
        self.assertEqual(event.data["assigned_position"], "RB")
        self.assertGreaterEqual(event.data["position_familiarity"], 0.86)

    def test_explicit_unfamiliar_manual_deployment_is_rejected(self):
        e = self.engine(seed=9111)
        with self.assertRaises(ValueError):
            e.substitute(0, "Jorge Henrique", "Rodrigo White", position="RB")

    def test_position_assignment_adds_no_ability_rating(self):
        e = self.engine(seed=9113)
        arthur = next(p for p in e.teams[0].bench if p.name == "Arthur Peixoto")
        before = dict(arthur.__dict__)
        _ = e.position_profile_diagnostic(arthur)
        self.assertEqual(before, arthur.__dict__)
        self.assertFalse(hasattr(arthur, "position_rating"))
        self.assertFalse(hasattr(arthur, "position_familiarity"))

    def test_assigned_position_survives_save_load_and_future(self):
        e = self.engine(seed=9115)
        e.substitute(0, "Jorge Henrique", "Arthur Peixoto")
        clone = MatchEngineV13Positions.from_json(e.export_json())
        self.assertEqual(clone.teams[0].by_name("Arthur Peixoto").player.position, "RB")
        self.assertEqual(clone.natural_position(clone.teams[0].by_name("Arthur Peixoto").player), "DM")
        a, b = e.step(), clone.step()
        self.assertEqual((a.minute, a.team, a.type, a.text_key, a.data), (b.minute, b.team, b.type, b.text_key, b.data))
        self.assertEqual(e.export_state(), clone.export_state())


if __name__ == "__main__":
    unittest.main()
