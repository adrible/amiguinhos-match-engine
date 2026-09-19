from __future__ import annotations

import unittest

from engine import Band, Lane, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_environment import MatchEngineV13Environment
from engine_experiment_v13_ratings import MatchEngineV13Ratings
from team_loader_v13 import load_team_v13


class MatchEnvironmentTests(unittest.TestCase):
    def teams(self):
        return (
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=808),
        )

    def engine(self, seed=10101, environment=None):
        home, away = self.teams()
        return MatchEngineV13Environment(home, away, seed=seed, environment=environment)

    def test_canonical_entrypoint_uses_environment_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Environment, MatchEngineV13Ratings))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13Environment))

    def test_environment_generation_is_same_seed_deterministic_and_rng_independent(self):
        home_a, away_a = self.teams()
        home_b, away_b = self.teams()
        weather = MatchEngineV13Environment(home_a, away_a, seed=10103)
        baseline = MatchEngineV13Ratings(home_b, away_b, seed=10103)
        again = self.engine(seed=10103)
        self.assertEqual(weather.environment_diagnostic(), again.environment_diagnostic())
        self.assertEqual(weather.rng.getstate(), baseline.rng.getstate())

    def test_explicit_environment_is_normalised_without_player_attribute_mutation(self):
        e = self.engine(
            seed=10105,
            environment={"weather":"rain","pitch":"slick","wind":0.55,"temperature_c":29},
        )
        player = e.teams[0].by_name("Mike Junior").player
        attrs = dict(player.__dict__)
        diag = e.environment_diagnostic()
        self.assertEqual(diag["weather"], "rain")
        self.assertEqual(diag["pitch"], "slick")
        self.assertGreater(diag["surface_control_penalty"], 0.0)
        self.assertEqual(attrs, player.__dict__)

    def test_strong_wind_penalises_long_action_context_more_than_calm(self):
        calm = self.engine(seed=10107, environment={"weather":"clear","pitch":"normal","wind":0.0,"temperature_c":22})
        wind = self.engine(seed=10107, environment={"weather":"clear","pitch":"normal","wind":0.9,"temperature_c":22})
        self.assertGreater(
            wind.environment_diagnostic()["long_ball_wind_penalty"],
            calm.environment_diagnostic()["long_ball_wind_penalty"],
        )
        actor_c = calm.teams[0].by_name("Gabriel Adib")
        actor_w = wind.teams[0].by_name("Gabriel Adib")
        ctx = {"pressure":0.4,"space":0.6,"space_behind":0.55,"support":0.55,"transition_threat":0.4}
        # The wrapper is tested through the deterministic diagnostic effects;
        # attributes remain identical and only context changes during execution.
        self.assertEqual(actor_c.player.passing, actor_w.player.passing)

    def test_hot_heavy_conditions_add_fatigue_load(self):
        neutral = self.engine(seed=10109, environment={"weather":"clear","pitch":"normal","wind":0.2,"temperature_c":22})
        harsh = self.engine(seed=10109, environment={"weather":"heavy_rain","pitch":"heavy","wind":0.2,"temperature_c":35})
        neutral._advance_clock(600.0, 0)
        harsh._advance_clock(600.0, 0)
        self.assertLess(
            harsh.teams[0].by_name("Gabriel Adib").energy,
            neutral.teams[0].by_name("Gabriel Adib").energy,
        )

    def test_environment_diagnostic_is_rng_pure(self):
        e = self.engine(seed=10111)
        state = e.rng.getstate()
        _ = e.environment_diagnostic()
        self.assertEqual(state, e.rng.getstate())

    def test_environment_survives_roundtrip_and_future(self):
        e = self.engine(seed=10113, environment={"weather":"rain","pitch":"slick","wind":0.48,"temperature_c":27})
        clone = MatchEngineV13Environment.from_json(e.export_json())
        self.assertEqual(e.environment_diagnostic(), clone.environment_diagnostic())
        a, b = e.step(), clone.step()
        self.assertEqual(
            (a.minute, a.team, a.type.value, a.text_key, a.data),
            (b.minute, b.team, b.type.value, b.text_key, b.data),
        )
        self.assertEqual(e.export_state(), clone.export_state())


if __name__ == "__main__":
    unittest.main()
