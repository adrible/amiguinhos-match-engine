from __future__ import annotations

import unittest

from historical_2014_v13 import (
    ATTRIBUTE_ORDER,
    BRAZIL_2014_PLAYERS,
    GERMANY_2014_PLAYERS,
    load_historical_2014_team,
    load_team_for_v13,
)
from runner_v13 import MatchSessionV13
from team_loader import load_team as load_stable_team


class Historical2014FixtureTests(unittest.TestCase):
    def test_both_world_cup_squads_register_all_23_players(self):
        self.assertEqual(len(BRAZIL_2014_PLAYERS), 23)
        self.assertEqual(len(GERMANY_2014_PLAYERS), 23)
        self.assertEqual(len({row[0] for row in BRAZIL_2014_PLAYERS}), 23)
        self.assertEqual(len({row[0] for row in GERMANY_2014_PLAYERS}), 23)

    def test_every_historical_player_has_every_engine_attribute(self):
        for roster in (BRAZIL_2014_PLAYERS, GERMANY_2014_PLAYERS):
            for row in roster:
                ratings = row[6]
                self.assertEqual(len(ratings), len(ATTRIBUTE_ORDER), row[0])
                self.assertTrue(all(1 <= int(v) <= 95 for v in ratings), row[0])
                self.assertTrue(1 <= int(row[4]) <= 95, row[0])
                self.assertTrue(0 <= float(row[7]) <= 100, row[0])
                self.assertTrue(0 <= float(row[8]) <= 100, row[0])
                self.assertTrue(0 <= float(row[9]) <= 100, row[0])

    def test_brazil_semifinal_xi_and_unavailable_players_are_correctly_separated(self):
        team = load_historical_2014_team("brazil_2014")
        expected = {
            "Júlio César", "Maicon", "David Luiz", "Dante", "Marcelo",
            "Luiz Gustavo", "Fernandinho", "Hulk", "Oscar", "Bernard", "Fred",
        }
        self.assertEqual({p.name for p in team.starters}, expected)
        active = {p.name for p in [*team.starters, *team.bench]}
        self.assertNotIn("Neymar", active)
        self.assertNotIn("Thiago Silva", active)
        self.assertEqual({p["name"] for p in team.unavailable}, {"Neymar", "Thiago Silva"})

    def test_germany_semifinal_xi_and_mustafi_unavailable(self):
        team = load_historical_2014_team("germany_2014")
        expected = {
            "Manuel Neuer", "Philipp Lahm", "Jérôme Boateng", "Mats Hummels",
            "Benedikt Höwedes", "Sami Khedira", "Bastian Schweinsteiger",
            "Toni Kroos", "Thomas Müller", "Mesut Özil", "Miroslav Klose",
        }
        self.assertEqual({p.name for p in team.starters}, expected)
        active = {p.name for p in [*team.starters, *team.bench]}
        self.assertNotIn("Shkodran Mustafi", active)
        self.assertEqual({p["name"] for p in team.unavailable}, {"Shkodran Mustafi"})

    def test_historical_strength_is_data_not_result_logic(self):
        brazil = load_historical_2014_team("brazil_2014")
        germany = load_historical_2014_team("germany_2014")
        brazil_avg = sum(p.overall for p in brazil.starters) / 11
        germany_avg = sum(p.overall for p in germany.starters) / 11
        self.assertAlmostEqual(brazil_avg, 86.6363636364, places=6)
        self.assertAlmostEqual(germany_avg, 90.3636363636, places=6)
        self.assertGreater(germany_avg, brazil_avg)

    def test_signature_player_profiles_are_literal(self):
        brazil = {row[0]: row for row in BRAZIL_2014_PLAYERS}
        germany = {row[0]: row for row in GERMANY_2014_PLAYERS}
        self.assertEqual(brazil["Neymar"][4], 94)
        self.assertEqual(brazil["Neymar"][6][ATTRIBUTE_ORDER.index("dribbling")], 95)
        self.assertEqual(germany["Manuel Neuer"][6][ATTRIBUTE_ORDER.index("one_on_one")], 95)
        self.assertEqual(germany["Toni Kroos"][6][ATTRIBUTE_ORDER.index("passing")], 95)
        self.assertEqual(germany["Philipp Lahm"][6][ATTRIBUTE_ORDER.index("positioning")], 95)

    def test_historical_teams_do_not_leak_into_frozen_stable_database(self):
        with self.assertRaises(KeyError):
            load_stable_team("brazil_2014")
        with self.assertRaises(KeyError):
            load_stable_team("germany_2014")

    def test_candidate_loader_still_routes_normal_tournament_teams(self):
        team = load_team_for_v13("amiguinhos_u21")
        self.assertIn("Amiguinhos", team.name)
        self.assertEqual(len(team.starters), 11)

    def test_live_runner_can_start_historical_semifinal_pristine_and_advance_one_p(self):
        session = MatchSessionV13.from_fixture(
            "brazil_2014",
            "germany_2014",
            seed=20140708,
            auto_adapt=True,
            allow_extra_time=True,
        )
        self.assertTrue(session.pristine)
        self.assertEqual(session.engine.score, (0, 0))
        event = session.press_p()
        self.assertGreaterEqual(float(event.minute), 0.0)
        self.assertFalse(session.pristine)


if __name__ == "__main__":
    unittest.main()
