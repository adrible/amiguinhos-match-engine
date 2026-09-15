from __future__ import annotations

import unittest

from engine import EventType, make_generic_team
from engine_experiment_v13 import MatchEngine as CanonicalMatchEngine
from engine_experiment_v13_instructions import MatchEngineV13IndividualInstructions
from engine_experiment_v13_ratings import MatchEngineV13Ratings
from team_loader_v13 import load_team_v13


class MatchRatingTests(unittest.TestCase):
    def engine(self, seed=9901):
        return MatchEngineV13Ratings(
            load_team_v13("amiguinhos_u21"),
            make_generic_team("Away", 80, "balanced", seed=707),
            seed=seed,
        )

    def test_canonical_entrypoint_uses_rating_layer(self):
        self.assertTrue(issubclass(MatchEngineV13Ratings, MatchEngineV13IndividualInstructions))
        self.assertIs(CanonicalMatchEngine, MatchEngineV13Ratings)

    def test_quiet_players_do_not_receive_overall_bonus(self):
        e = self.engine()
        adib = e.player_match_rating(0, "Gabriel Adib")
        joao = e.player_match_rating(0, "João Peixoto")
        self.assertEqual(adib["rating"], 6.0)
        self.assertEqual(joao["rating"], 6.0)

    def test_goal_and_chance_creation_raise_rating(self):
        e = self.engine(seed=9903)
        e._emit(
            EventType.DANGER, 0, 3, "danger_created",
            creator="Mike Junior", receiver="Gabriel Félix", danger=0.72,
        )
        e._emit(
            EventType.GOAL, 0, 5, "goal",
            scorer="Gabriel Félix", keeper="Away GK", xg=0.31,
        )
        mike = e.player_match_rating(0, "Mike Junior")
        felix = e.player_match_rating(0, "Gabriel Félix")
        self.assertGreater(mike["rating"], 6.0)
        self.assertGreater(felix["rating"], mike["rating"])
        self.assertIn("goal", felix["contributions"])

    def test_big_chance_miss_and_red_card_are_negative(self):
        e = self.engine(seed=9905)
        e._emit(
            EventType.MISS, 0, 3, "shot_missed",
            shooter="Pedro Valverde", xg=0.56, big_chance=True,
        )
        e._emit(
            EventType.CARD, 0, 4, "card_shown_contextual",
            player="Felipe", card="direct_red",
        )
        self.assertLess(e.player_match_rating(0, "Pedro Valverde")["rating"], 6.0)
        self.assertLess(e.player_match_rating(0, "Felipe")["rating"], 5.5)

    def test_save_value_scales_with_shot_quality(self):
        low = self.engine(seed=9907)
        high = self.engine(seed=9907)
        keeper_low = low.teams[1].on_field[0].player.name
        keeper_high = high.teams[1].on_field[0].player.name
        low._emit(EventType.SAVE, 0, 3, "shot_saved", shooter="Gabriel Félix", keeper=keeper_low, xg=0.08)
        high._emit(EventType.SAVE, 0, 4, "shot_saved", shooter="Gabriel Félix", keeper=keeper_high, xg=0.62)
        self.assertGreater(
            high.player_match_rating(1, keeper_high)["rating"],
            low.player_match_rating(1, keeper_low)["rating"],
        )

    def test_defensive_error_is_charged_to_named_defender(self):
        e = self.engine(seed=9909)
        defender = e.teams[0].by_name("João Peixoto")
        e._emit(
            EventType.DANGER, 1, 3, "danger_created",
            creator=e.teams[1].on_field[7].player.name,
            receiver=e.teams[1].on_field[9].player.name,
            danger=0.7,
            defensive_error={"type":"lost_runner","defender":defender.player.name,"severity":0.8},
        )
        self.assertLess(e.player_match_rating(0, defender.player.name)["rating"], 6.0)

    def test_rating_diagnostic_is_rng_pure(self):
        e = self.engine(seed=9911)
        state = e.rng.getstate()
        _ = e.match_ratings()
        self.assertEqual(e.rng.getstate(), state)

    def test_ratings_survive_roundtrip_because_events_survive(self):
        e = self.engine(seed=9913)
        e._emit(EventType.GOAL, 0, 5, "goal", scorer="Gabriel Adib", xg=0.18)
        before = e.player_match_rating(0, "Gabriel Adib")
        clone = MatchEngineV13Ratings.from_json(e.export_json())
        after = clone.player_match_rating(0, "Gabriel Adib")
        self.assertEqual(before, after)
        self.assertEqual(e.rng.getstate(), clone.rng.getstate())


if __name__ == "__main__":
    unittest.main()
