from __future__ import annotations

import unittest

from engine import Band, Lane, MatchConfig, Player, Zone, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_positions import MatchEngineV13Positions
from engine_experiment_v13_substitution_strategy import MatchEngineV13SubstitutionStrategy
from team_loader_v13 import load_team_v13


class StrategicSubstitutionTests(unittest.TestCase):
    def engine(self, seed=9301):
        return MatchEngineV13SubstitutionStrategy(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=404),
            seed=seed,
            config=MatchConfig(allow_extra_time=True),
        )

    @staticmethod
    def open_stoppage(e, minute):
        e.state.second = minute * 60.0
        e.state.restart = "free_kick"
        e.state.restart_team = 0
        e.state.restart_zone = Zone(Band.MID, Lane.CENTER)

    def test_canonical_entrypoint_contains_strategic_substitution_layer(self):
        self.assertTrue(issubclass(MatchEngineV13SubstitutionStrategy, MatchEngineV13Positions))
        self.assertTrue(issubclass(CanonicalMatchEngine, MatchEngineV13SubstitutionStrategy))

    def test_sixth_substitution_is_available_in_extra_time(self):
        e = self.engine()
        e.state.second = 101.0 * 60.0
        e.state.period_markers = [105, 120]
        e.teams[0].substitutions = 5
        self.assertEqual(e._substitution_limit(), 6)

    def test_meaningful_continuing_injury_can_trigger_managed_change(self):
        e = self.engine(seed=9303)
        self.open_stoppage(e, 67.0)
        jorge = e.teams[0].by_name("Jorge Henrique")
        e._v13_injury_state = {
            e._injury_key(0, jorge.player.name): {
                "team": 0,
                "player": jorge.player.name,
                "grade": "minor",
                "region": "lower_body",
                "body_area": "lower_leg",
                "impact": 0.9,
                "onset_minute": 64.0,
                "concussion_protocol": False,
                "suspected_concussion": False,
                "initial_limitation": 0.18,
                "recovery_minutes": 42.0,
                "forced_off": False,
                "can_continue": True,
                "medical_action": "continue_under_observation",
            }
        }
        diag = e.auto_substitution_diagnostic()
        self.assertIsNotNone(diag)
        self.assertEqual(diag["out"], "Jorge Henrique")
        self.assertEqual(diag["reason"], "injury_management")

    def test_small_or_recovered_limitation_does_not_force_managed_change(self):
        e = self.engine(seed=9305)
        self.open_stoppage(e, 67.0)
        jorge = e.teams[0].by_name("Jorge Henrique")
        e._v13_injury_state = {
            e._injury_key(0, jorge.player.name): {
                "team": 0,
                "player": jorge.player.name,
                "grade": "knock",
                "region": "lower_body",
                "body_area": "lower_leg",
                "impact": 0.2,
                "onset_minute": 55.0,
                "concussion_protocol": False,
                "suspected_concussion": False,
                "initial_limitation": 0.05,
                "recovery_minutes": 9.0,
                "forced_off": False,
                "can_continue": True,
                "medical_action": "continue_after_treatment",
            }
        }
        self.assertIsNone(e._continuing_injury_reason(0, jorge))

    def test_shootout_preparation_only_exists_late_in_tied_extra_time(self):
        e = self.engine(seed=9307)
        valverde = e.teams[0].by_name("Pedro Valverde")
        e.state.period_markers = [105, 120]
        e.state.second = 114.0 * 60.0
        self.assertFalse(e._shootout_preparation_context())
        e.state.second = 117.0 * 60.0
        self.assertTrue(e._shootout_preparation_context())
        reason = e._outgoing_reason(0, valverde)
        self.assertIn(reason["reason"], {"shootout_preparation", "fatigue", "freshness"})

    def test_penalty_preparation_requires_material_gain(self):
        e = self.engine(seed=9309)
        e.state.period_markers = [105, 120]
        e.state.second = 118.0 * 60.0
        outgoing = e.teams[0].by_name("Léo")
        incoming = Player(
            name="Penalty Specialist",
            position=outgoing.player.position,
            overall=78,
            finishing=95,
            composure=95,
            technique=93,
            long_shots=91,
            pace=75,
            passing=75,
            vision=75,
            dribbling=75,
            crossing=75,
            heading=75,
            strength=75,
            tackling=75,
            positioning=75,
            anticipation=75,
            off_ball=75,
            stamina=75,
        )
        e.teams[0].bench = [incoming]
        profile = e._replacement_profile(0, outgoing, incoming, "shootout_preparation")
        self.assertIsNotNone(profile)
        self.assertGreaterEqual(profile["penalty_gain"], e.SHOOTOUT_PREP_MIN_GAIN)

    def test_extra_time_penalty_factor_is_a_tiebreaker_not_attribute_boost(self):
        e = self.engine(seed=9311)
        e.state.period_markers = [105, 120]
        e.state.second = 110.0 * 60.0
        outgoing = e.teams[0].by_name("Gabriel Adib")
        incoming = next(p for p in e.teams[0].bench if p.name == "Arthur Peixoto")
        before = dict(incoming.__dict__)
        _ = e._replacement_profile(0, outgoing, incoming, "fatigue")
        self.assertEqual(before, incoming.__dict__)
        self.assertFalse(hasattr(incoming, "penalty_rating"))

    def test_same_seed_sequence_remains_deterministic(self):
        a, b = self.engine(seed=9313), self.engine(seed=9313)
        for _ in range(30):
            ea, eb = a.step(), b.step()
            self.assertEqual(
                (ea.minute, ea.team, ea.type.value, ea.text_key, ea.data),
                (eb.minute, eb.team, eb.type.value, eb.text_key, eb.data),
            )
        self.assertEqual(a.export_state(), b.export_state())


if __name__ == "__main__":
    unittest.main()
