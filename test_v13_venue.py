from __future__ import annotations

import unittest

from engine import Band, make_generic_team
from engine_experiment_v13_venue import MatchEngineV13VenueContext


class VenueContextV13Tests(unittest.TestCase):
    def make_engine(self, *, venue_context=None, seed=777):
        return MatchEngineV13VenueContext(
            make_generic_team("Home", 78, "balanced", seed=101),
            make_generic_team("Away", 78, "balanced", seed=202),
            seed=seed,
            venue_context=venue_context,
        )

    def test_default_is_neutral_and_has_no_contextual_edge(self):
        engine = self.make_engine()
        diag = engine.venue_diagnostic()
        self.assertEqual(diag["mode"], "neutral")
        self.assertAlmostEqual(diag["home_effects"]["pressure_shift"], 0.0, places=6)
        self.assertAlmostEqual(diag["away_effects"]["pressure_shift"], 0.0, places=6)
        self.assertAlmostEqual(diag["away_environment_strain"], 0.0, places=6)
        self.assertTrue(all(value == 0.0 for value in diag["away_attacking_caution"].values()))
        self.assertEqual(diag["referee_bias"], 0.0)

    def test_home_away_context_favours_familiar_home_environment_without_rating_bonus(self):
        engine = self.make_engine(venue_context="home_away")
        diag = engine.venue_diagnostic()
        home = diag["home_effects"]
        away = diag["away_effects"]
        self.assertLess(home["pressure_shift"], 0.0)
        self.assertGreater(home["support_shift"], 0.0)
        self.assertGreater(away["pressure_shift"], 0.0)
        self.assertLess(away["support_shift"], 0.0)
        self.assertGreater(away["travel_load"], 0.0)
        self.assertGreater(away["environment_strain"], 0.0)
        # Execution-context pressure remains deliberately small; the stronger
        # venue signal belongs to attacking decisions, not player skill.
        self.assertLess(away["pressure_shift"], 0.02)

    def test_shared_stadium_has_smaller_asymmetry_than_home_away(self):
        normal_engine = self.make_engine(venue_context="home_away")
        shared_engine = self.make_engine(venue_context="shared_stadium")
        normal = normal_engine.venue_diagnostic()
        shared = shared_engine.venue_diagnostic()
        normal_gap = abs(normal["home_effects"]["pressure_shift"] - normal["away_effects"]["pressure_shift"])
        shared_gap = abs(shared["home_effects"]["pressure_shift"] - shared["away_effects"]["pressure_shift"])
        self.assertLess(shared_gap, normal_gap)
        self.assertLess(shared["away_environment_strain"], normal["away_environment_strain"])
        self.assertLess(
            shared["away_attacking_caution"][Band.BOX.value],
            normal["away_attacking_caution"][Band.BOX.value],
        )

    def test_away_attacking_caution_is_concentrated_in_advanced_possession(self):
        engine = self.make_engine(venue_context="home_away")
        defensive = engine._away_attacking_caution(Band.DEF)
        midfield = engine._away_attacking_caution(Band.MID)
        attacking = engine._away_attacking_caution(Band.ATT)
        box = engine._away_attacking_caution(Band.BOX)

        self.assertEqual(defensive, 0.0)
        self.assertGreater(midfield, defensive)
        self.assertGreater(attacking, midfield)
        self.assertGreater(box, attacking)

    def test_venue_diagnostic_is_rng_pure_and_does_not_mutate_player_attributes(self):
        engine = self.make_engine(venue_context="home_away")
        before_rng = engine.rng.getstate()
        before_players = [ps.player.__dict__.copy() for rt in engine.teams for ps in rt.on_field]
        engine.venue_diagnostic()
        after_players = [ps.player.__dict__.copy() for rt in engine.teams for ps in rt.on_field]
        self.assertEqual(before_rng, engine.rng.getstate())
        self.assertEqual(before_players, after_players)

    def test_explicit_context_is_normalised_and_bounded(self):
        engine = self.make_engine(
            venue_context={
                "mode": "home_away",
                "home_familiarity": 1.2,
                "away_familiarity": -0.2,
                "crowd_home_share": 0.8,
                "away_travel_load": 0.6,
                "source": "test",
            }
        )
        diag = engine.venue_diagnostic()
        self.assertEqual(diag["home_familiarity"], 1.0)
        self.assertEqual(diag["away_familiarity"], 0.0)
        self.assertEqual(diag["source"], "test")

    def test_save_load_preserves_venue_and_future_determinism(self):
        engine = self.make_engine(venue_context="home_away", seed=991)
        for _ in range(4):
            engine.step()
        restored = MatchEngineV13VenueContext.from_json(engine.export_json())
        self.assertEqual(engine.venue_diagnostic(), restored.venue_diagnostic())
        left = engine.step()
        right = restored.step()
        self.assertEqual(engine._event_to_dict(left), restored._event_to_dict(right))
        self.assertEqual(engine.snapshot(), restored.snapshot())

    def test_invalid_mode_is_rejected(self):
        with self.assertRaises(ValueError):
            self.make_engine(venue_context="moon_base")

    def test_canonical_entrypoint_contains_venue_layer(self):
        from engine_experiment_v13 import MatchEngine

        self.assertTrue(issubclass(MatchEngine, MatchEngineV13VenueContext))


if __name__ == "__main__":
    unittest.main()
