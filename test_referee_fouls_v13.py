from __future__ import annotations

import copy
import unittest

from engine import Band, EventType, Lane, MatchConfig, Zone
from engine_experiment_v13 import MatchEngine
from engine_experiment_v13_referee import RefereeProfile
from team_loader import load_team as load_stable_team
from team_loader_v13 import load_team_v13


class RefereeFoulsV13Tests(unittest.TestCase):
    def make_engine(self, seed=123, **config_changes):
        config = MatchConfig(**config_changes) if config_changes else None
        return MatchEngine(
            load_team_v13("amiguinhos_u21"),
            load_team_v13("flamengo_u21"),
            seed=seed,
            config=config,
        )

    def test_stable_v12_engine_data_model_is_untouched(self):
        stable = load_stable_team("amiguinhos_u21")
        self.assertEqual(stable.starters[0].name, "Christian")
        # Referee state belongs to the v1.3 engine, not Team / Player data.
        self.assertFalse(hasattr(stable, "referee"))

    def test_same_seed_builds_same_referee_profile(self):
        a = self.make_engine(seed=8181)
        b = self.make_engine(seed=8181)
        self.assertEqual(a.referee_diagnostic(), b.referee_diagnostic())
        self.assertIn(a.referee.style, {"strict", "balanced", "permissive"})
        for key in (
            "strictness",
            "contact_tolerance",
            "advantage_tendency",
            "dissent_tolerance",
            "game_management",
            "consistency",
        ):
            self.assertGreaterEqual(getattr(a.referee, key), 0.0)
            self.assertLessEqual(getattr(a.referee, key), 1.0)

    def test_referee_diagnostic_is_rng_pure(self):
        e = self.make_engine(seed=22)
        before = e.rng.getstate()
        _ = e.referee_diagnostic()
        self.assertEqual(before, e.rng.getstate())

    def test_stricter_referee_raises_yellow_probability_for_same_incident(self):
        e = self.make_engine(seed=5)
        defender = e.teams[0].by_name("Felipe")
        incident = {
            "type": "late_tackle",
            "severity": 0.58,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        e.referee = RefereeProfile("permissive", 0.42, 0.68, 0.55, 0.60, 0.60, 1.0)
        low = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
        e.referee = RefereeProfile("strict", 0.72, 0.32, 0.55, 0.60, 0.60, 1.0)
        high = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
        self.assertGreater(high["yellow"], low["yellow"])

    def test_persistent_infringement_raises_yellow_probability(self):
        e = self.make_engine(seed=9)
        e.referee.consistency = 1.0
        defender = e.teams[0].by_name("Felipe")
        incident = {
            "type": "trip",
            "severity": 0.42,
            "spa": False,
            "dogso": False,
            "attempt_to_play_ball": True,
            "violent": False,
        }
        first = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 1)
        fourth = e._card_probabilities(0, defender, incident, Zone(Band.MID, Lane.CENTER), 4)
        self.assertGreater(fourth["yellow"], first["yellow"])

    def test_penalty_area_dogso_ball_attempt_has_less_red_than_non_ball_challenge(self):
        e = self.make_engine(seed=11)
        e.referee.consistency = 1.0
        defender = e.teams[0].by_name("Jorge Henrique")
        base = {
            "type": "late_tackle",
            "severity": 0.70,
            "spa": True,
            "dogso": True,
            "violent": False,
        }
        attempt = {**base, "attempt_to_play_ball": True}
        hold = {**base, "type": "holding", "attempt_to_play_ball": False}
        ball = e._card_probabilities(0, defender, attempt, Zone(Band.BOX, Lane.CENTER), 1)
        non_ball = e._card_probabilities(0, defender, hold, Zone(Band.BOX, Lane.CENTER), 1)
        self.assertLess(ball["direct_red"], non_ball["direct_red"])
        self.assertGreaterEqual(ball["yellow"], 0.64)

    def test_advantage_is_impossible_for_red_and_defensive_third(self):
        e = self.make_engine(seed=13)
        attacker = e.teams[1].by_name("Joshua")
        incident = {
            "type": "holding",
            "severity": 0.35,
            "spa": True,
            "dogso": False,
            "attempt_to_play_ball": False,
            "violent": False,
        }
        self.assertEqual(
            e._advantage_probability(1, attacker, Zone(Band.ATT, Lane.CENTER), incident, "direct_red", None),
            0.0,
        )
        self.assertEqual(
            e._advantage_probability(1, attacker, Zone(Band.DEF, Lane.CENTER), incident, None, None),
            0.0,
        )
        self.assertGreater(
            e._advantage_probability(1, attacker, Zone(Band.ATT, Lane.CENTER), incident, None, None),
            0.0,
        )

    def test_advantage_defers_yellow_until_next_stoppage(self):
        e = self.make_engine(seed=17)
        defender = e.teams[0].by_name("Felipe")
        attacker = e.teams[1].by_name("Joshua")
        e._decide_card = lambda *args, **kwargs: ("yellow", {"yellow": 1.0, "direct_red": 0.0})
        e._injury_outcome = lambda *args, **kwargs: None
        e._advantage_probability = lambda *args, **kwargs: 1.0
        e._reaction_outcome = lambda *args, **kwargs: None
        ev = e._commit_foul(
            0,
            defender,
            attacker,
            Zone(Band.ATT, Lane.CENTER),
            forced_incident={
                "type": "holding",
                "severity": 0.35,
                "spa": True,
                "dogso": False,
                "attempt_to_play_ball": False,
                "violent": False,
            },
        )
        self.assertEqual(ev.text_key, "advantage_played")
        self.assertEqual(defender.yellow, 1)
        self.assertEqual(len(e._deferred_discipline), 1)
        self.assertIsNone(e.state.restart)

        # Simulate the next genuine stoppage. Card must be surfaced before restart.
        e.state.restart = "free_kick"
        e.state.restart_team = 1
        e.state.restart_zone = Zone(Band.MID, Lane.CENTER)
        card = e.step()
        self.assertEqual(card.type, EventType.CARD)
        self.assertEqual(card.text_key, "deferred_card_after_advantage")
        self.assertEqual(card.data["player"], "Felipe")
        self.assertEqual(len(e._deferred_discipline), 0)

    def test_direct_red_removes_player_and_is_a_public_followup_event(self):
        e = self.make_engine(seed=19)
        defender = e.teams[0].by_name("Felipe")
        attacker = e.teams[1].by_name("Joshua")
        e._decide_card = lambda *args, **kwargs: ("direct_red", {"yellow": 0.0, "direct_red": 1.0})
        e._injury_outcome = lambda *args, **kwargs: None
        e._advantage_probability = lambda *args, **kwargs: 0.0
        e._reaction_outcome = lambda *args, **kwargs: None
        primary = e._commit_foul(
            0,
            defender,
            attacker,
            Zone(Band.MID, Lane.CENTER),
            forced_incident={
                "type": "reckless_tackle",
                "severity": 0.94,
                "spa": False,
                "dogso": False,
                "attempt_to_play_ball": True,
                "violent": True,
            },
        )
        self.assertEqual(primary.type, EventType.FOUL)
        self.assertTrue(defender.red)
        self.assertNotIn(defender, e.teams[0].on_field)
        follow = e.step()
        self.assertEqual(follow.type, EventType.CARD)
        self.assertEqual(follow.data["card"], "direct_red")

    def test_reaction_yellow_can_become_second_yellow_red(self):
        e = self.make_engine(seed=23)
        player = e.teams[0].by_name("Felipe")
        player.yellow = 1
        before_count = len(e.teams[0].on_field)
        applied = e._apply_reaction_sanctions(
            [{"team": 0, "player": player, "reason": "confrontation", "card": "yellow"}]
        )
        self.assertEqual(applied[0]["card"], "second_yellow_red")
        self.assertTrue(player.red)
        self.assertEqual(len(e.teams[0].on_field), before_count - 1)

    def test_foul_type_maps_to_contextual_body_area(self):
        e = self.make_engine(seed=29)
        self.assertEqual(e._body_area_for_foul("elbow_or_forearm"), "head_or_face")
        self.assertEqual(e._body_area_for_foul("reckless_tackle"), "ankle_knee_or_lower_leg")
        self.assertEqual(e._body_area_for_foul("push_charge"), "upper_body")

    def test_referee_state_and_queued_card_survive_roundtrip(self):
        e = self.make_engine(seed=31)
        defender = e.teams[0].by_name("Felipe")
        attacker = e.teams[1].by_name("Joshua")
        e._decide_card = lambda *args, **kwargs: ("yellow", {"yellow": 1.0, "direct_red": 0.0})
        e._injury_outcome = lambda *args, **kwargs: None
        e._advantage_probability = lambda *args, **kwargs: 0.0
        e._reaction_outcome = lambda *args, **kwargs: None
        _ = e._commit_foul(
            0,
            defender,
            attacker,
            Zone(Band.MID, Lane.CENTER),
            forced_incident={
                "type": "late_tackle",
                "severity": 0.62,
                "spa": False,
                "dogso": False,
                "attempt_to_play_ball": True,
                "violent": False,
            },
        )
        payload = e.export_json()
        restored = MatchEngine.from_json(payload)
        self.assertEqual(restored.referee_diagnostic(), e.referee_diagnostic())
        self.assertEqual(len(restored._referee_event_queue), 1)
        a = e.step()
        b = restored.step()
        self.assertEqual((a.type, a.text_key, a.data), (b.type, b.text_key, b.data))

    def test_same_seed_full_match_remains_reproducible_with_referee_layer(self):
        a = self.make_engine(seed=733)
        b = self.make_engine(seed=733)
        for _ in range(350):
            if a.state.ended or b.state.ended:
                break
            ea = a.step()
            eb = b.step()
            self.assertEqual((ea.type, ea.team, ea.text_key, ea.data), (eb.type, eb.team, eb.text_key, eb.data))
        self.assertEqual(a.snapshot(), b.snapshot())


if __name__ == "__main__":
    unittest.main()
